import pytest

from app.models import DownloadStatus, Episode, Podcast, TranscriptStatus
from app.services import packs, whisper_models


@pytest.fixture(autouse=True)
def _isolate_progress_state():
    whisper_models._progress.clear()
    packs._progress.clear()
    yield
    whisper_models._progress.clear()
    packs._progress.clear()


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(rss_url="https://example.com/feed.xml", title="Nihongo News", language="ja")
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def test_activity_inactive_by_default(client):
    response = client.get("/api/activity")
    assert response.status_code == 200
    assert response.json() == {"active": False}


def test_activity_active_when_episode_downloading(client, session):
    podcast = _make_podcast(session)
    session.add(Episode(podcast_id=podcast.id, guid="a", title="A", audio_url="https://example.com/a.mp3",
                         download_status=DownloadStatus.downloading))
    session.commit()

    response = client.get("/api/activity")
    assert response.json() == {"active": True}


def test_activity_active_when_transcript_pending(session, client):
    podcast = _make_podcast(session)
    session.add(Episode(podcast_id=podcast.id, guid="a", title="A", audio_url="https://example.com/a.mp3",
                         transcript_status=TranscriptStatus.pending))
    session.commit()

    response = client.get("/api/activity")
    assert response.json() == {"active": True}


def test_activity_active_when_model_downloading(client):
    name = next(iter(whisper_models.CATALOG))
    whisper_models._progress[name] = whisper_models._Progress(state="downloading", bytes_total=100)

    response = client.get("/api/activity")
    assert response.json() == {"active": True}


def test_activity_active_when_pack_downloading(client):
    name = next(iter(packs.CATALOG))
    packs._progress[name] = packs._Progress(state="downloading", bytes_total=100)

    response = client.get("/api/activity")
    assert response.json() == {"active": True}


def test_activity_inactive_once_download_completes(client, session):
    podcast = _make_podcast(session)
    session.add(Episode(podcast_id=podcast.id, guid="a", title="A", audio_url="https://example.com/a.mp3",
                         download_status=DownloadStatus.downloaded))
    session.commit()

    response = client.get("/api/activity")
    assert response.json() == {"active": False}
