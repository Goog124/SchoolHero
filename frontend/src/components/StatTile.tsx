import type { ReactNode } from 'react';
import '../styles/student.css';
import '../styles/info.css';
import type { IconName } from './Icon';

type StatTileProps = {
  /** Оставлено для совместимости; плитка без иконки. */
  icon?: IconName;
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'violet' | 'gold' | 'cyan' | 'lime' | 'pink' | 'red';
  onClick?: () => void;
  /** Кнопка «i» рядом с подписью (не используется вместе с onClick). */
  info?: ReactNode;
};

export function StatTile({ label, value, hint, onClick, info }: StatTileProps) {
  const content = (
    <>
      <span className="st-stat__label">
        {info && !onClick ? (
          <>
            {label.includes(' ') ? `${label.slice(0, label.lastIndexOf(' '))} ` : ''}
            <span className="info-nw">
              {label.slice(label.lastIndexOf(' ') + 1)}
              {info}
            </span>
          </>
        ) : (
          label
        )}
      </span>
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
