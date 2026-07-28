import { useCallback, useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { AddPodcastPanel } from '../components/AddPodcastPanel';
import { api } from '../lib/api';
import { DIRECTION_META, PALETTE } from '../lib/palette';
import { useProfiles } from '../state/ProfileContext';
import type { Podcast } from '../lib/types';

export function Library() {
  const { currentProfile, clearProfile, loading } = useProfiles();
  const navigate = useNavigate();
  const [subscriptions, setSubscriptions] = useState<Podcast[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const refreshSubscriptions = useCallback(() => {
    if (!currentProfile) return;
    api.listSubscriptions(currentProfile.id).then((subs) => {
      setSubscriptions(subs);
      setLoaded(true);
    });
  }, [currentProfile]);

  useEffect(() => {
    refreshSubscriptions();
  }, [refreshSubscriptions]);

  if (!currentProfile) return loading ? null : <Navigate to="/" replace />;

  const swatch = PALETTE[currentProfile.palette_index % PALETTE.length];
  const meta = DIRECTION_META[currentProfile.direction];

  const unfollow = async (podcastId: number) => {
    await api.unsubscribe(currentProfile.id, podcastId);
    refreshSubscriptions();
  };

  return (
    <div style={{ position: 'relative', display: 'flex', height: '100vh', background: '#fbfaf7', color: '#211f1b' }}>
          {/* nav rail */}
          <div style={{ width: 212, flex: 'none', borderRight: '1px solid rgba(32,30,26,.08)', display: 'flex', flexDirection: 'column', padding: '20px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 8px 18px' }}>
              <div style={{ width: 26, height: 26, borderRadius: 7, background: '#211f1b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="#fff" strokeWidth={1.7}>
                  <path d="M6 10a4 4 0 0 1 8 0M8.5 10v4M11.5 10v4M10 3v3" />
                </svg>
              </div>
              <span style={{ font: '600 14px/1 IBM Plex Sans' }}>Kotoba</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <div style={navItemActiveStyle}>
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <rect x="3" y="3" width="6" height="6" rx="1.5" />
                  <rect x="11" y="3" width="6" height="6" rx="1.5" />
                  <rect x="3" y="11" width="6" height="6" rx="1.5" />
                  <rect x="11" y="11" width="6" height="6" rx="1.5" />
                </svg>
                My podcasts
              </div>
              <div onClick={() => setAddOpen(true)} style={navItemStyle}>
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <circle cx="9" cy="9" r="6" />
                  <path d="M17 17l-3.5-3.5" />
                </svg>
                Discover
              </div>
              <div style={navItemStyle}>
                <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <path d="M4 5h12M4 10h12M4 15h8" />
                </svg>
                Continue
              </div>
            </div>
            <div style={{ height: 1, background: 'rgba(32,30,26,.08)', margin: '16px 6px' }} />
            <div style={{ font: '500 10px/1 IBM Plex Mono', letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(32,30,26,.4)', padding: '0 10px 10px' }}>
              Learning
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, font: '500 12px/1 IBM Plex Sans', color: 'rgba(32,30,26,.6)', padding: '0 10px' }}>
              <span style={{ fontSize: 13 }}>{meta.flag}</span> {meta.title}
            </div>
            <div
              onClick={() => {
                clearProfile();
                navigate('/');
              }}
              style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', gap: 10, padding: 8, borderRadius: 10, border: '1px solid rgba(32,30,26,.08)', cursor: 'pointer' }}
            >
              <div style={{ width: 30, height: 30, borderRadius: '50%', background: swatch.art, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', font: '600 12px/1 IBM Plex Sans' }}>
                {currentProfile.name[0]?.toUpperCase()}
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ font: '600 12px/1.2 IBM Plex Sans' }}>{currentProfile.name}</div>
                <div style={{ font: '400 10px/1.3 IBM Plex Mono', color: 'rgba(32,30,26,.45)', marginTop: 2 }}>{meta.code}</div>
              </div>
            </div>
          </div>

          {/* main */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', padding: '26px 30px 18px', flex: 'none' }}>
              <div>
                <div style={{ font: '500 11px/1 IBM Plex Mono', letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(32,30,26,.45)', marginBottom: 9 }}>
                  My podcasts
                </div>
                <h1 style={{ font: '600 25px/1.2 IBM Plex Sans', margin: 0 }}>
                  {loaded ? (subscriptions.length === 1 ? '1 podcast' : `${subscriptions.length} podcasts`) : '…'}
                </h1>
              </div>
              <button onClick={() => setAddOpen(true)} style={addBtnStyle}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.9}>
                  <path d="M8 3v10M3 8h10" />
                </svg>
                Add podcast
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '4px 30px 28px', display: 'flex', flexDirection: 'column', gap: 11 }}>
              {subscriptions.map((p) => {
                const goToEpisodes = () => navigate(`/library/podcasts/${p.id}/episodes`, { state: { podcast: p } });
                return (
                  <div key={p.id} style={cardStyle}>
                    {p.artwork_url ? (
                      <img src={p.artwork_url} alt="" style={cardArtStyle} onClick={goToEpisodes} />
                    ) : (
                      <div style={{ ...cardArtStyle, background: 'rgba(32,30,26,.08)' }} onClick={goToEpisodes} />
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                        <span style={{ font: '600 15px/1.3 IBM Plex Sans', cursor: 'pointer' }} onClick={goToEpisodes}>{p.title}</span>
                        {p.level_tag && <span style={levelBadgeStyle}>{p.level_tag}</span>}
                      </div>
                      <div style={{ font: '400 12px/1.5 IBM Plex Sans', color: 'rgba(32,30,26,.55)', marginTop: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 440 }}>
                        {p.description}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 'none' }}>
                      <button onClick={() => unfollow(p.id)} style={unfollowBtnStyle} title="Unfollow">
                        <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}>
                          <path d="M5 5l10 10M15 5L5 15" />
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
              {loaded && subscriptions.length === 0 && (
                <div style={{ margin: '30px auto', textAlign: 'center', maxWidth: 360, padding: '40px 24px', border: '1.5px dashed rgba(32,30,26,.16)', borderRadius: 16 }}>
                  <div style={{ font: '600 15px/1.4 IBM Plex Sans', marginBottom: 8 }}>No podcasts followed yet</div>
                  <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.55)' }}>
                    Add a podcast to start shadowing. Search the directory or paste an RSS feed.
                  </div>
                </div>
              )}
            </div>
          </div>

          {addOpen && (
            <AddPodcastPanel
              profileId={currentProfile.id}
              language={currentProfile.direction === 'en_ja' ? 'ja' : 'en'}
              onClose={() => setAddOpen(false)}
              onSubscriptionChange={refreshSubscriptions}
            />
          )}
    </div>
  );
}

const navItemActiveStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', borderRadius: 9, background: 'rgba(32,30,26,.06)', font: '600 13px/1 IBM Plex Sans', color: '#211f1b' };
const navItemStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', borderRadius: 9, font: '500 13px/1 IBM Plex Sans', color: 'rgba(32,30,26,.55)', cursor: 'pointer' };
const addBtnStyle: React.CSSProperties = { height: 40, padding: '0 17px', borderRadius: 20, border: 'none', background: '#211f1b', color: '#fff', display: 'flex', alignItems: 'center', gap: 8, font: '600 13px/1 IBM Plex Sans', cursor: 'pointer', boxShadow: '0 3px 12px rgba(32,30,26,.2)' };
const cardStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 16, padding: 14, borderRadius: 14, background: '#fff', border: '1px solid rgba(32,30,26,.08)' };
const cardArtStyle: React.CSSProperties = { width: 60, height: 60, flex: 'none', borderRadius: 11, objectFit: 'cover', cursor: 'pointer' };
const levelBadgeStyle: React.CSSProperties = { font: '500 10px/1 IBM Plex Mono', color: 'oklch(0.42 0.06 195)', background: 'oklch(0.55 0.055 195 / 0.12)', padding: '3px 6px', borderRadius: 5 };
const unfollowBtnStyle: React.CSSProperties = { width: 34, height: 34, borderRadius: '50%', border: '1px solid rgba(32,30,26,.12)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'rgba(32,30,26,.5)' };
