import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Player } from './Player';
import { ProfileProvider } from '../state/ProfileContext';
import { ToastProvider } from '../state/ToastContext';
import { api } from '../lib/api';
import { DEFAULT_KEYMAP } from '../lib/keybindings';
import type { Episode, Podcast, Profile, Transcript } from '../lib/types';

vi.mock('../lib/api');

const profile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  learning_language: 'ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
};

const podcast: Podcast = {
  id: 1,
  rss_url: 'https://example.com/feed.xml',
  youtube_playlist_url: null,
  local_directory_path: null,
  kind: 'rss',
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
  position_seconds: null,
};

const transcript: Transcript = {
  id: 1,
  episode_id: 42,
  language: 'ja',
  source: 'published',
  created_at: '2026-01-01T00:00:00Z',
  sentences: [
    { id: 100, index: 0, start_time: 0, end_time: 2, text: '一つ目', segments: [{ base: '一つ目', reading: 'ひとつめ' }] },
    { id: 101, index: 1, start_time: 2, end_time: 5, text: '二つ目', segments: [{ base: '二つ目', reading: 'ふたつめ' }] },
    { id: 102, index: 2, start_time: 5, end_time: 8, text: '三つ目', segments: [{ base: '三つ目', reading: 'みっつめ' }] },
  ],
};

