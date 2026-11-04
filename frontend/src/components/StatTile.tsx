import '../styles/student.css';
import type { IconName } from './Icon';

type StatTileProps = {
  /** Оставлено для совместимости; плитка без иконки. */
  icon?: IconName;
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'violet' | 'gold' | 'cyan' | 'lime' | 'pink' | 'red';
  onClick?: () => void;
};

export function StatTile({ label, value, hint, onClick }: StatTileProps) {
  const content = (
    <>
      <span className="st-stat__label">{label}</span>
      <span className="st-stat__value">{value}</span>
      {hint ? <span className="st-stat__hint">{hint}</span> : null}
    </>
  );

  return onClick ? (
    <button type="button" className="st-stat" onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className="st-stat">{content}</div>
  );
}
