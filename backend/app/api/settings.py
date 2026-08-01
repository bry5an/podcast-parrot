from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel

from app import paths
from app.db import get_session
from app.models import AppSettings, AutoRemovePolicy, ComputeDevice
from app.services.downloads import RelocateStorageError, relocate_storage

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsRead(SQLModel):
    auto_remove: AutoRemovePolicy
    storage_root: str
    compute_device: ComputeDevice
    cache_transcripts: bool


class SettingsUpdate(SQLModel):
    auto_remove: AutoRemovePolicy | None = None
    storage_root: str | None = None
    compute_device: ComputeDevice | None = None
    cache_transcripts: bool | None = None


def _get_or_create(session: Session) -> AppSettings:
    settings = session.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def _to_read(settings: AppSettings) -> SettingsRead:
    return SettingsRead(
        auto_remove=settings.auto_remove,
        storage_root=str(paths.storage_dir()),
        compute_device=settings.compute_device,
        cache_transcripts=settings.cache_transcripts,
    )


@router.get("", response_model=SettingsRead)
def get_settings(session: Session = Depends(get_session)):
    settings = _get_or_create(session)
    return _to_read(settings)


@router.patch("", response_model=SettingsRead)
def update_settings(payload: SettingsUpdate, session: Session = Depends(get_session)):
    settings = _get_or_create(session)

    if payload.auto_remove is not None or payload.compute_device is not None or payload.cache_transcripts is not None:
        if payload.auto_remove is not None:
            settings.auto_remove = payload.auto_remove
        if payload.compute_device is not None:
            settings.compute_device = payload.compute_device
        if payload.cache_transcripts is not None:
            settings.cache_transcripts = payload.cache_transcripts
        session.add(settings)
        session.commit()
        session.refresh(settings)

    if payload.storage_root is not None:
        try:
            relocate_storage(Path(payload.storage_root))
        except RelocateStorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_read(settings)
