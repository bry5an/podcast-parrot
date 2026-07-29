export type Direction = 'en_ja' | 'ja_en';

export interface Profile {
  id: number;
  name: string;
  palette_index: number;
  direction: Direction;
  show_furigana: boolean;
  created_at: string;
}

export interface ProfileCreate {
  name: string;
  palette_index: number;
  direction: Direction;
  show_furigana: boolean;
}

export type PodcastSource = 'curated' | 'user_added';

export interface Podcast {
  id: number;
  rss_url: string;
  title: string;
  description: string;
  artwork_url: string | null;
  language: string;
  level_tag: string | null;
  source: PodcastSource;
  subscribed: boolean;
}

export type DownloadStatus = 'idle' | 'downloading' | 'downloaded' | 'failed';
export type TranscriptStatus = 'none' | 'pending' | 'queued' | 'auto' | 'full' | 'failed' | 'canceled';
export type EpisodeFilter = 'all' | 'unplayed' | 'downloaded';
export type EpisodeSort = 'newest' | 'oldest';

export interface Episode {
  id: number;
  podcast_id: number;
  guid: string;
  title: string;
  pub_date: string | null;
  duration_seconds: number | null;
  audio_url: string;
  local_audio_path: string | null;
  transcript_source_url: string | null;
  download_status: DownloadStatus;
  transcript_status: TranscriptStatus;
  // Only populated when the list was fetched with a profileId; null means never started.
  position_seconds: number | null;
}

export interface EpisodeStatus {
  id: number;
  download_status: DownloadStatus;
  transcript_status: TranscriptStatus;
  // Only populated while transcript_status is 'pending'.
  progress: number | null;
}

export type TranscriptSource = 'published' | 'asr';

export interface Segment {
  base: string;
  reading: string;
}

export interface Sentence {
  id: number;
  index: number;
  start_time: number;
  end_time: number;
  text: string;
  segments: Segment[];
}

export interface Transcript {
  id: number;
  episode_id: number;
  language: string;
  source: TranscriptSource;
  created_at: string;
  sentences: Sentence[];
}

export interface ShadowSummary {
  doneToday: number;
  total: number;
}

export interface Streak {
  streak: number;
}

export type DownloadError = 'offline' | 'network' | 'disk_space' | 'checksum' | 'unknown' | null;

export type WhisperModelName = 'tiny' | 'base' | 'small';

export interface WhisperModel {
  name: WhisperModelName;
  size_bytes: number;
  installed: boolean;
  active: boolean;
}

export type WhisperModelState = 'not_installed' | 'downloading' | 'verifying' | 'installed' | 'failed';

export interface WhisperModelStatus {
  state: WhisperModelState;
  bytes_done: number;
  bytes_total: number;
  error: DownloadError;
}

export type PackName = 'japanese';

export interface Pack {
  name: PackName;
  download_size_bytes: number;
  installed: boolean;
}

export type PackState = 'not_installed' | 'downloading' | 'verifying' | 'extracting' | 'installed' | 'failed';

export interface PackStatus {
  state: PackState;
  bytes_done: number;
  bytes_total: number;
  error: DownloadError;
}
