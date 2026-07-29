from app.models import Episode, Podcast, PodcastKind
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
