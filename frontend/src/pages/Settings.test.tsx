import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Settings } from './Settings';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import { loadKeymap, loadSeekStepSeconds } from '../lib/keybindings';
import type { Profile } from '../lib/types';

vi.mock('../lib/api');

const profile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  direction: 'en_ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
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

  it('toggles a segmented control selection on click', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const defaultSpeed = screen.getByRole('button', { name: '1.0×' });
    const fasterSpeed = screen.getByRole('button', { name: '1.25×' });
    expect(defaultSpeed).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(fasterSpeed);
    expect(fasterSpeed).toHaveAttribute('aria-pressed', 'true');
    expect(defaultSpeed).toHaveAttribute('aria-pressed', 'false');
  });

  it('flips a toggle switch on click', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Playback & keybindings' });

    const autoAdvance = screen.getByRole('switch', { name: 'Auto-advance to next sentence' });
    expect(autoAdvance).toHaveAttribute('aria-checked', 'true');

    await userEvent.click(autoAdvance);
    expect(autoAdvance).toHaveAttribute('aria-checked', 'false');
  });

  it('selects a different Whisper model card on click', async () => {
    localStorage.setItem('kotoba.profileId', '1');
    renderSettings();
    await screen.findByRole('heading', { name: 'Transcription' });

    const small = screen.getByRole('button', { name: /Small/ });
    const medium = screen.getByRole('button', { name: /Medium/ });
    expect(small).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(medium);
    expect(medium).toHaveAttribute('aria-pressed', 'true');
    expect(small).toHaveAttribute('aria-pressed', 'false');
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
});
