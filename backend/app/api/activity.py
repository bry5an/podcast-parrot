from fastapi import APIRouter, Depends
from sqlmodel import Session, or_, select

from app.db import get_session
from app.models import DownloadStatus, Episode, TranscriptStatus
from app.services import packs, whisper_models

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity")
def get_activity(session: Session = Depends(get_session)) -> dict:
    """Whether a download or transcription is in flight, so the desktop shell
    can warn before quitting mid-operation instead of orphaning it."""
    in_flight_episode = session.exec(
        select(Episode.id)
        .where(
            or_(
                Episode.download_status == DownloadStatus.downloading,
                Episode.transcript_status == TranscriptStatus.pending,
            )
        )
        .limit(1)
    ).first()
    in_flight_model = any(whisper_models.is_downloading(name) for name in whisper_models.CATALOG)
    in_flight_pack = any(packs.is_downloading(name) for name in packs.CATALOG)
    return {"active": in_flight_episode is not None or in_flight_model or in_flight_pack}
