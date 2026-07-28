from sqlmodel import Session, select

from app.models import DownloadStatus, Episode, Transcript, TranscriptSource, TranscriptStatus
from app.services.downloads import STORAGE_DIR


def recover_startup_state(session: Session) -> None:
    """Undo the effects of a process that died mid-download or mid-transcription.
    Both `start_download` and `ingest_transcript` set a "busy" status, do the
    slow part, then set a terminal status on completion — with nothing to
    revert the "busy" status if the process is killed in between. Run once at
    startup, before the app accepts traffic, so those rows don't stay stuck
    forever."""
    _recover_pending_transcripts(session)
    _recover_interrupted_downloads(session)
    _delete_stale_part_files()


def _recover_pending_transcripts(session: Session) -> None:
    episodes = session.exec(select(Episode).where(Episode.transcript_status == TranscriptStatus.pending)).all()
    for episode in episodes:
        transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
        if transcript is None:
            episode.transcript_status = TranscriptStatus.none
        elif transcript.source == TranscriptSource.published:
            episode.transcript_status = TranscriptStatus.full
        else:
            episode.transcript_status = TranscriptStatus.auto
        session.add(episode)
    if episodes:
        session.commit()


def _recover_interrupted_downloads(session: Session) -> None:
    episodes = session.exec(select(Episode).where(Episode.download_status == DownloadStatus.downloading)).all()
    for episode in episodes:
        episode.download_status = DownloadStatus.idle
        session.add(episode)
    if episodes:
        session.commit()


def _delete_stale_part_files() -> None:
    if not STORAGE_DIR.is_dir():
        return
    for part_file in STORAGE_DIR.glob("*.part"):
        part_file.unlink(missing_ok=True)
