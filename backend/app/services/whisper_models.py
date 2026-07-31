import errno
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlmodel import Session, select

from app import paths
from app.db import engine
from app.models import Episode, TranscriptStatus

_HF_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    filename: str
    url: str
    size_bytes: int
    sha256: str


CATALOG: dict[str, ModelSpec] = {
    spec.name: spec
    for spec in (
        ModelSpec(
            "tiny",
            "ggml-tiny.bin",
            f"{_HF_BASE}/ggml-tiny.bin",
            77691713,
            "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
        ),
        ModelSpec(
            "base",
            "ggml-base.bin",
            f"{_HF_BASE}/ggml-base.bin",
            147951465,
            "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        ),
        ModelSpec(
            "small",
            "ggml-small.bin",
            f"{_HF_BASE}/ggml-small.bin",
            487601967,
            "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
        ),
    )
}

_DEFAULT_ACTIVE_MODEL = "base"
_ACTIVE_MODEL_STATE_PATH = paths.data_dir() / "active_whisper_model"


@dataclass
class _Progress:
    state: str
    bytes_done: int = 0
    bytes_total: int = 0
    error: str | None = None


_progress: dict[str, _Progress] = {}


def _model_file_path(name: str) -> Path:
    return paths.models_dir() / CATALOG[name].filename


def _is_installed(name: str) -> bool:
    return _model_file_path(name).is_file()


def _active_model_name() -> str:
    if _ACTIVE_MODEL_STATE_PATH.is_file():
        name = _ACTIVE_MODEL_STATE_PATH.read_text().strip()
        if name in CATALOG:
            return name
    return _DEFAULT_ACTIVE_MODEL


def set_active_model(name: str) -> None:
    _ACTIVE_MODEL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_MODEL_STATE_PATH.write_text(name)


def active_model_path() -> Path:
    return _model_file_path(_active_model_name())


def list_models() -> list[dict]:
    active = _active_model_name()
    return [
        {
            "name": spec.name,
            "size_bytes": spec.size_bytes,
            "installed": _is_installed(spec.name),
            "active": spec.name == active,
        }
        for spec in CATALOG.values()
    ]


def get_status(name: str) -> dict:
    progress = _progress.get(name)
    if progress is not None:
        return {
            "state": progress.state,
            "bytes_done": progress.bytes_done,
            "bytes_total": progress.bytes_total,
            "error": progress.error,
        }
    size_bytes = CATALOG[name].size_bytes
    if _is_installed(name):
        return {"state": "installed", "bytes_done": size_bytes, "bytes_total": size_bytes, "error": None}
    return {"state": "not_installed", "bytes_done": 0, "bytes_total": size_bytes, "error": None}


def is_downloading(name: str) -> bool:
    progress = _progress.get(name)
    return progress is not None and progress.state in ("downloading", "verifying")


def delete_model(name: str) -> None:
    _model_file_path(name).unlink(missing_ok=True)
    if _active_model_name() == name:
        _ACTIVE_MODEL_STATE_PATH.unlink(missing_ok=True)
    _progress.pop(name, None)


def download_model(name: str) -> None:
    spec = CATALOG[name]
    models_dir = paths.models_dir()
    models_dir.mkdir(parents=True, exist_ok=True)
    part_path = models_dir / f"{spec.filename}.part"
    final_path = models_dir / spec.filename

    progress = _Progress(state="downloading", bytes_total=spec.size_bytes)
    _progress[name] = progress

    if shutil.disk_usage(models_dir).free < spec.size_bytes:
        progress.state = "failed"
        progress.error = "disk_space"
        return

    hasher = hashlib.sha256()
    try:
        with httpx.stream("GET", spec.url, follow_redirects=True, timeout=60.0) as response:
            response.raise_for_status()
            with part_path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
                    hasher.update(chunk)
                    progress.bytes_done += len(chunk)
    except OSError as exc:
        part_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "disk_space" if exc.errno == errno.ENOSPC else "unknown"
        return
    except httpx.HTTPError:
        part_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "offline" if progress.bytes_done == 0 else "network"
        return

    progress.state = "verifying"
    if hasher.hexdigest() != spec.sha256:
        part_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "checksum"
        return

    part_path.rename(final_path)
    set_active_model(name)
    progress.bytes_done = spec.size_bytes
    progress.state = "installed"
    _retry_queued_transcriptions()


def _retry_queued_transcriptions() -> None:
    # Deferred imports: transcription.py resolves the active model through this
    # module, so top-level imports here would cycle back through downloads.py/
    # transcripts.py -> transcription.py -> whisper_models.py.
    from app import paths
    from app.services.transcripts import ingest_transcript

    with Session(engine) as session:
        episodes = session.exec(
            select(Episode).where(
                Episode.transcript_status == TranscriptStatus.queued,
                Episode.local_audio_path.is_not(None),
            )
        ).all()
        for episode in episodes:
            ingest_transcript(session, episode, audio_path=paths.storage_dir() / episode.local_audio_path)
