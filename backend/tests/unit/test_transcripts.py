from pathlib import Path

from sqlmodel import select

from app.models import Episode, Podcast, Sentence, Transcript, TranscriptSource, TranscriptStatus
from app.services.transcript_parsers import Cue
from app.services.transcription import WhisperModelNotFoundError
from app.services.transcripts import ingest_transcript


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


def test_ingest_transcript_reverts_to_original_status_on_generic_asr_failure(session, monkeypatch):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, transcript_status=TranscriptStatus.none)

    def fake_transcribe_audio(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.transcripts.transcribe_audio", fake_transcribe_audio)

    ingest_transcript(session, episode, audio_path=Path("/fake/audio.mp3"))

    session.refresh(episode)
    assert episode.transcript_status == TranscriptStatus.none


def test_ingest_transcript_reverts_to_original_status_on_furigana_failure(session, monkeypatch):
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
    assert episode.transcript_status == TranscriptStatus.none
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
