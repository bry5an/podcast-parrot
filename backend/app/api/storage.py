import json

from fastapi import APIRouter, Depends
from sqlmodel import Session, SQLModel, select

from app import paths
from app.db import get_session
from app.models import DownloadStatus, Episode, Sentence

router = APIRouter(prefix="/api/storage", tags=["storage"])


class StorageStats(SQLModel):
    bytes_used: int
    episode_count: int
    storage_root: str
    transcript_bytes: int


def _bytes_used(directory) -> int:
    if not directory.is_dir():
        return 0
    return sum(f.stat().st_size for f in directory.iterdir() if f.is_file())


def _transcript_bytes_used(session: Session) -> int:
    # Transcripts have no on-disk files (Sentence.text/segments live in
    # SQLite), so this estimates their footprint from the serialized row
    # content rather than walking a directory.
    total = 0
    for text, segments in session.exec(select(Sentence.text, Sentence.segments)).all():
        total += len(text.encode("utf-8")) + len(json.dumps(segments).encode("utf-8"))
    return total


@router.get("", response_model=StorageStats)
def get_storage_stats(session: Session = Depends(get_session)):
    storage_dir = paths.storage_dir()
    episode_count = len(session.exec(select(Episode).where(Episode.download_status == DownloadStatus.downloaded)).all())
    return StorageStats(
        bytes_used=_bytes_used(storage_dir),
        episode_count=episode_count,
        storage_root=str(storage_dir),
        transcript_bytes=_transcript_bytes_used(session),
    )
