import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SavedSentences } from './SavedSentences';
import { ProfileProvider } from '../state/ProfileContext';
import { ToastProvider } from '../state/ToastContext';
import { api } from '../lib/api';
import type { Profile, SavedSentence } from '../lib/types';

vi.mock('../lib/api');

const profile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  direction: 'en_ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
};

function makeClip(overrides: Partial<SavedSentence> = {}): SavedSentence {
  return {
    id: 1,
    profile_id: 1,
    episode_id: 42,
    podcast_id: 7,
    name: 'Greeting',
    podcast_title: 'Nihongo News',
    episode_title: 'Episode One',
    text: 'こんにちは',
    start_time: 0,
    end_time: 2,
    audio_available: true,
    created_at: '2026-01-01T00:00:00Z',
    sentences: [
      { id: 101, index: 0, start_time: 0, end_time: 1, text: 'こんにちは', segments: [{ base: 'こんにちは', reading: '' }] },
      { id: 102, index: 1, start_time: 1, end_time: 2, text: '元気ですか', segments: [{ base: '元気ですか', reading: '' }] },
    ],
    ...overrides,
  };
}

function PlayerProbe() {
  const { podcastId, episodeId } = useParams();
  return <div data-testid="player-probe">{`${podcastId}/${episodeId}`}</div>;
}

