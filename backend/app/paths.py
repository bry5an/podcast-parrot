import os
import sys
from pathlib import Path

APP_NAME = "Kotoba"


def data_dir() -> Path:
    override = os.environ.get("KOTOBA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / "Library" / "Application Support" / APP_NAME


def storage_dir() -> Path:
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
