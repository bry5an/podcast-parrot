import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { useProfiles } from '../state/ProfileContext';
import type { Episode, EpisodeFilter, EpisodeSort, Podcast } from '../lib/types';

const FILTERS: { key: EpisodeFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'unplayed', label: 'Unplayed' },
  { key: 'downloaded', label: 'Downloaded' },
];

function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function formatDate(value: string | null): string {
  if (!value) return '';
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function cadenceLabel(episodes: Episode[]): string | null {
  const dates = episodes
    .map((e) => e.pub_date)
    .filter((d): d is string => !!d)
    .map((d) => new Date(d).getTime())
    .sort((a, b) => b - a)
    .slice(0, 6);
  if (dates.length < 2) return null;
  const gaps: number[] = [];
  for (let i = 0; i < dates.length - 1; i++) gaps.push(dates[i] - dates[i + 1]);
  const avgDays = gaps.reduce((a, b) => a + b, 0) / gaps.length / 86_400_000;
  if (avgDays <= 1.5) return 'Daily';
  if (avgDays <= 4) return 'A few times a week';
  if (avgDays <= 9) return 'Weekly';
  if (avgDays <= 20) return 'Biweekly';
  return 'Monthly';
}

export function Episodes() {
  const { podcastId } = useParams();
  const id = Number(podcastId);
  const location = useLocation();
  const navigate = useNavigate();
  const { currentProfile, loading: profileLoading } = useProfiles();

  const [podcast, setPodcast] = useState<Podcast | null>(
    (location.state as { podcast?: Podcast } | null)?.podcast ?? null,
  );
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = useState<EpisodeFilter>('all');
  const [sort, setSort] = useState<EpisodeSort>('newest');
  const pollTimers = useRef<Record<number, number>>({});

  // requestSeq guards against out-of-order responses: only the response to the
  // most-recently-issued request is applied, so a slow request for a stale
  // filter can never clobber a faster one for the filter the user picked next.
  const requestSeq = useRef(0);
  const refresh = useCallback(() => {
    if (!currentProfile) return;
    const seq = ++requestSeq.current;
    api.listEpisodes(id, { profileId: currentProfile.id, filter, sort }).then((rows) => {
      if (seq !== requestSeq.current) return;
      setEpisodes(rows);
      setLoaded(true);
    });
  }, [id, currentProfile, filter, sort]);

  // refreshRef always points at the refresh closure for the CURRENT filter/sort,
  // so a download-completion callback fired long after the user changed tabs
  // re-fetches under today's filter rather than the one active when it started.
  const refreshRef = useRef(refresh);
  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (podcast || !currentProfile) return;
    api.listSubscriptions(currentProfile.id).then((subs) => {
      const match = subs.find((p) => p.id === id);
      if (match) setPodcast(match);
    });
  }, [podcast, currentProfile, id]);

  useEffect(() => {
    const timers = pollTimers.current;
    return () => {
      Object.values(timers).forEach((t) => window.clearInterval(t));
    };
  }, []);

  const pollStatus = useCallback((episodeId: number) => {
    if (pollTimers.current[episodeId]) return;
    const timer = window.setInterval(async () => {
      const status = await api.getEpisodeStatus(episodeId);
      if (status.download_status !== 'downloading') {
        window.clearInterval(pollTimers.current[episodeId]);
        delete pollTimers.current[episodeId];
        // Authoritative refetch: the episode may since have scrolled out of
        // (or into) the active filter, so a local patch can't be trusted here.
        refreshRef.current();
      } else {
        setEpisodes((prev) =>
          prev.map((e) => (e.id === episodeId ? { ...e, download_status: status.download_status } : e)),
        );
      }
    }, 1200);
    pollTimers.current[episodeId] = timer;
  }, []);

  const startDownload = useCallback(
    async (episode: Episode) => {
      setEpisodes((prev) =>
        prev.map((e) => (e.id === episode.id ? { ...e, download_status: 'downloading' } : e)),
      );
      await api.startDownload(episode.id);
      pollStatus(episode.id);
    },
    [pollStatus],
  );

  const removeDownload = async (episode: Episode) => {
    await api.deleteDownload(episode.id);
    refreshRef.current();
  };

  const downloadAll = () => {
    episodes
      .filter((e) => e.download_status === 'idle' || e.download_status === 'failed')
      .forEach((e) => startDownload(e));
  };

  const cadence = useMemo(() => cadenceLabel(episodes), [episodes]);

  if (!profileLoading && !currentProfile) return <Navigate to="/" replace />;
  if (!currentProfile) return null;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', padding: 32 }}>
      <div style={{ width: '100%', maxWidth: 1120, background: '#fff', border: '1px solid rgba(32,30,26,.1)', borderRadius: 16, boxShadow: '0 12px 48px rgba(32,30,26,.14)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 712, background: '#fbfaf7', color: '#211f1b' }}>
          <div style={{ padding: '22px 30px 0', flex: 'none' }}>
            <button onClick={() => navigate('/library')} style={backBtnStyle}>
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path d="M12 4l-6 6 6 6" />
              </svg>
              My podcasts
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, padding: '16px 30px 20px', flex: 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
              {podcast?.artwork_url ? (
                <img src={podcast.artwork_url} alt="" style={headerArtStyle} />
              ) : (
                <div style={{ ...headerArtStyle, background: 'rgba(32,30,26,.08)' }} />
              )}
              <div style={{ minWidth: 0 }}>
                <h1 style={{ font: '600 22px/1.25 IBM Plex Sans', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {podcast?.title ?? '…'}
                </h1>
                <div style={{ font: '500 12px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 8 }}>
                  {loaded ? (episodes.length === 1 ? '1 episode' : `${episodes.length} episodes`) : '…'}
                  {cadence ? ` · ${cadence}` : ''}
                </div>
              </div>
            </div>
            <button onClick={downloadAll} style={downloadAllBtnStyle}>
              <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.7}>
                <path d="M10 3v10M6 9l4 4 4-4M4 16h12" />
              </svg>
              Download all
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 30px 14px', flex: 'none' }}>
            <div style={{ display: 'flex', gap: 6 }}>
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  style={{ ...filterTabStyle, ...(filter === f.key ? filterTabActiveStyle : {}) }}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <button onClick={() => setSort((s) => (s === 'newest' ? 'oldest' : 'newest'))} style={sortBtnStyle}>
              <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path d="M6 4v12M6 16l-3-3M6 16l3-3M14 16V4M14 4l-3 3M14 4l3 3" />
              </svg>
              {sort === 'newest' ? 'Newest first' : 'Oldest first'}
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 30px 28px', display: 'flex', flexDirection: 'column', gap: 9 }}>
            {episodes.map((ep) => {
              // "In progress" excludes both a near-zero start and the last few
              // seconds, so a barely-begun or essentially-finished episode
              // still reads as "Shadow" rather than "Continue".
              const inProgress =
                ep.position_seconds != null &&
                ep.position_seconds > 5 &&
                (!ep.duration_seconds || ep.position_seconds < ep.duration_seconds - 5);
              return (
                <div key={ep.id} style={rowStyle}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ font: '600 14px/1.35 IBM Plex Sans', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ep.title}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, font: '400 11.5px/1 IBM Plex Mono', color: 'rgba(32,30,26,.5)' }}>
                      <span>{formatDate(ep.pub_date)}</span>
                      {ep.duration_seconds ? <span>· {formatDuration(ep.duration_seconds)}</span> : null}
                      {ep.transcript_source_url && <span style={transcriptBadgeStyle}>Transcript</span>}
                      {ep.transcript_status === 'queued' && (
                        <span style={queuedBadgeStyle} title="Waiting for a Whisper model — install one in Setup">
                          Queued
                        </span>
                      )}
                    </div>
                    {ep.position_seconds != null && ep.duration_seconds ? (
                      <div style={progressTrackStyle} data-testid={`progress-${ep.id}`}>
                        <div
                          style={{
                            ...progressFillStyle,
                            width: `${Math.min(100, (ep.position_seconds / ep.duration_seconds) * 100)}%`,
                          }}
                        />
                      </div>
                    ) : null}
                  </div>
                  {ep.download_status === 'downloaded' && (
                    <button
                      onClick={() => navigate(`/library/podcasts/${id}/episodes/${ep.id}/player`, { state: { podcast, episode: ep } })}
                      style={shadowBtnStyle}
                      title={inProgress ? 'Continue shadowing this episode' : 'Shadow this episode'}
                    >
                      <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M6 4l10 6-10 6V4z" />
                      </svg>
                      {inProgress ? 'Continue' : 'Shadow'}
                    </button>
                  )}
                  <DownloadButton episode={ep} onDownload={() => startDownload(ep)} onRemove={() => removeDownload(ep)} />
                </div>
              );
            })}
            {loaded && episodes.length === 0 && (
              <div style={{ margin: '30px auto', textAlign: 'center', maxWidth: 360, padding: '40px 24px', border: '1.5px dashed rgba(32,30,26,.16)', borderRadius: 16 }}>
                <div style={{ font: '600 15px/1.4 IBM Plex Sans', marginBottom: 8 }}>No episodes here</div>
                <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)' }}>
                  {filter === 'all' ? 'This show has no episodes yet.' : 'Try a different filter.'}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function DownloadButton({
  episode,
  onDownload,
  onRemove,
}: {
  episode: Episode;
  onDownload: () => void;
  onRemove: () => void;
}) {
  if (episode.download_status === 'downloading') {
    return (
      <div style={downloadBtnStyle} title="Downloading…">
        <svg className="spinner" width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="rgba(32,30,26,.55)" strokeWidth={1.8}>
          <path d="M10 3a7 7 0 1 1-7 7" />
        </svg>
      </div>
    );
  }
  if (episode.download_status === 'downloaded') {
    return (
      <button onClick={onRemove} style={{ ...downloadBtnStyle, ...downloadBtnDoneStyle }} title="Remove download">
        <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="oklch(0.42 0.1 155)" strokeWidth={1.9}>
          <path d="M4.5 10.5 8 14l7.5-8" />
        </svg>
      </button>
    );
  }
  return (
    <button onClick={onDownload} style={downloadBtnStyle} title={episode.download_status === 'failed' ? 'Retry download' : 'Download'}>
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke={episode.download_status === 'failed' ? 'oklch(0.5 0.13 25)' : 'currentColor'} strokeWidth={1.7}>
        <path d="M10 3v10M6 9l4 4 4-4M4 16h12" />
      </svg>
    </button>
  );
}

const backBtnStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, border: 'none', background: 'none', cursor: 'pointer', padding: '6px 4px', font: '600 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)' };
const headerArtStyle: React.CSSProperties = { width: 64, height: 64, flex: 'none', borderRadius: 13, objectFit: 'cover' };
const downloadAllBtnStyle: React.CSSProperties = { height: 38, padding: '0 16px', borderRadius: 19, border: '1px solid rgba(32,30,26,.14)', background: '#fff', display: 'flex', alignItems: 'center', gap: 8, font: '600 12.5px/1 IBM Plex Sans', color: '#211f1b', cursor: 'pointer', flex: 'none' };
const filterTabStyle: React.CSSProperties = { height: 32, padding: '0 14px', borderRadius: 16, border: '1px solid rgba(32,30,26,.12)', background: '#fff', font: '600 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)', cursor: 'pointer' };
const filterTabActiveStyle: React.CSSProperties = { background: '#211f1b', borderColor: '#211f1b', color: '#fff' };
const sortBtnStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 7, height: 32, padding: '0 13px', borderRadius: 16, border: '1px solid rgba(32,30,26,.12)', background: '#fff', font: '600 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.6)', cursor: 'pointer' };
const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 16, padding: '13px 14px', borderRadius: 13, background: '#fff', border: '1px solid rgba(32,30,26,.08)' };
const transcriptBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.42 0.06 195)', background: 'oklch(0.55 0.055 195 / 0.12)', padding: '2px 6px', borderRadius: 5 };
const queuedBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.5 0.13 70)', background: 'oklch(0.55 0.13 70 / 0.14)', padding: '2px 6px', borderRadius: 5 };
const progressTrackStyle: React.CSSProperties = { marginTop: 8, height: 3, borderRadius: 2, background: 'rgba(32,30,26,.08)', overflow: 'hidden' };
const progressFillStyle: React.CSSProperties = { height: '100%', borderRadius: 2, background: 'oklch(0.55 0.055 195)' };
const downloadBtnStyle: React.CSSProperties = { width: 34, height: 34, flex: 'none', borderRadius: '50%', border: '1px solid rgba(32,30,26,.14)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'rgba(32,30,26,.6)' };
const downloadBtnDoneStyle: React.CSSProperties = { background: 'oklch(0.6 0.06 155 / 0.14)', borderColor: 'oklch(0.6 0.06 155 / 0.4)' };
const shadowBtnStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6, height: 34, padding: '0 14px', borderRadius: 17, border: '1px solid rgba(32,30,26,.14)', background: '#211f1b', color: '#fff', font: '600 12px/1 IBM Plex Sans', cursor: 'pointer', flex: 'none' };
