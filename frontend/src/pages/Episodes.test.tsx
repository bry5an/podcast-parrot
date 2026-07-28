import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Episodes } from './Episodes';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import type { Episode, Profile } from '../lib/types';

vi.mock('../lib/api');

const profile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  direction: 'en_ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
};

function makeEpisode(overrides: Partial<Episode>): Episode {
  return {
    id: 1,
    podcast_id: 1,
    guid: 'guid-1',
    title: 'Episode',
    pub_date: '2026-01-01T00:00:00Z',
    duration_seconds: 600,
    audio_url: 'https://example.com/a.mp3',
    local_audio_path: null,
    transcript_source_url: null,
    download_status: 'idle',
    transcript_status: 'none',
    position_seconds: null,
    ...overrides,
  };
}

function renderEpisodes() {
  return render(
    <MemoryRouter initialEntries={['/library/podcasts/1/episodes']}>
      <ProfileProvider>
        <Routes>
          <Route path="/library/podcasts/:podcastId/episodes" element={<Episodes />} />
        </Routes>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

describe('Episodes', () => {
  beforeEach(() => {
    localStorage.setItem('kotoba.profileId', '1');
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.listSubscriptions).mockResolvedValue([]);
  });

  it('re-fetches from the API when the filter changes', async () => {
    const allEpisodes = [
      makeEpisode({ id: 1, title: 'Idle episode', download_status: 'idle' }),
      makeEpisode({ id: 2, title: 'Downloaded episode', download_status: 'downloaded' }),
    ];
    const downloadedOnly = [allEpisodes[1]];
    vi.mocked(api.listEpisodes).mockImplementation((_podcastId, opts = {}) =>
      Promise.resolve(opts.filter === 'downloaded' ? downloadedOnly : allEpisodes),
    );

    renderEpisodes();

    expect(await screen.findByText('Idle episode')).toBeInTheDocument();
    expect(screen.getByText('Downloaded episode')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Downloaded' }));

    await waitFor(() => {
      expect(screen.queryByText('Idle episode')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Downloaded episode')).toBeInTheDocument();
    expect(api.listEpisodes).toHaveBeenLastCalledWith(1, { profileId: 1, filter: 'downloaded', sort: 'newest' });
  });

  it('shows a Continue button and progress bar for a downloaded, in-progress episode', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([
      makeEpisode({
        id: 1,
        title: 'In progress episode',
        download_status: 'downloaded',
        duration_seconds: 100,
        position_seconds: 40,
      }),
      makeEpisode({ id: 2, title: 'Fresh episode', download_status: 'downloaded', duration_seconds: 100 }),
    ]);
    renderEpisodes();

    await screen.findByText('In progress episode');
    expect(screen.getByRole('button', { name: /Continue/ })).toBeInTheDocument();
    expect(screen.getByTestId('progress-1')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /Shadow/ })).toBeInTheDocument();
    expect(screen.queryByTestId('progress-2')).not.toBeInTheDocument();
  });

  it('shows a queued badge for an episode waiting on an ASR model', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([
      makeEpisode({ id: 1, title: 'Queued episode', transcript_status: 'queued' }),
      makeEpisode({ id: 2, title: 'Untranscribed episode', transcript_status: 'none' }),
    ]);
    renderEpisodes();

    await screen.findByText('Queued episode');
    expect(screen.getByText('Queued')).toBeInTheDocument();
  });

  it('shows a Transcribe button for a downloaded episode with no transcript, and triggers the endpoint', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([
      makeEpisode({ id: 1, title: 'Untranscribed episode', download_status: 'downloaded', transcript_status: 'none' }),
      makeEpisode({ id: 2, title: 'Transcribed episode', download_status: 'downloaded', transcript_status: 'full' }),
    ]);
    vi.mocked(api.transcribeEpisode).mockResolvedValue({ id: 1, download_status: 'downloaded', transcript_status: 'pending' });

    renderEpisodes();

    await screen.findByText('Untranscribed episode');
    const transcribeButton = screen.getByRole('button', { name: 'Transcribe' });
    expect(screen.queryAllByRole('button', { name: /Transcribe|Retry transcription/ })).toHaveLength(1);

    await userEvent.click(transcribeButton);

    expect(api.transcribeEpisode).toHaveBeenCalledWith(1);
  });

  it('labels the Transcribe button as a retry when the episode is queued', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([
      makeEpisode({ id: 1, title: 'Queued episode', download_status: 'downloaded', transcript_status: 'queued' }),
    ]);
    renderEpisodes();

    await screen.findByText('Queued episode');
    expect(screen.getByRole('button', { name: 'Retry transcription' })).toBeInTheDocument();
  });

  it('toggles sort order and re-fetches with the new sort', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([makeEpisode({ id: 1, title: 'Episode' })]);
    renderEpisodes();

    await screen.findByText('Episode');
    const sortButton = screen.getByRole('button', { name: /Newest first/ });

    await userEvent.click(sortButton);

    expect(await screen.findByRole('button', { name: /Oldest first/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.listEpisodes).toHaveBeenLastCalledWith(1, { profileId: 1, filter: 'all', sort: 'oldest' });
    });
  });
});
