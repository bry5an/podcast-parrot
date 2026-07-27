import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { DIRECTION_META, PALETTE } from '../lib/palette';
import { useProfiles } from '../state/ProfileContext';
import type { Direction } from '../lib/types';

const initial = (name: string) => (name.trim()[0] || '?').toUpperCase();

export function ProfilePicker() {
  const { profiles, selectProfile, refreshProfiles } = useProfiles();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [paletteIndex, setPaletteIndex] = useState(2);
  const [direction, setDirection] = useState<Direction>('en_ja');
  const [showFurigana, setShowFurigana] = useState(true);
  const [saving, setSaving] = useState(false);

  const pick = (id: number) => {
    selectProfile(id);
    navigate('/library');
  };

  const startCreate = () => {
    setName('');
    setPaletteIndex(2);
    setDirection('en_ja');
    setShowFurigana(true);
    setCreating(true);
  };

  const save = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      const profile = await api.createProfile({
        name: name.trim(),
        palette_index: paletteIndex,
        direction,
        show_furigana: showFurigana,
      });
      await refreshProfiles();
      setCreating(false);
      pick(profile.id);
    } finally {
      setSaving(false);
    }
  };

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

      {!creating ? (
        <div style={styles.selectView}>
          <div style={{ textAlign: 'center' }}>
            <div style={styles.eyebrow}>Who&apos;s shadowing?</div>
            <h1 style={styles.h1}>Choose a profile</h1>
          </div>
          <div style={styles.tileRow}>
            {profiles.map((p) => {
              const swatch = PALETTE[p.palette_index % PALETTE.length];
              const meta = DIRECTION_META[p.direction];
              return (
                <div key={p.id} onClick={() => pick(p.id)} style={styles.tile}>
                  <div style={{ ...styles.avatar, background: swatch.art, boxShadow: `0 8px 24px ${swatch.shadow}` }}>
                    {initial(p.name)}
                    <div style={styles.flagBadge}>{meta.flag}</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ font: '600 17px/1.2 IBM Plex Sans' }}>{p.name}</div>
                    <div style={styles.mono}>{meta.code}</div>
                  </div>
                </div>
              );
            })}
            <div onClick={startCreate} style={styles.tile}>
              <div style={styles.addAvatar}>
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ font: '600 16px/1.2 IBM Plex Sans', color: 'rgba(32,30,26,.55)' }}>Add learner</div>
                <div style={{ font: '400 11.5px/1.4 IBM Plex Sans', color: 'rgba(32,30,26,.4)', marginTop: 7 }}>
                  New profile
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={styles.createView}>
          <div>
            <div style={styles.eyebrow}>New profile</div>
            <h1 style={{ font: '600 26px/1.2 IBM Plex Sans', margin: 0 }}>Create a learner</h1>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                ...styles.newAvatar,
                background: PALETTE[paletteIndex].art,
                boxShadow: `0 6px 18px ${PALETTE[paletteIndex].shadow}`,
              }}
            >
              {initial(name)}
            </div>
            <div style={{ flex: 1 }}>
              <label style={styles.label}>Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Kenji"
                style={styles.input}
              />
            </div>
          </div>

          <div>
            <label style={styles.label}>Avatar color</label>
            <div style={{ display: 'flex', gap: 10 }}>
              {PALETTE.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setPaletteIndex(i)}
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 11,
                    cursor: 'pointer',
                    background: s.art,
                    border: `2px solid ${i === paletteIndex ? '#211f1b' : 'transparent'}`,
                    padding: 0,
                  }}
                />
              ))}
            </div>
          </div>

          <div>
            <label style={styles.label}>Learning direction</label>
            <div style={{ display: 'flex', gap: 12 }}>
              {(['en_ja', 'ja_en'] as Direction[]).map((d) => {
                const m = DIRECTION_META[d];
                const sel = direction === d;
                return (
                  <button
                    key={d}
                    onClick={() => setDirection(d)}
                    style={{
                      flex: 1,
                      padding: '15px 14px',
                      borderRadius: 13,
                      cursor: 'pointer',
                      textAlign: 'left',
                      background: sel ? 'oklch(0.55 0.055 195 / 0.1)' : 'rgba(255,255,255,.55)',
                      border: `1.5px solid ${sel ? 'oklch(0.55 0.055 195)' : 'rgba(32,30,26,.12)'}`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 7 }}>
                      <span style={{ fontSize: 20 }}>{m.flag}</span>
                      {sel && (
                        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="oklch(0.45 0.055 195)" strokeWidth={2}>
                          <path d="M4.5 10.5 8 14l7.5-8" />
                        </svg>
                      )}
                    </div>
                    <div style={{ font: '600 14px/1.2 IBM Plex Sans' }}>{m.title}</div>
                    <div style={styles.mono}>{m.sub}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {direction === 'en_ja' && (
            <label style={styles.furiganaRow}>
              <div>
                <div style={{ font: '600 13px/1.2 IBM Plex Sans' }}>Show furigana over kanji</div>
                <div style={{ font: '400 11px/1.3 IBM Plex Sans', color: 'rgba(32,30,26,.5)', marginTop: 3 }}>
                  Reading aid for Japanese transcripts
                </div>
              </div>
              <button
                onClick={() => setShowFurigana((v) => !v)}
                style={{
                  width: 44,
                  height: 26,
                  borderRadius: 13,
                  border: 'none',
                  cursor: 'pointer',
                  padding: 3,
                  display: 'flex',
                  background: showFurigana ? 'oklch(0.55 0.055 195)' : 'rgba(32,30,26,.2)',
                  justifyContent: showFurigana ? 'flex-end' : 'flex-start',
                }}
              >
                <span style={{ width: 20, height: 20, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.25)' }} />
              </button>
            </label>
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button onClick={() => setCreating(false)} style={styles.cancelBtn}>
              Cancel
            </button>
            <button
              onClick={save}
              disabled={!name.trim() || saving}
              style={{
                flex: 1,
                height: 44,
                borderRadius: 22,
                border: 'none',
                font: '600 13.5px/1 IBM Plex Sans',
                cursor: name.trim() ? 'pointer' : 'not-allowed',
                background: name.trim() ? '#211f1b' : 'rgba(32,30,26,.14)',
                color: name.trim() ? '#fff' : 'rgba(32,30,26,.4)',
              }}
            >
              {saving ? 'Creating…' : 'Create profile'}
            </button>
          </div>
        </div>
      )}
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
  selectView: { flex: 1, width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 38, padding: 20 },
  eyebrow: { font: '500 11px/1 IBM Plex Mono', letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(32,30,26,.45)', marginBottom: 12 },
  h1: { font: '600 30px/1.2 IBM Plex Sans', margin: 0 },
  tileRow: { display: 'flex', gap: 26, alignItems: 'flex-start' },
  tile: { width: 184, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 15, cursor: 'pointer', padding: 10, borderRadius: 16 },
  avatar: { width: 118, height: 118, borderRadius: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', font: '600 42px/1 IBM Plex Sans', color: '#fff', position: 'relative' },
  flagBadge: { position: 'absolute', bottom: -6, right: -6, width: 38, height: 38, borderRadius: '50%', background: '#fff', border: '1px solid rgba(32,30,26,.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, boxShadow: '0 3px 10px rgba(32,30,26,.15)' },
  mono: { font: '500 11px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 6 },
  addAvatar: { width: 118, height: 118, borderRadius: 26, border: '1.5px dashed rgba(32,30,26,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(32,30,26,.4)' },
  createView: { flex: 1, width: '100%', maxWidth: 520, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 24, padding: '20px 24px' },
  newAvatar: { width: 72, height: 72, flex: 'none', borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', font: '600 28px/1 IBM Plex Sans', color: '#fff' },
  label: { font: '600 11px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)', display: 'block', marginBottom: 7 },
  input: { width: '100%', height: 42, padding: '0 14px', borderRadius: 11, border: '1px solid rgba(32,30,26,.16)', background: '#fff', font: '400 14px/1 IBM Plex Sans', color: '#211f1b', outline: 'none' },
  furiganaRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 15px', borderRadius: 12, background: 'rgba(255,255,255,.6)', border: '1px solid rgba(32,30,26,.1)', cursor: 'pointer' },
  cancelBtn: { height: 44, padding: '0 20px', borderRadius: 22, border: '1px solid rgba(32,30,26,.14)', background: '#fff', font: '600 13px/1 IBM Plex Sans', color: 'rgba(32,30,26,.6)', cursor: 'pointer' },
};
