import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { looksLikeRssUrl } from '../lib/rss';
import type { Podcast } from '../lib/types';

interface Props {
  profileId: number;
  onClose: () => void;
  onSubscriptionChange: () => void;
}

export function AddPodcastPanel({ profileId, onClose, onSubscriptionChange }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Podcast[]>([]);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const isRss = looksLikeRssUrl(query);

  useEffect(() => {
    if (isRss) {
      setResults([]);
      return;
    }
    let cancelled = false;
    api.searchDirectory({ query, profileId }).then((res) => {
      if (!cancelled) setResults(res);
    });
    return () => {
      cancelled = true;
    };
  }, [query, isRss, profileId]);

  const toggleFollow = async (podcast: Podcast) => {
    if (podcast.subscribed) {
      await api.unsubscribe(profileId, podcast.id);
    } else {
      await api.subscribe(profileId, podcast.id);
    }
    setResults((prev) => prev.map((p) => (p.id === podcast.id ? { ...p, subscribed: !p.subscribed } : p)));
    onSubscriptionChange();
  };

  const addFeed = async () => {
    setAdding(true);
    setAddError(null);
    try {
      const podcast = await api.addRssPodcast(query.trim());
      await api.subscribe(profileId, podcast.id);
      setQuery('');
      onSubscriptionChange();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Could not add that feed');
    } finally {
      setAdding(false);
    }
  };

  return (
    <>
      <div onClick={onClose} style={overlayStyle} />
      <div style={panelStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px 16px', flex: 'none' }}>
          <div>
            <div style={{ font: '600 17px/1.2 IBM Plex Sans' }}>Add a podcast</div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="rgba(32,30,26,.55)" strokeWidth={1.7}>
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        <div style={{ padding: '0 24px 14px', flex: 'none' }}>
          <div style={searchBoxStyle}>
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="rgba(32,30,26,.45)" strokeWidth={1.7}>
              <circle cx="9" cy="9" r="6" />
              <path d="M17 17l-3.5-3.5" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search shows, or paste an RSS URL"
              style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', font: '400 13.5px/1 IBM Plex Sans', color: '#211f1b' }}
            />
          </div>
        </div>

        {isRss && (
          <div style={rssBannerStyle}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="oklch(0.45 0.055 195)" strokeWidth={1.7}>
              <circle cx="5" cy="15" r="1.6" />
              <path d="M4 9a7 7 0 0 1 7 7M4 4a12 12 0 0 1 12 12" />
            </svg>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: '600 12.5px/1.3 IBM Plex Sans' }}>RSS feed detected</div>
              <div style={{ font: '400 11px/1.4 IBM Plex Mono', color: 'rgba(32,30,26,.5)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {query}
              </div>
              {addError && <div style={{ font: '400 11px/1.4 IBM Plex Sans', color: 'oklch(0.5 0.13 25)', marginTop: 4 }}>{addError}</div>}
            </div>
            <button onClick={addFeed} disabled={adding} style={addFeedBtnStyle}>
              {adding ? 'Adding…' : 'Add feed'}
            </button>
          </div>
        )}

        <div style={{ padding: '0 24px 6px', flex: 'none' }}>
          <span style={{ font: '500 10px/1 IBM Plex Mono', letterSpacing: '.09em', textTransform: 'uppercase', color: 'rgba(32,30,26,.4)' }}>
            {isRss ? 'Directory' : query ? 'Search results' : 'Suggested shows'}
          </span>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 24px 22px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {!isRss &&
            results.map((r) => (
              <div key={r.id} style={resultRowStyle}>
                {r.artwork_url ? (
                  <img src={r.artwork_url} alt="" style={artStyle} />
                ) : (
                  <div style={{ ...artStyle, background: 'rgba(32,30,26,.08)' }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ font: '600 13.5px/1.3 IBM Plex Sans', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title}
                    </span>
                    {r.level_tag && <span style={levelBadgeStyle}>{r.level_tag}</span>}
                  </div>
                  <div style={{ font: '400 11.5px/1.45 IBM Plex Sans', color: 'rgba(32,30,26,.5)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 230 }}>
                    {r.description}
                  </div>
                </div>
                <button
                  onClick={() => toggleFollow(r)}
                  style={{
                    height: 32,
                    padding: '0 13px',
                    borderRadius: 16,
                    cursor: 'pointer',
                    font: '600 12px/1 IBM Plex Sans',
                    flex: 'none',
                    background: r.subscribed ? 'oklch(0.6 0.06 155 / 0.14)' : '#211f1b',
                    border: `1px solid ${r.subscribed ? 'oklch(0.6 0.06 155 / 0.4)' : '#211f1b'}`,
                    color: r.subscribed ? 'oklch(0.45 0.07 155)' : '#fff',
                  }}
                >
                  {r.subscribed ? 'Following' : 'Follow'}
                </button>
              </div>
            ))}
          {!isRss && query && results.length === 0 && (
            <div style={{ textAlign: 'center', padding: '34px 20px', color: 'rgba(32,30,26,.5)', font: '400 13px/1.6 IBM Plex Sans' }}>
              No shows match "{query}".
              <br />
              Paste the podcast's RSS feed URL to add it directly.
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const overlayStyle: React.CSSProperties = { position: 'absolute', inset: 0, background: 'rgba(32,30,26,.32)', backdropFilter: 'blur(2px)' };
const panelStyle: React.CSSProperties = { position: 'absolute', top: 0, right: 0, bottom: 0, width: 452, background: '#fbfaf7', borderLeft: '1px solid rgba(32,30,26,.1)', boxShadow: '-12px 0 40px rgba(32,30,26,.14)', display: 'flex', flexDirection: 'column' };
const closeBtnStyle: React.CSSProperties = { width: 32, height: 32, borderRadius: 9, border: '1px solid rgba(32,30,26,.12)', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };
const searchBoxStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, height: 44, padding: '0 14px', borderRadius: 11, background: '#fff', border: '1px solid rgba(32,30,26,.14)' };
const rssBannerStyle: React.CSSProperties = { margin: '2px 24px 12px', padding: 14, borderRadius: 12, background: 'oklch(0.55 0.055 195 / 0.09)', border: '1px solid oklch(0.55 0.055 195 / 0.3)', display: 'flex', alignItems: 'center', gap: 12 };
const addFeedBtnStyle: React.CSSProperties = { height: 32, padding: '0 13px', borderRadius: 16, border: 'none', background: '#211f1b', color: '#fff', font: '600 12px/1 IBM Plex Sans', cursor: 'pointer', flex: 'none' };
const resultRowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 13, padding: 11, borderRadius: 12, background: '#fff', border: '1px solid rgba(32,30,26,.08)' };
const artStyle: React.CSSProperties = { width: 48, height: 48, flex: 'none', borderRadius: 10, objectFit: 'cover' };
const levelBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.42 0.06 195)', background: 'oklch(0.55 0.055 195 / 0.12)', padding: '2px 5px', borderRadius: 4, flex: 'none' };
