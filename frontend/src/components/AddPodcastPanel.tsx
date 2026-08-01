import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { looksLikeRssUrl } from '../lib/rss';
import { isTauri } from '../lib/tauri';
import type { Podcast } from '../lib/types';
import { looksLikeYoutubePlaylistUrl } from '../lib/youtube';

interface Props {
  profileId: number;
  language: string;
  onClose: () => void;
  onSubscriptionChange: () => void;
}

export function AddPodcastPanel({ profileId, language, onClose, onSubscriptionChange }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Podcast[]>([]);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [localFolder, setLocalFolder] = useState<string | null>(null);

  const isYoutube = looksLikeYoutubePlaylistUrl(query);
  // The RSS pattern matches any https:// URL, so a pasted YouTube link would
  // otherwise also satisfy it — check YouTube first.
  const isRss = !isYoutube && looksLikeRssUrl(query);

  useEffect(() => {
    if (isRss || isYoutube || localFolder) {
      setResults([]);
      return;
    }
    let cancelled = false;
    api.searchDirectory({ query, profileId, language }).then((res) => {
      if (!cancelled) setResults(res);
    });
    return () => {
      cancelled = true;
    };
  }, [query, isRss, isYoutube, localFolder, profileId, language]);

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

  const addPlaylist = async () => {
    setAdding(true);
    setAddError(null);
    try {
      const podcast = await api.addYoutubePodcast(query.trim());
      await api.subscribe(profileId, podcast.id);
      setQuery('');
      onSubscriptionChange();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Could not add that playlist');
    } finally {
      setAdding(false);
    }
  };

  const pickLocalFolder = async () => {
    if (!isTauri()) return;
    const { open } = await import('@tauri-apps/plugin-dialog');
    const selected = await open({ directory: true, multiple: false });
    if (selected && typeof selected === 'string') {
      setAddError(null);
      setLocalFolder(selected);
    }
  };

  const addLocalFolder = async () => {
    if (!localFolder) return;
    setAdding(true);
    setAddError(null);
    try {
      const podcast = await api.addLocalDirectoryPodcast(localFolder);
      await api.subscribe(profileId, podcast.id);
      setLocalFolder(null);
      onSubscriptionChange();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Could not add that folder');
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
            <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="rgb(var(--fg-rgb) / .55)" strokeWidth={1.7}>
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        <div style={{ padding: '0 24px 14px', flex: 'none' }}>
          <div style={searchBoxStyle}>
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="rgb(var(--fg-rgb) / .45)" strokeWidth={1.7}>
              <circle cx="9" cy="9" r="6" />
              <path d="M17 17l-3.5-3.5" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search shows, or paste an RSS or YouTube playlist URL"
              style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', font: '400 13.5px/1 IBM Plex Sans', color: 'var(--fg)' }}
            />
          </div>
        </div>

        {isTauri() && !isRss && !isYoutube && !localFolder && (
          <div style={{ padding: '0 24px 14px', flex: 'none' }}>
            <button onClick={pickLocalFolder} style={chooseFolderBtnStyle}>
              Choose a local folder…
            </button>
          </div>
        )}

        {localFolder && (
          <div style={rssBannerStyle}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="oklch(0.45 0.055 195)" strokeWidth={1.7}>
              <path d="M3 6a2 2 0 0 1 2-2h3l1.5 2H15a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6Z" />
            </svg>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: '600 12.5px/1.3 IBM Plex Sans' }}>Local folder selected</div>
              <div style={{ font: '400 11px/1.4 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .5)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {localFolder}
              </div>
              {addError && <div style={{ font: '400 11px/1.4 IBM Plex Sans', color: 'oklch(0.5 0.13 25)', marginTop: 4 }}>{addError}</div>}
            </div>
            <button onClick={addLocalFolder} disabled={adding} style={addFeedBtnStyle}>
              {adding ? 'Adding…' : 'Add folder'}
            </button>
          </div>
        )}

        {isYoutube && (
          <div style={rssBannerStyle}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="oklch(0.45 0.055 195)" strokeWidth={1.7}>
              <circle cx="5" cy="15" r="1.6" />
              <path d="M4 9a7 7 0 0 1 7 7M4 4a12 12 0 0 1 12 12" />
            </svg>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: '600 12.5px/1.3 IBM Plex Sans' }}>YouTube playlist detected</div>
              <div style={{ font: '400 11px/1.4 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .5)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {query}
              </div>
              {addError && <div style={{ font: '400 11px/1.4 IBM Plex Sans', color: 'oklch(0.5 0.13 25)', marginTop: 4 }}>{addError}</div>}
            </div>
            <button onClick={addPlaylist} disabled={adding} style={addFeedBtnStyle}>
              {adding ? 'Adding…' : 'Add playlist'}
            </button>
          </div>
        )}

        {isRss && (
          <div style={rssBannerStyle}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="oklch(0.45 0.055 195)" strokeWidth={1.7}>
              <circle cx="5" cy="15" r="1.6" />
              <path d="M4 9a7 7 0 0 1 7 7M4 4a12 12 0 0 1 12 12" />
            </svg>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: '600 12.5px/1.3 IBM Plex Sans' }}>RSS feed detected</div>
              <div style={{ font: '400 11px/1.4 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .5)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
          <span style={{ font: '500 10px/1 IBM Plex Mono', letterSpacing: '.09em', textTransform: 'uppercase', color: 'rgb(var(--fg-rgb) / .4)' }}>
            {isRss || isYoutube || localFolder ? 'Directory' : query ? 'Search results' : 'Suggested shows'}
          </span>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 24px 22px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {!isRss &&
            !isYoutube &&
            !localFolder &&
            results.map((r) => (
              <div key={r.id} style={resultRowStyle}>
                {r.artwork_url ? (
                  <img src={r.artwork_url} alt="" style={artStyle} />
                ) : (
                  <div style={{ ...artStyle, background: 'rgb(var(--fg-rgb) / .08)' }} />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ font: '600 13.5px/1.3 IBM Plex Sans', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title}
                    </span>
                    {r.level_tag && <span style={levelBadgeStyle}>{r.level_tag}</span>}
                    {r.locale_tag && <span style={localeBadgeStyle}>{r.locale_tag}</span>}
                  </div>
                  <div style={{ font: '400 11.5px/1.45 IBM Plex Sans', color: 'rgb(var(--fg-rgb) / .5)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 230 }}>
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
                    background: r.subscribed ? 'oklch(0.6 0.06 155 / 0.14)' : 'var(--fg)',
                    border: `1px solid ${r.subscribed ? 'oklch(0.6 0.06 155 / 0.4)' : 'var(--fg)'}`,
                    color: r.subscribed ? 'oklch(0.45 0.07 155)' : 'var(--bg-page)',
                  }}
                >
                  {r.subscribed ? 'Following' : 'Follow'}
                </button>
              </div>
            ))}
          {!isRss && !isYoutube && !localFolder && query && results.length === 0 && (
            <div style={{ textAlign: 'center', padding: '34px 20px', color: 'rgb(var(--fg-rgb) / .5)', font: '400 13px/1.6 IBM Plex Sans' }}>
              No shows match "{query}".
              <br />
              Paste the podcast's RSS feed URL or a YouTube playlist URL to add it directly.
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const overlayStyle: React.CSSProperties = { position: 'absolute', inset: 0, background: 'rgb(var(--fg-rgb) / .32)', backdropFilter: 'blur(2px)' };
const panelStyle: React.CSSProperties = { position: 'absolute', top: 0, right: 0, bottom: 0, width: 452, background: 'var(--bg-page)', borderLeft: '1px solid rgb(var(--fg-rgb) / .1)', boxShadow: '-12px 0 40px rgb(var(--fg-rgb) / .14)', display: 'flex', flexDirection: 'column' };
const closeBtnStyle: React.CSSProperties = { width: 32, height: 32, borderRadius: 9, border: '1px solid rgb(var(--fg-rgb) / .12)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' };
const searchBoxStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, height: 44, padding: '0 14px', borderRadius: 11, background: 'var(--bg-surface)', border: '1px solid rgb(var(--fg-rgb) / .14)' };
const rssBannerStyle: React.CSSProperties = { margin: '2px 24px 12px', padding: 14, borderRadius: 12, background: 'oklch(0.55 0.055 195 / 0.09)', border: '1px solid oklch(0.55 0.055 195 / 0.3)', display: 'flex', alignItems: 'center', gap: 12 };
const addFeedBtnStyle: React.CSSProperties = { height: 32, padding: '0 13px', borderRadius: 16, border: 'none', background: 'var(--fg)', color: 'var(--bg-page)', font: '600 12px/1 IBM Plex Sans', cursor: 'pointer', flex: 'none' };
const chooseFolderBtnStyle: React.CSSProperties = { width: '100%', height: 40, borderRadius: 11, border: '1px dashed rgb(var(--fg-rgb) / .25)', background: 'transparent', color: 'rgb(var(--fg-rgb) / .7)', font: '500 12.5px/1 IBM Plex Sans', cursor: 'pointer' };
const resultRowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 13, padding: 11, borderRadius: 12, background: 'var(--bg-surface)', border: '1px solid rgb(var(--fg-rgb) / .08)' };
const artStyle: React.CSSProperties = { width: 48, height: 48, flex: 'none', borderRadius: 10, objectFit: 'cover' };
const levelBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'oklch(0.42 0.06 195)', background: 'oklch(0.55 0.055 195 / 0.12)', padding: '2px 5px', borderRadius: 4, flex: 'none' };
const localeBadgeStyle: React.CSSProperties = { font: '500 9.5px/1 IBM Plex Mono', color: 'rgb(var(--fg-rgb) / .55)', background: 'rgb(var(--fg-rgb) / .08)', padding: '2px 5px', borderRadius: 4, flex: 'none' };
