from sqlmodel import Session, select

from app.models import (
    Episode,
    PlaybackState,
    Podcast,
    SavedSentence,
    Sentence,
    ShadowEvent,
    Subscription,
    Transcript,
)
from app.services.downloads import remove_audio


def delete_feed(session: Session, podcast: Podcast) -> None:
    """Deletes a podcast and everything derived from it: subscriptions,
    episodes, transcripts, sentences, saved clips, playback/shadow history,
    and downloaded audio files. No FK in this schema cascades (SQLite
    doesn't enforce them here), so every dependent table is cleared by hand
    in FK-safe order before the episode and podcast rows themselves."""
    episodes = session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
    episode_ids = [e.id for e in episodes]

    transcripts = session.exec(select(Transcript).where(Transcript.episode_id.in_(episode_ids))).all()
    transcript_ids = [t.id for t in transcripts]

    sentences = session.exec(select(Sentence).where(Sentence.transcript_id.in_(transcript_ids))).all()

    for shadow_event in session.exec(select(ShadowEvent).where(ShadowEvent.episode_id.in_(episode_ids))).all():
        session.delete(shadow_event)
    for saved_sentence in session.exec(select(SavedSentence).where(SavedSentence.episode_id.in_(episode_ids))).all():
        session.delete(saved_sentence)
    for playback_state in session.exec(select(PlaybackState).where(PlaybackState.episode_id.in_(episode_ids))).all():
        session.delete(playback_state)
    for sentence in sentences:
        session.delete(sentence)
    for transcript in transcripts:
        session.delete(transcript)
    for episode in episodes:
        remove_audio(session, episode)
        session.delete(episode)
    for subscription in session.exec(select(Subscription).where(Subscription.podcast_id == podcast.id)).all():
        session.delete(subscription)

    session.delete(podcast)
    session.commit()
