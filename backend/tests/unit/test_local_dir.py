import pytest

from app.services.local_dir import LocalDirectoryError, fetch_directory_metadata, scan_episodes, validate_directory


def test_validate_directory_rejects_non_directory(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("hi")

    with pytest.raises(LocalDirectoryError):
        validate_directory(not_a_dir)


def test_validate_directory_rejects_missing_path(tmp_path):
    with pytest.raises(LocalDirectoryError):
        validate_directory(tmp_path / "does-not-exist")


def test_validate_directory_rejects_directory_with_no_audio(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")

    with pytest.raises(LocalDirectoryError):
        validate_directory(tmp_path)


def test_validate_directory_accepts_directory_with_audio(tmp_path):
    (tmp_path / "episode1.mp3").write_bytes(b"fake-audio")

    result = validate_directory(tmp_path)

    assert result == tmp_path.resolve()


def test_fetch_directory_metadata_uses_folder_name(tmp_path):
    folder = tmp_path / "My Japanese Show"
    folder.mkdir()

    metadata = fetch_directory_metadata(folder)

    assert metadata == {
        "title": "My Japanese Show",
        "description": "",
        "artwork_url": None,
        "language": "ja",
    }


def test_scan_episodes_returns_one_episode_per_audio_file(tmp_path):
    (tmp_path / "episode1.mp3").write_bytes(b"fake-audio-1")
    (tmp_path / "episode2.m4a").write_bytes(b"fake-audio-2")
    (tmp_path / "notes.txt").write_text("not audio")

    episodes = scan_episodes(tmp_path)

    assert {e["guid"] for e in episodes} == {"episode1.mp3", "episode2.m4a"}
    assert {e["title"] for e in episodes} == {"episode1", "episode2"}
    for e in episodes:
        assert e["duration_seconds"] is None
        assert e["transcript_source_url"] is None
        assert e["transcript_source_type"] is None
        assert e["transcript_source_format"] is None
        assert e["pub_date"] is not None


def test_scan_episodes_detects_sidecar_transcript(tmp_path):
    (tmp_path / "episode1.mp3").write_bytes(b"fake-audio")
    (tmp_path / "episode1.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nこんにちは。\n")

    episodes = scan_episodes(tmp_path)

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["transcript_source_url"] == str(tmp_path / "episode1.srt")
    assert episode["transcript_source_type"] == "srt"
    assert episode["transcript_source_format"] == "srt"


def test_scan_episodes_audio_url_is_absolute_path(tmp_path):
    audio = tmp_path / "episode1.wav"
    audio.write_bytes(b"fake-audio")

    episodes = scan_episodes(tmp_path)

    assert episodes[0]["audio_url"] == str(audio)


def test_scan_episodes_raises_on_removed_directory(tmp_path):
    missing = tmp_path / "gone"

    with pytest.raises(LocalDirectoryError):
        scan_episodes(missing)
