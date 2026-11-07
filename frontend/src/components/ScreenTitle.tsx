import type { ReactNode } from 'react';
import '../styles/info.css';

type ScreenTitleProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  /** Кнопка «i» после заголовка. */
  info?: ReactNode;
};

export function ScreenTitle({ eyebrow, title, subtitle, action, info }: ScreenTitleProps) {
  // Последнее слово держим вместе с кнопкой, чтобы она не оставалась одна на строке.
  const cut = title.lastIndexOf(' ');
  return (
    <div className="screen-head">
      <div className="screen-head__text">
        {eyebrow ? <span className="screen-head__eyebrow">{eyebrow}</span> : null}
        <h1>
          {info ? (
            <>
              {cut > 0 ? `${title.slice(0, cut)} ` : ''}
              <span className="info-nw">
                {cut > 0 ? title.slice(cut + 1) : title}
                {info}
              </span>
            </>
          ) : (
            title
          )}
        </h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action ? <div className="screen-head__action">{action}</div> : null}
    </div>
  );
}
