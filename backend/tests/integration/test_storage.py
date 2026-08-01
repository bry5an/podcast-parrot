import json

from app.models import DownloadStatus, Episode, Podcast, Sentence, Transcript, TranscriptSource


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


def test_storage_stats_reflect_real_files_on_disk(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
    podcast = _make_podcast(session)
    _make_episode(session, podcast, guid="a", local_audio_path="1.mp3", download_status=DownloadStatus.downloaded)
    _make_episode(session, podcast, guid="b", download_status=DownloadStatus.idle)
    (tmp_path / "1.mp3").write_bytes(b"x" * 1000)
    (tmp_path / "stray.part").write_bytes(b"y" * 250)

    response = client.get("/api/storage")

    assert response.status_code == 200
    body = response.json()
    assert body["bytes_used"] == 1250
    assert body["episode_count"] == 1
    assert body["storage_root"] == str(tmp_path)
    assert body["transcript_bytes"] == 0


def test_storage_stats_handles_missing_directory(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path / "does-not-exist")

    response = client.get("/api/storage")

    assert response.status_code == 200
    assert response.json()["bytes_used"] == 0


def test_storage_stats_sums_transcript_row_bytes(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    transcript = Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.asr)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)
    sentence = Sentence(
        transcript_id=transcript.id,
        index=0,
        start_time=0.0,
        end_time=1.0,
        text="こんにちは",
        segments=[{"base": "こんにちは", "reading": "こんにちは"}],
    )
    session.add(sentence)
    session.commit()

    response = client.get("/api/storage")

    assert response.status_code == 200
    expected = len("こんにちは".encode()) + len(
        json.dumps([{"base": "こんにちは", "reading": "こんにちは"}]).encode()
    )
    assert response.json()["transcript_bytes"] == expected
