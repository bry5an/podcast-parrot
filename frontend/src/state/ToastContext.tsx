import { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { ReactNode } from 'react';

type ToastVariant = 'success' | 'error';

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = 'success') => {
      const id = ++nextId.current;
      setToasts((prev) => [...prev, { id, message, variant }]);
      window.setTimeout(() => dismissToast(id), AUTO_DISMISS_MS);
    },
    [dismissToast],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div style={viewportStyle}>
        {toasts.map((toast) => (
          <div key={toast.id} style={{ ...toastStyle, ...(toast.variant === 'error' ? toastErrorStyle : {}) }}>
            <span style={{ flex: 1 }}>{toast.message}</span>
            <button onClick={() => dismissToast(toast.id)} style={closeBtnStyle} aria-label="Dismiss">
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}

const viewportStyle: React.CSSProperties = {
  position: 'fixed',
  bottom: 24,
  right: 24,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
  zIndex: 1000,
  pointerEvents: 'none',
};

const toastStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  maxWidth: 360,
  padding: '13px 16px',
  borderRadius: 12,
  background: '#211f1b',
  color: '#fff',
  font: '500 13px/1.4 IBM Plex Sans',
  boxShadow: '0 8px 24px rgba(0,0,0,.2)',
  pointerEvents: 'auto',
};

const toastErrorStyle: React.CSSProperties = {
  background: 'oklch(0.32 0.1 25)',
};

const closeBtnStyle: React.CSSProperties = {
  flex: 'none',
  border: 'none',
  background: 'none',
  color: 'rgba(255,255,255,.7)',
  cursor: 'pointer',
  padding: 2,
  display: 'flex',
};
