from sqlmodel import select

from app.models import Episode, Podcast, PodcastSource, Sentence, Subscription, Transcript
from app.services.rss import FeedFetchError
from app.services.youtube import YoutubeFetchError


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(
        rss_url="https://example.com/feed.xml",
        title="Nihongo News",
        description="Daily Japanese news",
        language="ja",
        source=PodcastSource.curated,
    )
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def _make_episode(session, podcast: Podcast, **overrides) -> Episode:
    defaults = dict(
        podcast_id=podcast.id,
        guid="guid-1",
        title="Episode",
        audio_url="https://example.com/audio.mp3",
    )
    defaults.update(overrides)
    episode = Episode(**defaults)
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


def test_search_directory_lists_all(client, session):
    _make_podcast(session, rss_url="https://example.com/a.xml", title="Nihongo News", language="ja")
    _make_podcast(session, rss_url="https://example.com/b.xml", title="English Hour", language="en")

    response = client.get("/api/directory")
    assert response.status_code == 200
    titles = {p["title"] for p in response.json()}
    assert titles == {"Nihongo News", "English Hour"}


def test_search_directory_filters_by_language_and_query(client, session):
    _make_podcast(session, rss_url="https://example.com/a.xml", title="Nihongo News", language="ja")
    _make_podcast(session, rss_url="https://example.com/b.xml", title="English Hour", language="en")

    response = client.get("/api/directory", params={"language": "ja"})
    assert [p["title"] for p in response.json()] == ["Nihongo News"]

    response = client.get("/api/directory", params={"query": "english"})
    assert [p["title"] for p in response.json()] == ["English Hour"]


def test_search_directory_includes_locale_tag_and_is_searchable(client, session):
    _make_podcast(
        session,
        rss_url="https://example.com/es-spain.xml",
        title="Español Show",
        language="es",
        locale_tag="Spain",
    )
    _make_podcast(
        session,
        rss_url="https://example.com/es-latam.xml",
        title="Español Show Dos",
        language="es",
        locale_tag="Latin America",
    )

    response = client.get("/api/directory", params={"language": "es"})
    by_title = {p["title"]: p["locale_tag"] for p in response.json()}
    assert by_title == {"Español Show": "Spain", "Español Show Dos": "Latin America"}

    response = client.get("/api/directory", params={"query": "latin america"})
    assert [p["title"] for p in response.json()] == ["Español Show Dos"]


def test_search_directory_marks_subscribed_podcasts(client, session):
    podcast = _make_podcast(session)
    profile_resp = client.post("/api/profiles", json={"name": "Kenji"})
    profile_id = profile_resp.json()["id"]
    client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")

    response = client.get("/api/directory", params={"profile_id": profile_id})
    assert response.json()[0]["subscribed"] is True


def test_add_podcast_from_rss(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.directory.fetch_podcast_metadata",
        lambda url: {"title": "New Show", "description": "desc", "artwork_url": None, "language": "ja"},
    )

    response = client.post("/api/directory/rss", json={"rss_url": "https://example.com/new.xml"})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New Show"
    assert body["source"] == "user_added"


def test_add_podcast_from_rss_dedupes_existing_url(client, session, monkeypatch):
    _make_podcast(session, rss_url="https://example.com/existing.xml", title="Existing")

    def fail_if_called(url):
        raise AssertionError("fetch_podcast_metadata should not be called for an already-known URL")

    monkeypatch.setattr("app.api.directory.fetch_podcast_metadata", fail_if_called)

    response = client.post("/api/directory/rss", json={"rss_url": "https://example.com/existing.xml"})
    assert response.status_code == 200
    assert response.json()["title"] == "Existing"


def test_add_podcast_from_rss_invalid_feed_returns_422(client, monkeypatch):
    def raise_error(url):
        raise FeedFetchError("could not parse")

    monkeypatch.setattr("app.api.directory.fetch_podcast_metadata", raise_error)

    response = client.post("/api/directory/rss", json={"rss_url": "https://example.com/broken.xml"})
    assert response.status_code == 422


