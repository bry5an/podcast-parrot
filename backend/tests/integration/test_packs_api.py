import pytest

from app.services import packs


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    packs_root = tmp_path / "packs"
    monkeypatch.setattr("app.services.packs.paths.packs_dir", lambda: packs_root)
    monkeypatch.setattr("app.api.packs.packs.install_pack", lambda name: None)
    packs._progress.clear()
    yield packs_root
    packs._progress.clear()


def test_list_packs_shape(client, _isolate_state):
    response = client.get("/api/packs")
    assert response.status_code == 200
    body = response.json()
    assert [p["name"] for p in body] == ["japanese"]
    entry = body[0]
    assert set(entry.keys()) == {"name", "download_size_bytes", "installed"}
    assert entry["installed"] is False


def test_unknown_pack_name_404s(client, _isolate_state):
    assert client.post("/api/packs/klingon").status_code == 404
    assert client.get("/api/packs/klingon/status").status_code == 404
    assert client.delete("/api/packs/klingon").status_code == 404


def test_post_not_installed_pack_kicks_off_install(client, monkeypatch, _isolate_state):
    calls = []
    monkeypatch.setattr("app.api.packs.packs.install_pack", lambda name: calls.append(name))

    response = client.post("/api/packs/japanese")
    assert response.status_code == 202
    assert calls == ["japanese"]


def test_post_already_installed_pack_does_not_reinstall(client, monkeypatch, _isolate_state):
    unidic_dir = _isolate_state / "unidic"
    unidic_dir.mkdir(parents=True)
    (unidic_dir / "sys.dic").write_bytes(b"data")

    called = False

    def fail_if_called(name):
        nonlocal called
        called = True

    monkeypatch.setattr("app.api.packs.packs.install_pack", fail_if_called)

    response = client.post("/api/packs/japanese")
    assert response.status_code == 202
    assert response.json()["installed"] is True
    assert not called


def test_get_status_not_installed(client, _isolate_state):
    response = client.get("/api/packs/japanese/status")
    assert response.status_code == 200
    assert response.json()["state"] == "not_installed"


def test_delete_pack(client, _isolate_state):
    unidic_dir = _isolate_state / "unidic"
    unidic_dir.mkdir(parents=True)
    (unidic_dir / "sys.dic").write_bytes(b"data")

    response = client.delete("/api/packs/japanese")
    assert response.status_code == 204
    assert not unidic_dir.exists()
