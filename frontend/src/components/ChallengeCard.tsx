import '../styles/student.css';
import { STATUS_META, formatDeadline, formatNumber } from '../game';
import type { Challenge } from '../types';
import { Icon } from './Icon';

type ChallengeCardProps = {
  challenge: Challenge;
  onOpen: (id: number) => void;
  compact?: boolean;
};

export function ChallengeCard({ challenge, onOpen, compact = false }: ChallengeCardProps) {
  const status = STATUS_META[challenge.status]?.short ?? '';
  const tag = [challenge.subject || challenge.category_label, challenge.kind_label]
    .filter(Boolean)
    .join(' · ');
  const deadline = formatDeadline(challenge.deadline);

  return (
    <button
      type="button"
      className="st-card-task"
      onClick={() => onOpen(challenge.id)}
      aria-label={`${challenge.title}. ${status}. Открыть`}
    >
      <span className="st-card-task__top">
        <span className="st-card-task__tag">{tag}</span>
        <span className="st-xp">+{formatNumber(challenge.xp)} XP</span>
      </span>
      <span className="st-card-task__title" style={{ display: 'block' }}>
        {challenge.title}
      </span>
      {!compact && challenge.description ? (
        <span className="st-card-task__desc">{challenge.description}</span>
      ) : null}
      <span className="st-card-task__foot">
        <span className="st-meta">
          {deadline ? (
            <>
              <Icon name="clock" size={14} />
              {deadline}
            </>
          ) : null}
        </span>
        <span className={`st-pill st-pill--${challenge.status}`}>{status}</span>
      </span>
    </button>
  );
}
