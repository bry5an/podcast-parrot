from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.models import Episode, Podcast, PodcastKind, TranscriptStatus
from app.services.local_dir import LocalDirectoryError
from app.services.local_dir import scan_episodes as scan_local_directory_episodes
from app.services.rss import TIMED_TRANSCRIPT_FORMATS, FeedFetchError, fetch_episodes
from app.services.youtube import YoutubeFetchError, fetch_playlist_episodes

POLL_INTERVAL = timedelta(minutes=15)


def _apply_transcript_fields(episode: Episode, data: dict) -> None:
    # A transcript already fully ingested (see build_transcript in
    # app.services.transcripts) is never downgraded by a later poll.
    if episode.transcript_status == TranscriptStatus.full:
        return

    transcript_format = data["transcript_source_format"]
    episode.transcript_source_url = data["transcript_source_url"]
    episode.transcript_source_type = data["transcript_source_type"]
    episode.transcript_source_language = data["transcript_source_language"]
    if transcript_format is None:
        episode.transcript_status = TranscriptStatus.none
    elif transcript_format in TIMED_TRANSCRIPT_FORMATS:
        episode.transcript_status = TranscriptStatus.pending
    else:
        episode.transcript_status = TranscriptStatus.auto


def sync_episodes(session: Session, podcast: Podcast) -> None:
    if podcast.last_polled_at and datetime.utcnow() - podcast.last_polled_at < POLL_INTERVAL:
        return

    try:
        if podcast.kind == PodcastKind.youtube:
            fetched = fetch_playlist_episodes(podcast.youtube_playlist_url)
        elif podcast.kind == PodcastKind.local_directory:
            fetched = scan_local_directory_episodes(Path(podcast.local_directory_path))
        else:
            fetched = fetch_episodes(podcast.rss_url)
    except (FeedFetchError, YoutubeFetchError, LocalDirectoryError):
        return

    existing = {
        e.guid: e
        for e in session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
    }
    for data in fetched:
        episode = existing.get(data["guid"])
        if episode:
            episode.title = data["title"]
            episode.pub_date = data["pub_date"]
            episode.duration_seconds = data["duration_seconds"]
            episode.audio_url = data["audio_url"]
            _apply_transcript_fields(episode, data)
            session.add(episode)
        else:
            episode = Episode(
                podcast_id=podcast.id,
                guid=data["guid"],
                title=data["title"],
                pub_date=data["pub_date"],
                duration_seconds=data["duration_seconds"],
                audio_url=data["audio_url"],
            )
            _apply_transcript_fields(episode, data)
            session.add(episode)

    podcast.last_polled_at = datetime.utcnow()
    session.add(podcast)
    session.commit()
