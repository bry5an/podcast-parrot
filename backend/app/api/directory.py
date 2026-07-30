from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import Podcast, PodcastKind, PodcastSource, Profile, Subscription
from app.services import youtube
from app.services.rss import FeedFetchError, fetch_podcast_metadata

router = APIRouter(prefix="/api", tags=["directory"])


class PodcastRead(SQLModel):
    id: int
    rss_url: str | None
    youtube_playlist_url: str | None
    kind: PodcastKind
    title: str
    description: str
    artwork_url: str | None
    language: str
    level_tag: str | None
    source: PodcastSource
    subscribed: bool = False


class RssAddRequest(SQLModel):
    rss_url: str


class YoutubeAddRequest(SQLModel):
    playlist_url: str


def _to_read(podcast: Podcast, subscribed_ids: set[int]) -> PodcastRead:
    return PodcastRead(
        id=podcast.id,
        rss_url=podcast.rss_url,
        youtube_playlist_url=podcast.youtube_playlist_url,
        kind=podcast.kind,
        title=podcast.title,
        description=podcast.description,
        artwork_url=podcast.artwork_url,
        language=podcast.language,
        level_tag=podcast.level_tag,
        source=podcast.source,
        subscribed=podcast.id in subscribed_ids,
    )


def _subscribed_podcast_ids(session: Session, profile_id: int | None) -> set[int]:
    if profile_id is None:
        return set()
    rows = session.exec(select(Subscription.podcast_id).where(Subscription.profile_id == profile_id)).all()
    return set(rows)


@router.get("/directory", response_model=list[PodcastRead])
def search_directory(
    query: str = "",
    language: str | None = None,
    profile_id: int | None = None,
    session: Session = Depends(get_session),
):
    statement = select(Podcast)
    if language:
        statement = statement.where(Podcast.language == language)
    podcasts = session.exec(statement).all()

    q = query.strip().lower()
    if q:
        podcasts = [
            p
            for p in podcasts
            if q in p.title.lower() or q in p.description.lower() or q in (p.level_tag or "").lower()
        ]

    subscribed_ids = _subscribed_podcast_ids(session, profile_id)
    return [_to_read(p, subscribed_ids) for p in podcasts]


@router.post("/directory/rss", response_model=PodcastRead)
def add_podcast_from_rss(payload: RssAddRequest, session: Session = Depends(get_session)):
    rss_url = payload.rss_url.strip()
    existing = session.exec(select(Podcast).where(Podcast.rss_url == rss_url)).first()
    if existing:
        return _to_read(existing, set())

    try:
        metadata = fetch_podcast_metadata(rss_url)
    except FeedFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    podcast = Podcast(rss_url=rss_url, source=PodcastSource.user_added, **metadata)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return _to_read(podcast, set())


@router.post("/directory/youtube", response_model=PodcastRead)
def add_podcast_from_youtube(payload: YoutubeAddRequest, session: Session = Depends(get_session)):
    playlist_url = payload.playlist_url.strip()
    existing = session.exec(select(Podcast).where(Podcast.youtube_playlist_url == playlist_url)).first()
    if existing:
        return _to_read(existing, set())

    try:
        metadata = youtube.fetch_playlist_metadata(playlist_url)
    except youtube.YoutubeFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    podcast = Podcast(
        youtube_playlist_url=playlist_url,
        kind=PodcastKind.youtube,
        source=PodcastSource.user_added,
        **metadata,
    )
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return _to_read(podcast, set())


@router.get("/profiles/{profile_id}/podcasts", response_model=list[PodcastRead])
def list_subscriptions(profile_id: int, session: Session = Depends(get_session)):
    if not session.get(Profile, profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    subscribed_ids = _subscribed_podcast_ids(session, profile_id)
    if not subscribed_ids:
        return []
    podcasts = session.exec(select(Podcast).where(Podcast.id.in_(subscribed_ids))).all()
    return [_to_read(p, subscribed_ids) for p in podcasts]


@router.post("/profiles/{profile_id}/podcasts/{podcast_id}", status_code=204)
def subscribe(profile_id: int, podcast_id: int, session: Session = Depends(get_session)):
    if not session.get(Profile, profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    if not session.get(Podcast, podcast_id):
        raise HTTPException(status_code=404, detail="Podcast not found")

    existing = session.exec(
        select(Subscription).where(
            Subscription.profile_id == profile_id, Subscription.podcast_id == podcast_id
        )
    ).first()
    if existing:
        return
    session.add(Subscription(profile_id=profile_id, podcast_id=podcast_id))
    session.commit()


@router.delete("/profiles/{profile_id}/podcasts/{podcast_id}", status_code=204)
def unsubscribe(profile_id: int, podcast_id: int, session: Session = Depends(get_session)):
    existing = session.exec(
        select(Subscription).where(
            Subscription.profile_id == profile_id, Subscription.podcast_id == podcast_id
        )
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")
    session.delete(existing)
    session.commit()
