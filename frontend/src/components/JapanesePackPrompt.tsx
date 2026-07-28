import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { DOWNLOAD_ERROR_MESSAGES } from '../lib/downloadErrors';
import type { PackStatus } from '../lib/types';

interface Props {
  onDone: () => void;
}

function formatSize(bytes: number): string {
  return `${Math.round(bytes / 1_000_000)} MB`;
}

export function JapanesePackPrompt({ onDone }: Props) {
  const [sizeBytes, setSizeBytes] = useState<number | null>(null);
  const [status, setStatus] = useState<PackStatus | null>(null);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    api.listPacks().then((packList) => {
      const japanese = packList.find((p) => p.name === 'japanese');
      if (japanese) setSizeBytes(japanese.download_size_bytes);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, []);

  const install = async () => {
    setStatus(null);
    await api.installPack('japanese');
    pollTimer.current = window.setInterval(async () => {
      const next = await api.getPackStatus('japanese');
      setStatus(next);
      if (next.state === 'installed' || next.state === 'failed') {
        if (pollTimer.current) window.clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    }, 800);
  };

  const downloading =
    status != null && (status.state === 'downloading' || status.state === 'verifying' || status.state === 'extracting');
  const installed = status?.state === 'installed';
  const failed = status?.state === 'failed';

  return (
    <>
      <div style={overlayStyle} onClick={downloading ? undefined : onDone} />
      <div style={panelStyle} data-testid="japanese-pack-prompt">
        {installed ? (
          <>
            <div style={{ font: '600 16px/1.3 IBM Plex Sans' }}>Reading pack installed</div>
            <div style={{ font: '400 12.5px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)', marginTop: 6 }}>
              Furigana will now show over kanji in Japanese transcripts.
            </div>
            <button onClick={onDone} style={{ ...primaryBtnStyle, width: '100%', marginTop: 16 }}>
              Continue
            </button>
          </>
        ) : (
          <>
            <div style={{ font: '600 16px/1.3 IBM Plex Sans' }}>Add furigana readings?</div>
            <div style={{ font: '400 12.5px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)', marginTop: 6 }}>
              This profile studies Japanese. Install the reading pack
              {sizeBytes != null ? ` (${formatSize(sizeBytes)})` : ''} to show furigana over kanji in transcripts —
              you can always add it later.
            </div>

            {downloading && status && (
              <div style={progressTrackStyle} data-testid="pack-prompt-progress">
                <div
                  style={{
                    ...progressFillStyle,
                    width: `${status.bytes_total ? Math.min(100, (status.bytes_done / status.bytes_total) * 100) : 0}%`,
                  }}
                />
              </div>
            )}
            {failed && (
              <div style={errorBoxStyle} data-testid="pack-prompt-error">
                {DOWNLOAD_ERROR_MESSAGES[status?.error ?? 'unknown']}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={onDone} disabled={downloading} style={skipBtnStyle}>
                Skip
              </button>
              <button onClick={install} disabled={downloading} style={primaryBtnStyle}>
                {downloading ? (status?.state === 'extracting' ? 'Installing…' : 'Downloading…') : failed ? 'Retry' : 'Install'}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(32,30,26,.32)', backdropFilter: 'blur(2px)', zIndex: 10 };
const panelStyle: React.CSSProperties = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: 360, padding: '24px 26px', borderRadius: 16, background: '#fbfaf7', border: '1px solid rgba(32,30,26,.1)', boxShadow: '0 20px 60px rgba(32,30,26,.25)', zIndex: 11 };
const progressTrackStyle: React.CSSProperties = { marginTop: 16, height: 4, borderRadius: 2, background: 'rgba(32,30,26,.08)', overflow: 'hidden' };
const progressFillStyle: React.CSSProperties = { height: '100%', borderRadius: 2, background: 'oklch(0.55 0.055 195)' };
const errorBoxStyle: React.CSSProperties = { font: '400 11.5px/1.5 IBM Plex Sans', color: 'oklch(0.5 0.13 25)', marginTop: 12 };
const skipBtnStyle: React.CSSProperties = { flex: 1, height: 40, borderRadius: 20, border: '1px solid rgba(32,30,26,.14)', background: '#fff', font: '600 12.5px/1 IBM Plex Sans', color: 'rgba(32,30,26,.6)', cursor: 'pointer' };
const primaryBtnStyle: React.CSSProperties = { flex: 1, height: 40, borderRadius: 20, border: 'none', background: '#211f1b', color: '#fff', font: '600 12.5px/1 IBM Plex Sans', cursor: 'pointer', marginTop: 0 };
