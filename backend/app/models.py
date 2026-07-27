from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint


class Direction(str, Enum):
    en_ja = "en_ja"  # learning Japanese, native English
    ja_en = "ja_en"  # learning English, native Japanese


class Profile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    palette_index: int = Field(default=0)
    direction: Direction = Field(default=Direction.en_ja)
    show_furigana: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PodcastSource(str, Enum):
    curated = "curated"
    user_added = "user_added"


class Podcast(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rss_url: str = Field(unique=True, index=True)
    title: str
    description: str = ""
    artwork_url: str | None = None
    language: str  # "ja" | "en" — which learning direction this show serves
    level_tag: str | None = None  # editorial difficulty band, curated shows only
    source: PodcastSource = Field(default=PodcastSource.user_added)
    last_polled_at: datetime | None = None


class Subscription(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("profile_id", "podcast_id", name="uq_profile_podcast"),)

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    podcast_id: int = Field(foreign_key="podcast.id", index=True)
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)


class DownloadStatus(str, Enum):
    idle = "idle"
    downloading = "downloading"
    downloaded = "downloaded"
    failed = "failed"


class TranscriptStatus(str, Enum):
    none = "none"
    pending = "pending"
    auto = "auto"
    full = "full"


class Episode(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("podcast_id", "guid", name="uq_podcast_episode_guid"),)

    id: int | None = Field(default=None, primary_key=True)
    podcast_id: int = Field(foreign_key="podcast.id", index=True)
    guid: str
    title: str
    pub_date: datetime | None = None
    duration_seconds: int | None = None
    audio_url: str
    local_audio_path: str | None = None
    transcript_source_url: str | None = None
    transcript_source_type: str | None = None  # mime type from the podcast:transcript tag, e.g. "text/vtt"
    transcript_source_language: str | None = None  # language attr from the podcast:transcript tag
    download_status: DownloadStatus = Field(default=DownloadStatus.idle)
    transcript_status: TranscriptStatus = Field(default=TranscriptStatus.none)


class TranscriptSource(str, Enum):
    published = "published"
    asr = "asr"


class Transcript(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    episode_id: int = Field(foreign_key="episode.id", unique=True, index=True)
    language: str = ""
    source: TranscriptSource = Field(default=TranscriptSource.published)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Sentence(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    transcript_id: int = Field(foreign_key="transcript.id", index=True)
    index: int
    start_time: float
    end_time: float
    text: str
    # [{base, reading}] — populated as plain {base: text, reading: ""} until furigana lands (#6)
    segments: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
