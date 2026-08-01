import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useProfiles } from '../state/ProfileContext';
import { api } from '../lib/api';
import type { AutoRemovePolicy, StorageStats } from '../lib/types';
import { isTauri } from '../lib/tauri';
import {
  DEFAULT_SEEK_STEP_SECONDS,
  formatKeyLabel,
  formatModifierLabel,
  isModifierKey,
  loadAutoAdvance,
  loadKeymap,
  loadPlaybackSpeed,
  loadSeekStepSeconds,
  modifierFromEvent,
  normalizeKey,
  saveAutoAdvance,
  saveKeymap,
  savePlaybackSpeed,
  saveSeekStepSeconds,
} from '../lib/keybindings';
import type { KeybindingAction, Keymap, PlaybackSpeed } from '../lib/keybindings';
import { loadDimInactiveLines, loadShowRomaji, loadTextSize, saveDimInactiveLines, saveShowRomaji, saveTextSize } from '../lib/readingAids';
import type { TextSize } from '../lib/readingAids';
import { loadTheme, saveTheme } from '../lib/theme';
import type { Theme } from '../lib/theme';

type SectionId = 'playback' | 'transcription' | 'reading-aids' | 'library-storage' | 'appearance';
type SeekStep = '3s' | '5s' | '10s';
type ComputeDevice = 'cpu' | 'gpu';

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 MB';
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
      {children}
    </svg>
  );
}

const NAV_ICONS: Record<SectionId, ReactNode> = {
  playback: <path d="M7 5l7 5-7 5V5z" />,
  transcription: <path d="M4 5h12M4 10h12M4 15h8" />,
  'reading-aids': <path d="M6 3h8a1 1 0 0 1 1 1v13l-5-3-5 3V4a1 1 0 0 1 1-1z" />,
  'library-storage': (
    <>
      <ellipse cx="10" cy="5" rx="6" ry="2.4" />
      <path d="M4 5v10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V5" />
      <path d="M4 10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" />
    </>
  ),
  appearance: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 3a7 7 0 0 1 0 14z" fill="currentColor" stroke="none" />
    </>
  ),
};

const NAV_ITEMS: { id: SectionId; label: string }[] = [
  { id: 'playback', label: 'Playback & keys' },
  { id: 'transcription', label: 'Transcription' },
  { id: 'reading-aids', label: 'Reading aids' },
  { id: 'library-storage', label: 'Library & storage' },
  { id: 'appearance', label: 'Appearance' },
];

const KEYBINDINGS: { id: KeybindingAction | 'seekModifier'; icon: ReactNode; label: string; description: string }[] = [
  { id: 'playPause', icon: <path d="M7 5l7 5-7 5V5z" />, label: 'Play / pause', description: 'Toggle audio' },
  { id: 'replaySentence', icon: <path d="M14 6a5 5 0 1 0 1.4 4.6M14 3v4h-4" />, label: 'Replay sentence once', description: 'Restart current line' },
  {
    id: 'toggleLoop',
    icon: (
      <>
        <circle cx="7" cy="10" r="2.4" />
        <circle cx="13" cy="10" r="2.4" />
      </>
    ),
    label: 'Toggle sentence loop',
    description: 'Infinite repeat',
  },
  {
    id: 'previousSentence',
    icon: (
      <>
        <path d="M6 5v10" />
        <path d="M15 5L8 10l7 5V5z" fill="currentColor" stroke="none" />
      </>
    ),
    label: 'Previous sentence',
    description: 'Jump back one line',
  },
  {
    id: 'nextSentence',
    icon: (
      <>
        <path d="M14 5v10" />
        <path d="M5 5l7 5-7 5V5z" fill="currentColor" stroke="none" />
      </>
    ),
    label: 'Next sentence',
    description: 'Jump forward one line',
  },
  { id: 'seekModifier', icon: <path d="M12 5l-5 5 5 5M17 5l-5 5 5 5" />, label: 'Seek back / forward', description: 'Scrub within a line' },
  { id: 'cycleSpeed', icon: <path d="M10 4a6 6 0 1 0 6 6M10 4V2M10 8l3-3" />, label: 'Cycle speed', description: 'Step playback rate' },
];

