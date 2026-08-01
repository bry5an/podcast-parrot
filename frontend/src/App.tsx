import { useEffect } from 'react';
import { Route, Routes, useNavigate } from 'react-router-dom';
import { ProfilePicker } from './pages/ProfilePicker';
import { Library } from './pages/Library';
import { Episodes } from './pages/Episodes';
import { Player } from './pages/Player';
import { AsrSetup } from './pages/AsrSetup';
import { Settings } from './pages/Settings';
import { SavedSentences } from './pages/SavedSentences';
import { applyTheme, loadTheme } from './lib/theme';

function App() {
  const navigate = useNavigate();

  useEffect(() => {
    applyTheme(loadTheme());
  }, []);

  // Cmd+, opens Settings from anywhere, matching standard macOS convention.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault();
        navigate('/settings');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [navigate]);

  return (
    <Routes>
      <Route path="/" element={<ProfilePicker />} />
      <Route path="/setup" element={<AsrSetup />} />
      <Route path="/library" element={<Library />} />
      <Route path="/library/podcasts/:podcastId/episodes" element={<Episodes />} />
      <Route path="/library/podcasts/:podcastId/episodes/:episodeId/player" element={<Player />} />
      <Route path="/saved-sentences" element={<SavedSentences />} />
      <Route path="/settings" element={<Settings />} />
    </Routes>
  );
}

export default App;
