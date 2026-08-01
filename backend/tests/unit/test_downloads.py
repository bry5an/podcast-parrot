import httpx
import pytest

from app.models import DownloadStatus, Episode, Podcast, PodcastKind, TranscriptStatus
from app.services import youtube
from app.services.downloads import (
    RelocateStorageError,
    download_episode_audio,
    relocate_storage,
    remove_audio,
    retry_transcription,
)


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
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
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
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

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
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(episode.id)

    assert calls == []


def test_retry_transcription_noop_for_missing_episode(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(999)

    assert calls == []


def test_download_local_directory_episode_links_without_copying(session, monkeypatch, tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    audio = source_dir / "episode1.mp3"
    audio.write_bytes(b"fake-audio")

    podcast = _make_podcast(
        session, rss_url=None, local_directory_path=str(source_dir), kind=PodcastKind.local_directory
    )
    episode = _make_episode(session, podcast, guid="episode1.mp3", audio_url=str(audio))
    storage_dir = tmp_path / "storage"
    _patch_common(monkeypatch, session, storage_dir)

    download_episode_audio(episode.id)

    assert not storage_dir.exists()
    session.refresh(episode)
    assert episode.download_status == DownloadStatus.downloaded
    assert episode.local_audio_path == str(audio)
    assert audio.exists()


def test_download_local_directory_episode_marks_failed_when_file_missing(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session, rss_url=None, local_directory_path=str(tmp_path), kind=PodcastKind.local_directory
    )
    episode = _make_episode(session, podcast, guid="gone.mp3", audio_url=str(tmp_path / "gone.mp3"))
    _patch_common(monkeypatch, session, tmp_path / "storage")

    download_episode_audio(episode.id)

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.failed
    assert episode.local_audio_path is None


def test_retry_transcription_resolves_absolute_path_for_local_directory(session, monkeypatch, tmp_path):
    podcast = _make_podcast(
        session, rss_url=None, local_directory_path=str(tmp_path), kind=PodcastKind.local_directory
    )
    audio = tmp_path / "episode1.mp3"
    episode = _make_episode(
        session,
        podcast,
        guid="episode1.mp3",
        audio_url=str(audio),
        local_audio_path=str(audio),
        transcript_status=TranscriptStatus.queued,
    )
    monkeypatch.setattr("app.services.downloads.engine", session.get_bind())

    calls = []
    monkeypatch.setattr(
        "app.services.downloads.ingest_transcript",
        lambda session, episode, audio_path=None: calls.append((episode.id, audio_path)),
    )

    retry_transcription(episode.id)

    assert calls == [(episode.id, audio)]


def test_remove_audio_does_not_unlink_local_directory_file(session, monkeypatch, tmp_path):
    audio = tmp_path / "episode1.mp3"
    audio.write_bytes(b"audio")
    podcast = _make_podcast(
        session, rss_url=None, local_directory_path=str(tmp_path), kind=PodcastKind.local_directory
    )
    episode = _make_episode(
        session,
        podcast,
        guid="episode1.mp3",
        audio_url=str(audio),
        local_audio_path=str(audio),
        download_status=DownloadStatus.downloaded,
    )

    remove_audio(session, episode)
    session.commit()

    assert audio.exists()
    assert episode.local_audio_path is None
    assert episode.download_status == DownloadStatus.idle


def test_remove_audio_unlinks_file_and_resets_status(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
    (tmp_path / "1.mp3").write_bytes(b"audio")
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, local_audio_path="1.mp3", download_status=DownloadStatus.downloaded)

    remove_audio(session, episode)
    session.commit()

    assert not (tmp_path / "1.mp3").exists()
    assert episode.local_audio_path is None
    assert episode.download_status == DownloadStatus.idle


def test_remove_audio_noop_without_local_path(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.storage_dir", lambda: tmp_path)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, local_audio_path=None, download_status=DownloadStatus.idle)

    remove_audio(session, episode)

    assert episode.download_status == DownloadStatus.idle


def test_relocate_storage_moves_files_and_updates_storage_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.data_dir", lambda: tmp_path)
    old_root = tmp_path / "storage"
    old_root.mkdir()
    (old_root / "1.mp3").write_bytes(b"audio")
    new_root = tmp_path / "elsewhere"

    from app import paths

    result = relocate_storage(new_root)

    assert result == new_root
    assert (new_root / "1.mp3").exists()
    assert not (old_root / "1.mp3").exists()
    assert paths.storage_dir() == new_root


def test_relocate_storage_rejects_non_empty_target(monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.data_dir", lambda: tmp_path)
    (tmp_path / "storage").mkdir()
    new_root = tmp_path / "elsewhere"
    new_root.mkdir()
    (new_root / "existing.txt").write_bytes(b"nope")

    with pytest.raises(RelocateStorageError):
        relocate_storage(new_root)


def test_relocate_storage_is_noop_when_target_matches_current(monkeypatch, tmp_path):
    monkeypatch.setattr("app.paths.data_dir", lambda: tmp_path)
    (tmp_path / "storage").mkdir()

    result = relocate_storage(tmp_path / "storage")

    assert result == tmp_path / "storage"