def test_add_podcast_from_youtube(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.directory.youtube.fetch_playlist_metadata",
        lambda url: {"title": "YT Show", "description": "desc", "artwork_url": None, "language": "ja"},
    )

    response = client.post(
        "/api/directory/youtube", json={"playlist_url": "https://www.youtube.com/playlist?list=abc"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "YT Show"
    assert body["kind"] == "youtube"
    assert body["youtube_playlist_url"] == "https://www.youtube.com/playlist?list=abc"
    assert body["rss_url"] is None
    assert body["source"] == "user_added"


def test_add_podcast_from_youtube_dedupes_existing_url(client, session, monkeypatch):
    _make_podcast(
        session,
        rss_url=None,
        youtube_playlist_url="https://www.youtube.com/playlist?list=existing",
        kind="youtube",
        title="Existing",
    )

    def fail_if_called(url):
        raise AssertionError("fetch_playlist_metadata should not be called for an already-known URL")

    monkeypatch.setattr("app.api.directory.youtube.fetch_playlist_metadata", fail_if_called)

    response = client.post(
        "/api/directory/youtube", json={"playlist_url": "https://www.youtube.com/playlist?list=existing"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Existing"


def test_add_podcast_from_youtube_invalid_playlist_returns_422(client, monkeypatch):
    def raise_error(url):
        raise YoutubeFetchError("could not read playlist")

    monkeypatch.setattr("app.api.directory.youtube.fetch_playlist_metadata", raise_error)

    response = client.post(
        "/api/directory/youtube", json={"playlist_url": "https://www.youtube.com/playlist?list=broken"}
    )
    assert response.status_code == 422


def test_add_podcast_from_local_directory(client, tmp_path):
    (tmp_path / "episode1.mp3").write_bytes(b"fake-audio")

    response = client.post("/api/directory/local", json={"directory_path": str(tmp_path)})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == tmp_path.name
    assert body["kind"] == "local_directory"
    assert body["local_directory_path"] == str(tmp_path)
    assert body["rss_url"] is None
    assert body["youtube_playlist_url"] is None
    assert body["source"] == "user_added"


def test_add_podcast_from_local_directory_dedupes_existing_path(client, session, tmp_path):
    (tmp_path / "episode1.mp3").write_bytes(b"fake-audio")
    _make_podcast(
        session,
        rss_url=None,
        local_directory_path=str(tmp_path),
        kind="local_directory",
        title="Existing Folder",
    )

    response = client.post("/api/directory/local", json={"directory_path": str(tmp_path)})
    assert response.status_code == 200
    assert response.json()["title"] == "Existing Folder"


def test_add_podcast_from_local_directory_missing_path_returns_422(client, tmp_path):
    response = client.post("/api/directory/local", json={"directory_path": str(tmp_path / "does-not-exist")})
    assert response.status_code == 422


def test_add_podcast_from_local_directory_empty_directory_returns_422(client, tmp_path):
    response = client.post("/api/directory/local", json={"directory_path": str(tmp_path)})
    assert response.status_code == 422


def test_list_subscriptions(client, session):
    podcast = _make_podcast(session)
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")

    response = client.get(f"/api/profiles/{profile_id}/podcasts")
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [podcast.id]


def test_list_subscriptions_missing_profile_returns_404(client):
    response = client.get("/api/profiles/999/podcasts")
    assert response.status_code == 404


def test_subscribe_is_idempotent(client, session):
    podcast = _make_podcast(session)
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]

    first = client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")
    second = client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")
    assert first.status_code == 204
    assert second.status_code == 204
    assert len(client.get(f"/api/profiles/{profile_id}/podcasts").json()) == 1


def test_subscribe_missing_profile_returns_404(client, session):
    podcast = _make_podcast(session)
    response = client.post(f"/api/profiles/999/podcasts/{podcast.id}")
    assert response.status_code == 404


def test_subscribe_missing_podcast_returns_404(client):
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    response = client.post(f"/api/profiles/{profile_id}/podcasts/999")
    assert response.status_code == 404


def test_unsubscribe(client, session):
    podcast = _make_podcast(session)
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")

    response = client.delete(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")
    assert response.status_code == 204
    assert client.get(f"/api/profiles/{profile_id}/podcasts").json() == []


def test_unsubscribe_missing_returns_404(client):
    response = client.delete("/api/profiles/999/podcasts/999")
    assert response.status_code == 404


def test_delete_feed(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
    podcast = _make_podcast(session)
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    client.post(f"/api/profiles/{profile_id}/podcasts/{podcast.id}")

    audio_file = tmp_path / "1.mp3"
    audio_file.write_bytes(b"fake audio")
    episode = _make_episode(session, podcast, local_audio_path="1.mp3")
    transcript = Transcript(episode_id=episode.id)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    sentence = Sentence(transcript_id=transcript.id, index=0, start_time=0, end_time=1, text="hello")
    session.add(sentence)
    session.commit()

    response = client.delete(f"/api/profiles/{profile_id}/podcasts/{podcast.id}/feed")
    assert response.status_code == 204

    assert not audio_file.exists()
    assert session.get(Podcast, podcast.id) is None
    assert session.get(Episode, episode.id) is None
    assert session.get(Transcript, transcript.id) is None
    assert session.get(Sentence, sentence.id) is None
    assert session.exec(select(Subscription).where(Subscription.podcast_id == podcast.id)).first() is None


def test_delete_feed_blocked_by_other_profile(client, session):
    podcast = _make_podcast(session)
    profile_a = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    profile_b = client.post("/api/profiles", json={"name": "Yuki"}).json()["id"]
    client.post(f"/api/profiles/{profile_a}/podcasts/{podcast.id}")
    client.post(f"/api/profiles/{profile_b}/podcasts/{podcast.id}")

    response = client.delete(f"/api/profiles/{profile_a}/podcasts/{podcast.id}/feed")
    assert response.status_code == 409
    assert session.get(Podcast, podcast.id) is not None


def test_delete_feed_missing_podcast_returns_404(client):
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]
    response = client.delete(f"/api/profiles/{profile_id}/podcasts/999/feed")
    assert response.status_code == 404


def test_delete_feed_missing_profile_returns_404(client, session):
    podcast = _make_podcast(session)
    response = client.delete(f"/api/profiles/999/podcasts/{podcast.id}/feed")
    assert response.status_code == 404
