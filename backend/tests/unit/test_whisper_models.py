import hashlib

import httpx
import pytest

from app.models import Episode, Podcast, TranscriptStatus
from app.services import whisper_models
from app.services.whisper_models import ModelSpec


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    models_dir = tmp_path / "models"
    monkeypatch.setattr("app.services.whisper_models.paths.models_dir", lambda: models_dir)
    monkeypatch.setattr("app.services.whisper_models._ACTIVE_MODEL_STATE_PATH", tmp_path / "active_whisper_model")
    whisper_models._progress.clear()
    yield models_dir
    whisper_models._progress.clear()


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


def _single_model_catalog(payload: bytes) -> dict[str, ModelSpec]:
    spec = ModelSpec(
        name="tiny",
        filename="ggml-tiny.bin",
        url="https://example.com/ggml-tiny.bin",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    return {"tiny": spec}


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(rss_url="https://example.com/feed.xml", title="Nihongo News", language="ja")
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def _make_episode(session, podcast: Podcast, **overrides) -> Episode:
    defaults = dict(
        podcast_id=podcast.id,
        guid=f"guid-{overrides.get('title', 'episode')}",
        title="Episode",
        audio_url="https://example.com/audio.mp3",
    )
    defaults.update(overrides)
    episode = Episode(**defaults)
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


def test_download_model_success_verifies_checksum_and_renames(monkeypatch, _isolate_state):
    payload = b"fake ggml model bytes"
    catalog = _single_model_catalog(payload)
    monkeypatch.setattr("app.services.whisper_models.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.whisper_models.httpx.stream",
        lambda *a, **k: _FakeStream(_FakeResponse([payload])),
    )
    monkeypatch.setattr("app.services.whisper_models._retry_queued_transcriptions", lambda: None)

    whisper_models.download_model("tiny")

    final_path = _isolate_state / "ggml-tiny.bin"
    assert final_path.read_bytes() == payload
    assert not (_isolate_state / "ggml-tiny.bin.part").exists()

    status = whisper_models.get_status("tiny")
    assert status == {"state": "installed", "bytes_done": len(payload), "bytes_total": len(payload), "error": None}
    assert whisper_models._active_model_name() == "tiny"


def test_download_model_checksum_mismatch_leaves_no_final_file(monkeypatch, _isolate_state):
    payload = b"fake ggml model bytes"
    catalog = _single_model_catalog(payload)
    catalog["tiny"] = ModelSpec(
        name="tiny", filename="ggml-tiny.bin", url="https://example.com/ggml-tiny.bin",
        size_bytes=len(payload), sha256="0" * 64,
    )
    monkeypatch.setattr("app.services.whisper_models.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.whisper_models.httpx.stream",
        lambda *a, **k: _FakeStream(_FakeResponse([payload])),
    )

    whisper_models.download_model("tiny")

    assert not (_isolate_state / "ggml-tiny.bin").exists()
    assert not (_isolate_state / "ggml-tiny.bin.part").exists()
    status = whisper_models.get_status("tiny")
    assert status["state"] == "failed"
    assert status["error"] == "checksum"


def test_download_model_disk_space_precheck_fails_before_network_call(monkeypatch, _isolate_state):
    payload = b"x" * 100
    catalog = _single_model_catalog(payload)
    monkeypatch.setattr("app.services.whisper_models.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.whisper_models.shutil.disk_usage", lambda path: type("_", (), {"free": 0})()
    )

    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("should not have opened a connection")

    monkeypatch.setattr("app.services.whisper_models.httpx.stream", fail_if_called)

    whisper_models.download_model("tiny")

    assert not called
    status = whisper_models.get_status("tiny")
    assert status == {"state": "failed", "bytes_done": 0, "bytes_total": len(payload), "error": "disk_space"}


def test_download_model_offline_when_zero_bytes_received(monkeypatch, _isolate_state):
    payload = b"x" * 100
    catalog = _single_model_catalog(payload)
    monkeypatch.setattr("app.services.whisper_models.CATALOG", catalog)

    def raise_connect_error(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr("app.services.whisper_models.httpx.stream", raise_connect_error)

    whisper_models.download_model("tiny")

    status = whisper_models.get_status("tiny")
    assert status["state"] == "failed"
    assert status["error"] == "offline"


def test_download_model_network_loss_after_partial_bytes(monkeypatch, _isolate_state):
    payload = b"x" * 100
    catalog = _single_model_catalog(payload)
    monkeypatch.setattr("app.services.whisper_models.CATALOG", catalog)
    monkeypatch.setattr(
        "app.services.whisper_models.httpx.stream",
        lambda *a, **k: _FakeStream(
            _FakeResponse([payload[:10]], stream_error=httpx.ReadError("connection dropped"))
        ),
    )

    whisper_models.download_model("tiny")

    assert not (_isolate_state / "ggml-tiny.bin.part").exists()
    status = whisper_models.get_status("tiny")
    assert status["state"] == "failed"
    assert status["error"] == "network"
    assert status["bytes_done"] == 10


def test_active_model_defaults_to_base():
    assert whisper_models._active_model_name() == "base"
    assert whisper_models.active_model_path().name == "ggml-base.bin"


def test_set_active_model_persists(_isolate_state):
    whisper_models.set_active_model("small")
    assert whisper_models._active_model_name() == "small"
    assert whisper_models.active_model_path().name == "ggml-small.bin"


def test_delete_model_clears_active_state_only_if_it_was_active(_isolate_state):
    _isolate_state.mkdir(parents=True, exist_ok=True)
    (_isolate_state / "ggml-tiny.bin").write_bytes(b"data")
    (_isolate_state / "ggml-base.bin").write_bytes(b"data")
    whisper_models.set_active_model("tiny")

    whisper_models.delete_model("base")
    assert whisper_models._active_model_name() == "tiny"  # untouched, base wasn't active

    whisper_models.delete_model("tiny")
    assert whisper_models._active_model_name() == "base"  # falls back to default
    assert not (_isolate_state / "ggml-tiny.bin").exists()


def test_list_models_reports_installed_and_active_flags(_isolate_state):
    _isolate_state.mkdir(parents=True, exist_ok=True)
    (_isolate_state / "ggml-tiny.bin").write_bytes(b"data")
    whisper_models.set_active_model("tiny")

    models = {m["name"]: m for m in whisper_models.list_models()}
    assert models["tiny"]["installed"] is True
    assert models["tiny"]["active"] is True
    assert models["base"]["installed"] is False
    assert models["base"]["active"] is False


def test_get_status_reports_installed_without_progress_entry(_isolate_state):
    _isolate_state.mkdir(parents=True, exist_ok=True)
    (_isolate_state / "ggml-base.bin").write_bytes(b"data")

    status = whisper_models.get_status("base")
    assert status["state"] == "installed"


def test_get_status_reports_not_installed_when_nothing_on_disk():
    status = whisper_models.get_status("base")
    assert status["state"] == "not_installed"


def test_retry_queued_transcriptions_reruns_ingest_transcript(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.whisper_models.engine", session.get_bind())
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    podcast = _make_podcast(session)
    queued_episode = _make_episode(
        session,
        podcast,
        guid="queued",
        transcript_status=TranscriptStatus.queued,
        local_audio_path="1.mp3",
    )
    _make_episode(
        session,
        podcast,
        guid="untouched",
        transcript_status=TranscriptStatus.none,
    )

    calls = []
    monkeypatch.setattr(
        "app.services.transcripts.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    whisper_models._retry_queued_transcriptions()

    assert calls == [(queued_episode.id, tmp_path / "1.mp3")]
