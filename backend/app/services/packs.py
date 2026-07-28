import errno
import hashlib
import logging
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app import paths

logger = logging.getLogger(__name__)

# unidic-lite's PyPI sdist bundles the exact UniDic dicdir this project needs,
# already compressed for transfer (47MB tarball -> 248MB extracted). Verified
# by downloading and hashing it directly rather than trusting the recorded
# value blind.
_UNIDIC_URL = "https://files.pythonhosted.org/packages/55/2b/8cf7514cb57d028abcef625afa847d60ff1ffbf0049c36b78faa7c35046f/unidic-lite-1.0.8.tar.gz"
_UNIDIC_SHA256 = "db9d4572d9fdd4d00a97949d4b0741ec480ee05a7e7e2e32f547500dae27b245"
_UNIDIC_DOWNLOAD_SIZE = 47356746
_UNIDIC_TAR_PREFIX = "unidic-lite-1.0.8/unidic_lite/dicdir/"


@dataclass(frozen=True)
class PackSpec:
    name: str
    dirname: str
    url: str
    download_size_bytes: int
    sha256: str
    tar_prefix: str


CATALOG: dict[str, PackSpec] = {
    "japanese": PackSpec(
        name="japanese",
        dirname="unidic",
        url=_UNIDIC_URL,
        download_size_bytes=_UNIDIC_DOWNLOAD_SIZE,
        sha256=_UNIDIC_SHA256,
        tar_prefix=_UNIDIC_TAR_PREFIX,
    ),
}


@dataclass
class _Progress:
    state: str
    bytes_done: int = 0
    bytes_total: int = 0
    error: str | None = None


_progress: dict[str, _Progress] = {}


def pack_dir(name: str) -> Path:
    return paths.packs_dir() / CATALOG[name].dirname


def is_installed(name: str) -> bool:
    return (pack_dir(name) / "sys.dic").is_file()


def list_packs() -> list[dict]:
    return [
        {"name": spec.name, "download_size_bytes": spec.download_size_bytes, "installed": is_installed(spec.name)}
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
    size_bytes = CATALOG[name].download_size_bytes
    if is_installed(name):
        return {"state": "installed", "bytes_done": size_bytes, "bytes_total": size_bytes, "error": None}
    return {"state": "not_installed", "bytes_done": 0, "bytes_total": size_bytes, "error": None}


def is_downloading(name: str) -> bool:
    progress = _progress.get(name)
    return progress is not None and progress.state in ("downloading", "verifying", "extracting")


def delete_pack(name: str) -> None:
    shutil.rmtree(pack_dir(name), ignore_errors=True)
    _progress.pop(name, None)


def install_pack(name: str) -> None:
    spec = CATALOG[name]
    packs_root = paths.packs_dir()
    packs_root.mkdir(parents=True, exist_ok=True)
    archive_path = packs_root / f"{name}.download.part"

    progress = _Progress(state="downloading", bytes_total=spec.download_size_bytes)
    _progress[name] = progress

    # Room for the compressed download plus the extracted copy staged alongside it.
    if shutil.disk_usage(packs_root).free < spec.download_size_bytes * 6:
        progress.state = "failed"
        progress.error = "disk_space"
        return

    hasher = hashlib.sha256()
    try:
        with httpx.stream("GET", spec.url, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            with archive_path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
                    hasher.update(chunk)
                    progress.bytes_done += len(chunk)
    except OSError as exc:
        archive_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "disk_space" if exc.errno == errno.ENOSPC else "unknown"
        return
    except httpx.HTTPError:
        archive_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "offline" if progress.bytes_done == 0 else "network"
        return

    progress.state = "verifying"
    if hasher.hexdigest() != spec.sha256:
        archive_path.unlink(missing_ok=True)
        progress.state = "failed"
        progress.error = "checksum"
        return

    progress.state = "extracting"
    staging_dir = packs_root / f"{name}.extracting"
    shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir()
    try:
        _extract_dicdir(archive_path, spec.tar_prefix, staging_dir)
    except tarfile.TarError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        progress.state = "failed"
        progress.error = "unknown"
        return
    finally:
        archive_path.unlink(missing_ok=True)

    final_dir = pack_dir(name)
    shutil.rmtree(final_dir, ignore_errors=True)
    staging_dir.rename(final_dir)

    progress.bytes_done = spec.download_size_bytes
    progress.state = "installed"
    try:
        _backfill_furigana()
    except Exception:
        # The pack itself is already installed at this point; a backfill
        # failure shouldn't be reported as an install failure.
        logger.exception("Furigana backfill failed after installing pack %s", name)


def _extract_dicdir(archive_path: Path, tar_prefix: str, staging_dir: Path) -> None:
    with tarfile.open(archive_path) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(tar_prefix):
                continue
            relative = member.name[len(tar_prefix) :]
            if not relative:
                continue
            member.name = relative
            tar.extract(member, path=staging_dir, filter="data")


def _backfill_furigana() -> None:
    # Deferred imports: this mirrors whisper_models.py's split from #23 — keeps
    # packs.py free of a hard dependency on the transcript/DB stack at import time.
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Sentence, Transcript
    from app.services.furigana import build_segments

    with Session(engine) as session:
        transcripts = session.exec(select(Transcript).where(Transcript.language.startswith("ja"))).all()
        for transcript in transcripts:
            sentences = session.exec(select(Sentence).where(Sentence.transcript_id == transcript.id)).all()
            for sentence in sentences:
                sentence.segments = build_segments(sentence.text, transcript.language)
                session.add(sentence)
        session.commit()
