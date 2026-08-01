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
    last_used_at: datetime | None = Field(default=None)


class PodcastSource(str, Enum):
    curated = "curated"
    user_added = "user_added"


class PodcastKind(str, Enum):
    rss = "rss"
    youtube = "youtube"
    local_directory = "local_directory"


class Podcast(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rss_url: str | None = Field(default=None, unique=True, index=True)
    youtube_playlist_url: str | None = Field(default=None, unique=True, index=True)
    local_directory_path: str | None = Field(default=None, unique=True, index=True)
    kind: PodcastKind = Field(default=PodcastKind.rss)
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
    queued = "queued"
    auto = "auto"
    full = "full"
    failed = "failed"
    canceled = "canceled"


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
    # [{base, reading}] — per-morpheme for Japanese sentences, single collapsed
    # segment (reading always "") for everything else. See services/furigana.py.
    segments: list[dict] = Field(default_factory=list, sa_column=Column(JSON))


class PlaybackState(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("profile_id", "episode_id", name="uq_profile_episode_playback"),)

    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    episode_id: int = Field(foreign_key="episode.id", index=True)
    position_seconds: float = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ShadowEvent(SQLModel, table=True):
    # Append-only; daily counts and streaks are derived from distinct rows here, never a mutable counter.
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    episode_id: int = Field(foreign_key="episode.id", index=True)
    sentence_id: int = Field(foreign_key="sentence.id", index=True)
    shadowed_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AutoRemovePolicy(str, Enum):
    never = "never"
    seven_days = "7d"
    thirty_days = "30d"


class AppSettings(SQLModel, table=True):
    # Single-row table: id is always 1. No per-profile concept here — storage
    # and auto-remove are app-wide, not per learner profile.
    id: int | None = Field(default=1, primary_key=True)
    auto_remove: AutoRemovePolicy = Field(default=AutoRemovePolicy.never)


class SavedSentence(SQLModel, table=True):
    # Sentences are immutable once a Transcript is built (see
    # services/transcripts.py — never deleted/rebuilt), so referencing them by
    # FK is safe; series/episode/text are derived at read time via joins
    # rather than duplicated here (see api/saved_sentences.py).
    id: int | None = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="profile.id", index=True)
    episode_id: int = Field(foreign_key="episode.id", index=True)
    name: str
    start_sentence_id: int = Field(foreign_key="sentence.id")
    end_sentence_id: int = Field(foreign_key="sentence.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
