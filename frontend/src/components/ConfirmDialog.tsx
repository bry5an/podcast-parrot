interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel, cancelLabel = 'Cancel', onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <>
      <div onClick={onCancel} style={overlayStyle} />
      <div style={dialogStyle} role="alertdialog" aria-modal="true" aria-label={title}>
        <div style={{ font: '600 15px/1.3 IBM Plex Sans', marginBottom: 8 }}>{title}</div>
        <div style={{ font: '400 13px/1.6 IBM Plex Sans', color: 'rgba(32,30,26,.6)', marginBottom: 20 }}>{message}</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onCancel} style={cancelBtnStyle}>{cancelLabel}</button>
          <button onClick={onConfirm} style={confirmBtnStyle}>{confirmLabel}</button>
        </div>
      </div>
    </>
  );
}

const overlayStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(32,30,26,.35)', zIndex: 100 };
const dialogStyle: React.CSSProperties = {
  position: 'fixed',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 340,
  background: '#fff',
  borderRadius: 14,
  padding: 20,
  boxShadow: '0 12px 32px rgba(32,30,26,.24)',
  zIndex: 101,
};
const cancelBtnStyle: React.CSSProperties = { height: 34, padding: '0 14px', borderRadius: 17, border: '1px solid rgba(32,30,26,.12)', background: '#fff', color: '#211f1b', font: '600 12.5px/1 IBM Plex Sans', cursor: 'pointer' };
const confirmBtnStyle: React.CSSProperties = { height: 34, padding: '0 14px', borderRadius: 17, border: 'none', background: 'oklch(0.5 0.16 25)', color: '#fff', font: '600 12.5px/1 IBM Plex Sans', cursor: 'pointer' };
