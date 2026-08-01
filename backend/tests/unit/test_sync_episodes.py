from sqlmodel import select

from app.models import Episode, Podcast, PodcastKind, TranscriptStatus
from app.services.episodes import sync_episodes


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(rss_url="https://example.com/feed.xml", title="Nihongo News", language="ja")
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def test_sync_episodes_uses_rss_fetch_for_rss_podcast(session, monkeypatch):
    podcast = _make_podcast(session)

    calls = []
    monkeypatch.setattr("app.services.episodes.fetch_episodes", lambda url: calls.append(url) or [])
    monkeypatch.setattr(
        "app.services.episodes.fetch_playlist_episodes",
        lambda url: (_ for _ in ()).throw(AssertionError("should not be called for an RSS podcast")),
    )

    sync_episodes(session, podcast)

    assert calls == ["https://example.com/feed.xml"]


def test_sync_episodes_uses_youtube_fetch_for_youtube_podcast(session, monkeypatch):
    podcast = _make_podcast(
        session,
        rss_url=None,
        youtube_playlist_url="https://www.youtube.com/playlist?list=abc",
        kind=PodcastKind.youtube,
    )

    calls = []
    monkeypatch.setattr(
        "app.services.episodes.fetch_episodes",
        lambda url: (_ for _ in ()).throw(AssertionError("should not be called for a YouTube podcast")),
    )
    monkeypatch.setattr("app.services.episodes.fetch_playlist_episodes", lambda url: calls.append(url) or [])

    sync_episodes(session, podcast)

    assert calls == ["https://www.youtube.com/playlist?list=abc"]


def test_sync_episodes_upserts_youtube_entries_as_episodes(session, monkeypatch):
    podcast = _make_podcast(
        session,
        rss_url=None,
        youtube_playlist_url="https://www.youtube.com/playlist?list=abc",
        kind=PodcastKind.youtube,
    )

    monkeypatch.setattr(
        "app.services.episodes.fetch_playlist_episodes",
        lambda url: [
            {
                "guid": "abc123",
                "title": "Episode One",
                "pub_date": None,
                "duration_seconds": 120,
                "audio_url": "https://www.youtube.com/watch?v=abc123",
                "transcript_source_url": None,
                "transcript_source_type": None,
                "transcript_source_language": None,
                "transcript_source_format": None,
            }
        ],
    )

    sync_episodes(session, podcast)

    from sqlmodel import select

    episode = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).one()
    assert episode.guid == "abc123"
    assert episode.title == "Episode One"
    assert episode.audio_url == "https://www.youtube.com/watch?v=abc123"
    assert episode.duration_seconds == 120


def test_sync_episodes_uses_local_directory_scan_for_local_podcast(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session,
        rss_url=None,
        local_directory_path=str(tmp_path),
        kind=PodcastKind.local_directory,
    )

    calls = []
    monkeypatch.setattr(
        "app.services.episodes.fetch_episodes",
        lambda url: (_ for _ in ()).throw(AssertionError("should not be called for a local-directory podcast")),
    )
    monkeypatch.setattr(
        "app.services.episodes.scan_local_directory_episodes", lambda path: calls.append(path) or []
    )

    sync_episodes(session, podcast)

    assert calls == [tmp_path]


def test_sync_episodes_upserts_local_directory_entries_as_episodes(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session,
        rss_url=None,
        local_directory_path=str(tmp_path),
        kind=PodcastKind.local_directory,
    )

    monkeypatch.setattr(
        "app.services.episodes.scan_local_directory_episodes",
        lambda path: [
            {
                "guid": "episode1.mp3",
                "title": "episode1",
                "pub_date": None,
                "duration_seconds": None,
                "audio_url": str(tmp_path / "episode1.mp3"),
                "transcript_source_url": str(tmp_path / "episode1.srt"),
                "transcript_source_type": "srt",
                "transcript_source_language": None,
                "transcript_source_format": "srt",
            }
        ],
    )

    sync_episodes(session, podcast)

    episode = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).one()
    assert episode.guid == "episode1.mp3"
    assert episode.audio_url == str(tmp_path / "episode1.mp3")
    assert episode.transcript_source_url == str(tmp_path / "episode1.srt")
    assert episode.transcript_status == TranscriptStatus.pending
