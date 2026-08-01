import json
import mimetypes
import shutil
from pathlib import Path

import httpx
from sqlmodel import Session

from app import paths
from app.db import engine
from app.models import DownloadStatus, Episode, Podcast, PodcastKind
from app.services import youtube
from app.services.transcripts import ingest_transcript


def _extension_for(url: str, content_type: str | None) -> str:
    suffix = Path(httpx.URL(url).path).suffix
    if suffix:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return ".mp3"


def resolve_audio_path(podcast: Podcast | None, episode: Episode) -> Path | None:
    """Where an episode's audio actually lives on disk. Local-directory audio
    stays in the user's own folder and is never copied into storage_dir(), so
    local_audio_path holds an absolute path for that kind instead of a
    filename to join with storage_dir()."""
    if not episode.local_audio_path:
        return None
    if podcast and podcast.kind == PodcastKind.local_directory:
        return Path(episode.local_audio_path)
    return paths.storage_dir() / episode.local_audio_path


def _link_local_audio(session: Session, episode: Episode) -> Path | None:
    source = Path(episode.audio_url)
    if not source.is_file():
        episode.download_status = DownloadStatus.failed
        session.add(episode)
        session.commit()
        return None
    return source


def _download_youtube_audio(session: Session, episode: Episode) -> Path | None:
    try:
        return youtube.download_audio(episode.audio_url, paths.storage_dir(), episode.id)
    except youtube.YoutubeDownloadError:
        episode.download_status = DownloadStatus.failed
        session.add(episode)
        session.commit()
        return None


def _download_rss_audio(session: Session, episode: Episode) -> Path | None:
    storage_dir = paths.storage_dir()
    part_path = storage_dir / f"{episode.id}.part"
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

    target = storage_dir / f"{episode.id}{extension}"
    part_path.rename(target)
    return target


def download_episode_audio(episode_id: int) -> None:
    with Session(engine) as session:
        episode = session.get(Episode, episode_id)
        if not episode:
            return

        podcast = session.get(Podcast, episode.podcast_id)

        if podcast and podcast.kind == PodcastKind.local_directory:
            target = _link_local_audio(session, episode)
            if target is None:
                return
            episode.local_audio_path = str(target)
        else:
            paths.storage_dir().mkdir(parents=True, exist_ok=True)
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
        podcast = session.get(Podcast, episode.podcast_id)
        audio_path = resolve_audio_path(podcast, episode)
        if audio_path is None:
            return
        ingest_transcript(session, episode, audio_path=audio_path)


def remove_audio(session: Session, episode: Episode) -> None:
    """Deletes an episode's downloaded audio file and resets its download
    state. Shared by the manual "delete download" action and the auto-remove
    sweep so both stay in sync (see api/episodes.py, services/recovery.py).
    Local-directory episodes reference a file the app doesn't own — never
    unlink it, just forget the reference (reopening relinks for free)."""
    podcast = session.get(Podcast, episode.podcast_id)
    is_local_directory = podcast is not None and podcast.kind == PodcastKind.local_directory
    if episode.local_audio_path and not is_local_directory:
        (paths.storage_dir() / episode.local_audio_path).unlink(missing_ok=True)
    episode.local_audio_path = None
    episode.download_status = DownloadStatus.idle
    session.add(episode)


class RelocateStorageError(RuntimeError):
    pass


def relocate_storage(new_root: Path) -> Path:
    """Moves all files from the current storage dir into new_root and
    records new_root as the storage location going forward (see
    paths.storage_dir())."""
    new_root = new_root.expanduser().resolve()
    current = paths.storage_dir()

    if new_root == current:
        return current
    if new_root.is_file():
        raise RelocateStorageError(f"{new_root} is a file, not a directory")
    if new_root.is_dir() and any(new_root.iterdir()):
        raise RelocateStorageError(f"{new_root} is not empty")

    try:
        new_root.mkdir(parents=True, exist_ok=True)
        probe = new_root / ".kotoba-write-test"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise RelocateStorageError(f"{new_root} is not writable: {e}") from e

    if current.is_dir():
        for entry in current.iterdir():
            shutil.move(str(entry), str(new_root / entry.name))

    paths.storage_location_file().write_text(json.dumps({"path": str(new_root)}))
    return new_root
