import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './fonts.css';
import './index.css';
import App from './App.tsx';
import { ProfileProvider } from './state/ProfileContext';
import { ToastProvider } from './state/ToastContext';
import { TranscriptionProvider } from './state/TranscriptionContext';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ProfileProvider>
        <ToastProvider>
          <TranscriptionProvider>
            <App />
          </TranscriptionProvider>
        </ToastProvider>
      </ProfileProvider>
    </BrowserRouter>
  </StrictMode>,
);
