import logging
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app.models import Episode, Podcast, Sentence, Transcript, TranscriptSource, TranscriptStatus
from app.services.furigana import build_segments
from app.services.rss import TIMED_TRANSCRIPT_FORMATS, classify_transcript_format
from app.services.transcript_parsers import parse_json_transcript, parse_srt, parse_vtt
from app.services.transcription import WhisperModelNotFoundError, transcribe_audio

logger = logging.getLogger(__name__)

_PARSERS = {"srt": parse_srt, "vtt": parse_vtt, "json": parse_json_transcript}


def get_or_build_transcript(session: Session, episode: Episode) -> Transcript | None:
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    if transcript:
        return transcript
    return build_transcript(session, episode)


def build_transcript(session: Session, episode: Episode) -> Transcript | None:
    """Fetch and parse the episode's published transcript on demand, building
    ordered Sentence rows from SRT/VTT/Podcasting-2.0-JSON cues. Untimed
    plain-text/HTML transcripts are left for the ASR fallback (#5)."""
    if not episode.transcript_source_url:
        return None

    transcript_format = classify_transcript_format(episode.transcript_source_type, episode.transcript_source_url)
    if transcript_format not in TIMED_TRANSCRIPT_FORMATS:
        return None

    try:
        response = httpx.get(episode.transcript_source_url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    try:
        cues = _PARSERS[transcript_format](response.text)
    except (ValueError, KeyError):
        return None
    if not cues:
        return None

    language = episode.transcript_source_language
    if not language:
        podcast = session.get(Podcast, episode.podcast_id)
        language = podcast.language if podcast else ""

    transcript = Transcript(
        episode_id=episode.id,
        language=language,
        source=TranscriptSource.published,
    )
    session.add(transcript)
    session.flush()

    for index, cue in enumerate(cues):
        session.add(
            Sentence(
                transcript_id=transcript.id,
                index=index,
                start_time=cue.start_time,
                end_time=cue.end_time,
                text=cue.text,
                segments=build_segments(cue.text, language),
            )
        )

    episode.transcript_status = TranscriptStatus.full
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript


def ingest_transcript(session: Session, episode: Episode, audio_path: Path | None = None) -> None:
    """Try the published-transcript path first; if it's unavailable (untimed
    source, none published, or the fetch/parse failed), fall back to ASR over
    the given local audio file. No-op if a transcript already exists."""
    if episode.transcript_status == TranscriptStatus.full:
        return

    original_status = episode.transcript_status
    episode.transcript_status = TranscriptStatus.pending
    session.add(episode)
    session.commit()

    if get_or_build_transcript(session, episode):
        return

    if audio_path is not None and _transcribe_with_asr(session, episode, audio_path):
        return

    # _transcribe_with_asr may have already set a more specific terminal status
    # (e.g. queued, when no ASR model is installed) — only fall back to the
    # pre-attempt status if nothing more specific was set.
    if episode.transcript_status == TranscriptStatus.pending:
        episode.transcript_status = original_status
        session.add(episode)
        session.commit()


def _transcribe_with_asr(session: Session, episode: Episode, audio_path: Path) -> Transcript | None:
    try:
        cues, detected_language = transcribe_audio(str(audio_path))
    except WhisperModelNotFoundError:
        episode.transcript_status = TranscriptStatus.queued
        session.add(episode)
        session.commit()
        return None
    except Exception:
        logger.exception("ASR transcription failed for episode %s", episode.id)
        return None
    if not cues:
        return None

    transcript = Transcript(
        episode_id=episode.id,
        language=detected_language or "",
        source=TranscriptSource.asr,
    )
    session.add(transcript)
    session.flush()

    try:
        for index, cue in enumerate(cues):
            session.add(
                Sentence(
                    transcript_id=transcript.id,
                    index=index,
                    start_time=cue.start_time,
                    end_time=cue.end_time,
                    text=cue.text,
                    segments=build_segments(cue.text, transcript.language),
                )
            )
    except Exception:
        logger.exception("Failed to build segments for episode %s", episode.id)
        session.rollback()
        return None

    episode.transcript_status = TranscriptStatus.auto
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript
