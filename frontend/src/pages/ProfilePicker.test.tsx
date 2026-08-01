import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfilePicker } from './ProfilePicker';
import { ProfileProvider } from '../state/ProfileContext';
import { api } from '../lib/api';
import type { PackStatus, Profile } from '../lib/types';

// The prompt polls via window.setInterval every 800ms — capture the callback
// and invoke it manually instead of juggling fake timers (see AsrSetup.test.tsx
// for the same pattern and rationale).
function captureIntervalCallback() {
  let callback: (() => void | Promise<void>) | null = null;
  vi.spyOn(window, 'setInterval').mockImplementation(((fn: () => void) => {
    callback = fn;
    return 1 as unknown as number;
  }) as typeof window.setInterval);
  vi.spyOn(window, 'clearInterval').mockImplementation(() => {});
  return {
    tick: async () => {
      await act(async () => {
        await callback?.();
      });
    },
  };
}

vi.mock('../lib/api');

function renderPicker() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ProfileProvider>
        <Routes>
          <Route path="/" element={<ProfilePicker />} />
          <Route path="/library" element={<div>Library page</div>} />
        </Routes>
      </ProfileProvider>
    </MemoryRouter>,
  );
}

const existingProfile: Profile = {
  id: 1,
  name: 'Kenji',
  palette_index: 0,
  learning_language: 'ja',
  show_furigana: true,
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
};

