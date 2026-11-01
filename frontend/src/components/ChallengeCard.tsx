import { CATEGORY_META, STATUS_META, formatDeadline, formatNumber } from '../game';
import type { Challenge } from '../types';
import { Icon } from './Icon';

type ChallengeCardProps = {
  challenge: Challenge;
  onOpen: (id: number) => void;
  compact?: boolean;
};

export function ChallengeCard({ challenge, onOpen, compact = false }: ChallengeCardProps) {
  const meta = CATEGORY_META[challenge.category];
  const status = STATUS_META[challenge.status];
  return (
    <button
      type="button"
      className={`challenge-card challenge-card--${challenge.status} ${
        compact ? 'challenge-card--compact' : ''
      }`.trim()}
      onClick={() => onOpen(challenge.id)}
    >
      <span className={`category-mark tone-${meta.tone}`}>
        <Icon name={meta.icon} size={18} />
      </span>
      <span className="challenge-card__main">
        <span className="challenge-card__top">
          <span className="challenge-card__title">{challenge.title}</span>
          <span className="xp-pill">
            <Icon name="spark" size={12} filled />+{challenge.xp}
          </span>
        </span>
        {!compact ? <span className="challenge-card__desc">{challenge.description}</span> : null}
        <span className="challenge-card__meta">
          <span className="challenge-card__deadline">
            <Icon name="clock" size={12} />
            {formatDeadline(challenge.deadline)}
          </span>
          <span className="challenge-card__participants">
            <Icon name="users" size={12} />
            {formatNumber(challenge.participants)}
          </span>
          <span className={`status-pill status-pill--${challenge.status}`}>
            {status.short}
          </span>
        </span>
      </span>
    </button>
  );
}
