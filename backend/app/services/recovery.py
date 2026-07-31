from datetime import datetime, timedelta

from sqlmodel import Session, select

from app import paths
from app.models import (
    AppSettings,
    AutoRemovePolicy,
    DownloadStatus,
    Episode,
    PlaybackState,
    Transcript,
    TranscriptSource,
    TranscriptStatus,
)
from app.services.downloads import remove_audio

AUTO_REMOVE_DAYS = {AutoRemovePolicy.seven_days: 7, AutoRemovePolicy.thirty_days: 30}


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
    _sweep_auto_remove(session)


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
    for directory in (paths.storage_dir(), paths.models_dir()):
        if not directory.is_dir():
            continue
        for part_file in directory.glob("*.part"):
            part_file.unlink(missing_ok=True)


def _sweep_auto_remove(session: Session) -> None:
    """Deletes downloaded audio for episodes the user hasn't touched in a
    while, per the auto-remove policy in AppSettings. There's no dedicated
    "finished listening" event in this app yet, so PlaybackState.updated_at
    (last time playback position was saved for that episode) is used as the
    best available proxy for "last played"."""
    settings = session.get(AppSettings, 1)
    if settings is None or settings.auto_remove == AutoRemovePolicy.never:
        return

    cutoff = datetime.utcnow() - timedelta(days=AUTO_REMOVE_DAYS[settings.auto_remove])
    episodes = session.exec(
        select(Episode)
        .join(PlaybackState, PlaybackState.episode_id == Episode.id)
        .where(Episode.download_status == DownloadStatus.downloaded, PlaybackState.updated_at < cutoff)
    ).all()
    for episode in episodes:
        remove_audio(session, episode)
    if episodes:
        session.commit()
