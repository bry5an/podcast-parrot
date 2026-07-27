def test_create_profile(client):
    response = client.post("/api/profiles", json={"name": "Kenji"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Kenji"
    assert body["direction"] == "en_ja"
    assert body["show_furigana"] is True
    assert body["id"] is not None


def test_create_profile_rejects_blank_name(client):
    response = client.post("/api/profiles", json={"name": "   "})
    assert response.status_code == 422


def test_list_profiles(client):
    client.post("/api/profiles", json={"name": "Kenji"})
    client.post("/api/profiles", json={"name": "Aoi"})

    response = client.get("/api/profiles")
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"Kenji", "Aoi"}


def test_get_profile(client):
    created = client.post("/api/profiles", json={"name": "Kenji"}).json()

    response = client.get(f"/api/profiles/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Kenji"


def test_get_profile_missing_returns_404(client):
    response = client.get("/api/profiles/999")
    assert response.status_code == 404


def test_update_profile_partial(client):
    created = client.post("/api/profiles", json={"name": "Kenji", "show_furigana": True}).json()

    response = client.patch(f"/api/profiles/{created['id']}", json={"show_furigana": False})
    assert response.status_code == 200
    body = response.json()
    assert body["show_furigana"] is False
    assert body["name"] == "Kenji"  # untouched fields survive a partial update


def test_update_profile_missing_returns_404(client):
    response = client.patch("/api/profiles/999", json={"name": "Nope"})
    assert response.status_code == 404


def test_delete_profile(client):
    created = client.post("/api/profiles", json={"name": "Kenji"}).json()

    response = client.delete(f"/api/profiles/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404


def test_delete_profile_missing_returns_404(client):
    response = client.delete("/api/profiles/999")
    assert response.status_code == 404
