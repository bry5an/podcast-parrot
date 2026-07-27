from datetime import datetime

from app.models import (
    DownloadStatus,
    Episode,
    Podcast,
    Sentence,
    Transcript,
    TranscriptSource,
    TranscriptStatus,
)


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(
        rss_url="https://example.com/feed.xml",
        title="Nihongo News",
        language="ja",
        # Recent last_polled_at keeps sync_episodes() inside its poll
        # window, so list_episodes doesn't attempt a real RSS fetch.
        last_polled_at=datetime.utcnow(),
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


def test_list_episodes(client, session):
    podcast = _make_podcast(session)
    _make_episode(
        session,
        podcast,
        guid="old",
        title="Old episode",
        pub_date=datetime(2024, 1, 1),
        download_status=DownloadStatus.idle,
    )
    _make_episode(
        session,
        podcast,
        guid="new",
        title="New episode",
        pub_date=datetime(2024, 6, 1),
        download_status=DownloadStatus.downloaded,
    )

    response = client.get(f"/api/podcasts/{podcast.id}/episodes")
    assert response.status_code == 200
    titles = [e["title"] for e in response.json()]
    assert titles == ["New episode", "Old episode"]  # newest first by default

    response = client.get(f"/api/podcasts/{podcast.id}/episodes", params={"sort": "oldest"})
    assert [e["title"] for e in response.json()] == ["Old episode", "New episode"]

    response = client.get(f"/api/podcasts/{podcast.id}/episodes", params={"filter": "downloaded"})
    assert [e["title"] for e in response.json()] == ["New episode"]


def test_list_episodes_missing_podcast_returns_404(client):
    response = client.get("/api/podcasts/999/episodes")
    assert response.status_code == 404


def test_list_episodes_invalid_filter_returns_422(client, session):
    podcast = _make_podcast(session)
    response = client.get(f"/api/podcasts/{podcast.id}/episodes", params={"filter": "bogus"})
    assert response.status_code == 422


def test_list_episodes_invalid_sort_returns_422(client, session):
    podcast = _make_podcast(session)
    response = client.get(f"/api/podcasts/{podcast.id}/episodes", params={"sort": "bogus"})
    assert response.status_code == 422


def test_start_download(client, session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, download_status=DownloadStatus.idle)

    calls = []
    monkeypatch.setattr("app.api.episodes.download_episode_audio", lambda episode_id: calls.append(episode_id))

    response = client.post(f"/api/episodes/{episode.id}/download")
    assert response.status_code == 202
    assert response.json()["download_status"] == "downloading"
    assert calls == [episode.id]


def test_start_download_missing_episode_returns_404(client):
    response = client.post("/api/episodes/999/download")
    assert response.status_code == 404


def test_delete_download(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.episodes.STORAGE_DIR", tmp_path)
    podcast = _make_podcast(session)
    audio_file = tmp_path / "1.mp3"
    audio_file.write_bytes(b"fake audio")
    episode = _make_episode(
        session,
        podcast,
        local_audio_path="1.mp3",
        download_status=DownloadStatus.downloaded,
    )

    response = client.delete(f"/api/episodes/{episode.id}/download")
    assert response.status_code == 204
    assert not audio_file.exists()

    status = client.get(f"/api/episodes/{episode.id}/status").json()
    assert status["download_status"] == "idle"


def test_delete_download_missing_episode_returns_404(client):
    response = client.delete("/api/episodes/999/download")
    assert response.status_code == 404


def test_get_status(client, session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, download_status=DownloadStatus.downloaded)

    response = client.get(f"/api/episodes/{episode.id}/status")
    assert response.status_code == 200
    assert response.json() == {
        "id": episode.id,
        "download_status": "downloaded",
        "transcript_status": "none",
    }


def test_get_status_missing_episode_returns_404(client):
    response = client.get("/api/episodes/999/status")
    assert response.status_code == 404


def test_get_transcript(client, session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.full)
    transcript = Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.published)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    session.add(
        Sentence(
            transcript_id=transcript.id,
            index=0,
            start_time=0.0,
            end_time=1.0,
            text="こんにちは",
            segments=[{"base": "こんにちは", "reading": ""}],
        )
    )
    session.commit()

    response = client.get(f"/api/episodes/{episode.id}/transcript")
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "ja"
    assert len(body["sentences"]) == 1
    assert body["sentences"][0]["text"] == "こんにちは"


def test_get_transcript_missing_episode_returns_404(client):
    response = client.get("/api/episodes/999/transcript")
    assert response.status_code == 404


def test_get_transcript_unavailable_returns_404(client, session):
    podcast = _make_podcast(session)
    # No transcript_source_url and no pre-built Transcript row means
    # get_or_build_transcript() has nothing to fetch or return.
    episode = _make_episode(session, podcast, transcript_source_url=None)

    response = client.get(f"/api/episodes/{episode.id}/transcript")
    assert response.status_code == 404
