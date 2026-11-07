import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon';

// Открытые окна друг над другом: Escape закрывает только верхнее.
const openSheets: symbol[] = [];

type SheetProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  className?: string;
};

export function Sheet({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  wide = false,
  className = '',
}: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // Родитель обычно передаёт новую функцию на каждый рендер; держим её в ref,
  // иначе эффект перезапускается при каждом нажатии клавиши и фокус уходит из поля.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const token = Symbol('sheet');
    openSheets.push(token);
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && openSheets[openSheets.length - 1] === token) {
        onCloseRef.current();
      }
    };
    document.addEventListener('keydown', handleKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const timer = window.setTimeout(() => {
      const panel = panelRef.current;
      if (panel && !panel.contains(document.activeElement)) panel.focus();
    }, 60);
    return () => {
      document.removeEventListener('keydown', handleKey);
      const at = openSheets.indexOf(token);
      if (at >= 0) openSheets.splice(at, 1);
      document.body.style.overflow = previousOverflow;
      window.clearTimeout(timer);
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="sheet-layer">
      <button
        type="button"
        className="sheet-backdrop"
        aria-label="Закрыть"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className={`sheet ${wide ? 'sheet--wide' : ''} ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label={title ?? 'Окно'}
        tabIndex={-1}
      >
        <div className="sheet__grip" aria-hidden="true" />
        {title ? (
          <header className="sheet__head">
            <div className="sheet__heading">
              <h2>{title}</h2>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть">
              <Icon name="x" size={18} />
            </button>
          </header>
        ) : null}
        <div className="sheet__body">{children}</div>
        {footer ? <div className="sheet__footer">{footer}</div> : null}
      </div>
    </div>
  );
}
