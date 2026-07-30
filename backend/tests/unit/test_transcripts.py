from pathlib import Path

from sqlmodel import select

from app.models import Episode, Podcast, PodcastKind, Sentence, Transcript, TranscriptSource, TranscriptStatus
from app.services import transcription
from app.services.transcript_parsers import Cue
from app.services.transcription import WhisperModelNotFoundError
from app.services.transcripts import ingest_transcript
from app.services.youtube import YoutubeFetchError


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


def test_ingest_transcript_noop_when_already_full(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.full)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.full


def test_ingest_transcript_queues_when_model_missing(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    def fake_transcribe_audio(*args, **kwargs):
        raise WhisperModelNotFoundError("no model")

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.queued
    assert session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first() is None


def test_ingest_transcript_marks_failed_on_generic_asr_failure(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.none)

    def fake_transcribe_audio(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.failed


def test_ingest_transcript_marks_failed_on_empty_cues(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.none)

    def fake_transcribe_audio(*args, **kwargs):
        return [], "ja"

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.failed


def test_ingest_transcript_marks_failed_on_furigana_failure(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.none)

    def fake_transcribe_audio(*args, **kwargs):
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    def fake_build_segments(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)
    monkeypatch.setattr("app.services.transcripts.build_segments", fake_build_segments)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.failed
    assert session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first() is None
    assert session.exec(select(Sentence)).first() is None


def test_ingest_transcript_succeeds_via_asr(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    def fake_transcribe_audio(*args, **kwargs):
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.auto
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    assert transcript is not None
    assert transcript.source == TranscriptSource.asr


def test_ingest_transcript_no_audio_path_leaves_status_none(session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    ingest_transcript(session, episode, audio_path=None)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.none


class _FakeSrtResponse:
    text = "1\n00:00:00,000 --> 00:00:01,000\nこんにちは。\n"

    def raise_for_status(self):
        pass


def test_ingest_transcript_reverts_status_on_published_transcript_furigana_failure(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(
        session, podcast, transcript_status=TranscriptStatus.none, transcript_source_url="https://example.com/t.srt"
    )

    def fake_build_segments(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.transcripts.httpx.get", lambda *a, **k: _FakeSrtResponse())
    monkeypatch.setattr("app.services.transcripts.build_segments", fake_build_segments)

    ingest_transcript(session, episode, audio_path=None)

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.none
    assert session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first() is None
    assert session.exec(select(Sentence)).first() is None


def test_ingest_transcript_falls_back_to_asr_on_published_transcript_furigana_failure(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(
        session, podcast, transcript_status=TranscriptStatus.none, transcript_source_url="https://example.com/t.srt"
    )

    call_count = {"n": 0}

    def fake_build_segments(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return [{"base": args[0], "reading": ""}]

    def fake_transcribe_audio(*args, **kwargs):
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    monkeypatch.setattr("app.services.transcripts.httpx.get", lambda *a, **k: _FakeSrtResponse())
    monkeypatch.setattr("app.services.transcripts.build_segments", fake_build_segments)
    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.auto
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    assert transcript is not None
    assert transcript.source == TranscriptSource.asr


# --- YouTube manual captions (#85) ---------------------------------------


def _make_youtube_podcast(session, **overrides) -> Podcast:
    defaults = dict(
        youtube_playlist_url="https://www.youtube.com/playlist?list=abc",
        kind=PodcastKind.youtube,
        title="Nihongo News",
        language="ja",
    )
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def test_ingest_transcript_uses_youtube_manual_captions_when_available(session, monkeypatch):
    podcast = _make_youtube_podcast(session)
    episode = _make_episode(
        session, podcast, audio_url="https://www.youtube.com/watch?v=abc123", transcript_status=TranscriptStatus.none
    )

    monkeypatch.setattr(
        "app.services.transcripts.youtube.fetch_manual_captions",
        lambda video_url, language: [Cue(0.0, 1.0, "こんにちは。")],
    )

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.m4a"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.full
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    assert transcript is not None
    assert transcript.source == TranscriptSource.published
    assert transcript.language == "ja"


def test_ingest_transcript_falls_back_to_asr_when_youtube_has_no_manual_captions(session, monkeypatch):
    podcast = _make_youtube_podcast(session)
    episode = _make_episode(
        session, podcast, audio_url="https://www.youtube.com/watch?v=abc123", transcript_status=TranscriptStatus.none
    )

    monkeypatch.setattr("app.services.transcripts.youtube.fetch_manual_captions", lambda video_url, language: None)

    def fake_transcribe_audio(*args, **kwargs):
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.m4a"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.auto
    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    assert transcript is not None
    assert transcript.source == TranscriptSource.asr


def test_ingest_transcript_falls_back_to_asr_when_youtube_caption_fetch_errors(session, monkeypatch):
    podcast = _make_youtube_podcast(session)
    episode = _make_episode(
        session, podcast, audio_url="https://www.youtube.com/watch?v=abc123", transcript_status=TranscriptStatus.none
    )

    def raise_fetch_error(*args, **kwargs):
        raise YoutubeFetchError("boom")

    monkeypatch.setattr("app.services.transcripts.youtube.fetch_manual_captions", raise_fetch_error)

    def fake_transcribe_audio(*args, **kwargs):
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.m4a"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.auto


# --- ASR progress cleanup (#69) ------------------------------------------


def test_progress_cleared_after_successful_asr(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    def fake_transcribe_audio(*args, episode_id=None, **kwargs):
        transcription._set_progress(episode_id, 50)
        return [Cue(0.0, 1.0, "こんにちは。")], "ja"

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    assert transcription.get_progress(episode.id) is None


def test_progress_cleared_after_failed_asr(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.none)

    def fake_transcribe_audio(*args, episode_id=None, **kwargs):
        transcription._set_progress(episode_id, 50)
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    assert transcription.get_progress(episode.id) is None
