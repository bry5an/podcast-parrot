from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlmodel import SQLModel

from app.services import whisper_models

router = APIRouter(prefix="/api", tags=["models"])


class ModelRead(SQLModel):
    name: str
    size_bytes: int
    installed: bool
    active: bool


class ModelStatusRead(SQLModel):
    state: str
    bytes_done: int
    bytes_total: int
    error: str | None


def _require_catalog_entry(name: str) -> None:
    if name not in whisper_models.CATALOG:
        raise HTTPException(status_code=404, detail="Unknown model")


@router.get("/models", response_model=list[ModelRead])
def list_models():
    return whisper_models.list_models()


@router.post("/models/{name}", response_model=ModelRead, status_code=202)
def start_model_download(name: str, background_tasks: BackgroundTasks):
    _require_catalog_entry(name)

    entry = next(m for m in whisper_models.list_models() if m["name"] == name)
    if entry["installed"]:
        whisper_models.set_active_model(name)
        return ModelRead(**{**entry, "active": True})

    if not whisper_models.is_downloading(name):
        background_tasks.add_task(whisper_models.download_model, name)

    return ModelRead(**entry)


@router.get("/models/{name}/status", response_model=ModelStatusRead)
def get_model_status(name: str):
    _require_catalog_entry(name)
    return whisper_models.get_status(name)


@router.delete("/models/{name}", status_code=204)
def delete_model(name: str):
    _require_catalog_entry(name)
    whisper_models.delete_model(name)
