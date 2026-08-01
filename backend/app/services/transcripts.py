import logging
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app.models import Episode, Podcast, PodcastKind, Sentence, Transcript, TranscriptSource, TranscriptStatus
from app.services import youtube
from app.services.furigana import build_segments
from app.services.rss import TIMED_TRANSCRIPT_FORMATS, classify_transcript_format
from app.services.transcript_parsers import Cue, parse_json_transcript, parse_srt, parse_vtt
from app.services.transcription import WhisperModelNotFoundError, clear_progress, transcribe_audio

logger = logging.getLogger(__name__)

_PARSERS = {"srt": parse_srt, "vtt": parse_vtt, "json": parse_json_transcript}


def get_or_build_transcript(session: Session, episode: Episode) -> Transcript | None:
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    if transcript:
        return transcript
    return build_transcript(session, episode)


def _persist_cues(
    session: Session, episode: Episode, cues: list[Cue], language: str, source: TranscriptSource
) -> Transcript | None:
    transcript = Transcript(episode_id=episode.id, language=language, source=source)
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
                    segments=build_segments(cue.text, language),
                )
            )
    except Exception:
        logger.exception("Failed to build segments for episode %s", episode.id)
        session.rollback()
        return None
    return transcript


def _build_youtube_transcript(session: Session, episode: Episode, podcast: Podcast) -> Transcript | None:
    # Only hand-written/manual captions count as a "published" transcript here
    # — YouTube's own auto-generated captions are deliberately left for the
    # whisper ASR fallback below (see youtube.fetch_manual_captions).
    try:
        cues = youtube.fetch_manual_captions(episode.audio_url, podcast.language)
    except youtube.YoutubeFetchError:
        return None
    if not cues:
        return None

    transcript = _persist_cues(session, episode, cues, podcast.language, TranscriptSource.published)
    if transcript is None:
        return None

    episode.transcript_status = TranscriptStatus.full
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript


def _build_local_directory_transcript(session: Session, episode: Episode, podcast: Podcast) -> Transcript | None:
    # transcript_source_url/type are populated by services.local_dir.scan_episodes
    # with a sidecar file's absolute path and its extension (srt/vtt/json) — no
    # separate published check needed since a sidecar's presence already means it's timed.
    if not episode.transcript_source_url or episode.transcript_source_type not in _PARSERS:
        return None

    try:
        content = Path(episode.transcript_source_url).read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        cues = _PARSERS[episode.transcript_source_type](content)
    except (ValueError, KeyError):
        return None
    if not cues:
        return None

    transcript = _persist_cues(session, episode, cues, podcast.language, TranscriptSource.published)
    if transcript is None:
        return None

    episode.transcript_status = TranscriptStatus.full
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript


def build_transcript(session: Session, episode: Episode) -> Transcript | None:
    """Fetch and parse the episode's published transcript on demand, building
    ordered Sentence rows from SRT/VTT/Podcasting-2.0-JSON cues. Untimed
    plain-text/HTML transcripts are left for the ASR fallback (#5)."""
    podcast = session.get(Podcast, episode.podcast_id)
    if podcast and podcast.kind == PodcastKind.youtube:
        return _build_youtube_transcript(session, episode, podcast)
    if podcast and podcast.kind == PodcastKind.local_directory:
        return _build_local_directory_transcript(session, episode, podcast)

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
        language = podcast.language if podcast else ""

    transcript = _persist_cues(session, episode, cues, language, TranscriptSource.published)
    if transcript is None:
        return None

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
    if original_status == TranscriptStatus.pending:
        # A caller (e.g. the /transcribe endpoint) may have already optimistically
        # set pending before invoking us — reverting to that would be a no-op.
        original_status = TranscriptStatus.none
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


def _transcribe_with_progress(episode_id: int, audio_path: Path) -> tuple[list[Cue], str]:
    try:
        return transcribe_audio(str(audio_path), episode_id=episode_id)
    finally:
        clear_progress(episode_id)


def _transcribe_with_asr(session: Session, episode: Episode, audio_path: Path) -> Transcript | None:
    try:
        cues, detected_language = _transcribe_with_progress(episode.id, audio_path)
    except WhisperModelNotFoundError:
        episode.transcript_status = TranscriptStatus.queued
        session.add(episode)
        session.commit()
        return None
    except Exception:
        logger.exception("ASR transcription failed for episode %s", episode.id)
        episode.transcript_status = TranscriptStatus.failed
        session.add(episode)
        session.commit()
        return None
    if not cues:
        episode.transcript_status = TranscriptStatus.failed
        session.add(episode)
        session.commit()
        return None

    transcript = _persist_cues(session, episode, cues, detected_language or "", TranscriptSource.asr)
    if transcript is None:
        episode.transcript_status = TranscriptStatus.failed
        session.add(episode)
        session.commit()
        return None

    episode.transcript_status = TranscriptStatus.auto
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript
