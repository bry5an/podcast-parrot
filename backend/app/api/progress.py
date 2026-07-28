from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import Episode, PlaybackState, Profile, Sentence, ShadowEvent, Transcript

router = APIRouter(prefix="/api/profiles", tags=["progress"])


class PositionUpdate(SQLModel):
    position_seconds: float


class ShadowCreate(SQLModel):
    sentence_id: int


class ShadowSummaryRead(SQLModel):
    doneToday: int
    total: int


class StreakRead(SQLModel):
    streak: int


def _require_profile_and_episode(session: Session, profile_id: int, episode_id: int) -> Episode:
    if not session.get(Profile, profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def _today_bounds() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    return start, start + timedelta(days=1)


@router.post("/{profile_id}/episodes/{episode_id}/position", response_model=PlaybackState)
def update_position(
    profile_id: int,
    episode_id: int,
    payload: PositionUpdate,
    session: Session = Depends(get_session),
):
    _require_profile_and_episode(session, profile_id, episode_id)

    state = session.exec(
        select(PlaybackState).where(
            PlaybackState.profile_id == profile_id, PlaybackState.episode_id == episode_id
        )
    ).first()
    if not state:
        state = PlaybackState(profile_id=profile_id, episode_id=episode_id)
    state.position_seconds = payload.position_seconds
    state.updated_at = datetime.utcnow()
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


@router.post("/{profile_id}/episodes/{episode_id}/shadow", response_model=ShadowEvent, status_code=201)
def log_shadow_event(
    profile_id: int,
    episode_id: int,
    payload: ShadowCreate,
    session: Session = Depends(get_session),
):
    _require_profile_and_episode(session, profile_id, episode_id)

    sentence = session.get(Sentence, payload.sentence_id)
    transcript = session.get(Transcript, sentence.transcript_id) if sentence else None
    if not sentence or not transcript or transcript.episode_id != episode_id:
        raise HTTPException(status_code=404, detail="Sentence not found for this episode")

    event = ShadowEvent(profile_id=profile_id, episode_id=episode_id, sentence_id=payload.sentence_id)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("/{profile_id}/episodes/{episode_id}/shadow-summary", response_model=ShadowSummaryRead)
def get_shadow_summary(profile_id: int, episode_id: int, session: Session = Depends(get_session)):
    _require_profile_and_episode(session, profile_id, episode_id)

    start, end = _today_bounds()
    sentence_ids_today = session.exec(
        select(ShadowEvent.sentence_id).where(
            ShadowEvent.profile_id == profile_id,
            ShadowEvent.episode_id == episode_id,
            ShadowEvent.shadowed_at >= start,
            ShadowEvent.shadowed_at < end,
        )
    ).all()

    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode_id)).first()
    total = 0
    if transcript:
        total = len(
            session.exec(select(Sentence.id).where(Sentence.transcript_id == transcript.id)).all()
        )

    return {"doneToday": len(set(sentence_ids_today)), "total": total}


@router.get("/{profile_id}/streak", response_model=StreakRead)
def get_streak(profile_id: int, session: Session = Depends(get_session)):
    if not session.get(Profile, profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")

    timestamps = session.exec(
        select(ShadowEvent.shadowed_at).where(ShadowEvent.profile_id == profile_id)
    ).all()
    event_dates = {ts.date() for ts in timestamps}
    if not event_dates:
        return {"streak": 0}

    # A day with no event yet doesn't break the streak until it actually
    # passes — only count backward from today if today already has an event,
    # otherwise start from yesterday so an in-progress streak stays intact.
    today = datetime.utcnow().date()
    cursor = today if today in event_dates else today - timedelta(days=1)
    streak = 0
    while cursor in event_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return {"streak": streak}
