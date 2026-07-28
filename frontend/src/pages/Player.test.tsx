import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Player } from './Player';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import type { Episode, Podcast, Profile, Transcript } from '../lib/types';

vi.mock('../lib/api');

const profile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  direction: 'en_ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
};

const podcast: Podcast = {
  id: 1,
  rss_url: 'https://example.com/feed.xml',
  title: 'Nihongo News',
  description: '',
  artwork_url: null,
  language: 'ja',
  level_tag: null,
  source: 'curated',
  subscribed: true,
};

const episode: Episode = {
  id: 42,
  podcast_id: 1,
  guid: 'guid-1',
  title: 'Episode One',
  pub_date: '2026-01-01T00:00:00Z',
  duration_seconds: 8,
  audio_url: 'https://example.com/a.mp3',
  local_audio_path: 'a.mp3',
  transcript_source_url: null,
  download_status: 'downloaded',
  transcript_status: 'full',
};

const transcript: Transcript = {
  id: 1,
  episode_id: 42,
  language: 'ja',
  source: 'published',
  created_at: '2026-01-01T00:00:00Z',
  sentences: [
    { index: 0, start_time: 0, end_time: 2, text: '一つ目', segments: [{ base: '一つ目', reading: 'ひとつめ' }] },
    { index: 1, start_time: 2, end_time: 5, text: '二つ目', segments: [{ base: '二つ目', reading: 'ふたつめ' }] },
    { index: 2, start_time: 5, end_time: 8, text: '三つ目', segments: [{ base: '三つ目', reading: 'みっつめ' }] },
  ],
};

function renderPlayer() {
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: '/library/podcasts/1/episodes/42/player',
          state: { podcast, episode },
        },
      ]}
    >
      <ProfileProvider>
        <Routes>
          <Route path="/library/podcasts/:podcastId/episodes/:episodeId/player" element={<Player />} />
        </Routes>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

describe('Player', () => {
  beforeEach(() => {
    localStorage.setItem('kotoba.profileId', '1');
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.getTranscript).mockResolvedValue(transcript);
    vi.mocked(api.audioUrl).mockImplementation((id) => `/api/episodes/${id}/audio`);
  });

  it('renders the sidebar badges and the sentence list with furigana on by default', async () => {
    renderPlayer();

    expect(await screen.findByText('Episode One')).toBeInTheDocument();
    expect(screen.getByText('Downloaded')).toBeInTheDocument();
    expect(screen.getByText('Published transcript')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());
    expect(screen.getByText('ひとつめ').tagName).toBe('RT');
    expect(screen.getByTestId('shadowed-count')).toHaveTextContent('0/3');
  });

  it('toggles furigana off and on via the sidebar control', async () => {
    const user = userEvent.setup();
    renderPlayer();

    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());
    expect(screen.getByText('ひとつめ').tagName).toBe('RT');

    await user.click(screen.getByTestId('furigana-toggle'));
    expect(screen.queryByText('ひとつめ')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('furigana-toggle'));
    expect(screen.getByText('ひとつめ').tagName).toBe('RT');
  });

  it('highlights the active sentence on timeupdate via binary search over [start, end)', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 3;
    fireEvent.timeUpdate(audio);

    await waitFor(() => expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-active', 'true'));
    expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'false');
  });

  it('clicking a sentence row jumps the audio to its start time and plays', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-2')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.click(screen.getByTestId('sentence-2'));

    expect(audio.currentTime).toBe(5);
    expect(playSpy).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('sentence-2')).toHaveAttribute('data-active', 'true'));
  });

  it('loops the active sentence back to its start when loop-one is enabled and its end is reached', async () => {
    const user = userEvent.setup();
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;

    // Establish sentence 0 as active first.
    audio.currentTime = 0.5;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));

    await user.click(screen.getByTestId('loop-toggle'));

    audio.currentTime = 2.1;
    fireEvent.timeUpdate(audio);

    await waitFor(() => expect(audio.currentTime).toBe(0));
    // Sentence 1 should not have become active since we looped back before advancing.
    expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-active', 'false');
  });

  it('counts a sentence toward "shadowed today" once its end boundary is crossed', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 0.5;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));

    audio.currentTime = 2.5;
    fireEvent.timeUpdate(audio);

    await waitFor(() => expect(screen.getByTestId('shadowed-count')).toHaveTextContent('1/3'));
  });

  it('cycles playback speed through 0.75x / 1x / 1.25x / 1.5x', async () => {
    const user = userEvent.setup();
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('speed-control')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const speedBtn = screen.getByTestId('speed-control');

    expect(speedBtn).toHaveTextContent('1×');
    await user.click(speedBtn);
    expect(speedBtn).toHaveTextContent('1.25×');
    expect(audio.playbackRate).toBe(1.25);
    await user.click(speedBtn);
    expect(speedBtn).toHaveTextContent('1.5×');
    await user.click(speedBtn);
    expect(speedBtn).toHaveTextContent('0.75×');
    expect(audio.playbackRate).toBe(0.75);
  });

  it('shows an empty state when the transcript is unavailable', async () => {
    vi.mocked(api.getTranscript).mockRejectedValue(new Error('404 Not Found'));
    renderPlayer();

    expect(await screen.findByText('Transcript not available')).toBeInTheDocument();
  });
});
