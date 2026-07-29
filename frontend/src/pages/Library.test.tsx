import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Library } from './Library';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
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

function renderLibrary() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <ProfileProvider>
        <Routes>
          <Route path="/library" element={<Library />} />
          <Route path="/settings" element={<div data-testid="settings-stub" />} />
          <Route path="/" element={<div data-testid="picker-stub" />} />
        </Routes>
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
