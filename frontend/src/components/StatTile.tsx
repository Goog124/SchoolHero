import { Icon, type IconName } from './Icon';

type StatTileProps = {
  icon: IconName;
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'violet' | 'gold' | 'cyan' | 'lime' | 'pink' | 'red';
};

export function StatTile({ icon, label, value, hint, tone = 'violet' }: StatTileProps) {
  return (
    <div className={`stat-tile stat-tile--${tone}`}>
      <span className="stat-tile__icon">
        <Icon name={icon} size={16} />
      </span>
      <span className="stat-tile__value">{value}</span>
      <span className="stat-tile__label">{label}</span>
      {hint ? <span className="stat-tile__hint">{hint}</span> : null}
    </div>
  );
}
