def test_get_settings_creates_default_row(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["auto_remove"] == "never"
    assert body["storage_root"] == str(tmp_path)
    assert body["compute_device"] == "gpu"
    assert body["cache_transcripts"] is True


def test_patch_settings_persists_compute_device_and_cache_transcripts(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    response = client.patch("/api/settings", json={"compute_device": "cpu", "cache_transcripts": False})
    assert response.status_code == 200
    body = response.json()
    assert body["compute_device"] == "cpu"
    assert body["cache_transcripts"] is False

    response = client.get("/api/settings")
    body = response.json()
    assert body["compute_device"] == "cpu"
    assert body["cache_transcripts"] is False


def test_patch_settings_persists_auto_remove(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    response = client.patch("/api/settings", json={"auto_remove": "30d"})
    assert response.status_code == 200
    assert response.json()["auto_remove"] == "30d"

    response = client.get("/api/settings")
    assert response.json()["auto_remove"] == "30d"


def test_patch_settings_relocates_storage(client, monkeypatch, tmp_path):
    # No storage_dir()/storage_location_file() override here — relocation
    # exercises the real marker-file logic in paths.py, just rooted at a
    # scratch data_dir() instead of the real Application Support path.
    monkeypatch.setattr("app.paths.data_dir", lambda: tmp_path)
    old_root = tmp_path / "storage"
    old_root.mkdir()
    (old_root / "1.mp3").write_bytes(b"audio")
    new_root = tmp_path / "new"

    response = client.patch("/api/settings", json={"storage_root": str(new_root)})

    assert response.status_code == 200
    assert response.json()["storage_root"] == str(new_root)
    assert (new_root / "1.mp3").exists()
    assert not (old_root / "1.mp3").exists()
    assert (tmp_path / "storage_location.json").is_file()


def test_patch_settings_rejects_non_empty_target(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.data_dir", lambda: tmp_path)
    old_root = tmp_path / "storage"
    old_root.mkdir()
    new_root = tmp_path / "new"
    new_root.mkdir()
    (new_root / "existing.txt").write_bytes(b"nope")

    response = client.patch("/api/settings", json={"storage_root": str(new_root)})

    assert response.status_code == 400
