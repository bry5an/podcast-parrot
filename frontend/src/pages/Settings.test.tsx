import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Settings } from './Settings';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import { loadAutoAdvance, loadKeymap, loadPlaybackSpeed, loadSeekStepSeconds } from '../lib/keybindings';
import { loadDimInactiveLines, loadShowRomaji } from '../lib/readingAids';
import type { Profile } from '../lib/types';

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

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <ProfileProvider>
        <Routes>
          <Route path="/settings" element={<Settings />} />
          <Route path="/library" element={<div data-testid="library-stub" />} />
        </Routes>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

describe('Settings', () => {
  beforeEach(() => {
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.getStorageStats).mockResolvedValue({
      bytes_used: 0,
      episode_count: 0,
      storage_root: '/tmp/storage',
      transcript_bytes: 0,
    });
    vi.mocked(api.getSettings).mockResolvedValue({
      auto_remove: 'never',
      storage_root: '/tmp/storage',
      compute_device: 'gpu',
      cache_transcripts: true,
    });
    vi.mocked(api.updateSettings).mockResolvedValue({
      auto_remove: 'never',
      storage_root: '/tmp/storage',
      compute_device: 'gpu',
      cache_transcripts: true,
    });
    vi.mocked(api.updateProfile).mockResolvedValue({ ...profile, show_furigana: false });
    vi.mocked(api.listModels).mockResolvedValue([
      { name: 'tiny', size_bytes: 77_691_713, installed: true, active: false },
      { name: 'base', size_bytes: 147_951_465, installed: true, active: true },
      { name: 'small', size_bytes: 487_601_967, installed: false, active: false },
    ]);
    vi.mocked(api.downloadModel).mockResolvedValue({ name: 'small', size_bytes: 487_601_967, installed: false, active: false });
    vi.mocked(api.getModelStatus).mockResolvedValue({ state: 'installed', bytes_done: 487_601_967, bytes_total: 487_601_967, error: null });
  });

  it('renders all five sections once a profile is loaded', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();

    expect(await screen.findByRole('heading', { name: 'Playback & keybindings' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Transcription' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reading aids' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Library & storage' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
  });

  it('redirects to /library when there is no current profile', async () => {
    renderSettings();
    expect(await screen.findByTestId('library-stub')).toBeInTheDocument();
  });

  it('marks the clicked sub-nav item active', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const playbackNav = screen.getByRole('button', { name: 'Playback & keys' });
    const transcriptionNav = screen.getByRole('button', { name: 'Transcription' });
    expect(playbackNav).toHaveAttribute('aria-current', 'true');
    expect(transcriptionNav).not.toHaveAttribute('aria-current');

    await userEvent.click(transcriptionNav);
    expect(transcriptionNav).toHaveAttribute('aria-current', 'true');
    expect(playbackNav).not.toHaveAttribute('aria-current');
  });

  it('toggles a segmented control selection on click and persists it', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const defaultSpeed = screen.getByRole('button', { name: '1.0×' });
    const fasterSpeed = screen.getByRole('button', { name: '1.25×' });
    expect(defaultSpeed).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(fasterSpeed);
    expect(fasterSpeed).toHaveAttribute('aria-pressed', 'true');
    expect(defaultSpeed).toHaveAttribute('aria-pressed', 'false');
    expect(loadPlaybackSpeed()).toBe('1.25x');
  });

  it('flips a toggle switch on click and persists it', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const autoAdvance = screen.getByRole('switch', { name: 'Auto-advance to next sentence' });
    expect(autoAdvance).toHaveAttribute('aria-checked', 'true');

    await userEvent.click(autoAdvance);
    expect(autoAdvance).toHaveAttribute('aria-checked', 'false');
    expect(loadAutoAdvance()).toBe(false);
  });

  it('renders the real Whisper model catalog with the active model marked', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Transcription' });

    const base = await screen.findByRole('button', { name: /base/i });
    const small = screen.getByRole('button', { name: /small/i });
    expect(base).toHaveAttribute('aria-pressed', 'true');
    expect(small).toHaveAttribute('aria-pressed', 'false');
  });

  it('downloads and activates an uninstalled model on click', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Transcription' });

    const small = await screen.findByRole('button', { name: /small/i });
    await userEvent.click(small);

    expect(api.downloadModel).toHaveBeenCalledWith('small');
  });

  it('persists the compute device selection via the API', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Transcription' });

    await userEvent.click(screen.getByRole('button', { name: 'CPU' }));
    expect(api.updateSettings).toHaveBeenCalledWith({ compute_device: 'cpu' });
  });

  it('persists the cache-transcripts toggle via the API', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Transcription' });

    await userEvent.click(screen.getByRole('switch', { name: 'Cache generated transcripts' }));
    expect(api.updateSettings).toHaveBeenCalledWith({ cache_transcripts: false });
  });

  it('navigates back to /library from the back chevron', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    await userEvent.click(screen.getByRole('button', { name: 'Settings' }));
    expect(await screen.findByTestId('library-stub')).toBeInTheDocument();
  });

  it('captures a rebind for a keybinding badge and persists it', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const badge = screen.getByRole('button', { name: 'Space' });
    await userEvent.click(badge);
    expect(badge).toHaveTextContent('Press a key…');

    fireEvent.keyDown(window, { key: 'p' });
    expect(badge).toHaveTextContent('P');
    expect(loadKeymap().playPause).toBe('p');
  });

  it('cancels a rebind on Escape without changing the binding', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const badge = screen.getByRole('button', { name: 'R' });
    await userEvent.click(badge);
    expect(badge).toHaveTextContent('Press a key…');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(badge).toHaveTextContent('R');
    expect(loadKeymap().replaySentence).toBe('r');
  });

  it('rebinds the seek modifier only from a modifier keypress, ignoring other keys', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const badge = screen.getByRole('button', { name: '⇧ ←/→' });
    await userEvent.click(badge);

    fireEvent.keyDown(window, { key: 'x' });
    expect(badge).toHaveTextContent('Press a key…');

    fireEvent.keyDown(window, { key: 'Alt', altKey: true });
    expect(badge).toHaveTextContent('⌥ ←/→');
    expect(loadKeymap().seekModifier).toBe('alt');
  });

  it('persists the seek step selection', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    await userEvent.click(screen.getByRole('button', { name: '10s' }));
    expect(loadSeekStepSeconds()).toBe(10);
  });

  it('persists the furigana toggle via the API', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Reading aids' });

    const furigana = screen.getByRole('switch', { name: 'Furigana over kanji' });
    expect(furigana).toHaveAttribute('aria-checked', 'true');

    await userEvent.click(furigana);
    expect(api.updateProfile).toHaveBeenCalledWith(1, { show_furigana: false });
  });

  it('persists the romaji and dim-inactive toggles to localStorage', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Reading aids' });

    await userEvent.click(screen.getByRole('switch', { name: 'Romaji fallback' }));
    expect(loadShowRomaji()).toBe(true);

    await userEvent.click(screen.getByRole('switch', { name: 'Dim inactive lines' }));
    expect(loadDimInactiveLines()).toBe(false);
  });

  it('renders real storage usage and download location from the API', async () => {
    vi.mocked(api.getStorageStats).mockResolvedValue({
      bytes_used: 2_400_000_000,
      episode_count: 38,
      storage_root: '/tmp/storage',
      transcript_bytes: 4_200_000,
    });
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();

    expect(await screen.findByText('2.2 GB · 38 episodes')).toBeInTheDocument();
    expect(screen.getByText('/tmp/storage')).toBeInTheDocument();
    expect(screen.getByText('Audio: 2.2 GB · Transcripts: 4 MB')).toBeInTheDocument();
  });

  it('persists the auto-remove policy via the API', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByText('/tmp/storage');

    await userEvent.click(screen.getByRole('button', { name: '30 days' }));

    expect(api.updateSettings).toHaveBeenCalledWith({ auto_remove: '30d' });
  });
});
