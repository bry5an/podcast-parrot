import hashlib
import io
import tarfile

import httpx
import pytest

from app.models import Sentence, Transcript, TranscriptSource
from app.services import packs
from app.services.packs import PackSpec


def _build_tarball(prefix: str, files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name=f"{prefix}{name}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


_PREFIX = "pkg-1.0/pkg/dicdir/"
_DICDIR_FILES = {"sys.dic": b"sys-dic-bytes", "matrix.bin": b"matrix-bytes"}


def _single_pack_catalog(files: dict[str, bytes] = _DICDIR_FILES, prefix: str = _PREFIX):
    payload = _build_tarball(prefix, files)
    spec = PackSpec(
        name="japanese",
        dirname="unidic",
        url="https://example.com/pkg.tar.gz",
        download_size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        tar_prefix=prefix,
    )
    return payload, {"japanese": spec}


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    packs_root = tmp_path / "packs"
    monkeypatch.setattr("app.services.packs.paths.packs_dir", lambda: packs_root)
    packs._progress.clear()
    yield packs_root
    packs._progress.clear()


class _FakeResponse:
    def __init__(self, chunks, stream_error=None, status_error=None):
        self._chunks = chunks
        self._stream_error = stream_error
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def iter_bytes(self):
        yield from self._chunks
        if self._stream_error:
            raise self._stream_error


class _FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc_info):
        return False


def test_install_pack_success_extracts_dicdir_and_backfills(monkeypatch, _isolate_state):
    payload, catalog = _single_pack_catalog()
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr("app.services.packs.httpx.stream", lambda *a, **k: _FakeStream(_FakeResponse([payload])))
    backfill_calls = []
    monkeypatch.setattr("app.services.packs._backfill_furigana", lambda: backfill_calls.append(1))

    packs.install_pack("japanese")

    final_dir = _isolate_state / "unidic"
    assert (final_dir / "sys.dic").read_bytes() == b"sys-dic-bytes"
    assert (final_dir / "matrix.bin").read_bytes() == b"matrix-bytes"
    assert not (_isolate_state / "japanese.download.part").exists()
    assert not (_isolate_state / "japanese.extracting").exists()
    assert backfill_calls == [1]

    status = packs.get_status("japanese")
    assert status["state"] == "installed"
    assert packs.is_installed("japanese") is True


def test_install_pack_ignores_files_outside_prefix(monkeypatch, _isolate_state):
    payload, catalog = _single_pack_catalog(
        files={"sys.dic": b"data", "../../evil.txt": b"nope"}, prefix=_PREFIX
    )
    # Also add a file outside the prefix entirely via a second tar entry.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=f"{_PREFIX}sys.dic")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"data"))
        outside = tarfile.TarInfo(name="pkg-1.0/README.md")
        outside.size = 3
        tar.addfile(outside, io.BytesIO(b"foo"))
    payload = buf.getvalue()
    spec = PackSpec(
        name="japanese", dirname="unidic", url="https://example.com/pkg.tar.gz",
        download_size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), tar_prefix=_PREFIX,
    )
    catalog = {"japanese": spec}
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr("app.services.packs.httpx.stream", lambda *a, **k: _FakeStream(_FakeResponse([payload])))
    monkeypatch.setattr("app.services.packs._backfill_furigana", lambda: None)

    packs.install_pack("japanese")

    final_dir = _isolate_state / "unidic"
    assert (final_dir / "sys.dic").read_bytes() == b"data"
    assert not (final_dir / "README.md").exists()
    assert not (_isolate_state / "README.md").exists()


def test_install_pack_checksum_mismatch_leaves_nothing_installed(monkeypatch, _isolate_state):
    payload, catalog = _single_pack_catalog()
    catalog["japanese"] = PackSpec(
        name="japanese", dirname="unidic", url="https://example.com/pkg.tar.gz",
        download_size_bytes=len(payload), sha256="0" * 64, tar_prefix=_PREFIX,
    )
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr("app.services.packs.httpx.stream", lambda *a, **k: _FakeStream(_FakeResponse([payload])))

    packs.install_pack("japanese")

    assert not (_isolate_state / "unidic").exists()
    status = packs.get_status("japanese")
    assert status["state"] == "failed"
    assert status["error"] == "checksum"


