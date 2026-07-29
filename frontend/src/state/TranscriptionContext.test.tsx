import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from './ToastContext';
import { TranscriptionProvider, useTranscriptions } from './TranscriptionContext';
import { api } from '../lib/api';
import type { EpisodeStatus } from '../lib/types';

vi.mock('../lib/api');

function Probe({ episodeId, title }: { episodeId: number; title: string }) {
  const { statuses, track } = useTranscriptions();
  return (
    <div>
      <button onClick={() => track(episodeId, title)}>track</button>
      <div data-testid="status">{statuses[episodeId] ?? 'untracked'}</div>
    </div>
  );
}

function renderProbe(episodeId = 1, title = 'Episode') {
  return render(
    <ToastProvider>
      <TranscriptionProvider>
        <Probe episodeId={episodeId} title={title} />
      </TranscriptionProvider>
    </ToastProvider>,
  );
}

describe('TranscriptionContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reaches a terminal status, updates state, and fires a success toast', async () => {
    vi.mocked(api.getEpisodeStatus).mockResolvedValue({
      id: 1,
      download_status: 'downloaded',
      transcript_status: 'full',
    } satisfies EpisodeStatus);

    renderProbe(1, 'My Episode');
    fireEvent.click(screen.getByText('track'));

    expect(screen.getByTestId('status')).toHaveTextContent('pending');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });

    expect(screen.getByTestId('status')).toHaveTextContent('full');
    expect(await screen.findByText('Transcription complete: My Episode')).toBeInTheDocument();

    const callsAfterCompletion = vi.mocked(api.getEpisodeStatus).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });
    expect(vi.mocked(api.getEpisodeStatus).mock.calls.length).toBe(callsAfterCompletion);
  });

  it('fires an error toast when the server reports a failed transcription', async () => {
    vi.mocked(api.getEpisodeStatus).mockResolvedValue({
      id: 1,
      download_status: 'downloaded',
      transcript_status: 'failed',
    } satisfies EpisodeStatus);

    renderProbe(1, 'My Episode');
    fireEvent.click(screen.getByText('track'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });

    expect(screen.getByTestId('status')).toHaveTextContent('failed');
    expect(await screen.findByText('Transcription failed: My Episode')).toBeInTheDocument();
  });

  it('treats 5 consecutive status-check errors as a failure and stops polling', async () => {
    vi.mocked(api.getEpisodeStatus).mockRejectedValue(new Error('network error'));

    renderProbe(1, 'My Episode');
    fireEvent.click(screen.getByText('track'));

    await act(async () => {
      for (let i = 0; i < 5; i += 1) {
        await vi.advanceTimersByTimeAsync(1200);
      }
    });

    expect(screen.getByTestId('status')).toHaveTextContent('failed');
    expect(await screen.findByText('Transcription failed: My Episode')).toBeInTheDocument();

    const callsAfterCap = vi.mocked(api.getEpisodeStatus).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });
    expect(vi.mocked(api.getEpisodeStatus).mock.calls.length).toBe(callsAfterCap);
  });

  it('does not start a second poll when track is called twice for the same episode', async () => {
    vi.mocked(api.getEpisodeStatus).mockResolvedValue({
      id: 1,
      download_status: 'downloaded',
      transcript_status: 'pending',
    } satisfies EpisodeStatus);

    renderProbe(1, 'My Episode');
    fireEvent.click(screen.getByText('track'));
    fireEvent.click(screen.getByText('track'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });

    expect(vi.mocked(api.getEpisodeStatus).mock.calls.length).toBe(1);
  });
});
