import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ASR_SETUP_SEEN_KEY, AsrSetup } from './AsrSetup';
import { api } from '../lib/api';
import type { WhisperModel, WhisperModelStatus } from '../lib/types';

vi.mock('../lib/api');

const models: WhisperModel[] = [
  { name: 'tiny', size_bytes: 77_691_713, installed: false, active: false },
  { name: 'base', size_bytes: 147_951_465, installed: false, active: true },
  { name: 'small', size_bytes: 487_601_967, installed: false, active: false },
];

function renderSetup() {
  return render(
    <MemoryRouter initialEntries={['/setup']}>
      <Routes>
        <Route path="/setup" element={<AsrSetup />} />
        <Route path="/" element={<div>Profile picker stub</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// The component polls via window.setInterval every 800ms. Rather than juggling
// fake-timer/microtask interleaving for a single new-to-this-codebase test
// pattern, capture the interval callback and invoke it manually — the polling
// cadence itself isn't business logic worth testing, just that each tick
// applies the latest status and stops on a terminal state.
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

describe('AsrSetup', () => {
  beforeEach(() => {
    vi.mocked(api.listModels).mockResolvedValue(models);
  });

  it('renders each model size with the recommended tag on base', async () => {
    renderSetup();

    expect(await screen.findByTestId('model-card-base')).toHaveTextContent('Recommended');
    expect(screen.getByTestId('model-card-tiny')).toHaveTextContent('78 MB');
    expect(screen.getByTestId('model-card-small')).toHaveTextContent('488 MB');
  });

  it('skips without downloading anything, and remembers the skip', async () => {
    const user = userEvent.setup();
    renderSetup();

    await screen.findByTestId('model-card-base');
    await user.click(screen.getByText('Skip for now'));

    expect(await screen.findByText('Profile picker stub')).toBeInTheDocument();
    expect(localStorage.getItem(ASR_SETUP_SEEN_KEY)).toBe('1');
    expect(api.downloadModel).not.toHaveBeenCalled();
  });

  it('downloads a model, polls progress, and finishes on install', async () => {
    const user = userEvent.setup();
    const interval = captureIntervalCallback();
    vi.mocked(api.downloadModel).mockResolvedValue(models[1]);

    const statuses: WhisperModelStatus[] = [
      { state: 'downloading', bytes_done: 0, bytes_total: 147_951_465, error: null },
      { state: 'downloading', bytes_done: 70_000_000, bytes_total: 147_951_465, error: null },
      { state: 'installed', bytes_done: 147_951_465, bytes_total: 147_951_465, error: null },
    ];
    let call = 0;
    vi.mocked(api.getModelStatus).mockImplementation(() =>
      Promise.resolve(statuses[Math.min(call++, statuses.length - 1)]),
    );

    renderSetup();
    await screen.findByTestId('model-card-base');

    const baseCard = screen.getByTestId('model-card-base');
    await user.click(within(baseCard).getByRole('button', { name: 'Download' }));

    expect(api.downloadModel).toHaveBeenCalledWith('base');

    await interval.tick();
    expect(screen.getByText('Downloading…')).toBeInTheDocument();
    expect(screen.getByTestId('progress-base')).toBeInTheDocument();

    await interval.tick();
    await interval.tick();

    expect(await screen.findByTestId('asr-setup-done')).toBeInTheDocument();
    expect(api.getModelStatus).toHaveBeenCalledWith('base');

    await user.click(screen.getByText('Continue'));
    expect(await screen.findByText('Profile picker stub')).toBeInTheDocument();
    expect(localStorage.getItem(ASR_SETUP_SEEN_KEY)).toBe('1');
  });

  it('shows a distinct error message per failure reason and allows retry', async () => {
    const user = userEvent.setup();
    const interval = captureIntervalCallback();
    vi.mocked(api.downloadModel).mockResolvedValue(models[0]);
    vi.mocked(api.getModelStatus).mockResolvedValue({
      state: 'failed',
      bytes_done: 0,
      bytes_total: 77_691_713,
      error: 'offline',
    });

    renderSetup();
    const tinyCard = await screen.findByTestId('model-card-tiny');
    await user.click(within(tinyCard).getByRole('button', { name: 'Download' }));
    await interval.tick();

    expect(await screen.findByTestId('asr-setup-error')).toHaveTextContent(/Couldn't reach the download server/);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
