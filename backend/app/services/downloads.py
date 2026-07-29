import mimetypes
from pathlib import Path

import httpx
from sqlmodel import Session

from app import paths
from app.db import engine
from app.models import DownloadStatus, Episode, Podcast, PodcastKind
from app.services import youtube
from app.services.transcripts import ingest_transcript

STORAGE_DIR = paths.storage_dir()


def _extension_for(url: str, content_type: str | None) -> str:
    suffix = Path(httpx.URL(url).path).suffix
    if suffix:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return ".mp3"


def _download_youtube_audio(session: Session, episode: Episode) -> Path | None:
    try:
        return youtube.download_audio(episode.audio_url, STORAGE_DIR, episode.id)
    except youtube.YoutubeDownloadError:
        episode.download_status = DownloadStatus.failed
        session.add(episode)
        session.commit()
        return None


def _download_rss_audio(session: Session, episode: Episode) -> Path | None:
    part_path = STORAGE_DIR / f"{episode.id}.part"
    try:
        with httpx.stream("GET", episode.audio_url, follow_redirects=True, timeout=60.0) as response:
            response.raise_for_status()
            extension = _extension_for(str(response.url), response.headers.get("content-type"))
            with part_path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError:
        part_path.unlink(missing_ok=True)
        episode.download_status = DownloadStatus.failed
        session.add(episode)
        session.commit()
        return None

    target = STORAGE_DIR / f"{episode.id}{extension}"
    part_path.rename(target)
    return target


def download_episode_audio(episode_id: int) -> None:
    with Session(engine) as session:
        episode = session.get(Episode, episode_id)
        if not episode:
            return

        podcast = session.get(Podcast, episode.podcast_id)
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        if podcast and podcast.kind == PodcastKind.youtube:
            target = _download_youtube_audio(session, episode)
        else:
            target = _download_rss_audio(session, episode)
        if target is None:
            return

        episode.local_audio_path = target.name
        episode.download_status = DownloadStatus.downloaded
        session.add(episode)
        session.commit()

        ingest_transcript(session, episode, audio_path=target)


def retry_transcription(episode_id: int) -> None:
    with Session(engine) as session:
        episode = session.get(Episode, episode_id)
        if not episode or not episode.local_audio_path:
            return
        ingest_transcript(session, episode, audio_path=STORAGE_DIR / episode.local_audio_path)
