type LevelBadgeProps = {
  level: number;
  title?: string;
  compact?: boolean;
};

export function LevelBadge({ level, title, compact = false }: LevelBadgeProps) {
  return (
    <span className={`level-badge ${compact ? 'level-badge--compact' : ''}`.trim()}>
      <span className="level-badge__star" aria-hidden="true">
        ★
      </span>
      <span className="level-badge__text">
        {compact ? level : `Уровень ${level}`}
        {title && !compact ? <span className="level-badge__title">{title}</span> : null}
      </span>
    </span>
  );
}
