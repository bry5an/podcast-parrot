import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../lib/api';
import type { TranscriptStatus } from '../lib/types';
import { useToast } from './ToastContext';

interface TranscriptionContextValue {
  statuses: Record<number, TranscriptStatus>;
  track: (episodeId: number, title: string) => void;
  untrack: (episodeId: number) => void;
}

const TranscriptionContext = createContext<TranscriptionContextValue | null>(null);

const POLL_INTERVAL_MS = 1200;
const MAX_CONSECUTIVE_ERRORS = 5;

export function TranscriptionProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const [statuses, setStatuses] = useState<Record<number, TranscriptStatus>>({});
  const timers = useRef<Record<number, number>>({});

  useEffect(() => {
    const activeTimers = timers.current;
    return () => {
      Object.values(activeTimers).forEach((t) => window.clearInterval(t));
    };
  }, []);

  const clearTimer = useCallback((episodeId: number) => {
    window.clearInterval(timers.current[episodeId]);
    delete timers.current[episodeId];
  }, []);

  const untrack = useCallback(
    (episodeId: number) => {
      clearTimer(episodeId);
      setStatuses((prev) => {
        if (!(episodeId in prev)) return prev;
        const next = { ...prev };
        delete next[episodeId];
        return next;
      });
    },
    [clearTimer],
  );

  const track = useCallback(
    (episodeId: number, title: string) => {
      if (timers.current[episodeId]) return;
      setStatuses((prev) => ({ ...prev, [episodeId]: 'pending' }));

      let consecutiveErrors = 0;
      const timer = window.setInterval(async () => {
        try {
          const status = await api.getEpisodeStatus(episodeId);
          consecutiveErrors = 0;
          if (status.transcript_status !== 'pending') {
            clearTimer(episodeId);
            // Keep the terminal status in place (rather than clearing it) so the
            // page can render the right badge/button without an extra refetch.
            setStatuses((prev) => ({ ...prev, [episodeId]: status.transcript_status }));
            if (status.transcript_status === 'failed') {
              showToast(`Transcription failed: ${title}`, 'error');
            } else if (status.transcript_status === 'canceled') {
              showToast(`Transcription canceled: ${title}`);
            } else {
              showToast(`Transcription complete: ${title}`, 'success');
            }
          } else {
            setStatuses((prev) => ({ ...prev, [episodeId]: 'pending' }));
          }
        } catch {
          consecutiveErrors += 1;
          if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
            clearTimer(episodeId);
            setStatuses((prev) => ({ ...prev, [episodeId]: 'failed' }));
            showToast(`Transcription failed: ${title}`, 'error');
          }
        }
      }, POLL_INTERVAL_MS);
      timers.current[episodeId] = timer;
    },
    [showToast, clearTimer],
  );

  return (
    <TranscriptionContext.Provider value={{ statuses, track, untrack }}>{children}</TranscriptionContext.Provider>
  );
}

export function useTranscriptions() {
  const ctx = useContext(TranscriptionContext);
  if (!ctx) throw new Error('useTranscriptions must be used within a TranscriptionProvider');
  return ctx;
}