def test_install_pack_disk_space_precheck_fails_before_network_call(monkeypatch, _isolate_state):
    _, catalog = _single_pack_catalog()
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr("app.services.packs.shutil.disk_usage", lambda path: type("_", (), {"free": 0})())

    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.packs.httpx.stream", fail_if_called)

    packs.install_pack("japanese")

    assert not called
    assert packs.get_status("japanese")["error"] == "disk_space"


def test_install_pack_offline_when_zero_bytes_received(monkeypatch, _isolate_state):
    _, catalog = _single_pack_catalog()
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.packs.httpx.stream", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("no network"))
    )

    packs.install_pack("japanese")

    assert packs.get_status("japanese")["error"] == "offline"


def test_install_pack_network_loss_after_partial_bytes(monkeypatch, _isolate_state):
    payload, catalog = _single_pack_catalog()
    monkeypatch.setattr("app.services.packs.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.packs.httpx.stream",
        lambda *a, **k: _FakeStream(_FakeResponse([payload[:10]], stream_error=httpx.ReadError("dropped"))),
    )

    packs.install_pack("japanese")

    status = packs.get_status("japanese")
    assert status["error"] == "network"
    assert status["bytes_done"] == 10


def test_install_pack_corrupt_archive_fails_cleanly(monkeypatch, _isolate_state):
    garbage = b"not a tarball"
    spec = PackSpec(
        name="japanese", dirname="unidic", url="https://example.com/pkg.tar.gz",
        download_size_bytes=len(garbage), sha256=hashlib.sha256(garbage).hexdigest(), tar_prefix=_PREFIX,
    )
    monkeypatch.setattr("app.services.packs.CATALOG", {"japanese": spec})
    monkeypatch.setattr("app.services.packs.httpx.stream", lambda *a, **k: _FakeStream(_FakeResponse([garbage])))

    packs.install_pack("japanese")

    status = packs.get_status("japanese")
    assert status["state"] == "failed"
    assert status["error"] == "unknown"
    assert not (_isolate_state / "unidic").exists()


def test_delete_pack_removes_directory(_isolate_state):
    unidic_dir = _isolate_state / "unidic"
    unidic_dir.mkdir(parents=True)
    (unidic_dir / "sys.dic").write_bytes(b"data")

    packs.delete_pack("japanese")

    assert not unidic_dir.exists()


def test_list_packs_reports_installed(_isolate_state):
    unidic_dir = _isolate_state / "unidic"
    unidic_dir.mkdir(parents=True)
    (unidic_dir / "sys.dic").write_bytes(b"data")

    entries = {p["name"]: p for p in packs.list_packs()}
    assert entries["japanese"]["installed"] is True


def test_get_status_reports_not_installed_when_nothing_on_disk():
    assert packs.get_status("japanese")["state"] == "not_installed"


def test_backfill_furigana_recomputes_segments_and_is_idempotent(session, monkeypatch):
    monkeypatch.setattr("app.db.engine", session.get_bind())

    transcript = Transcript(episode_id=1, language="ja", source=TranscriptSource.asr)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    sentence = Sentence(
        transcript_id=transcript.id, index=0, start_time=0.0, end_time=1.0, text="東京",
        segments=[{"base": "東京", "reading": ""}],
    )
    session.add(sentence)
    session.commit()
    session.refresh(sentence)

    calls = []

    def fake_build_segments(text, language):
        calls.append((text, language))
        return [{"base": text, "reading": "とうきょう"}]

    monkeypatch.setattr("app.services.furigana.build_segments", fake_build_segments)

    packs._backfill_furigana()

    session.refresh(sentence)
    assert sentence.segments == [{"base": "東京", "reading": "とうきょう"}]
    assert calls == [("東京", "ja")]

    packs._backfill_furigana()  # idempotent: same result, no error
    session.refresh(sentence)
    assert sentence.segments == [{"base": "東京", "reading": "とうきょう"}]
