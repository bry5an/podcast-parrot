import mimetypes
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, SQLModel, select

from app.db import get_session
from app.models import DownloadStatus, Episode, Podcast, Sentence, TranscriptSource, TranscriptStatus
from app.services.downloads import STORAGE_DIR, download_episode_audio
from app.services.episodes import sync_episodes
from app.services.transcripts import get_or_build_transcript

router = APIRouter(prefix="/api", tags=["episodes"])


class EpisodeRead(SQLModel):
    id: int
    podcast_id: int
    guid: str
    title: str
    pub_date: datetime | None
    duration_seconds: int | None
    audio_url: str
    local_audio_path: str | None
    transcript_source_url: str | None
    transcript_source_type: str | None
    transcript_source_language: str | None
    download_status: DownloadStatus
    transcript_status: TranscriptStatus


class SentenceRead(SQLModel):
    index: int
    start_time: float
    end_time: float
    text: str
    segments: list[dict]


class TranscriptRead(SQLModel):
    id: int
    episode_id: int
    language: str
    source: TranscriptSource
    created_at: datetime
    sentences: list[SentenceRead]


class EpisodeStatusRead(SQLModel):
    id: int
    download_status: DownloadStatus
    transcript_status: TranscriptStatus


VALID_FILTERS = {"all", "unplayed", "downloaded"}
VALID_SORTS = {"newest", "oldest"}


@router.get("/podcasts/{podcast_id}/episodes", response_model=list[EpisodeRead])
def list_episodes(
    podcast_id: int,
    profile_id: int | None = None,
    filter: str = "all",
    sort: str = "newest",
    session: Session = Depends(get_session),
):
    if filter not in VALID_FILTERS:
        raise HTTPException(status_code=422, detail=f"filter must be one of {sorted(VALID_FILTERS)}")
    if sort not in VALID_SORTS:
        raise HTTPException(status_code=422, detail=f"sort must be one of {sorted(VALID_SORTS)}")

    podcast = session.get(Podcast, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    sync_episodes(session, podcast)

    statement = select(Episode).where(Episode.podcast_id == podcast_id)
    if filter == "downloaded":
        statement = statement.where(Episode.download_status == DownloadStatus.downloaded)
    # "unplayed": no play-progress tracking yet (see milestone 8), so every
    # episode currently qualifies — same result set as "all".

    episodes = session.exec(statement).all()
    episodes.sort(key=lambda e: e.pub_date or datetime.min, reverse=(sort != "oldest"))
    return episodes


@router.post("/episodes/{episode_id}/download", response_model=EpisodeStatusRead, status_code=202)
def start_download(episode_id: int, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    if episode.download_status != DownloadStatus.downloading:
        episode.download_status = DownloadStatus.downloading
        session.add(episode)
        session.commit()
        session.refresh(episode)
        background_tasks.add_task(download_episode_audio, episode.id)

    return episode


@router.delete("/episodes/{episode_id}/download", status_code=204)
def delete_download(episode_id: int, session: Session = Depends(get_session)):
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    if episode.local_audio_path:
        (STORAGE_DIR / episode.local_audio_path).unlink(missing_ok=True)

    episode.local_audio_path = None
    episode.download_status = DownloadStatus.idle
    session.add(episode)
    session.commit()


@router.get("/episodes/{episode_id}/status", response_model=EpisodeStatusRead)
def get_status(episode_id: int, session: Session = Depends(get_session)):
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/episodes/{episode_id}/transcript", response_model=TranscriptRead)
def get_transcript(episode_id: int, session: Session = Depends(get_session)):
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    transcript = get_or_build_transcript(session, episode)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not available")

    sentences = session.exec(
        select(Sentence).where(Sentence.transcript_id == transcript.id).order_by(Sentence.index)
    ).all()

    return {
        "id": transcript.id,
        "episode_id": transcript.episode_id,
        "language": transcript.language,
        "source": transcript.source,
        "created_at": transcript.created_at,
        "sentences": [
            {
                "index": s.index,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "text": s.text,
                "segments": s.segments,
            }
            for s in sentences
        ],
    }


@router.get("/episodes/{episode_id}/audio")
def stream_audio(episode_id: int, session: Session = Depends(get_session)):
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.local_audio_path:
        raise HTTPException(status_code=404, detail="Episode has not been downloaded")

    path = STORAGE_DIR / episode.local_audio_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    media_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
    return FileResponse(path, media_type=media_type, content_disposition_type="inline")