describe('ProfilePicker', () => {
  beforeEach(() => {
    vi.mocked(api.listProfiles).mockResolvedValue([]);
    vi.mocked(api.getStreak).mockResolvedValue({ streak: 0 });
    vi.mocked(api.listModels).mockResolvedValue([
      { name: 'tiny', size_bytes: 1, installed: true, active: false },
      { name: 'base', size_bytes: 1, installed: false, active: true },
      { name: 'small', size_bytes: 1, installed: false, active: false },
    ]);
    vi.mocked(api.listPacks).mockResolvedValue([{ name: 'japanese', download_size_bytes: 1, installed: true }]);
    vi.mocked(api.updateProfile).mockResolvedValue(existingProfile);
    localStorage.setItem('kotoba.asrSetupSeen', '1');
  });

  it('lists existing profiles and lets the user open the create form', async () => {
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile]);
    renderPicker();

    expect(await screen.findByText('Kenji')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Add learner'));

    expect(screen.getByText('Create a learner')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. Kenji')).toBeInTheDocument();
  });

  it('redirects straight to /library when the stored profile id matches an existing profile', async () => {
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile]);
    localStorage.setItem('kotoba.profileId', String(existingProfile.id));
    renderPicker();

    expect(await screen.findByText('Library page')).toBeInTheDocument();
    expect(screen.queryByText('Choose a profile')).not.toBeInTheDocument();
  });

  it('redirects straight to /library using the last-used profile when no id is stored', async () => {
    const otherProfile: Profile = { ...existingProfile, id: 2, name: 'Aoi', last_used_at: '2026-01-05T00:00:00Z' };
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile, otherProfile]);
    renderPicker();

    expect(await screen.findByText('Library page')).toBeInTheDocument();
    expect(screen.queryByText('Choose a profile')).not.toBeInTheDocument();
  });

  it('shows the picker when no profile has ever been used and none is stored', async () => {
    vi.mocked(api.listProfiles).mockResolvedValue([existingProfile]);
    renderPicker();

    expect(await screen.findByText('Choose a profile')).toBeInTheDocument();
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
      learning_language: 'ja',
      show_furigana: true,
      created_at: '2026-01-02T00:00:00Z',
      last_used_at: null,
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
      learning_language: 'ja',
      show_furigana: true,
    });
  });

  it('prompts to install the Japanese pack after creating a Japanese profile when it is missing', async () => {
    const created: Profile = {
      id: 2,
      name: 'Aoi',
      palette_index: 2,
      learning_language: 'ja',
      show_furigana: true,
      created_at: '2026-01-02T00:00:00Z',
      last_used_at: null,
    };
    vi.mocked(api.createProfile).mockResolvedValue(created);
    vi.mocked(api.listPacks).mockResolvedValue([{ name: 'japanese', download_size_bytes: 47_000_000, installed: false }]);
    renderPicker();

    await userEvent.click(await screen.findByText('Add learner'));
    await userEvent.type(screen.getByPlaceholderText('e.g. Kenji'), 'Aoi');
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }));

    expect(await screen.findByTestId('japanese-pack-prompt')).toBeInTheDocument();
    expect(screen.getByText(/47 MB/)).toBeInTheDocument();
  });

  it('never prompts for an English profile even when the pack is missing', async () => {
    const created: Profile = {
      id: 2,
      name: 'Kenji2',
      palette_index: 2,
      learning_language: 'en',
      show_furigana: true,
      created_at: '2026-01-02T00:00:00Z',
      last_used_at: null,
    };
    vi.mocked(api.createProfile).mockResolvedValue(created);
    vi.mocked(api.listPacks).mockResolvedValue([{ name: 'japanese', download_size_bytes: 1, installed: false }]);
    vi.mocked(api.listPacks).mockClear();
    renderPicker();

    await userEvent.click(await screen.findByText('Add learner'));
    await userEvent.click(screen.getByText('🇺🇸').closest('button')!);
    await userEvent.type(screen.getByPlaceholderText('e.g. Kenji'), 'Kenji2');
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }));

    await waitFor(() => expect(api.createProfile).toHaveBeenCalled());
    expect(screen.queryByTestId('japanese-pack-prompt')).not.toBeInTheDocument();
    expect(api.listPacks).not.toHaveBeenCalled();
  });

  it('never prompts for the Japanese pack and hides the furigana toggle for a Spanish, French, or Korean profile', async () => {
    renderPicker();

    await userEvent.click(await screen.findByText('Add learner'));
    expect(screen.getByText('Show furigana over kanji')).toBeInTheDocument();

    await userEvent.click(screen.getByText('🇪🇸').closest('button')!);
    expect(screen.queryByText('Show furigana over kanji')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('🇫🇷').closest('button')!);
    expect(screen.queryByText('Show furigana over kanji')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('🇰🇷').closest('button')!);
    expect(screen.queryByText('Show furigana over kanji')).not.toBeInTheDocument();
  });

  it('installs the pack from the prompt and shows progress to completion', async () => {
    const created: Profile = {
      id: 2,
      name: 'Aoi',
      palette_index: 2,
      learning_language: 'ja',
      show_furigana: true,
      created_at: '2026-01-02T00:00:00Z',
      last_used_at: null,
    };
    vi.mocked(api.createProfile).mockResolvedValue(created);
    vi.mocked(api.listPacks).mockResolvedValue([{ name: 'japanese', download_size_bytes: 47_000_000, installed: false }]);
    vi.mocked(api.installPack).mockResolvedValue({ name: 'japanese', download_size_bytes: 47_000_000, installed: false });
    const statuses: PackStatus[] = [
      { state: 'downloading', bytes_done: 0, bytes_total: 47_000_000, error: null },
      { state: 'installed', bytes_done: 47_000_000, bytes_total: 47_000_000, error: null },
    ];
    let call = 0;
    vi.mocked(api.getPackStatus).mockImplementation(() =>
      Promise.resolve(statuses[Math.min(call++, statuses.length - 1)]),
    );
    const interval = captureIntervalCallback();

    renderPicker();
    await userEvent.click(await screen.findByText('Add learner'));
    await userEvent.type(screen.getByPlaceholderText('e.g. Kenji'), 'Aoi');
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }));

    await screen.findByTestId('japanese-pack-prompt');
    await userEvent.click(screen.getByRole('button', { name: 'Install' }));
    expect(api.installPack).toHaveBeenCalledWith('japanese');

    await interval.tick();
    expect(screen.getByTestId('pack-prompt-progress')).toBeInTheDocument();

    await interval.tick();
    expect(await screen.findByText('Reading pack installed')).toBeInTheDocument();
  });
});
