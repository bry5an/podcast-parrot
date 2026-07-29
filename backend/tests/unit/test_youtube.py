import pytest
import yt_dlp

from app.services.youtube import (
    YoutubeDownloadError,
    YoutubeFetchError,
    download_audio,
    fetch_manual_captions,
    fetch_playlist_episodes,
    fetch_playlist_metadata,
    looks_like_youtube_playlist_url,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.youtube.com/playlist?list=PLabc123", True),
        ("https://youtube.com/playlist?list=abc", True),
        ("  https://www.youtube.com/playlist?list=abc  ", True),
        ("https://www.youtube.com/watch?v=abc123", False),
        ("https://example.com/feed.xml", False),
        ("https://www.youtube.com/@handle/podcasts", False),
    ],
)
def test_looks_like_youtube_playlist_url(value, expected):
    assert looks_like_youtube_playlist_url(value) == expected


class _FakeYoutubeDL:
    def __init__(self, info=None, error=None, prepared_filename=None):
        self._info = info
        self._error = error
        self._prepared_filename = prepared_filename

    def __call__(self, opts):
        self.opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=False):
        if self._error:
            raise self._error
        return self._info

    def prepare_filename(self, info):
        return self._prepared_filename


def test_fetch_playlist_metadata_maps_fields(monkeypatch):
    fake = _FakeYoutubeDL(
        info={
            "title": "Japanese Podcast for Advanced",
            "description": "  #JapaneseCulture  ",
            "thumbnails": [{"url": "https://example.com/small.jpg"}, {"url": "https://example.com/large.jpg"}],
        }
    )
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    metadata = fetch_playlist_metadata("https://www.youtube.com/playlist?list=abc")

    assert metadata == {
        "title": "Japanese Podcast for Advanced",
        "description": "#JapaneseCulture",
        "artwork_url": "https://example.com/large.jpg",
        "language": "ja",
    }


def test_fetch_playlist_metadata_raises_on_download_error(monkeypatch):
    fake = _FakeYoutubeDL(error=yt_dlp.utils.DownloadError("boom"))
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    with pytest.raises(YoutubeFetchError):
        fetch_playlist_metadata("https://www.youtube.com/playlist?list=abc")


def test_fetch_playlist_episodes_maps_entries(monkeypatch):
    fake = _FakeYoutubeDL(
        info={
            "entries": [
                {"id": "abc123", "title": "Episode One", "duration": 2408.0},
                {"id": "def456", "title": "Episode Two", "duration": None},
                {"id": None, "title": "Skipped — no id"},
            ]
        }
    )
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    episodes = fetch_playlist_episodes("https://www.youtube.com/playlist?list=abc")

    assert episodes == [
        {
            "guid": "abc123",
            "title": "Episode One",
            "pub_date": None,
            "duration_seconds": 2408,
            "audio_url": "https://www.youtube.com/watch?v=abc123",
            "transcript_source_url": None,
            "transcript_source_type": None,
            "transcript_source_language": None,
            "transcript_source_format": None,
        },
        {
            "guid": "def456",
            "title": "Episode Two",
            "pub_date": None,
            "duration_seconds": None,
            "audio_url": "https://www.youtube.com/watch?v=def456",
            "transcript_source_url": None,
            "transcript_source_type": None,
            "transcript_source_language": None,
            "transcript_source_format": None,
        },
    ]


def test_fetch_manual_captions_returns_none_when_language_missing(monkeypatch):
    fake = _FakeYoutubeDL(info={"subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}]}})
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    assert fetch_manual_captions("https://www.youtube.com/watch?v=abc123", "ja") is None


class _FakeVttResponse:
    text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nこんにちは\n"

    def raise_for_status(self):
        pass


def test_fetch_manual_captions_fetches_and_parses_vtt(monkeypatch):
    fake = _FakeYoutubeDL(
        info={
            "subtitles": {
                "ja": [
                    {"ext": "srv1", "url": "https://example.com/ja.srv1"},
                    {"ext": "vtt", "url": "https://example.com/ja.vtt"},
                ]
            },
            "automatic_captions": {"ja": [{"ext": "vtt", "url": "https://example.com/auto-ja.vtt"}]},
        }
    )
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    captured_urls = []

    def fake_get(url, **kwargs):
        captured_urls.append(url)
        return _FakeVttResponse()

    monkeypatch.setattr("app.services.youtube.httpx.get", fake_get)

    cues = fetch_manual_captions("https://www.youtube.com/watch?v=abc123", "ja")

    assert captured_urls == ["https://example.com/ja.vtt"]
    assert cues == [(0.0, 1.0, "こんにちは")]


def test_fetch_manual_captions_raises_on_download_error(monkeypatch):
    fake = _FakeYoutubeDL(error=yt_dlp.utils.DownloadError("boom"))
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    with pytest.raises(YoutubeFetchError):
        fetch_manual_captions("https://www.youtube.com/watch?v=abc123", "ja")


def test_download_audio_returns_prepared_path(monkeypatch, tmp_path):
    target = tmp_path / "42.m4a"
    fake = _FakeYoutubeDL(info={"ext": "m4a"}, prepared_filename=str(target))
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    result = download_audio("https://www.youtube.com/watch?v=abc123", tmp_path, 42)

    assert result == target
    assert fake.opts["outtmpl"] == str(tmp_path / "42.%(ext)s")


def test_download_audio_raises_on_download_error(monkeypatch, tmp_path):
    fake = _FakeYoutubeDL(error=yt_dlp.utils.DownloadError("boom"))
    monkeypatch.setattr("app.services.youtube.yt_dlp.YoutubeDL", fake)

    with pytest.raises(YoutubeDownloadError):
        download_audio("https://www.youtube.com/watch?v=abc123", tmp_path, 42)
