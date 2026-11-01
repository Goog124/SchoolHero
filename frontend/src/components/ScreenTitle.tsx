import type { ReactNode } from 'react';

type ScreenTitleProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
};

export function ScreenTitle({ eyebrow, title, subtitle, action }: ScreenTitleProps) {
  return (
    <div className="screen-head">
      <div className="screen-head__text">
        {eyebrow ? <span className="screen-head__eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {action ? <div className="screen-head__action">{action}</div> : null}
    </div>
  );
}
