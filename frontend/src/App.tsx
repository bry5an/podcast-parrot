import { Route, Routes } from 'react-router-dom';
import { ProfilePicker } from './pages/ProfilePicker';
import { Library } from './pages/Library';
import { Episodes } from './pages/Episodes';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ProfilePicker />} />
      <Route path="/library" element={<Library />} />
      <Route path="/library/podcasts/:podcastId/episodes" element={<Episodes />} />
    </Routes>
  );
}

export default App;
