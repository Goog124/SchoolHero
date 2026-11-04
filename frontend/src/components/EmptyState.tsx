import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

type EmptyStateProps = {
  icon?: IconName;
  title: string;
  text?: string;
  action?: ReactNode;
  compact?: boolean;
};

export function EmptyState({
  icon = 'info',
  title,
  text,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={`empty ${compact ? 'empty--compact' : ''}`.trim()}>
      <span className="empty__icon" aria-hidden="true">
        <Icon name={icon} size={compact ? 20 : 24} />
      </span>
      <h3>{title}</h3>
      {text ? <p>{text}</p> : null}
      {action ? <div className="empty__action">{action}</div> : null}
    </div>
  );
}
