from app.models import DownloadStatus, Episode, Podcast, Transcript, TranscriptSource, TranscriptStatus
from app.services.recovery import recover_startup_state


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


def test_recover_pending_transcript_without_transcript_row_resets_to_none(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.pending)

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.none


def test_recover_pending_transcript_with_published_transcript_resets_to_full(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.pending)
    session.add(Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.published))
    session.commit()

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.full


def test_recover_pending_transcript_with_asr_transcript_resets_to_auto(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.pending)
    session.add(Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.asr))
    session.commit()

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.auto


def test_recover_leaves_non_pending_transcript_status_untouched(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.full)
    session.add(Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.published))
    session.commit()

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.full


def test_recover_interrupted_download_resets_to_idle(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, download_status=DownloadStatus.downloading)

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.idle


def test_recover_leaves_non_downloading_status_untouched(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, download_status=DownloadStatus.downloaded)

    recover_startup_state(session)

    session.refresh(episode)
    assert episode.download_status == DownloadStatus.downloaded


def test_recover_deletes_stale_part_files(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.recovery.STORAGE_DIR", tmp_path)
    part_file = tmp_path / "1.part"
    part_file.write_bytes(b"partial")
    keep_file = tmp_path / "2.mp3"
    keep_file.write_bytes(b"complete")

    recover_startup_state(session)

    assert not part_file.exists()
    assert keep_file.exists()


def test_recover_handles_missing_storage_dir(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.recovery.STORAGE_DIR", tmp_path / "does-not-exist")

    recover_startup_state(session)


def test_recover_deletes_stale_model_part_files(session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.recovery.paths.models_dir", lambda: tmp_path)
    part_file = tmp_path / "ggml-base.bin.part"
    part_file.write_bytes(b"partial")
    keep_file = tmp_path / "ggml-tiny.bin"
    keep_file.write_bytes(b"complete")

    recover_startup_state(session)

    assert not part_file.exists()
    assert keep_file.exists()