const WHISPER_MODELS: { id: string; name: string; size: string; installed: boolean; speed: string; quality: string; description: string }[] = [
  { id: 'tiny', name: 'Tiny', size: '75 MB', installed: true, speed: '~8× realtime', quality: 'basic', description: 'Fastest. Rough drafts, quick checks.' },
  { id: 'base', name: 'Base', size: '142 MB', installed: true, speed: '~5× realtime', quality: 'fair', description: 'Good speed, usable for clear studio audio.' },
  { id: 'small', name: 'Small', size: '466 MB', installed: true, speed: '~2× realtime', quality: 'good', description: 'Balanced — recommended for most podcasts.' },
  { id: 'medium', name: 'Medium', size: '1.5 GB', installed: false, speed: '~1× realtime', quality: 'high', description: 'High accuracy on fast or noisy speech.' },
  { id: 'large-v3', name: 'Large v3', size: '3.1 GB', installed: false, speed: '~0.5× realtime', quality: 'best', description: 'Best accuracy. Slow without a strong GPU.' },
];

const SEEK_STEP_SECONDS: Record<SeekStep, number> = { '3s': 3, '5s': 5, '10s': 10 };
const SECONDS_TO_SEEK_STEP: Record<number, SeekStep> = { 3: '3s', 5: '5s', 10: '10s' };

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      style={{ ...styles.toggleTrack, background: checked ? 'var(--accent)' : 'rgb(var(--fg-rgb) / .15)' }}
    >
      <span style={{ ...styles.toggleThumb, transform: checked ? 'translateX(16px)' : 'translateX(0)' }} />
    </button>
  );
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div style={styles.segmentedRow}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          style={{ ...styles.segmentBtn, ...(value === opt.value ? styles.segmentBtnActive : {}) }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function SettingRow({ icon, title, subtitle, control }: { icon?: ReactNode; title: string; subtitle: string; control: ReactNode }) {
  return (
    <div style={styles.settingRow}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        {icon && (
          <div style={styles.rowIcon}>
            <Icon>{icon}</Icon>
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <div style={styles.rowTitle}>{title}</div>
          <div style={styles.rowSubtitle}>{subtitle}</div>
        </div>
      </div>
      <div style={{ flex: 'none' }}>{control}</div>
    </div>
  );
}

function Section({ id, title, subtitle, registerRef, children }: {
  id: SectionId;
  title: string;
  subtitle: string;
  registerRef: (id: SectionId, el: HTMLElement | null) => void;
  children: ReactNode;
}) {
  return (
    <section id={id} ref={(el) => registerRef(id, el)} style={styles.section}>
      <h2 style={styles.sectionTitle}>{title}</h2>
      <p style={styles.sectionSubtitle}>{subtitle}</p>
      <div style={styles.sectionBody}>{children}</div>
    </section>
  );
}

export function Settings() {
  const { currentProfile, loading, refreshProfiles } = useProfiles();
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState<SectionId>('playback');
  const sectionRefs = useRef<Partial<Record<SectionId, HTMLElement | null>>>({});

  const [speed, setSpeed] = useState<PlaybackSpeed>(() => loadPlaybackSpeed());
  const [seekStep, setSeekStep] = useState<SeekStep>(() => SECONDS_TO_SEEK_STEP[loadSeekStepSeconds()] ?? SECONDS_TO_SEEK_STEP[DEFAULT_SEEK_STEP_SECONDS]);
  const [autoAdvance, setAutoAdvance] = useState(() => loadAutoAdvance());

  const [keymap, setKeymap] = useState<Keymap>(() => loadKeymap());
  const [listening, setListening] = useState<KeybindingAction | 'seekModifier' | null>(null);

  useEffect(() => {
    if (!listening) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setListening(null);
        return;
      }
      if (listening === 'seekModifier') {
        const modifier = modifierFromEvent(e);
        if (!modifier) return;
        e.preventDefault();
        setKeymap((prev) => {
          const next = { ...prev, seekModifier: modifier };
          saveKeymap(next);
          return next;
        });
        setListening(null);
        return;
      }
      if (isModifierKey(e.key)) return;
      e.preventDefault();
      const key = normalizeKey(e.key);
      setKeymap((prev) => {
        const next = { ...prev, [listening]: key };
        saveKeymap(next);
        return next;
      });
      setListening(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [listening]);

  const handleSeekStepChange = (value: SeekStep) => {
    setSeekStep(value);
    saveSeekStepSeconds(SEEK_STEP_SECONDS[value]);
  };

  const handleSpeedChange = (value: PlaybackSpeed) => {
    setSpeed(value);
    savePlaybackSpeed(value);
  };

  const handleAutoAdvanceChange = () => {
    setAutoAdvance((v) => {
      const next = !v;
      saveAutoAdvance(next);
      return next;
    });
  };

  const handleTextSizeChange = (value: TextSize) => {
    setTextSize(value);
    saveTextSize(value);
  };

  const [selectedModel, setSelectedModel] = useState('small');
  const [computeDevice, setComputeDevice] = useState<ComputeDevice>('gpu');
  const [cacheTranscripts, setCacheTranscripts] = useState(true);

  const [furigana, setFurigana] = useState(true);
  const furiganaInitRef = useRef(false);
  const [romaji, setRomaji] = useState(() => loadShowRomaji());
  const [dimInactive, setDimInactive] = useState(() => loadDimInactiveLines());
  const [textSize, setTextSize] = useState<TextSize>(() => loadTextSize());

  const [autoRemove, setAutoRemove] = useState<AutoRemovePolicy>('never');
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);
  const [storageRoot, setStorageRoot] = useState<string | null>(null);
  const [relocating, setRelocating] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);

  const [theme, setTheme] = useState<Theme>(() => loadTheme());

  useEffect(() => {
    api.getStorageStats().then(setStorageStats).catch(() => setStorageError('Could not load storage usage'));
    api
      .getSettings()
      .then((s) => {
        setAutoRemove(s.auto_remove);
        setStorageRoot(s.storage_root);
      })
      .catch(() => setStorageError('Could not load storage settings'));
  }, []);

  useEffect(() => {
    if (!furiganaInitRef.current && currentProfile) {
      setFurigana(currentProfile.show_furigana);
      furiganaInitRef.current = true;
    }
  }, [currentProfile]);

  const handleFuriganaChange = () => {
    if (!currentProfile) return;
    const previous = furigana;
    const next = !previous;
    setFurigana(next);
    api
      .updateProfile(currentProfile.id, { show_furigana: next })
      .then(() => refreshProfiles())
      .catch(() => setFurigana(previous));
  };

  const handleRomajiChange = () => {
    setRomaji((v) => {
      const next = !v;
      saveShowRomaji(next);
      return next;
    });
  };

  const handleDimInactiveChange = () => {
    setDimInactive((v) => {
      const next = !v;
      saveDimInactiveLines(next);
      return next;
    });
  };

  const handleAutoRemoveChange = (value: AutoRemovePolicy) => {
    const previous = autoRemove;
    setAutoRemove(value);
    api.updateSettings({ auto_remove: value }).catch(() => {
      setAutoRemove(previous);
      setStorageError('Could not save auto-remove setting');
    });
  };

  const handleChangeLocation = async () => {
    if (!isTauri()) return;
    setStorageError(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false });
      if (!selected || typeof selected !== 'string') return;
      setRelocating(true);
      const updated = await api.updateSettings({ storage_root: selected });
      setStorageRoot(updated.storage_root);
      setStorageStats(await api.getStorageStats());
    } catch {
      setStorageError('Could not move storage to that folder');
    } finally {
      setRelocating(false);
    }
  };

  if (!currentProfile) return loading ? null : <Navigate to="/library" replace />;

  const registerRef = (id: SectionId, el: HTMLElement | null) => {
    sectionRefs.current[id] = el;
  };

  const goToSection = (id: SectionId) => {
    setActiveSection(id);
    sectionRefs.current[id]?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div style={{ position: 'relative', display: 'flex', height: '100vh', background: 'var(--bg-page)', color: 'var(--fg)' }}>
      {/* sub-nav */}
      <div style={styles.navRail}>
        <button type="button" onClick={() => navigate('/library')} style={styles.backRow}>
          <Icon>
            <path d="M12 5l-5 5 5 5" />
          </Icon>
          <span style={{ font: '600 14px/1 IBM Plex Sans', color: 'var(--fg)' }}>Settings</span>
        </button>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 8 }}>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={activeSection === item.id ? 'true' : undefined}
              onClick={() => goToSection(item.id)}
              style={{ ...styles.navItem, ...(activeSection === item.id ? styles.navItemActive : {}) }}
            >
              <Icon>{NAV_ICONS[item.id]}</Icon>
              {item.label}
            </button>
          ))}
        </div>
        <div style={styles.navFooter}>Kotoba · local build · macOS</div>
      </div>

      {/* content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '30px 40px 60px' }}>
        <Section
          id="playback"
          registerRef={registerRef}
          title="Playback & keybindings"
          subtitle="Global shortcuts while shadowing. Click any key to rebind, then press the new key."
        >
          <div style={styles.card}>
            {KEYBINDINGS.map((kb) => {
              const isListening = listening === kb.id;
              const label = kb.id === 'seekModifier' ? `${formatModifierLabel(keymap.seekModifier)} ←/→` : formatKeyLabel(keymap[kb.id]);
              return (
                <SettingRow
                  key={kb.label}
                  icon={kb.icon}
                  title={kb.label}
                  subtitle={kb.description}
                  control={
                    <button
                      type="button"
                      onClick={() => setListening(kb.id)}
                      style={{ ...styles.keyBadge, ...(isListening ? styles.keyBadgeListening : {}) }}
                    >
                      {isListening ? 'Press a key…' : label}
                    </button>
                  }
                />
              );
            })}
          </div>

          <div style={styles.inlineRow}>
            <div style={{ flex: 1 }}>
              <div style={styles.groupLabel}>Default playback speed</div>
              <SegmentedControl
                options={[
                  { value: '0.75x', label: '0.75×' },
                  { value: '1x', label: '1.0×' },
                  { value: '1.25x', label: '1.25×' },
                  { value: '1.5x', label: '1.5×' },
                ]}
                value={speed}
                onChange={handleSpeedChange}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={styles.groupLabel}>Seek step</div>
              <SegmentedControl
                options={[
                  { value: '3s', label: '3s' },
                  { value: '5s', label: '5s' },
                  { value: '10s', label: '10s' },
                ]}
                value={seekStep}
                onChange={handleSeekStepChange}
              />
            </div>
          </div>

          <div style={styles.card}>
            <SettingRow
              title="Auto-advance to next sentence"
              subtitle="Continue automatically when a line ends (unless looping)"
              control={<Toggle checked={autoAdvance} onChange={handleAutoAdvanceChange} label="Auto-advance to next sentence" />}
            />
          </div>
        </Section>

        <Section
          id="transcription"
          registerRef={registerRef}
          title="Transcription"
          subtitle="When an episode has no published transcript, Kotoba generates one locally with Whisper. Larger models are more accurate but slower."
        >
          <div style={styles.card}>
            {WHISPER_MODELS.map((m) => {
              const selected = selectedModel === m.id;
              return (
                <button
                  key={m.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setSelectedModel(m.id)}
                  style={{ ...styles.modelCard, ...(selected ? styles.modelCardSelected : {}) }}
                >
                  <div style={{ ...styles.radioOuter, ...(selected ? styles.radioOuterSelected : {}) }}>
                    {selected && <div style={styles.radioInner} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={styles.rowTitle}>{m.name}</span>
                      <span style={styles.sizeTag}>{m.size}</span>
                      {m.installed && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, font: '500 11px/1 IBM Plex Sans', color: 'rgb(var(--fg-rgb) / .5)' }}>
                          <span style={styles.installedDot} /> installed
                        </span>
                      )}
                    </div>
                    <div style={styles.rowSubtitle}>{m.description}</div>
                  </div>
                  <div style={{ textAlign: 'right', flex: 'none' }}>
                    <div style={{ font: '500 12px/1 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .6)' }}>{m.speed}</div>
                    <div style={{ font: '400 11px/1.4 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .4)' }}>{m.quality}</div>
                  </div>
                </button>
              );
            })}
          </div>

          <div style={styles.card}>
            <SettingRow
              title="Compute device"
              subtitle="Uses Metal acceleration when available on Apple Silicon"
              control={
                <SegmentedControl
                  options={[
                    { value: 'cpu' as ComputeDevice, label: 'CPU' },
                    { value: 'gpu' as ComputeDevice, label: 'GPU' },
                  ]}
                  value={computeDevice}
                  onChange={setComputeDevice}
                />
              }
            />
            <SettingRow
              title="Cache generated transcripts"
              subtitle="Reuse instead of re-transcribing on replay"
              control={<Toggle checked={cacheTranscripts} onChange={() => setCacheTranscripts((v) => !v)} label="Cache generated transcripts" />}
            />
          </div>
        </Section>

        <Section id="reading-aids" registerRef={registerRef} title="Reading aids" subtitle="How transcripts are displayed. Furigana and romaji apply to Japanese only.">
          <div style={styles.card}>
            <SettingRow
              title="Furigana over kanji"
              subtitle="Hiragana readings above Japanese kanji"
              control={<Toggle checked={furigana} onChange={handleFuriganaChange} label="Furigana over kanji" />}
            />
            <SettingRow
              title="Romaji fallback"
              subtitle="Latin transliteration under Japanese lines"
              control={<Toggle checked={romaji} onChange={handleRomajiChange} label="Romaji fallback" />}
            />
            <SettingRow
              title="Dim inactive lines"
              subtitle="Fade all but the current sentence"
              control={<Toggle checked={dimInactive} onChange={handleDimInactiveChange} label="Dim inactive lines" />}
            />
            <SettingRow
              title="Transcript text size"
              subtitle={textSize === 'S' ? 'Compact · 15px' : textSize === 'L' ? 'Large · 21px' : 'Standard · 18px'}
              control={
                <SegmentedControl
                  options={[
                    { value: 'S' as TextSize, label: 'S' },
                    { value: 'M' as TextSize, label: 'M' },
                    { value: 'L' as TextSize, label: 'L' },
                  ]}
                  value={textSize}
                  onChange={handleTextSizeChange}
                />
              }
            />
          </div>
        </Section>

        <Section id="library-storage" registerRef={registerRef} title="Library & storage" subtitle="Where downloaded audio lives on this Mac.">
          {storageError && <div style={styles.storageErrorBanner}>{storageError}</div>}

          <div style={styles.card}>
            <SettingRow
              title="Download location"
              subtitle={storageRoot ?? 'Loading…'}
              control={
                <button
                  type="button"
                  style={{ ...styles.secondaryBtn, ...(relocating || !isTauri() ? { opacity: 0.5, cursor: 'default' } : {}) }}
                  disabled={relocating || !isTauri()}
                  title={isTauri() ? undefined : 'Available in the desktop app'}
                  onClick={handleChangeLocation}
                >
                  {relocating ? 'Moving…' : 'Change…'}
                </button>
              }
            />
          </div>

          <div style={styles.card}>
            <div style={{ padding: '16px 18px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                <div style={styles.rowTitle}>Storage used</div>
                <div style={{ font: '500 12px/1 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .6)' }}>
                  {storageStats
                    ? `${formatBytes(storageStats.bytes_used)} · ${storageStats.episode_count} episode${storageStats.episode_count === 1 ? '' : 's'}`
                    : 'Loading…'}
                </div>
              </div>
              <div style={styles.storageBar}>
                <div style={{ width: storageStats && storageStats.bytes_used > 0 ? '100%' : '0%', background: 'var(--accent)' }} />
              </div>
            </div>
          </div>

          <div style={styles.card}>
            <SettingRow
              title="Auto-remove played episodes"
              subtitle="Keep everything until I delete it manually"
              control={
                <SegmentedControl
                  options={[
                    { value: 'never' as AutoRemovePolicy, label: 'Never' },
                    { value: '7d' as AutoRemovePolicy, label: '7 days' },
                    { value: '30d' as AutoRemovePolicy, label: '30 days' },
                  ]}
                  value={autoRemove}
                  onChange={handleAutoRemoveChange}
                />
              }
            />
          </div>
        </Section>

        <Section id="appearance" registerRef={registerRef} title="Appearance" subtitle="Theme for the app window.">
          <div style={styles.inlineRow}>
            {(
              [
                { id: 'warm' as Theme, label: 'Warm paper', swatch: '#f1ecdf' },
                { id: 'light' as Theme, label: 'Light', swatch: '#ffffff' },
                { id: 'dark' as Theme, label: 'Dark', swatch: '#1e1e2e' },
              ]
            ).map((t) => {
              const selected = theme === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => {
                    setTheme(t.id);
                    saveTheme(t.id);
                  }}
                  style={{ ...styles.themeCard, ...(selected ? styles.themeCardSelected : {}) }}
                >
                  <div style={{ ...styles.themeSwatch, background: t.swatch, border: t.id === 'light' ? '1px solid rgb(var(--fg-rgb) / .1)' : 'none' }} />
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={styles.rowTitle}>{t.label}</span>
                    {selected && (
                      <Icon>
                        <path d="M5 10l3.5 3.5L15 6" />
                      </Icon>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </Section>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  navRail: { width: 220, flex: 'none', borderRight: '1px solid rgb(var(--fg-rgb) / .08)', display: 'flex', flexDirection: 'column', padding: '20px 14px' },
  backRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 4px 16px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)' },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '9px 10px',
    borderRadius: 9,
    font: '500 13px/1 IBM Plex Sans',
    color: 'rgb(var(--fg-rgb) / .55)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left',
  },
  navItemActive: { background: 'var(--bg-hover)', font: '600 13px/1 IBM Plex Sans', color: 'var(--fg)' },
  navFooter: { marginTop: 'auto', font: '400 10px/1.5 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .35)', padding: '10px 6px 0' },
  section: { maxWidth: 760, marginBottom: 40 },
  sectionTitle: { font: '600 20px/1.3 IBM Plex Sans', margin: '0 0 4px' },
  sectionSubtitle: { font: '400 13px/1.6 IBM Plex Sans', color: 'rgb(var(--fg-rgb) / .55)', margin: '0 0 16px' },
  sectionBody: { display: 'flex', flexDirection: 'column', gap: 14 },
  card: { background: 'var(--bg-surface)', border: '1px solid rgb(var(--fg-rgb) / .08)', borderRadius: 14, overflow: 'hidden' },
  settingRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '14px 18px', borderBottom: '1px solid rgb(var(--fg-rgb) / .06)' },
  rowIcon: { width: 30, height: 30, borderRadius: 8, background: 'rgb(var(--fg-rgb) / .05)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none', color: 'rgb(var(--fg-rgb) / .6)' },
  rowTitle: { font: '600 13.5px/1.3 IBM Plex Sans', color: 'var(--fg)' },
  rowSubtitle: { font: '400 12px/1.5 IBM Plex Sans', color: 'rgb(var(--fg-rgb) / .5)', marginTop: 2 },
  keyBadge: { minWidth: 56, height: 32, padding: '0 12px', borderRadius: 8, border: '1px solid rgb(var(--fg-rgb) / .14)', background: 'var(--bg-surface)', font: '600 12px/1 IBM Plex Mono', color: 'var(--fg)', cursor: 'pointer' },
  keyBadgeListening: { border: '1.5px solid var(--accent)', color: 'var(--accent-strong)', background: 'var(--accent-soft)' },
  inlineRow: { display: 'flex', gap: 24, marginBottom: 14 },
  groupLabel: { font: '500 11px/1 IBM Plex Mono', letterSpacing: '.04em', textTransform: 'uppercase', color: 'rgb(var(--fg-rgb) / .45)', marginBottom: 8 },
  segmentedRow: { display: 'flex', gap: 6 },
  segmentBtn: { height: 34, padding: '0 14px', borderRadius: 17, border: '1px solid rgb(var(--fg-rgb) / .14)', background: 'var(--bg-surface)', color: 'rgb(var(--fg-rgb) / .7)', font: '600 12.5px/1 IBM Plex Mono', cursor: 'pointer' },
  segmentBtnActive: { background: 'var(--fg)', color: 'var(--bg-page)', border: '1px solid var(--fg)' },
  toggleTrack: { width: 40, height: 24, borderRadius: 12, border: 'none', padding: 2, cursor: 'pointer', display: 'flex', alignItems: 'center' },
  toggleThumb: { width: 20, height: 20, borderRadius: 10, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.25)', transition: 'transform .15s ease' },
  modelCard: { display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', borderBottom: '1px solid rgb(var(--fg-rgb) / .06)', background: 'none', border: 'none', width: '100%', cursor: 'pointer', textAlign: 'left' },
  modelCardSelected: { background: 'var(--accent-soft)' },
  radioOuter: { width: 18, height: 18, borderRadius: '50%', border: '1.5px solid rgb(var(--fg-rgb) / .25)', flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  radioOuterSelected: { border: '1.5px solid var(--accent)' },
  radioInner: { width: 9, height: 9, borderRadius: '50%', background: 'var(--accent)' },
  sizeTag: { font: '500 10px/1 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .5)', background: 'rgb(var(--fg-rgb) / .06)', padding: '2px 6px', borderRadius: 5 },
  installedDot: { width: 5, height: 5, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' },
  secondaryBtn: { height: 34, padding: '0 16px', borderRadius: 17, border: '1px solid rgb(var(--fg-rgb) / .14)', background: 'var(--bg-surface)', color: 'var(--fg)', font: '600 12.5px/1 IBM Plex Sans', cursor: 'pointer' },
  storageBar: { display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: 'rgb(var(--fg-rgb) / .08)', marginTop: 10 },
  storageErrorBanner: {
    font: '500 12px/1.4 IBM Plex Sans',
    color: 'var(--danger)',
    background: 'var(--danger-soft)',
    border: '1px solid var(--danger-border)',
    borderRadius: 10,
    padding: '10px 14px',
  },
  themeCard: { flex: 1, padding: 10, borderRadius: 14, border: '1.5px solid rgb(var(--fg-rgb) / .1)', background: 'var(--bg-surface)', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 10, textAlign: 'left' },
  themeCardSelected: { border: '1.5px solid var(--accent-strong)' },
  themeSwatch: { height: 64, borderRadius: 9 },
};
