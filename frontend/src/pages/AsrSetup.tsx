import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { DOWNLOAD_ERROR_MESSAGES } from '../lib/downloadErrors';
import type { WhisperModel, WhisperModelName, WhisperModelStatus } from '../lib/types';

export const ASR_SETUP_SEEN_KEY = 'kotoba.asrSetupSeen';

const MODEL_BLURBS: Record<WhisperModelName, string> = {
  tiny: 'Fastest, least accurate — noticeably weak on Japanese.',
  base: 'Recommended for Japanese shadowing.',
  small: 'Most accurate, largest download.',
};

function formatSize(bytes: number): string {
  return `${Math.round(bytes / 1_000_000)} MB`;
}

export function AsrSetup() {
  const navigate = useNavigate();
  const [models, setModels] = useState<WhisperModel[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [activeDownload, setActiveDownload] = useState<WhisperModelName | null>(null);
  const [status, setStatus] = useState<WhisperModelStatus | null>(null);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    api.listModels().then((rows) => {
      setModels(rows);
      setLoaded(true);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, []);

  const finish = () => {
    localStorage.setItem(ASR_SETUP_SEEN_KEY, '1');
    navigate('/');
  };

  const download = async (name: WhisperModelName) => {
    setActiveDownload(name);
    setStatus(null);
    await api.downloadModel(name);
    pollTimer.current = window.setInterval(async () => {
      const next = await api.getModelStatus(name);
      setStatus(next);
      if (next.state === 'installed' || next.state === 'failed') {
        if (pollTimer.current) window.clearInterval(pollTimer.current);
        pollTimer.current = null;
      }
    }, 800);
  };

  const downloading = status != null && (status.state === 'downloading' || status.state === 'verifying');
  const installed = status?.state === 'installed';
  const failed = status?.state === 'failed';

  return (
    <div style={styles.page}>
      <div style={styles.brand}>
        <div style={styles.brandMark}>
          <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="#fff" strokeWidth={1.7}>
            <path d="M6 10a4 4 0 0 1 8 0M8.5 10v4M11.5 10v4M10 3v3" />
          </svg>
        </div>
        <span style={{ font: '600 14px/1 IBM Plex Sans' }}>Kotoba</span>
      </div>

      <div style={styles.body}>
        <div style={{ textAlign: 'center', maxWidth: 460 }}>
          <div style={styles.eyebrow}>First-run setup</div>
          <h1 style={styles.h1}>Set up speech recognition</h1>
          <p style={styles.copy}>
            Episodes without a published transcript are transcribed on your Mac using a local Whisper
            model. Pick a size below, or skip for now — shows with published transcripts work either way.
          </p>
        </div>

        {installed ? (
          <div style={styles.doneCard} data-testid="asr-setup-done">
            <div style={{ font: '600 15px/1.4 IBM Plex Sans' }}>Model installed</div>
            <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)', marginTop: 4 }}>
              You&apos;re all set — episodes without a transcript will now be transcribed automatically.
            </div>
            <button onClick={finish} style={styles.primaryBtn}>
              Continue
            </button>
          </div>
        ) : (
          <>
            <div style={styles.cardRow}>
              {loaded &&
                models.map((m) => {
                  const isActive = activeDownload === m.name;
                  const isDownloadingThis = isActive && downloading;
                  const isFailedThis = isActive && failed;
                  return (
                    <div
                      key={m.name}
                      style={{ ...styles.card, ...(m.name === 'base' ? styles.cardRecommended : {}) }}
                      data-testid={`model-card-${m.name}`}
                    >
                      {m.name === 'base' && <div style={styles.recommendedTag}>Recommended</div>}
                      <div style={{ font: '600 15px/1.2 IBM Plex Sans', textTransform: 'capitalize' }}>{m.name}</div>
                      <div style={styles.mono}>{formatSize(m.size_bytes)}</div>
                      <div style={styles.blurb}>{MODEL_BLURBS[m.name]}</div>
                      <button
                        onClick={() => download(m.name)}
                        disabled={downloading}
                        style={{ ...styles.downloadBtn, ...(downloading ? styles.downloadBtnDisabled : {}) }}
                      >
                        {isDownloadingThis ? (status?.state === 'verifying' ? 'Verifying…' : 'Downloading…') : 'Download'}
                      </button>
                      {isDownloadingThis && status && (
                        <div style={styles.progressTrack} data-testid={`progress-${m.name}`}>
                          <div
                            style={{
                              ...styles.progressFill,
                              width: `${status.bytes_total ? Math.min(100, (status.bytes_done / status.bytes_total) * 100) : 0}%`,
                            }}
                          />
                        </div>
                      )}
                      {isFailedThis && (
                        <div style={styles.errorBox} data-testid="asr-setup-error">
                          {DOWNLOAD_ERROR_MESSAGES[status?.error ?? 'unknown']}
                          <button onClick={() => download(m.name)} style={styles.retryBtn}>
                            Retry
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>

            <button onClick={finish} style={styles.skipBtn}>
              Skip for now
            </button>
          </>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: 'radial-gradient(120% 90% at 50% -10%, #f3f0ea, #efece5 55%, #eae6df)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  brand: { display: 'flex', alignItems: 'center', gap: 9, padding: '26px 0 0' },
  brandMark: { width: 26, height: 26, borderRadius: 7, background: '#211f1b', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  body: { flex: 1, width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 34, padding: 20 },
  eyebrow: { font: '500 11px/1 IBM Plex Mono', letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(32,30,26,.45)', marginBottom: 12 },
  h1: { font: '600 28px/1.25 IBM Plex Sans', margin: 0 },
  copy: { font: '400 13.5px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.6)', marginTop: 14 },
  cardRow: { display: 'flex', gap: 18, alignItems: 'stretch' },
  card: { position: 'relative', width: 190, padding: '20px 18px', borderRadius: 16, background: '#fff', border: '1px solid rgba(32,30,26,.1)', display: 'flex', flexDirection: 'column', gap: 8 },
  cardRecommended: { border: '1.5px solid oklch(0.55 0.055 195)' },
  recommendedTag: { position: 'absolute', top: -11, left: 18, font: '600 9.5px/1 IBM Plex Mono', letterSpacing: '.04em', textTransform: 'uppercase', color: '#fff', background: 'oklch(0.55 0.055 195)', padding: '3px 8px', borderRadius: 6 },
  mono: { font: '500 11px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)' },
  blurb: { font: '400 11.5px/1.5 IBM Plex Sans', color: 'rgba(32,30,26,.55)', minHeight: 48 },
  downloadBtn: { height: 36, borderRadius: 18, border: 'none', background: '#211f1b', color: '#fff', font: '600 12.5px/1 IBM Plex Sans', cursor: 'pointer', marginTop: 4 },
  downloadBtnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  progressTrack: { marginTop: 4, height: 4, borderRadius: 2, background: 'rgba(32,30,26,.08)', overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 2, background: 'oklch(0.55 0.055 195)' },
  errorBox: { font: '400 11px/1.5 IBM Plex Sans', color: 'oklch(0.5 0.13 25)', marginTop: 2, display: 'flex', flexDirection: 'column', gap: 6 },
  retryBtn: { alignSelf: 'flex-start', height: 26, padding: '0 12px', borderRadius: 13, border: '1px solid oklch(0.5 0.13 25 / 0.4)', background: '#fff', color: 'oklch(0.5 0.13 25)', font: '600 11px/1 IBM Plex Sans', cursor: 'pointer' },
  skipBtn: { border: 'none', background: 'none', cursor: 'pointer', font: '600 12.5px/1 IBM Plex Sans', color: 'rgba(32,30,26,.45)', textDecoration: 'underline' },
  doneCard: { width: 360, textAlign: 'center', padding: '28px 26px', borderRadius: 16, background: '#fff', border: '1px solid rgba(32,30,26,.1)' },
  primaryBtn: { height: 42, width: '100%', marginTop: 18, borderRadius: 21, border: 'none', background: '#211f1b', color: '#fff', font: '600 13px/1 IBM Plex Sans', cursor: 'pointer' },
};
