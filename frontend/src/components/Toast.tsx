import { useEffect } from 'react';
import { Icon, type IconName } from './Icon';

export type ToastTone = 'success' | 'error' | 'info';

export type ToastData = {
  id: number;
  message: string;
  tone: ToastTone;
  icon?: IconName;
};

type ToastProps = {
  toast: ToastData | null;
  onClose: () => void;
};

const TONE_ICON: Record<ToastTone, IconName> = {
  success: 'check',
  error: 'alert',
  info: 'info',
};

export function Toast({ toast, onClose }: ToastProps) {
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(onClose, 3600);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  if (!toast) return null;

  return (
    <div className="toast-layer" aria-live="polite">
      <div key={toast.id} className={`toast toast--${toast.tone}`} role="status">
        <span className="toast__icon">
          <Icon name={toast.icon ?? TONE_ICON[toast.tone]} size={17} />
        </span>
        <span className="toast__text">{toast.message}</span>
        <button type="button" className="toast__close" onClick={onClose} aria-label="Скрыть">
          <Icon name="x" size={14} />
        </button>
      </div>
    </div>
  );
}