function renderPlayer(episodeOverride: Episode = episode, autoplay = false, transcriptOverride?: Transcript) {
  if (transcriptOverride) vi.mocked(api.getTranscript).mockResolvedValue(transcriptOverride);
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: '/library/podcasts/1/episodes/42/player',
          state: { podcast, episode: episodeOverride, autoplay },
        },
      ]}
    >
      <ProfileProvider>
        <ToastProvider>
          <Routes>
            <Route path="/library/podcasts/:podcastId/episodes/:episodeId/player" element={<Player />} />
          </Routes>
        </ToastProvider>
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
    vi.mocked(api.getShadowSummary).mockResolvedValue({ doneToday: 0, total: 3 });
    vi.mocked(api.logShadowEvent).mockResolvedValue(undefined);
    vi.mocked(api.updatePosition).mockResolvedValue(undefined);
    vi.mocked(api.createSavedSentence).mockResolvedValue({
      id: 1,
      profile_id: 1,
      episode_id: 42,
      podcast_id: 1,
      name: 'clip',
      podcast_title: 'Nihongo News',
      episode_title: 'Episode One',
      text: '一つ目',
      start_time: 0,
      end_time: 2,
      audio_available: true,
      created_at: '2026-01-01T00:00:00Z',
      sentences: [],
    });
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

  it('clicking a word shows its definition in a popover without jumping playback', async () => {
    vi.mocked(api.lookupWord).mockResolvedValue({
      word: '一つ目',
      reading: 'ひとつめ',
      senses: [{ part_of_speech: 'Noun', definitions: ['the first one'] }],
    });
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.click(screen.getAllByTestId('word')[0]);

    expect(screen.getByTestId('definition-popover')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('the first one')).toBeInTheDocument());
    expect(api.lookupWord).toHaveBeenCalledWith('一つ目', 'ja');
    expect(playSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'false');
  });

  it('dismisses the definition popover on close-button click', async () => {
    vi.mocked(api.lookupWord).mockResolvedValue({ word: '一つ目', reading: 'ひとつめ', senses: [] });
    const user = userEvent.setup();
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    fireEvent.click(screen.getAllByTestId('word')[0]);
    await waitFor(() => expect(screen.getByTestId('definition-popover')).toBeInTheDocument());

    await user.click(screen.getByTestId('definition-popover-close'));
    expect(screen.queryByTestId('definition-popover')).not.toBeInTheDocument();
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

  it('logs a ShadowEvent and refreshes the persisted count once a sentence\'s end boundary is crossed', async () => {
    vi.mocked(api.getShadowSummary)
      .mockResolvedValueOnce({ doneToday: 0, total: 3 })
      .mockResolvedValueOnce({ doneToday: 1, total: 3 });
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('shadowed-count')).toHaveTextContent('0/3'));

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 0.5;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));

    audio.currentTime = 2.5;
    fireEvent.timeUpdate(audio);

    expect(api.logShadowEvent).toHaveBeenCalledWith(1, 42, 100);
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

  it('still advances the scrub bar and elapsed time when there is no transcript', async () => {
    vi.mocked(api.getTranscript).mockRejectedValue(new Error('404 Not Found'));
    renderPlayer();
    await screen.findByText('Transcript not available');

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 3;
    fireEvent.timeUpdate(audio);

    await waitFor(() => expect(screen.getByText('0:03')).toBeInTheDocument());
    expect(screen.getByRole('slider')).toHaveValue('3');
  });

  it('resumes playback from a persisted position and saves it back on pause', async () => {
    renderPlayer({ ...episode, position_seconds: 4 });
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 8, configurable: true });
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(4);

    audio.currentTime = 6;
    fireEvent.pause(audio);
    expect(api.updatePosition).toHaveBeenCalledWith(1, 42, 6);
  });

  it('starts playback automatically when navigated to with autoplay state', async () => {
    renderPlayer(episode, true);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.loadedMetadata(audio);

    expect(playSpy).toHaveBeenCalled();
  });

  it('does not autoplay when navigated to without the autoplay flag', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.loadedMetadata(audio);

    expect(playSpy).not.toHaveBeenCalled();
  });

  it('Space toggles play/pause via the keyboard', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'paused', { value: true, configurable: true });
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.keyDown(window, { key: ' ' });
    expect(playSpy).toHaveBeenCalled();
  });

  it('"r" replays the active sentence from its start', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 3;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-active', 'true'));

    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();
    fireEvent.keyDown(window, { key: 'r' });

    expect(audio.currentTime).toBe(2);
    expect(playSpy).toHaveBeenCalled();
  });

  it('"l" toggles sentence loop via the keyboard', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 0.5;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));

    fireEvent.keyDown(window, { key: 'l' });

    audio.currentTime = 2.1;
    fireEvent.timeUpdate(audio);

    await waitFor(() => expect(audio.currentTime).toBe(0));
  });

  it('ArrowRight/ArrowLeft move to the next/previous sentence, bounds-checked at the ends', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    // No active sentence yet — previous/next are no-ops.
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(playSpy).not.toHaveBeenCalled();

    audio.currentTime = 0.5;
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));

    // Already at the first sentence — previous is a no-op.
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(playSpy).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    await waitFor(() => expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-active', 'true'));
    expect(audio.currentTime).toBe(2);

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-active', 'true'));
  });

  it('"s" cycles playback speed via the keyboard', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('speed-control')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    const speedBtn = screen.getByTestId('speed-control');

    expect(speedBtn).toHaveTextContent('1×');
    fireEvent.keyDown(window, { key: 's' });
    expect(speedBtn).toHaveTextContent('1.25×');
    expect(audio.playbackRate).toBe(1.25);
  });

  it('Shift+ArrowRight/ArrowLeft seek within the active sentence, clamped to its bounds', async () => {
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-1')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    audio.currentTime = 3; // sentence-1 spans [2, 5)
    fireEvent.timeUpdate(audio);
    await waitFor(() => expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-active', 'true'));

    fireEvent.keyDown(window, { key: 'ArrowRight', shiftKey: true });
    expect(audio.currentTime).toBe(5); // 3 + default 5s step, clamped to the sentence end

    fireEvent.keyDown(window, { key: 'ArrowLeft', shiftKey: true });
    expect(audio.currentTime).toBe(2); // 5 - 5s step would go below the sentence start, clamped
  });

  it('reads a custom keymap from localStorage instead of the hardcoded defaults', async () => {
    localStorage.setItem('kotoba.keymap', JSON.stringify({ ...DEFAULT_KEYMAP, playPause: 'p' }));
    renderPlayer();
    await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

    const audio = screen.getByTestId('audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'paused', { value: true, configurable: true });
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

    fireEvent.keyDown(window, { key: ' ' });
    expect(playSpy).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'p' });
    expect(playSpy).toHaveBeenCalled();
  });

  describe('saving sentence clips', () => {
    it('clicking a row in select mode selects it instead of jumping/playing', async () => {
      const user = userEvent.setup();
      renderPlayer();
      await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

      const audio = screen.getByTestId('audio') as HTMLAudioElement;
      const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));

      expect(playSpy).not.toHaveBeenCalled();
      expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-selected', 'true');
      expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-selected', 'false');
      expect(await screen.findByTestId('save-selection-bar')).toHaveTextContent('1 sentence selected');
    });

    it('a second click extends the contiguous selection', async () => {
      const user = userEvent.setup();
      renderPlayer();
      await waitFor(() => expect(screen.getByTestId('sentence-2')).toBeInTheDocument());

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));
      await user.click(screen.getByTestId('sentence-2'));

      expect(screen.getByTestId('sentence-0')).toHaveAttribute('data-selected', 'true');
      expect(screen.getByTestId('sentence-1')).toHaveAttribute('data-selected', 'true');
      expect(screen.getByTestId('sentence-2')).toHaveAttribute('data-selected', 'true');
      expect(screen.getByTestId('save-selection-bar')).toHaveTextContent('3 sentences selected');
    });

    it('clamps the selection to 5 contiguous sentences when extending further', async () => {
      const user = userEvent.setup();
      const longTranscript: Transcript = {
        ...transcript,
        sentences: Array.from({ length: 8 }, (_, i) => ({
          id: 200 + i,
          index: i,
          start_time: i,
          end_time: i + 1,
          text: `s${i}`,
          segments: [{ base: `s${i}`, reading: '' }],
        })),
      };
      renderPlayer(episode, false, longTranscript);
      await waitFor(() => expect(screen.getByTestId('sentence-7')).toBeInTheDocument());

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));
      await user.click(screen.getByTestId('sentence-7'));

      expect(screen.getByTestId('save-selection-bar')).toHaveTextContent('5 sentences selected');
      expect(screen.getByTestId('sentence-4')).toHaveAttribute('data-selected', 'true');
      expect(screen.getByTestId('sentence-5')).toHaveAttribute('data-selected', 'false');
    });

    it('saves the selection with a name and shows a success toast', async () => {
      const user = userEvent.setup();
      renderPlayer();
      await waitFor(() => expect(screen.getByTestId('sentence-1')).toBeInTheDocument());

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));
      await user.click(screen.getByTestId('sentence-1'));
      await user.type(screen.getByTestId('save-name-input'), 'Greeting');
      await user.click(screen.getByTestId('save-selection'));

      await waitFor(() =>
        expect(api.createSavedSentence).toHaveBeenCalledWith(1, {
          episode_id: 42,
          name: 'Greeting',
          start_sentence_id: 100,
          end_sentence_id: 101,
        }),
      );
      expect(await screen.findByText('Saved "Greeting"')).toBeInTheDocument();
      expect(screen.queryByTestId('save-selection-bar')).not.toBeInTheDocument();
    });

    it('shows an error toast and keeps the selection when saving fails', async () => {
      vi.mocked(api.createSavedSentence).mockRejectedValue(new Error('422 boom'));
      const user = userEvent.setup();
      renderPlayer();
      await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));
      await user.type(screen.getByTestId('save-name-input'), 'Oops');
      await user.click(screen.getByTestId('save-selection'));

      expect(await screen.findByText('422 boom')).toBeInTheDocument();
      expect(screen.getByTestId('save-selection-bar')).toBeInTheDocument();
    });

    it('Cancel clears the selection', async () => {
      const user = userEvent.setup();
      renderPlayer();
      await waitFor(() => expect(screen.getByTestId('sentence-0')).toBeInTheDocument());

      await user.click(screen.getByTestId('select-mode-toggle'));
      await user.click(screen.getByTestId('sentence-0'));
      expect(screen.getByTestId('save-selection-bar')).toBeInTheDocument();

      await user.click(screen.getByTestId('cancel-selection'));
      expect(screen.queryByTestId('save-selection-bar')).not.toBeInTheDocument();
    });
  });
});
