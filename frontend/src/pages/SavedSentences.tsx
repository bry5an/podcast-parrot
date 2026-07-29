import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { Ruby } from '../components/Ruby';
import { findActiveIndex } from '../lib/transcriptSync';
import { useProfiles } from '../state/ProfileContext';
import { useToast } from '../state/ToastContext';
import type { SavedSentence, Sentence } from '../lib/types';

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function SavedSentences() {
  const navigate = useNavigate();
  const { currentProfile, loading: profileLoading } = useProfiles();
  const { showToast } = useToast();

  const [clips, setClips] = useState<SavedSentence[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const [currentTime, setCurrentTime] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const activeClipRef = useRef<SavedSentence | null>(null);
  const showFurigana = currentProfile?.show_furigana ?? true;

  const refresh = useCallback(() => {
    if (!currentProfile) return;
    api.listSavedSentences(currentProfile.id).then((rows) => {
      setClips(rows);
      setLoaded(true);
    });
  }, [currentProfile]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const playClip = (clip: SavedSentence) => {
    if (!clip.audio_available) return;
    const audio = audioRef.current;
    if (!audio) return;
    if (playingId === clip.id) {
      audio.pause();
      setPlayingId(null);
      return;
    }
    activeClipRef.current = clip;
    audio.src = api.audioUrl(clip.episode_id);
    setPlayingId(clip.id);
  };

  const seekToSentence = (clip: SavedSentence, sentence: Sentence) => {
    const audio = audioRef.current;
    if (!audio || playingId !== clip.id) return;
    audio.currentTime = sentence.start_time;
    setCurrentTime(sentence.start_time);
  };

  const startRename = (clip: SavedSentence) => {
    setEditingId(clip.id);
    setEditValue(clip.name);
  };

  const submitRename = async (clip: SavedSentence) => {
    const name = editValue.trim();
    setEditingId(null);
    if (!currentProfile || !name || name === clip.name) return;
    try {
      const updated = await api.renameSavedSentence(currentProfile.id, clip.id, name);
      setClips((prev) => prev.map((c) => (c.id === clip.id ? updated : c)));
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to rename clip', 'error');
    }
  };

  const deleteClip = async (clip: SavedSentence) => {
    if (!currentProfile) return;
    await api.deleteSavedSentence(currentProfile.id, clip.id);
    showToast(`Deleted "${clip.name}"`);
    refresh();
  };

  if (!profileLoading && !currentProfile) return <Navigate to="/" replace />;
  if (!currentProfile) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#fbfaf7', color: '#211f1b' }}>
      <div style={{ padding: '22px 30px 0', flex: 'none' }}>
        <button onClick={() => navigate('/library')} style={backBtnStyle}>
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path d="M12 4l-6 6 6 6" />
          </svg>
          My podcasts
        </button>
      </div>

      <div style={{ padding: '16px 30px 20px', flex: 'none' }}>
        <h1 style={{ font: '600 22px/1.25 IBM Plex Sans', margin: 0 }}>Saved Sentences</h1>
        <div style={{ font: '500 12px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 8 }}>
          {loaded ? (clips.length === 1 ? '1 saved clip' : `${clips.length} saved clips`) : '…'}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 30px 28px', display: 'flex', flexDirection: 'column', gap: 9 }}>
        {clips.map((clip) => (
          <div key={clip.id} style={rowStyle} data-testid={`saved-sentence-${clip.id}`}>
            <button
              onClick={() => playClip(clip)}
              disabled={!clip.audio_available}
              title={clip.audio_available ? 'Play' : 'Re-download the episode to play this clip'}
              style={{ ...playBtnStyle, opacity: clip.audio_available ? 1 : 0.35 }}
              data-testid={`play-saved-sentence-${clip.id}`}
            >
              {playingId === clip.id ? (
                <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
                  <rect x="5" y="4" width="4" height="12" rx="1" />
                  <rect x="11" y="4" width="4" height="12" rx="1" />
                </svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M6 4l10 6-10 6V4z" />
                </svg>
              )}
            </button>

            <div style={{ flex: 1, minWidth: 0 }}>
              {editingId === clip.id ? (
                <input
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => submitRename(clip)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') submitRename(clip);
                    else if (e.key === 'Escape') setEditingId(null);
                  }}
                  style={nameInputStyle}
                  data-testid={`rename-input-${clip.id}`}
                />
              ) : (
                <div
                  onClick={() => startRename(clip)}
                  style={{ font: '600 14px/1.35 IBM Plex Sans', cursor: 'text' }}
                  data-testid={`clip-name-${clip.id}`}
                >
                  {clip.name}
                </div>
              )}
              <div
                onClick={() =>
                  navigate(`/library/podcasts/${clip.podcast_id}/episodes/${clip.episode_id}/player`)
                }
                style={{ font: '500 11.5px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 6, cursor: 'pointer' }}
              >
                {clip.podcast_title} · {clip.episode_title}
              </div>
              {playingId === clip.id ? (
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {(() => {
                    const activeIdx = findActiveIndex(clip.sentences, currentTime);
                    return clip.sentences.map((s, i) => (
                      <div
                        key={s.id}
                        onClick={() => seekToSentence(clip, s)}
                        data-testid={`clip-sentence-${clip.id}-${s.index}`}
                        data-active={i === activeIdx}
                        style={{ ...clipSentenceRowStyle, ...(i === activeIdx ? clipSentenceRowActiveStyle : {}) }}
                      >
                        <Ruby segments={s.segments} showFurigana={showFurigana} />
                      </div>
                    ));
                  })()}
                </div>
              ) : (
                <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.7)', marginTop: 6 }}>
                  {clip.text}
                </div>
              )}
              <div style={{ font: '400 10.5px/1 IBM Plex Mono', color: 'rgba(32,30,26,.4)', marginTop: 8 }}>
                Saved {formatDate(clip.created_at)}
              </div>
            </div>

            <button
              onClick={() => deleteClip(clip)}
              style={deleteBtnStyle}
              title="Delete"
              data-testid={`delete-saved-sentence-${clip.id}`}
            >
              <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          </div>
        ))}
        {loaded && clips.length === 0 && (
          <div style={{ margin: '30px auto', textAlign: 'center', maxWidth: 360, padding: '40px 24px', border: '1.5px dashed rgba(32,30,26,.16)', borderRadius: 16 }}>
            <div style={{ font: '600 15px/1.4 IBM Plex Sans', marginBottom: 8 }}>No saved sentences yet</div>
            <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)' }}>
              Toggle Select in the Shadowing Player, pick up to 5 sentences, and save them here.
            </div>
          </div>
        )}
      </div>

      <audio
        ref={audioRef}
        data-testid="saved-sentence-audio"
        onLoadedMetadata={(e) => {
          const clip = activeClipRef.current;
          if (clip) {
            e.currentTarget.currentTime = clip.start_time;
            setCurrentTime(clip.start_time);
          }
          e.currentTarget.play();
        }}
        onTimeUpdate={(e) => {
          const clip = activeClipRef.current;
          setCurrentTime(e.currentTarget.currentTime);
          if (clip && e.currentTarget.currentTime >= clip.end_time) {
            e.currentTarget.pause();
            setPlayingId(null);
          }
        }}
        style={{ display: 'none' }}
      />
    </div>
  );
}

const backBtnStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, border: 'none', background: 'none', cursor: 'pointer', padding: '6px 4px', font: '600 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)' };
const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'flex-start', gap: 14, padding: '13px 14px', borderRadius: 13, background: '#fff', border: '1px solid rgba(32,30,26,.08)' };
const playBtnStyle: React.CSSProperties = { width: 34, height: 34, flex: 'none', borderRadius: '50%', border: 'none', background: '#211f1b', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };
const deleteBtnStyle: React.CSSProperties = { width: 34, height: 34, flex: 'none', borderRadius: '50%', border: '1px solid rgba(32,30,26,.12)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'rgba(32,30,26,.5)' };
const nameInputStyle: React.CSSProperties = { width: '100%', height: 28, padding: '0 8px', borderRadius: 6, border: '1px solid rgba(32,30,26,.2)', font: '600 14px/1 IBM Plex Sans' };
const clipSentenceRowStyle: React.CSSProperties = { padding: '6px 10px', borderRadius: 8, cursor: 'pointer', font: '500 13px/1.7 "IBM Plex Sans", sans-serif' };
const clipSentenceRowActiveStyle: React.CSSProperties = { background: 'oklch(0.55 0.055 195 / 0.14)', boxShadow: 'inset 3px 0 0 oklch(0.42 0.06 195)' };
