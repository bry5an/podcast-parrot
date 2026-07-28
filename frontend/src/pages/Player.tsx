import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Ruby } from '../components/Ruby';
import { useProfiles } from '../state/ProfileContext';
import { invokeTauri, listenTauri } from '../lib/tauri';
import type { Episode, Podcast, Sentence, Transcript } from '../lib/types';

const SPEEDS = [0.75, 1, 1.25, 1.5] as const;

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// Binary-searches ordered, non-overlapping [start_time, end_time) sentences
// for the one containing `t`; -1 if `t` falls in a gap between sentences.
function findActiveIndex(sentences: Sentence[], t: number): number {
  let lo = 0;
  let hi = sentences.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const s = sentences[mid];
    if (t < s.start_time) hi = mid - 1;
    else if (t >= s.end_time) lo = mid + 1;
    else return mid;
  }
  return -1;
}

export function Player() {
  const { podcastId, episodeId } = useParams();
  const pId = Number(podcastId);
  const eId = Number(episodeId);
  const location = useLocation();
  const navigate = useNavigate();
  const { currentProfile, loading: profileLoading } = useProfiles();

  const [podcast, setPodcast] = useState<Podcast | null>(
    (location.state as { podcast?: Podcast } | null)?.podcast ?? null,
  );
  const [episode, setEpisode] = useState<Episode | null>(
    (location.state as { episode?: Episode } | null)?.episode ?? null,
  );
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [transcriptError, setTranscriptError] = useState(false);

  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loopOne, setLoopOne] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const [showFurigana, setShowFurigana] = useState(true);
  const [, setShadowed] = useState<Set<number>>(new Set());
  const [doneToday, setDoneToday] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const activeIndexRef = useRef(-1);
  const loopOneRef = useRef(false);
  const furiganaInitRef = useRef(false);
  const resumedRef = useRef(false);
  const autoplayRef = useRef((location.state as { autoplay?: boolean } | null)?.autoplay ?? false);

  const sentences = transcript?.sentences ?? [];
  const sentencesRef = useRef<Sentence[]>(sentences);
  sentencesRef.current = sentences;

  useEffect(() => {
    loopOneRef.current = loopOne;
  }, [loopOne]);

  useEffect(() => {
    if (episode || !currentProfile) return;
    api.listEpisodes(pId, { profileId: currentProfile.id }).then((rows) => {
      const match = rows.find((e) => e.id === eId);
      if (match) setEpisode(match);
    });
  }, [episode, currentProfile, pId, eId]);

  useEffect(() => {
    if (podcast || !currentProfile) return;
    api.listSubscriptions(currentProfile.id).then((subs) => {
      const match = subs.find((p) => p.id === pId);
      if (match) setPodcast(match);
    });
  }, [podcast, currentProfile, pId]);

  useEffect(() => {
    let cancelled = false;
    api
      .getTranscript(eId)
      .then((t) => {
        if (!cancelled) setTranscript(t);
      })
      .catch(() => {
        if (!cancelled) setTranscriptError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [eId]);

  useEffect(() => {
    if (!furiganaInitRef.current && currentProfile) {
      setShowFurigana(currentProfile.show_furigana);
      furiganaInitRef.current = true;
    }
  }, [currentProfile]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = SPEEDS[speedIdx];
    if (!audio.paused) pushNowPlayingRef.current(SPEEDS[speedIdx]);
  }, [speedIdx]);

  const refreshShadowSummary = useCallback(() => {
    if (!currentProfile) return;
    api.getShadowSummary(currentProfile.id, eId).then((s) => setDoneToday(s.doneToday));
  }, [currentProfile, eId]);

  useEffect(() => {
    refreshShadowSummary();
  }, [refreshShadowSummary]);

  // Logs to the backend the first time a sentence's loop wraps (or it
  // completes one natural playthrough); the displayed count then comes back
  // from shadow-summary, which is the source of truth, not this local set.
  const markShadowed = useCallback(
    (idx: number) => {
      setShadowed((prev) => {
        if (prev.has(idx)) return prev;
        const sentence = sentencesRef.current[idx];
        if (currentProfile && sentence) {
          api.logShadowEvent(currentProfile.id, eId, sentence.id).then(refreshShadowSummary);
        }
        return new Set(prev).add(idx);
      });
    },
    [currentProfile, eId, refreshShadowSummary],
  );

  const savePosition = useCallback(() => {
    if (currentProfile && episode && audioRef.current) {
      api.updatePosition(currentProfile.id, episode.id, audioRef.current.currentTime);
    }
  }, [currentProfile, episode]);
  const savePositionRef = useRef(savePosition);
  savePositionRef.current = savePosition;

  // Publishes Now Playing metadata to macOS's Control Center / media keys.
  // Only needs to be called on discontinuities (load, play, pause, seek,
  // speed change) - the OS interpolates elapsed time from `rate` in between.
  const pushNowPlaying = useCallback(
    (rate: number) => {
      const audio = audioRef.current;
      if (!audio || !episode) return;
      invokeTauri('update_now_playing', {
        title: episode.title,
        artist: podcast?.title ?? '',
        duration: audio.duration || 0,
        elapsed: audio.currentTime,
        rate,
      });
    },
    [episode, podcast],
  );
  const pushNowPlayingRef = useRef(pushNowPlaying);
  pushNowPlayingRef.current = pushNowPlaying;

  useEffect(() => {
    const flush = () => savePositionRef.current();
    window.addEventListener('beforeunload', flush);
    return () => {
      window.removeEventListener('beforeunload', flush);
      flush();
      // Unmounting (e.g. navigating back to the library) removes the <audio>
      // element without firing a `pause` DOM event, so the wake lock started
      // in onPlay would otherwise never be released.
      invokeTauri('end_playback_wake_lock');
      invokeTauri('clear_now_playing');
    };
  }, []);

  // Media keys / Control Center send these when there's no <audio> element
  // for the OS to control directly on macOS; forward them onto the one this
  // page owns so it stays the single source of playback truth.
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    listenTauri<string>('media-command', (command) => {
      const audio = audioRef.current;
      if (!audio) return;
      if (command === 'play') audio.play();
      else if (command === 'pause') audio.pause();
      else if (command === 'toggle') {
        if (audio.paused) audio.play();
        else audio.pause();
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  const handleTimeUpdate = useCallback(() => {
    const audio = audioRef.current;
    const list = sentencesRef.current;
    if (!audio || list.length === 0) return;
    const t = audio.currentTime;
    setCurrentTime(t);

    const prevIndex = activeIndexRef.current;
    if (prevIndex !== -1 && t >= list[prevIndex].end_time) {
      markShadowed(prevIndex);
      if (loopOneRef.current) {
        audio.currentTime = list[prevIndex].start_time;
        return;
      }
    }

    const idx = findActiveIndex(list, t);
    if (idx !== -1 && idx !== prevIndex) {
      activeIndexRef.current = idx;
      setActiveIndex(idx);
      rowRefs.current[idx]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [markShadowed]);

  const jumpTo = (idx: number) => {
    const audio = audioRef.current;
    const s = sentences[idx];
    if (!audio || !s) return;
    audio.currentTime = s.start_time;
    activeIndexRef.current = idx;
    setActiveIndex(idx);
    audio.play();
    pushNowPlaying(SPEEDS[speedIdx]);
  };

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play();
    else audio.pause();
  };

  const onScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = Number(e.target.value);
    const audio = audioRef.current;
    if (audio) audio.currentTime = t;
    setCurrentTime(t);
    pushNowPlaying(audio && !audio.paused ? SPEEDS[speedIdx] : 0);
  };

  if (!profileLoading && !currentProfile) return <Navigate to="/" replace />;
  if (!currentProfile) return null;

  const sourceLabel = transcript ? (transcript.source === 'asr' ? 'Auto-generated' : 'Published transcript') : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#fbfaf7', color: '#211f1b' }}>
          <div style={{ padding: '22px 30px 0', flex: 'none' }}>
            <button
              onClick={() => navigate(`/library/podcasts/${pId}/episodes`, { state: { podcast } })}
              style={backBtnStyle}
            >
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path d="M12 4l-6 6 6 6" />
              </svg>
              Episodes
            </button>
          </div>

          <div style={{ flex: 1, display: 'flex', minHeight: 0, padding: '16px 0 0' }}>
            <div style={{ width: 240, flex: 'none', borderRight: '1px solid rgba(32,30,26,.08)', padding: '4px 22px 22px', display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
              {podcast?.artwork_url ? (
                <img src={podcast.artwork_url} alt="" style={sidebarArtStyle} />
              ) : (
                <div style={{ ...sidebarArtStyle, background: 'rgba(32,30,26,.08)' }} />
              )}
              <div>
                <div style={{ font: '600 15px/1.35 IBM Plex Sans' }}>{episode?.title ?? '…'}</div>
                {podcast?.title && (
                  <div style={{ font: '400 11.5px/1.4 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 6 }}>
                    {podcast.title}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {episode?.download_status === 'downloaded' && <span style={downloadedBadgeStyle}>Downloaded</span>}
                {sourceLabel && <span style={sourceBadgeStyle}>{sourceLabel}</span>}
              </div>

              <div style={sidebarRowStyle}>
                <span style={sidebarLabelStyle}>Shadowed today</span>
                <span style={sidebarValueStyle} data-testid="shadowed-count">
                  {doneToday}/{sentences.length}
                </span>
              </div>

              <button onClick={() => setSpeedIdx((i) => (i + 1) % SPEEDS.length)} style={sidebarButtonStyle} data-testid="speed-control">
                <span style={sidebarLabelStyle}>Speed</span>
                <span style={sidebarValueStyle}>{SPEEDS[speedIdx]}×</span>
              </button>

              <button onClick={() => setShowFurigana((v) => !v)} style={sidebarButtonStyle} data-testid="furigana-toggle">
                <span style={sidebarLabelStyle}>Furigana</span>
                <span style={sidebarValueStyle}>{showFurigana ? 'On' : 'Off'}</span>
              </button>
            </div>

            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <div style={{ flex: 1, overflowY: 'auto', padding: '14px 30px 20px', display: 'flex', flexDirection: 'column', gap: 3 }}>
                {transcriptError && (
                  <div style={emptyStateStyle}>
                    <div style={{ font: '600 15px/1.4 IBM Plex Sans', marginBottom: 8 }}>Transcript not available</div>
                    <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)' }}>
                      Download the episode or check back once a transcript has been generated.
                    </div>
                  </div>
                )}
                {!transcriptError && !transcript && (
                  <div style={{ font: '500 13px/1 IBM Plex Sans', color: 'rgba(32,30,26,.5)', padding: '20px 4px' }}>
                    Loading transcript…
                  </div>
                )}
                {sentences.map((s, i) => (
                  <div
                    key={s.index}
                    ref={(el) => {
                      rowRefs.current[i] = el;
                    }}
                    onClick={() => jumpTo(i)}
                    data-testid={`sentence-${s.index}`}
                    data-active={i === activeIndex}
                    style={{ ...sentenceRowStyle, ...(i === activeIndex ? sentenceRowActiveStyle : {}) }}
                  >
                    <Ruby segments={s.segments} showFurigana={showFurigana} />
                  </div>
                ))}
              </div>

              <div style={{ flex: 'none', borderTop: '1px solid rgba(32,30,26,.08)', padding: '14px 30px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <button onClick={togglePlay} style={playBtnStyle} disabled={!episode} data-testid="play-pause">
                  {playing ? (
                    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
                      <rect x="5" y="4" width="4" height="12" rx="1" />
                      <rect x="11" y="4" width="4" height="12" rx="1" />
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
                      <path d="M6 4l10 6-10 6V4z" />
                    </svg>
                  )}
                </button>
                <span style={timeLabelStyle}>{formatTime(currentTime)}</span>
                <input
                  type="range"
                  min={0}
                  max={duration || 0}
                  step={0.01}
                  value={currentTime}
                  onChange={onScrub}
                  style={{ flex: 1, accentColor: '#211f1b' }}
                />
                <span style={timeLabelStyle}>{formatTime(duration)}</span>
                <button
                  onClick={() => setLoopOne((v) => !v)}
                  style={{ ...loopBtnStyle, ...(loopOne ? loopBtnActiveStyle : {}) }}
                  title="Loop this sentence"
                  data-testid="loop-toggle"
                >
                  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.7}>
                    <path d="M4 7h9a3 3 0 0 1 3 3v1M16 13H7a3 3 0 0 1-3-3V9" />
                    <path d="M14 4l3 3-3 3M6 16l-3-3 3-3" />
                  </svg>
                </button>
              </div>

              <audio
                ref={audioRef}
                data-testid="audio"
                src={episode ? api.audioUrl(episode.id) : undefined}
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={(e) => {
                  setDuration(e.currentTarget.duration);
                  if (!resumedRef.current && episode?.position_seconds) {
                    e.currentTarget.currentTime = episode.position_seconds;
                  }
                  resumedRef.current = true;
                  if (autoplayRef.current) {
                    autoplayRef.current = false;
                    e.currentTarget.play();
                  }
                  pushNowPlaying(0);
                }}
                onDurationChange={(e) => setDuration(e.currentTarget.duration)}
                onPlay={() => {
                  setPlaying(true);
                  invokeTauri('begin_playback_wake_lock');
                  pushNowPlaying(SPEEDS[speedIdx]);
                }}
                onPause={() => {
                  setPlaying(false);
                  savePosition();
                  invokeTauri('end_playback_wake_lock');
                  pushNowPlaying(0);
                }}
                style={{ display: 'none' }}
              />
            </div>
          </div>
    </div>
  );
}

const backBtnStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, border: 'none', background: 'none', cursor: 'pointer', padding: '6px 4px', font: '600 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)' };
const sidebarArtStyle: React.CSSProperties = { width: '100%', aspectRatio: '1', borderRadius: 13, objectFit: 'cover', flex: 'none' };
const downloadedBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.42 0.1 155)', background: 'oklch(0.6 0.06 155 / 0.14)', padding: '3px 7px', borderRadius: 5 };
const sourceBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.42 0.06 195)', background: 'oklch(0.55 0.055 195 / 0.12)', padding: '3px 7px', borderRadius: 5 };
const sidebarRowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: 10, background: 'rgba(32,30,26,.04)', border: '1px solid rgba(32,30,26,.06)' };
const sidebarButtonStyle: React.CSSProperties = { ...sidebarRowStyle, cursor: 'pointer', background: '#fff', width: '100%', font: 'inherit', textAlign: 'left' };
const sidebarLabelStyle: React.CSSProperties = { font: '500 10.5px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', textTransform: 'uppercase', letterSpacing: '.05em' };
const sidebarValueStyle: React.CSSProperties = { font: '600 13px/1 IBM Plex Sans', color: '#211f1b' };
const emptyStateStyle: React.CSSProperties = { margin: '30px auto', textAlign: 'center', maxWidth: 360, padding: '40px 24px', border: '1.5px dashed rgba(32,30,26,.16)', borderRadius: 16 };
const sentenceRowStyle: React.CSSProperties = { padding: '10px 14px', borderRadius: 10, cursor: 'pointer', font: '500 16px/1.9 "IBM Plex Sans", sans-serif' };
const sentenceRowActiveStyle: React.CSSProperties = { background: 'oklch(0.55 0.055 195 / 0.14)', boxShadow: 'inset 3px 0 0 oklch(0.42 0.06 195)' };
const playBtnStyle: React.CSSProperties = { width: 42, height: 42, flex: 'none', borderRadius: '50%', border: 'none', background: '#211f1b', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };
const timeLabelStyle: React.CSSProperties = { font: '500 11px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', flex: 'none', minWidth: 34, textAlign: 'center' };
const loopBtnStyle: React.CSSProperties = { width: 34, height: 34, flex: 'none', borderRadius: '50%', border: '1px solid rgba(32,30,26,.14)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'rgba(32,30,26,.6)' };
const loopBtnActiveStyle: React.CSSProperties = { background: 'oklch(0.55 0.055 195 / 0.14)', borderColor: 'oklch(0.42 0.06 195 / 0.4)', color: 'oklch(0.42 0.06 195)' };
