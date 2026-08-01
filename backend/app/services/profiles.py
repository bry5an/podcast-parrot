from sqlmodel import Session, select

from app.models import PlaybackState, Profile, SavedSentence, ShadowEvent, Subscription


def delete_profile(session: Session, profile: Profile) -> None:
    """Deletes a profile and everything scoped to it: subscriptions,
    saved sentences, and playback/shadow history. No FK in this schema
    cascades (SQLite doesn't enforce them here), so every dependent
    table is cleared by hand before the profile row itself."""
    for shadow_event in session.exec(select(ShadowEvent).where(ShadowEvent.profile_id == profile.id)).all():
        session.delete(shadow_event)
    for saved_sentence in session.exec(select(SavedSentence).where(SavedSentence.profile_id == profile.id)).all():
        session.delete(saved_sentence)
    for playback_state in session.exec(select(PlaybackState).where(PlaybackState.profile_id == profile.id)).all():
        session.delete(playback_state)
    for subscription in session.exec(select(Subscription).where(Subscription.profile_id == profile.id)).all():
        session.delete(subscription)

    session.delete(profile)
    session.commit()
