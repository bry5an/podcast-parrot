import httpx

from app.models import DownloadStatus, Episode, Podcast, PodcastKind, TranscriptStatus
from app.services import youtube
from app.services.downloads import download_episode_audio, retry_transcription


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
        guid="guid-episode",
        title="Episode",
        audio_url="https://example.com/audio.mp3",
    )
    defaults.update(overrides)
    episode = Episode(**defaults)
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


class _FakeResponse:
    def __init__(self, chunks, url, content_type, error=None):
        self._chunks = chunks
        self.url = url
        self.headers = {"content-type": content_type}
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def iter_bytes(self):
        yield from self._chunks


class _FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc_info):
        return False


def _patch_common(monkeypatch, session, tmp_path):
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())
    monkeypatch.setattr("app.services.downloads.STORAGE_DIR", tmp_path)
    monkeypatch.setattr("app.services.downloads.ingest_transcript", lambda *args, **kwargs: None)


def test_download_writes_part_file_then_renames_to_final_path(session, monkeypatch, tmp_path):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    _patch_common(monkeypatch, session, tmp_path)

    def fake_stream(method, url, **kwargs):
        response = _FakeResponse(
            [b"chunk-1", b"chunk-2"], url="https://example.com/audio.mp3", content_type="audio/mpeg"
        )
        return _FakeStream(response)

    monkeypatch.setattr("app.services.downloads.httpx.stream", fake_stream)

    download_episode_audio(episode.id)

    part_path = tmp_path / f"{episode.id}.part"
    final_path = tmp_path / f"{episode.id}.mp3"
    assert not part_path.exists()
    assert final_path.exists()
    assert final_path.read_bytes() == b"chunk-1chunk-2"

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.downloaded
    assert episode.local_audio_path == f"{episode.id}.mp3"


def test_download_failure_cleans_up_part_file_and_marks_failed(session, monkeypatch, tmp_path):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    _patch_common(monkeypatch, session, tmp_path)

    def failing_stream(method, url, **kwargs):
        response = _FakeResponse(
            [b"partial-chunk"],
            url="https://example.com/audio.mp3",
            content_type="audio/mpeg",
            error=httpx.HTTPStatusError("boom", request=None, response=None),
        )
        return _FakeStream(response)

    monkeypatch.setattr("app.services.downloads.httpx.stream", failing_stream)

    download_episode_audio(episode.id)

    part_path = tmp_path / f"{episode.id}.part"
    assert not part_path.exists()
    assert list(tmp_path.iterdir()) == []

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.failed
    assert episode.local_audio_path is None


def test_download_youtube_episode_uses_youtube_download_audio(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session,
        rss_url=None,
        youtube_playlist_url="https://www.youtube.com/playlist?list=abc",
        kind=PodcastKind.youtube,
    )
    episode = _make_episode(session, podcast, audio_url="https://www.youtube.com/watch?v=abc123")
    _patch_common(monkeypatch, session, tmp_path)

    calls = []

    def fake_download_audio(video_url, dest_dir, episode_id):
        calls.append((video_url, dest_dir, episode_id))
        target = dest_dir / f"{episode_id}.m4a"
        target.write_bytes(b"audio-bytes")
        return target

    monkeypatch.setattr("app.services.downloads.youtube.download_audio", fake_download_audio)

    download_episode_audio(episode.id)

    assert calls == [(episode.audio_url, tmp_path, episode.id)]
    session.refresh(episode)
    assert episode.download_status == DownloadStatus.downloaded
    assert episode.local_audio_path == f"{episode.id}.m4a"


def test_download_youtube_episode_marks_failed_on_download_error(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session,
        rss_url=None,
        youtube_playlist_url="https://www.youtube.com/playlist?list=abc",
        kind=PodcastKind.youtube,
    )
    episode = _make_episode(session, podcast, audio_url="https://www.youtube.com/watch?v=abc123")
    _patch_common(monkeypatch, session, tmp_path)

    def failing_download_audio(video_url, dest_dir, episode_id):
        raise youtube.YoutubeDownloadError("boom")

    monkeypatch.setattr("app.services.downloads.youtube.download_audio", failing_download_audio)

    download_episode_audio(episode.id)

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.failed
    assert episode.local_audio_path is None


def test_retry_transcription_calls_ingest_transcript(session, monkeypatch, tmp_path):
    podcast = _make_podcast(session)
    episode = _make_episode(
        session, podcast, local_audio_path="1.mp3", transcript_status=TranscriptStatus.queued
    )
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())
    monkeypatch.setattr("app.services.downloads.STORAGE_DIR", tmp_path)

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(episode.id)

    assert calls == [(episode.id, tmp_path / "1.mp3")]


def test_retry_transcription_noop_without_local_audio(session, monkeypatch, tmp_path):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, local_audio_path=None)
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())
    monkeypatch.setattr("app.services.downloads.STORAGE_DIR", tmp_path)

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(episode.id)

    assert calls == []


def test_retry_transcription_noop_for_missing_episode(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())
    monkeypatch.setattr("app.services.downloads.STORAGE_DIR", tmp_path)

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(999)

    assert calls == []
