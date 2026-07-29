def test_health_is_always_reachable_without_a_token(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ok_with_no_token_configured(client):
    response = client.get("/api/health")
    assert response.status_code == 200


def test_api_requests_pass_through_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.delenv("KOTOBA_AUTH_TOKEN", raising=False)
    response = client.get("/api/profiles")
    assert response.status_code == 200


def test_api_requests_rejected_without_the_configured_token(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/profiles")
    assert response.status_code == 401


def test_api_requests_rejected_with_the_wrong_token(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/profiles", headers={"x-kotoba-token": "wrong"})
    assert response.status_code == 401


def test_api_requests_accepted_with_the_correct_token(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/profiles", headers={"x-kotoba-token": "secret"})
    assert response.status_code == 200


def test_index_route_injects_the_configured_token(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/")
    assert response.status_code == 200
    assert "window.KOTOBA_AUTH_TOKEN = \"secret\";" in response.text


def test_index_route_injects_empty_token_when_unset(client, monkeypatch):
    monkeypatch.delenv("KOTOBA_AUTH_TOKEN", raising=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "window.KOTOBA_AUTH_TOKEN = \"\";" in response.text


def test_audio_route_accepts_correct_token_as_query_param(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/episodes/9/audio?token=secret")
    assert response.status_code != 401


def test_audio_route_rejects_wrong_token_as_query_param(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/episodes/9/audio?token=wrong")
    assert response.status_code == 401


def test_query_param_token_does_not_authorize_other_routes(client, monkeypatch):
    monkeypatch.setenv("KOTOBA_AUTH_TOKEN", "secret")
    response = client.get("/api/profiles?token=secret")
    assert response.status_code == 401
