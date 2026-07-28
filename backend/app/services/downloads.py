import mimetypes
from pathlib import Path

import httpx
from sqlmodel import Session

from app import paths
from app.db import engine
from app.models import DownloadStatus, Episode
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


def download_episode_audio(episode_id: int) -> None:
    with Session(engine) as session:
        episode = session.get(Episode, episode_id)
        if not episode:
            return

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        part_path = STORAGE_DIR / f"{episode_id}.part"

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
            return

        filename = f"{episode_id}{extension}"
        target = STORAGE_DIR / filename
        part_path.rename(target)

        episode.local_audio_path = filename
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
