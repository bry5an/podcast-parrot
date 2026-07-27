import httpx
from sqlmodel import Session, select

from app.models import Episode, Podcast, Sentence, Transcript, TranscriptSource, TranscriptStatus
from app.services.rss import TIMED_TRANSCRIPT_FORMATS, classify_transcript_format
from app.services.transcript_parsers import parse_json_transcript, parse_srt, parse_vtt

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
                segments=[{"base": cue.text, "reading": ""}],
            )
        )

    episode.transcript_status = TranscriptStatus.full
    session.add(episode)
    session.commit()
    session.refresh(transcript)
    return transcript
