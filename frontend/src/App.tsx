import { Route, Routes } from 'react-router-dom';
import { ProfilePicker } from './pages/ProfilePicker';
import { Library } from './pages/Library';
import { Episodes } from './pages/Episodes';
import { Player } from './pages/Player';
import { AsrSetup } from './pages/AsrSetup';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ProfilePicker />} />
      <Route path="/setup" element={<AsrSetup />} />
      <Route path="/library" element={<Library />} />
      <Route path="/library/podcasts/:podcastId/episodes" element={<Episodes />} />
      <Route path="/library/podcasts/:podcastId/episodes/:episodeId/player" element={<Player />} />
    </Routes>
  );
}

export default App;
