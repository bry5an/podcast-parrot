import type {
  DictionaryEntry,
  Episode,
  EpisodeFilter,
  EpisodeSort,
  EpisodeStatus,
  Pack,
  PackStatus,
  Podcast,
  Profile,
  ProfileCreate,
  SavedSentence,
  SavedSentenceCreate,
  ShadowSummary,
  Streak,
  Transcript,
  WhisperModel,
  WhisperModelStatus,
} from './types';

declare global {
  interface Window {
    // Injected into index.html by the packaged backend's per-launch auth
    // token (see backend/app/main.py); empty/undefined in dev.
    KOTOBA_AUTH_TOKEN?: string;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.KOTOBA_AUTH_TOKEN;
  const res = await fetch(path, {
    headers: {
      'content-type': 'application/json',
      ...(token ? { 'x-kotoba-token': token } : {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listProfiles: () => request<Profile[]>('/api/profiles'),
  createProfile: (payload: ProfileCreate) =>
    request<Profile>('/api/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProfile: (id: number, payload: Partial<ProfileCreate>) =>
    request<Profile>(`/api/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteProfile: (id: number) =>
    request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),

  searchDirectory: (opts: { query?: string; language?: string; profileId?: number }) => {
    const params = new URLSearchParams();
    if (opts.query) params.set('query', opts.query);
    if (opts.language) params.set('language', opts.language);
    if (opts.profileId != null) params.set('profile_id', String(opts.profileId));
    return request<Podcast[]>(`/api/directory?${params.toString()}`);
  },
  addRssPodcast: (rssUrl: string) =>
    request<Podcast>('/api/directory/rss', {
      method: 'POST',
      body: JSON.stringify({ rss_url: rssUrl }),
    }),
  addYoutubePodcast: (playlistUrl: string) =>
    request<Podcast>('/api/directory/youtube', {
      method: 'POST',
      body: JSON.stringify({ playlist_url: playlistUrl }),
    }),
  listSubscriptions: (profileId: number) =>
    request<Podcast[]>(`/api/profiles/${profileId}/podcasts`),
  subscribe: (profileId: number, podcastId: number) =>
    request<void>(`/api/profiles/${profileId}/podcasts/${podcastId}`, { method: 'POST' }),
  unsubscribe: (profileId: number, podcastId: number) =>
    request<void>(`/api/profiles/${profileId}/podcasts/${podcastId}`, { method: 'DELETE' }),

  listEpisodes: (
    podcastId: number,
    opts: { profileId?: number; filter?: EpisodeFilter; sort?: EpisodeSort } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.profileId != null) params.set('profile_id', String(opts.profileId));
    if (opts.filter) params.set('filter', opts.filter);
    if (opts.sort) params.set('sort', opts.sort);
    return request<Episode[]>(`/api/podcasts/${podcastId}/episodes?${params.toString()}`);
  },
  startDownload: (episodeId: number) =>
    request<EpisodeStatus>(`/api/episodes/${episodeId}/download`, { method: 'POST' }),
  deleteDownload: (episodeId: number) =>
    request<void>(`/api/episodes/${episodeId}/download`, { method: 'DELETE' }),
  transcribeEpisode: (episodeId: number) =>
    request<EpisodeStatus>(`/api/episodes/${episodeId}/transcribe`, { method: 'POST' }),
  getEpisodeStatus: (episodeId: number) => request<EpisodeStatus>(`/api/episodes/${episodeId}/status`),
  getTranscript: (episodeId: number) => request<Transcript>(`/api/episodes/${episodeId}/transcript`),
  audioUrl: (episodeId: number) => {
    const token = window.KOTOBA_AUTH_TOKEN;
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    return `/api/episodes/${episodeId}/audio${query}`;
  },

  updatePosition: (profileId: number, episodeId: number, positionSeconds: number) =>
    request<void>(`/api/profiles/${profileId}/episodes/${episodeId}/position`, {
      method: 'POST',
      body: JSON.stringify({ position_seconds: positionSeconds }),
    }),
  logShadowEvent: (profileId: number, episodeId: number, sentenceId: number) =>
    request<void>(`/api/profiles/${profileId}/episodes/${episodeId}/shadow`, {
      method: 'POST',
      body: JSON.stringify({ sentence_id: sentenceId }),
    }),
  getShadowSummary: (profileId: number, episodeId: number) =>
    request<ShadowSummary>(`/api/profiles/${profileId}/episodes/${episodeId}/shadow-summary`),
  getStreak: (profileId: number) => request<Streak>(`/api/profiles/${profileId}/streak`),

  listSavedSentences: (profileId: number) =>
    request<SavedSentence[]>(`/api/profiles/${profileId}/saved-sentences`),
  createSavedSentence: (profileId: number, payload: SavedSentenceCreate) =>
    request<SavedSentence>(`/api/profiles/${profileId}/saved-sentences`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  renameSavedSentence: (profileId: number, id: number, name: string) =>
    request<SavedSentence>(`/api/profiles/${profileId}/saved-sentences/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  deleteSavedSentence: (profileId: number, id: number) =>
    request<void>(`/api/profiles/${profileId}/saved-sentences/${id}`, { method: 'DELETE' }),

  listModels: () => request<WhisperModel[]>('/api/models'),
  downloadModel: (name: string) => request<WhisperModel>(`/api/models/${name}`, { method: 'POST' }),
  getModelStatus: (name: string) => request<WhisperModelStatus>(`/api/models/${name}/status`),
  deleteModel: (name: string) => request<void>(`/api/models/${name}`, { method: 'DELETE' }),

  listPacks: () => request<Pack[]>('/api/packs'),
  installPack: (name: string) => request<Pack>(`/api/packs/${name}`, { method: 'POST' }),
  getPackStatus: (name: string) => request<PackStatus>(`/api/packs/${name}/status`),
  deletePack: (name: string) => request<void>(`/api/packs/${name}`, { method: 'DELETE' }),

  lookupWord: (word: string, language: string) =>
    request<DictionaryEntry>(`/api/dictionary?word=${encodeURIComponent(word)}&language=${encodeURIComponent(language)}`),
};
