import { useEffect, useState } from 'react';
import {
  CATEGORY_META,
  STATUS_META,
  formatDeadline,
  formatNumber,
  formatRelative,
} from '../game';
import type { Challenge, ChallengeCategory } from '../types';
import { Chip } from './Chip';
import { Icon } from './Icon';
import { Sheet } from './Sheet';

const PROOF_HINTS: Record<ChallengeCategory, string[]> = {
  homework: ['Фото тетради', 'Сдал(а) на уроке', 'Скрин из электронного дневника'],
  club: ['Фото с занятия', 'Отметка руководителя', 'Расскажу, что делал(а)'],
  help: ['Кому помог(ла)', 'Что объяснил(а)', 'Подтвердит одноклассник'],
  weekly: ['Коротко о результате', 'Фото или скрин', 'Ссылка на работу'],
  olympiad: ['Диплом или грамота', 'Результат с сайта', 'Скрин из личного кабинета'],
  event: ['Фото события', 'Что я делал(а)', 'Отметка организатора'],
  streak: ['Отметка за сегодня', 'Скрин серии', 'Пара слов о дне'],
};

type ChallengeSheetProps = {
  challenge: Challenge | null;
  onClose: () => void;
  onSubmit: (challengeId: number, proof: string) => Promise<boolean>;
  busy: boolean;
};

export function ChallengeSheet({ challenge, onClose, onSubmit, busy }: ChallengeSheetProps) {
  const [proof, setProof] = useState('');
  const challengeId = challenge?.id ?? null;

  useEffect(() => {
    setProof(challenge?.status === 'rejected' ? challenge.proof : '');
  }, [challengeId, challenge?.status]);

  if (!challenge) return null;

  const meta = CATEGORY_META[challenge.category];
  const status = STATUS_META[challenge.status];
  const canSubmit =
    challenge.status === 'available' || challenge.status === 'rejected';
  const hints = PROOF_HINTS[challenge.category];
  const trimmed = proof.trim();

  const handleSubmit = async () => {
    if (!canSubmit || trimmed.length < 3) return;
    const ok = await onSubmit(challenge.id, trimmed);
    if (ok) onClose();
  };

  return (
    <Sheet
      open
      onClose={onClose}
      title={challenge.title}
      subtitle={`${challenge.category_label} · ${challenge.kind_label}`}
      footer={
        canSubmit ? (
          <button
            type="button"
            className="btn btn--block"
            onClick={handleSubmit}
            disabled={busy || trimmed.length < 3}
          >
            {busy ? 'Отправляем…' : 'Отправить на проверку'}
            {!busy ? <Icon name="send" size={17} /> : null}
          </button>
        ) : undefined
      }
    >
      <div className="challenge-sheet__hero">
        <span className={`challenge-sheet__icon category-mark tone-${meta.tone}`}>
          <Icon name={meta.icon} size={24} />
        </span>
        <div className="challenge-sheet__xp">
          <span>Награда</span>
          <strong>
            <Icon name="spark" size={16} filled />+{challenge.xp} XP
          </strong>
        </div>
        <span className={`status-pill status-pill--${challenge.status}`}>{status.short}</span>
      </div>

      <p className="challenge-sheet__desc">{challenge.description}</p>

      <div className="challenge-sheet__facts">
        <Chip icon="clock" size="sm">
          {formatDeadline(challenge.deadline)}
        </Chip>
        <Chip icon="users" size="sm">
          {formatNumber(challenge.participants)} участн.
        </Chip>
        <Chip icon="user" size="sm">
          {challenge.author}
        </Chip>
      </div>

      {challenge.status === 'pending' ? (
        <div className="status-panel status-panel--pending">
          <span className="status-panel__icon">
            <Icon name="clock" size={20} />
          </span>
          <div>
            <strong>Ждёт подтверждения педагога</strong>
            <p>
              Отправлено {formatRelative(challenge.submitted_at)}. XP придёт сразу после
              проверки.
            </p>
            {challenge.proof ? <blockquote>{challenge.proof}</blockquote> : null}
          </div>
        </div>
      ) : null}

      {challenge.status === 'approved' ? (
        <div className="status-panel status-panel--approved">
          <span className="status-panel__icon">
            <Icon name="check" size={20} />
          </span>
          <div>
            <strong>Задание выполнено</strong>
            <p>Педагог подтвердил работу. +{challenge.xp} XP уже в копилке класса.</p>
            {challenge.proof ? <blockquote>{challenge.proof}</blockquote> : null}
          </div>
        </div>
      ) : null}

      {challenge.status === 'expired' ? (
        <div className="status-panel status-panel--expired">
          <span className="status-panel__icon">
            <Icon name="lock" size={20} />
          </span>
          <div>
            <strong>Срок истёк</strong>
            <p>Задание больше нельзя отправить, но можно спросить педагога о новом.</p>
          </div>
        </div>
      ) : null}

      {challenge.status === 'rejected' ? (
        <div className="status-panel status-panel--rejected">
          <span className="status-panel__icon">
            <Icon name="alert" size={20} />
          </span>
          <div>
            <strong>Нужно исправить</strong>
            <p>{challenge.reject_reason || 'Педагог попросил дополнить подтверждение.'}</p>
          </div>
        </div>
      ) : null}

      {canSubmit ? (
        <div className="proof-form">
          <label htmlFor="proof">
            {challenge.status === 'rejected' ? 'Что исправим?' : 'Как подтвердишь?'}
          </label>
          <p className="proof-form__hint">
            Пара слов или ссылка. Педагог увидит это в кабинете и подтвердит в один тап.
          </p>
          <div className="proof-chips">
            {hints.map((hint) => (
              <button
                key={hint}
                type="button"
                className="proof-chip"
                onClick={() => setProof(hint)}
              >
                {hint}
              </button>
            ))}
          </div>
          <textarea
            id="proof"
            value={proof}
            onChange={(event) => setProof(event.target.value)}
            maxLength={300}
            rows={3}
            placeholder="Например: решил задачу №14, фото в чате класса"
          />
          <span className="proof-form__count">{proof.length} / 300</span>
        </div>
      ) : null}
    </Sheet>
  );
}
