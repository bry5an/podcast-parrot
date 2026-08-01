from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import LearningLanguage, Profile
from app.services.profiles import delete_profile as delete_profile_service

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class ProfileCreate(SQLModel):
    name: str
    palette_index: int = 0
    learning_language: LearningLanguage = LearningLanguage.ja
    show_furigana: bool = True


class ProfileUpdate(SQLModel):
    name: str | None = None
    palette_index: int | None = None
    learning_language: LearningLanguage | None = None
    show_furigana: bool | None = None
    last_used_at: datetime | None = None


@router.get("", response_model=list[Profile])
def list_profiles(session: Session = Depends(get_session)):
    return session.exec(select(Profile)).all()


@router.post("", response_model=Profile)
def create_profile(payload: ProfileCreate, session: Session = Depends(get_session)):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Name is required")
    profile = Profile(**payload.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=Profile)
def get_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/{profile_id}", response_model=Profile)
def update_profile(profile_id: int, payload: ProfileUpdate, session: Session = Depends(get_session)):
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    delete_profile_service(session, profile)
