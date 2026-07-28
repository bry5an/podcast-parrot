import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfilePicker } from './ProfilePicker';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import type { Profile } from '../lib/types';

vi.mock('../lib/api');

function renderPicker() {
  return render(
    <MemoryRouter>
      <ProfileProvider>
        <ProfilePicker />
      </ProfileProvider>
    </MemoryRouter>,
  );
}

const existingProfile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  direction: 'en_ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('ProfilePicker', () => {
  beforeEach(() => {
    vi.mocked(api.listProfiles).mockResolvedValue([]);
    vi.mocked(api.getStreak).mockResolvedValue({ streak: 0 });
  });

  it('lists existing profiles and lets the user open the create form', async () => {
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile]);
    renderPicker();

    expect(await screen.findByText('Kenji')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Add learner'));

    expect(screen.getByText('Create a learner')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. Kenji')).toBeInTheDocument();
  });

  it('shows a streak subline for a profile with an active streak, and none for a zero streak', async () => {
    const otherProfile: Profile = { ...existingProfile, id: 2, name: 'Aoi' };
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile, otherProfile]);
    vi.mocked(api.getStreak).mockImplementation((id) =>
      Promise.resolve({ streak: id === existingProfile.id ? 5 : 0 }),
    );
    renderPicker();

    await screen.findByText('Kenji');
    expect(await screen.findByTestId(`streak-${existingProfile.id}`)).toHaveTextContent('5 days streak');
    expect(screen.queryByTestId(`streak-${otherProfile.id}`)).not.toBeInTheDocument();
  });

  it('disables submit until a name is entered, then creates the profile', async () => {
    const created: Profile = {
      id: 2,
      name: 'Aoi',
      palette_index: 2,
      direction: 'en_ja',
      show_furigana: true,
      created_at: '2026-01-02T00:00:00Z',
    };
    vi.mocked(api.createProfile).mockResolvedValue(created);
    renderPicker();

    await userEvent.click(await screen.findByText('Add learner'));

    const submit = screen.getByRole('button', { name: 'Create profile' });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByPlaceholderText('e.g. Kenji'), 'Aoi');
    expect(submit).toBeEnabled();

    await userEvent.click(submit);

    expect(api.createProfile).toHaveBeenCalledWith({
      name: 'Aoi',
      palette_index: 2,
      direction: 'en_ja',
      show_furigana: true,
    });
  });
});
