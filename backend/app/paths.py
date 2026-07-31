import json
import os
import sys
from pathlib import Path

APP_NAME = "Kotoba"


def data_dir() -> Path:
    override = os.environ.get("KOTOBA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / "Library" / "Application Support" / APP_NAME


def storage_location_file() -> Path:
    return data_dir() / "storage_location.json"


def storage_dir() -> Path:
    """Where downloaded episode audio lives. Defaults under data_dir(), but a
    user can relocate it (see services.downloads.relocate_storage); that
    choice is recorded in storage_location_file() rather than the DB, since
    this module has no DB dependency and is imported before the DB exists."""
    marker = storage_location_file()
    if marker.is_file():
        try:
            location = json.loads(marker.read_text()).get("path")
        except (json.JSONDecodeError, OSError):
            location = None
        if location:
            return Path(location)
    return data_dir() / "storage"


def models_dir() -> Path:
    return data_dir() / "models"


def packs_dir() -> Path:
    return data_dir() / "packs"


def resource_dir() -> Path:
    """Root for read-only bundled assets: sys._MEIPASS when frozen, the repo root otherwise."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent.parent
