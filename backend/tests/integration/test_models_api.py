import pytest

from app.services import whisper_models


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    models_dir = tmp_path / "models"
    monkeypatch.setattr("app.services.whisper_models.paths.models_dir", lambda: models_dir)
    monkeypatch.setattr("app.services.whisper_models._ACTIVE_MODEL_STATE_PATH", tmp_path / "active_whisper_model")
    monkeypatch.setattr("app.api.models.whisper_models.download_model", lambda name: None)
    whisper_models._progress.clear()
    yield models_dir
    whisper_models._progress.clear()


def test_list_models_shape(client, _isolate_state):
    response = client.get("/api/models")
    assert response.status_code == 200
    body = response.json()
    names = [m["name"] for m in body]
    assert names == ["tiny", "base", "small"]
    for entry in body:
        assert set(entry.keys()) == {"name", "size_bytes", "installed", "active"}
        assert entry["installed"] is False
    assert next(m for m in body if m["name"] == "base")["active"] is True


def test_unknown_model_name_404s(client, _isolate_state):
    assert client.post("/api/models/huge").status_code == 404
    assert client.get("/api/models/huge/status").status_code == 404
    assert client.delete("/api/models/huge").status_code == 404


def test_post_already_installed_model_marks_active_without_downloading(client, monkeypatch, _isolate_state):
    _isolate_state.mkdir(parents=True, exist_ok=True)
    (_isolate_state / "ggml-tiny.bin").write_bytes(b"data")

    called = False

    def fail_if_called(name):
        nonlocal called
        called = True

    monkeypatch.setattr("app.api.models.whisper_models.download_model", fail_if_called)

    response = client.post("/api/models/tiny")
    assert response.status_code == 202
    body = response.json()
    assert body["installed"] is True
    assert body["active"] is True
    assert not called
    assert whisper_models._active_model_name() == "tiny"


def test_post_not_installed_model_kicks_off_download(client, monkeypatch, _isolate_state):
    calls = []
    monkeypatch.setattr("app.api.models.whisper_models.download_model", lambda name: calls.append(name))

    response = client.post("/api/models/tiny")
    assert response.status_code == 202
    assert calls == ["tiny"]


def test_get_status_not_installed(client, _isolate_state):
    response = client.get("/api/models/tiny/status")
    assert response.status_code == 200
    assert response.json()["state"] == "not_installed"


def test_delete_model(client, _isolate_state):
    _isolate_state.mkdir(parents=True, exist_ok=True)
    model_path = _isolate_state / "ggml-tiny.bin"
    model_path.write_bytes(b"data")

    response = client.delete("/api/models/tiny")
    assert response.status_code == 204
    assert not model_path.exists()
