from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from app.api.episodes import SentenceRead
from app.db import get_session
from app.models import Episode, Podcast, Profile, SavedSentence, Sentence, Transcript

router = APIRouter(prefix="/api/profiles", tags=["saved-sentences"])


class SavedSentenceCreate(SQLModel):
    episode_id: int
    name: str
    start_sentence_id: int
    end_sentence_id: int


class SavedSentenceUpdate(SQLModel):
    name: str


class SavedSentenceRead(SQLModel):
    id: int
    profile_id: int
    episode_id: int
    podcast_id: int
    name: str
    podcast_title: str
    episode_title: str
    text: str
    start_time: float
    end_time: float
    audio_available: bool
    created_at: datetime
    sentences: list[SentenceRead]


def _require_profile(session: Session, profile_id: int) -> Profile:
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _to_read(session: Session, clip: SavedSentence) -> SavedSentenceRead:
    episode = session.get(Episode, clip.episode_id)
    podcast = session.get(Podcast, episode.podcast_id) if episode else None
    start = session.get(Sentence, clip.start_sentence_id)
    end = session.get(Sentence, clip.end_sentence_id)
    sentences = session.exec(
        select(Sentence)
        .where(
            Sentence.transcript_id == start.transcript_id,
            Sentence.index >= start.index,
            Sentence.index <= end.index,
        )
        .order_by(Sentence.index)
    ).all()

    return SavedSentenceRead(
        id=clip.id,
        profile_id=clip.profile_id,
        episode_id=clip.episode_id,
        podcast_id=episode.podcast_id if episode else 0,
        name=clip.name,
        podcast_title=podcast.title if podcast else "",
        episode_title=episode.title if episode else "",
        text=" ".join(s.text for s in sentences),
        start_time=start.start_time,
        end_time=end.end_time,
        audio_available=bool(episode and episode.local_audio_path),
        created_at=clip.created_at,
        sentences=[
            SentenceRead(
                id=s.id,
                index=s.index,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                segments=s.segments,
            )
            for s in sentences
        ],
    )


@router.get("/{profile_id}/saved-sentences", response_model=list[SavedSentenceRead])
def list_saved_sentences(profile_id: int, session: Session = Depends(get_session)):
    _require_profile(session, profile_id)
    clips = session.exec(
        select(SavedSentence)
        .where(SavedSentence.profile_id == profile_id)
        .order_by(SavedSentence.created_at.desc())
    ).all()
    return [_to_read(session, clip) for clip in clips]


@router.post("/{profile_id}/saved-sentences", response_model=SavedSentenceRead, status_code=201)
def create_saved_sentence(profile_id: int, payload: SavedSentenceCreate, session: Session = Depends(get_session)):
    _require_profile(session, profile_id)

    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Name is required")

    episode = session.get(Episode, payload.episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    transcript = session.exec(select(Transcript).where(Transcript.episode_id == episode.id)).first()
    start = session.get(Sentence, payload.start_sentence_id)
    end = session.get(Sentence, payload.end_sentence_id)
    if (
        not transcript
        or not start
        or not end
        or start.transcript_id != transcript.id
        or end.transcript_id != transcript.id
    ):
        raise HTTPException(status_code=404, detail="Sentence not found for this episode")

    span = end.index - start.index
    if span < 0 or span > 4:
        raise HTTPException(status_code=422, detail="Selection must be 1-5 contiguous sentences")

    clip = SavedSentence(
        profile_id=profile_id,
        episode_id=episode.id,
        name=payload.name.strip(),
        start_sentence_id=start.id,
        end_sentence_id=end.id,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _to_read(session, clip)


def _get_owned_clip(session: Session, profile_id: int, clip_id: int) -> SavedSentence:
    clip = session.get(SavedSentence, clip_id)
    if not clip or clip.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Saved sentence not found")
    return clip


@router.patch("/{profile_id}/saved-sentences/{clip_id}", response_model=SavedSentenceRead)
def rename_saved_sentence(
    profile_id: int, clip_id: int, payload: SavedSentenceUpdate, session: Session = Depends(get_session)
):
    _require_profile(session, profile_id)
    clip = _get_owned_clip(session, profile_id, clip_id)
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Name is required")

    clip.name = payload.name.strip()
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _to_read(session, clip)


@router.delete("/{profile_id}/saved-sentences/{clip_id}", status_code=204)
def delete_saved_sentence(profile_id: int, clip_id: int, session: Session = Depends(get_session)):
    _require_profile(session, profile_id)
    clip = _get_owned_clip(session, profile_id, clip_id)
    session.delete(clip)
    session.commit()