function LibraryProbe() {
  useLocation();
  return <div data-testid="library-probe" />;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/saved-sentences']}>
      <ProfileProvider>
        <ToastProvider>
          <Routes>
            <Route path="/saved-sentences" element={<SavedSentences />} />
            <Route path="/library" element={<LibraryProbe />} />
            <Route
              path="/library/podcasts/:podcastId/episodes/:episodeId/player"
              element={<PlayerProbe />}
            />
          </Routes>
        </ToastProvider>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

describe('SavedSentences', () => {
  beforeEach(() => {
    localStorage.setItem('kotoba.profileId', '1');
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.audioUrl).mockImplementation((id) => `/api/episodes/${id}/audio`);
  });

  it('lists saved clips with series, episode, and text', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    renderPage();

    expect(await screen.findByText('Greeting')).toBeInTheDocument();
    expect(screen.getByText('Nihongo News · Episode One')).toBeInTheDocument();
    expect(screen.getByText('こんにちは')).toBeInTheDocument();
    expect(screen.getByText('1 saved clip')).toBeInTheDocument();
  });

  it('shows an empty state when there are no saved clips', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('No saved sentences yet')).toBeInTheDocument();
  });

  it('disables playback for clips whose episode audio is unavailable', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip({ audio_available: false })]);
    renderPage();

    const playBtn = await screen.findByTestId('play-saved-sentence-1');
    expect(playBtn).toBeDisabled();
  });

  it('play seeks to start_time and stops once end_time is reached', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    const playBtn = await screen.findByTestId('play-saved-sentence-1');
    await user.click(playBtn);

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    expect(audio.src).toContain('/api/episodes/42/audio');

    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(0);
    expect(playSpy).toHaveBeenCalled();

    const pauseSpy = vi.spyOn(audio, 'pause').mockImplementation(() => {});
    audio.currentTime = 2;
    fireEvent.timeUpdate(audio);
    expect(pauseSpy).toHaveBeenCalled();
  });

  it('loops back to start_time at end_time when repeat is enabled, instead of stopping', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId('repeat-toggle-1'));
    await user.click(await screen.findByTestId('play-saved-sentence-1'));

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    const pauseSpy = vi.spyOn(audio, 'pause').mockImplementation(() => {});
    fireEvent.loadedMetadata(audio);

    audio.currentTime = 2;
    fireEvent.timeUpdate(audio);

    expect(pauseSpy).not.toHaveBeenCalled();
    expect(audio.currentTime).toBe(0);
    // still "playing" (transcript stays expanded) rather than stopping
    expect(screen.getByTestId('clip-sentence-1-0')).toBeInTheDocument();
  });

  it('repeats only the selected sentence, not the whole clip', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId('play-saved-sentence-1'));

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    const pauseSpy = vi.spyOn(audio, 'pause').mockImplementation(() => {});
    fireEvent.loadedMetadata(audio);

    // sentence 0 spans [0, 1); enable repeat on it specifically.
    await user.click(await screen.findByTestId('repeat-sentence-1-0'));

    audio.currentTime = 1;
    fireEvent.timeUpdate(audio);

    expect(audio.currentTime).toBe(0);
    expect(pauseSpy).not.toHaveBeenCalled();
  });

  it('enabling sentence repeat clears an active clip repeat (mutually exclusive)', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId('repeat-toggle-1'));
    await user.click(await screen.findByTestId('play-saved-sentence-1'));

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    const pauseSpy = vi.spyOn(audio, 'pause').mockImplementation(() => {});
    fireEvent.loadedMetadata(audio);

    // Turning sentence repeat on for sentence 1 should clear clip-level repeat;
    // turning it back off leaves neither mode active.
    await user.click(await screen.findByTestId('repeat-sentence-1-1'));
    await user.click(screen.getByTestId('repeat-sentence-1-1'));

    audio.currentTime = 2;
    fireEvent.timeUpdate(audio);

    expect(pauseSpy).toHaveBeenCalled();
  });

  it('expands into a synced sentence transcript while playing and highlights the active sentence', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    const playBtn = await screen.findByTestId('play-saved-sentence-1');
    await user.click(playBtn);

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    fireEvent.loadedMetadata(audio);

    const firstRow = await screen.findByTestId('clip-sentence-1-0');
    const secondRow = screen.getByTestId('clip-sentence-1-1');
    expect(firstRow).toHaveAttribute('data-active', 'true');
    expect(secondRow).toHaveAttribute('data-active', 'false');

    audio.currentTime = 1.5;
    fireEvent.timeUpdate(audio);

    expect(firstRow).toHaveAttribute('data-active', 'false');
    expect(secondRow).toHaveAttribute('data-active', 'true');
  });

  it('renames a clip via the inline editor', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    vi.mocked(api.renameSavedSentence).mockResolvedValue(makeClip({ name: 'Hello there' }));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId('clip-name-1'));
    const input = screen.getByTestId('rename-input-1');
    await user.clear(input);
    await user.type(input, 'Hello there{Enter}');

    await waitFor(() => expect(api.renameSavedSentence).toHaveBeenCalledWith(1, 1, 'Hello there'));
    expect(await screen.findByText('Hello there')).toBeInTheDocument();
  });

  it('deletes a clip and refreshes the list', async () => {
    vi.mocked(api.listSavedSentences)
      .mockResolvedValueOnce([makeClip()])
      .mockResolvedValueOnce([]);
    vi.mocked(api.deleteSavedSentence).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId('delete-saved-sentence-1'));

    expect(api.deleteSavedSentence).toHaveBeenCalledWith(1, 1);
    expect(await screen.findByText('Deleted "Greeting"')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('No saved sentences yet')).toBeInTheDocument());
  });

  it('clicking the podcast/episode line navigates to that episode\'s player', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('Nihongo News · Episode One'));

    expect(await screen.findByTestId('player-probe')).toHaveTextContent('7/42');
  });

  it('keeps transcript unfurled when audio is paused', async () => {
    vi.mocked(api.listSavedSentences).mockResolvedValue([makeClip()]);
    const user = userEvent.setup();
    renderPage();

    const playBtn = await screen.findByTestId('play-saved-sentence-1');
    await user.click(playBtn);

    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    const pauseSpy = vi.spyOn(audio, 'pause').mockImplementation(() => {});
    fireEvent.loadedMetadata(audio);

    expect(screen.getByTestId('clip-sentence-1-0')).toBeInTheDocument();

    // Pause clip by clicking play/pause button again
    await user.click(playBtn);

    expect(pauseSpy).toHaveBeenCalled();
    // Transcript should remain unfurled even after pausing
    expect(screen.getByTestId('clip-sentence-1-0')).toBeInTheDocument();
  });

  it('minimizes previous transcript and unfurls new transcript when a different clip is played', async () => {
    const clip1 = makeClip({ id: 1, name: 'Clip 1', text: 'Clip 1 text' });
    const clip2 = makeClip({ id: 2, name: 'Clip 2', text: 'Clip 2 text' });
    vi.mocked(api.listSavedSentences).mockResolvedValue([clip1, clip2]);
    const user = userEvent.setup();
    renderPage();

    // Play Clip 1
    await user.click(await screen.findByTestId('play-saved-sentence-1'));
    const audio = screen.getByTestId('saved-sentence-audio') as HTMLAudioElement;
    Object.defineProperty(audio, 'duration', { value: 10, configurable: true });
    vi.spyOn(audio, 'play').mockResolvedValue();
    fireEvent.loadedMetadata(audio);

    // Clip 1 transcript is expanded, Clip 2 is minimized
    expect(screen.getByTestId('clip-sentence-1-0')).toBeInTheDocument();
    expect(screen.queryByTestId('clip-sentence-2-0')).not.toBeInTheDocument();

    // Play Clip 2
    await user.click(screen.getByTestId('play-saved-sentence-2'));
    fireEvent.loadedMetadata(audio);

    // Clip 1 transcript is minimized, Clip 2 transcript is expanded
    expect(screen.queryByTestId('clip-sentence-1-0')).not.toBeInTheDocument();
    expect(screen.getByTestId('clip-sentence-2-0')).toBeInTheDocument();
  });
});
