import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Library } from './Library';
import { ProfileProvider } from '../state/ProfileContext';
import { ToastProvider } from '../state/ToastContext';
import { api } from '../lib/api';
import type { Podcast, Profile } from '../lib/types';

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
  id: 7,
  rss_url: 'https://example.com/feed.xml',
  youtube_playlist_url: null,
  local_directory_path: null,
  kind: 'rss',
  title: 'Nihongo News',
  description: 'Daily Japanese news',
  artwork_url: null,
  language: 'ja',
  level_tag: null,
  source: 'curated',
  subscribed: true,
};

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <ProfileProvider>
        <ToastProvider>
          <Routes>
            <Route path="/library" element={<Library />} />
            <Route path="/settings" element={<div data-testid="settings-stub" />} />
            <Route path="/" element={<div data-testid="picker-stub" />} />
          </Routes>
        </ToastProvider>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

describe('Library profile menu', () => {
  beforeEach(() => {
    localStorage.setItem('kotoba.profileId', '1');
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.listSubscriptions).mockResolvedValue([]);
  });

  it('is closed until the profile card is clicked', async () => {
    renderLibrary();
    await screen.findByText('Kenji');
    expect(screen.queryByTestId('profile-menu')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('Kenji'));
    expect(screen.getByTestId('profile-menu')).toBeInTheDocument();
  });

  it('navigates to /settings from the Settings menu item', async () => {
    renderLibrary();
    await userEvent.click(await screen.findByText('Kenji'));

    await userEvent.click(screen.getByRole('button', { name: /Settings/ }));
    expect(await screen.findByTestId('settings-stub')).toBeInTheDocument();
  });

  it('clears the profile and returns to the picker from Switch profile', async () => {
    renderLibrary();
    await userEvent.click(await screen.findByText('Kenji'));

    await userEvent.click(screen.getByRole('button', { name: /Switch profile/ }));
    expect(await screen.findByTestId('picker-stub')).toBeInTheDocument();
    expect(localStorage.getItem('kotoba.profileId')).toBeNull();
  });
});

describe('Library delete feed', () => {
  beforeEach(() => {
    localStorage.setItem('kotoba.profileId', '1');
    vi.mocked(api.listProfiles).mockResolvedValue([profile]);
    vi.mocked(api.listSubscriptions).mockResolvedValue([podcast]);
  });

  it('does not call deleteFeed when the confirmation is canceled', async () => {
    renderLibrary();
    await userEvent.click(await screen.findByTitle('Delete feed'));
    const dialog = await screen.findByRole('alertdialog');

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(api.deleteFeed).not.toHaveBeenCalled();
  });

  it('calls deleteFeed and refreshes the list on confirm', async () => {
    vi.mocked(api.deleteFeed).mockResolvedValue(undefined);
    renderLibrary();
    await userEvent.click(await screen.findByTitle('Delete feed'));
    const dialog = await screen.findByRole('alertdialog');

    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete feed' }));
    expect(api.deleteFeed).toHaveBeenCalledWith(1, 7);
    expect(await screen.findByText(/Deleted/)).toBeInTheDocument();
    const callsAfterDelete = vi.mocked(api.listSubscriptions).mock.calls.length;
    expect(callsAfterDelete).toBeGreaterThan(1);
  });
});
