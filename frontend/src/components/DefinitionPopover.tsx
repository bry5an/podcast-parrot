import { useEffect, useRef } from 'react';
import type { DictionaryEntry } from '../lib/types';

const POPOVER_WIDTH = 280;

interface DefinitionPopoverProps {
  x: number;
  y: number;
  word: string;
  loading: boolean;
  error: string | null;
  entry: DictionaryEntry | null;
  onClose: () => void;
}

export function DefinitionPopover({ x, y, word, loading, error, entry, onClose }: DefinitionPopoverProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('mousedown', onMouseDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  const left = Math.max(8, Math.min(x, window.innerWidth - POPOVER_WIDTH - 8));
  const top = Math.max(8, y + 16);

  return (
    <div
      ref={ref}
      data-testid="definition-popover"
      style={{ ...popoverStyle, left, top, width: POPOVER_WIDTH }}
    >
      <div style={headerStyle}>
        <span style={{ font: '600 14px/1.3 "IBM Plex Sans", sans-serif' }}>{word}</span>
        <button onClick={onClose} style={closeBtnStyle} aria-label="Close" data-testid="definition-popover-close">
          <svg width="11" height="11" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="M5 5l10 10M15 5L5 15" />
          </svg>
        </button>
      </div>
      {loading && <div style={statusStyle}>Loading…</div>}
      {error && <div style={statusStyle}>{error}</div>}
      {entry && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
          {entry.reading && <div style={readingStyle}>{entry.reading}</div>}
          {entry.senses.map((sense, i) => (
            <div key={i}>
              {sense.part_of_speech && <div style={posStyle}>{sense.part_of_speech}</div>}
              <div style={definitionStyle}>{sense.definitions.join('; ')}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const popoverStyle: React.CSSProperties = {
  position: 'fixed',
  zIndex: 1100,
  background: '#fff',
  borderRadius: 12,
  border: '1px solid rgba(32,30,26,.1)',
  boxShadow: '0 8px 24px rgba(0,0,0,.18)',
  padding: '12px 14px',
  color: '#211f1b',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
};

const closeBtnStyle: React.CSSProperties = {
  flex: 'none',
  border: 'none',
  background: 'none',
  color: 'rgba(32,30,26,.5)',
  cursor: 'pointer',
  padding: 2,
  display: 'flex',
};

const statusStyle: React.CSSProperties = {
  marginTop: 6,
  font: '500 12.5px/1.4 "IBM Plex Sans", sans-serif',
  color: 'rgba(32,30,26,.55)',
};

const readingStyle: React.CSSProperties = {
  font: '500 12.5px/1 "IBM Plex Mono", monospace',
  color: 'rgba(32,30,26,.55)',
};

const posStyle: React.CSSProperties = {
  font: '600 10.5px/1 IBM Plex Mono',
  color: 'rgba(32,30,26,.45)',
  textTransform: 'uppercase',
  letterSpacing: '.05em',
  marginBottom: 3,
};

const definitionStyle: React.CSSProperties = {
  font: '400 13px/1.5 "IBM Plex Sans", sans-serif',
};
