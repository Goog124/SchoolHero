import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';

type ChipProps = {
  icon?: IconName;
  children: ReactNode;
  tone?: 'default' | 'violet' | 'gold' | 'cyan' | 'lime' | 'pink' | 'orange' | 'red';
  className?: string;
  size?: 'sm' | 'md';
};

export function Chip({
  icon,
  children,
  tone = 'default',
  className = '',
  size = 'md',
}: ChipProps) {
  return (
    <span className={`chip chip--${tone} chip--${size} ${className}`.trim()}>
      {icon ? <Icon name={icon} size={size === 'sm' ? 12 : 14} filled={icon === 'spark'} /> : null}
      <span>{children}</span>
    </span>
  );
}
