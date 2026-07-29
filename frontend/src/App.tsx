import { Route, Routes } from 'react-router-dom';
import { ProfilePicker } from './pages/ProfilePicker';
import { Library } from './pages/Library';
import { Episodes } from './pages/Episodes';
import { Player } from './pages/Player';
import { AsrSetup } from './pages/AsrSetup';
import { Settings } from './pages/Settings';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ProfilePicker />} />
      <Route path="/setup" element={<AsrSetup />} />
      <Route path="/library" element={<Library />} />
      <Route path="/library/podcasts/:podcastId/episodes" element={<Episodes />} />
      <Route path="/library/podcasts/:podcastId/episodes/:episodeId/player" element={<Player />} />
      <Route path="/settings" element={<Settings />} />
    </Routes>
  );
}

export default App;
