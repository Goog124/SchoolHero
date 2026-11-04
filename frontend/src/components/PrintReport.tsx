import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import '../styles/print.css';

export const PDF_HINT = 'Для PDF: в окне печати выберите принтер «Сохранить как PDF».';

/**
 * Лист для печати. Выносится в <body>, на экране скрыт,
 * при печати остаётся единственным видимым элементом.
 */
export function PrintSheet({ children }: { children: ReactNode }) {
  if (typeof document === 'undefined') return null;
  return createPortal(
    <div className="pr-sheet" aria-hidden="true">
      {children}
    </div>,
    document.body,
  );
}

export function PrintHint() {
  return <p className="pr-hint">{PDF_HINT}</p>;
}

export function printDocument(): void {
  try {
    window.print();
  } catch {
    // печать недоступна в этом окружении
  }
}

export function formatPrintDate(date: Date = new Date()): string {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}

export function formatShortDate(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(d);
}
