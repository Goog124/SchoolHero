import { useEffect, useState } from 'react';
import '../styles/student.css';
import { STATUS_META, formatDeadline, formatNumber, formatRelative } from '../game';
import type { Challenge, ChallengeCategory } from '../types';
import { Sheet } from './Sheet';

const PROOF_HINTS: Record<ChallengeCategory, string[]> = {
  homework: ['Сдал(а) работу на уроке', 'Выполнил(а) в электронном дневнике', 'Прикрепил(а) фото решения'],
  club: ['Был(а) на занятии', 'Защитил(а) проект', 'Ссылка на работу'],
  help: ['Объяснил(а) тему однокласснику', 'Помог(ла) подготовиться к контрольной'],
  weekly: ['Задание выполнено', 'Ссылка на результат'],
  olympiad: ['Ссылка на диплом или результат', 'Принял(а) участие'],
  event: ['Участвовал(а) в мероприятии', 'Помогал(а) в организации'],
  streak: ['Посетил(а) все уроки', 'Без опозданий и пропусков'],
};

type ChallengeSheetProps = {
  challenge: Challenge | null;
  onClose: () => void;
  onSubmit: (challengeId: number, proof: string, proofUrl?: string) => Promise<boolean>;
  busy: boolean;
};

export function ChallengeSheet({ challenge, onClose, onSubmit, busy }: ChallengeSheetProps) {
  const [proof, setProof] = useState('');
  const [proofUrl, setProofUrl] = useState('');
  const challengeId = challenge?.id ?? null;

  useEffect(() => {
    setProof(challenge?.status === 'rejected' ? challenge.proof : '');
    setProofUrl(challenge?.proof_url || '');
  }, [challengeId, challenge?.status, challenge?.proof_url, challenge?.proof]);

  if (!challenge) return null;

  const status = STATUS_META[challenge.status]?.short ?? '';
  const canSubmit = challenge.status === 'available' || challenge.status === 'rejected';
  const hints = PROOF_HINTS[challenge.category] ?? [];
  const trimmed = proof.trim();
  const deadline = formatDeadline(challenge.deadline);

  const handleSubmit = async () => {
    if (!canSubmit || trimmed.length < 3) return;
    const ok = await onSubmit(challenge.id, trimmed, proofUrl.trim());
    if (ok) onClose();
  };

  return (
    <Sheet
      open
      onClose={onClose}
      title={challenge.title}
      subtitle={[challenge.subject || challenge.category_label, challenge.kind_label]
        .filter(Boolean)
        .join(' · ')}
      footer={
        canSubmit ? (
          <button
            type="button"
            className="st-btn st-btn--block"
            onClick={handleSubmit}
            disabled={busy || trimmed.length < 3}
          >
            {busy ? 'Отправляем…' : 'Отправить на проверку'}
          </button>
        ) : undefined
      }
    >
      <div className="st-sheet">
        <div className="st-sheet__reward">
          <div>
            <span>Награда</span>
            <strong>+{formatNumber(challenge.xp)} XP</strong>
          </div>
          <span className={`st-pill st-pill--${challenge.status}`}>{status}</span>
        </div>

        {challenge.description ? <p className="st-sheet__desc">{challenge.description}</p> : null}

        <dl className="st-facts">
          {deadline ? (
            <div>
              <dt>Срок</dt>
              <dd>{deadline}</dd>
            </div>
          ) : null}
          {challenge.author ? (
            <div>
              <dt>Автор</dt>
              <dd>{challenge.author}</dd>
            </div>
          ) : null}
          <div>
            <dt>Участников</dt>
            <dd>{formatNumber(challenge.participants)}</dd>
          </div>
        </dl>

        {challenge.status === 'pending' ? (
          <div className="st-notice st-notice--pending">
            <strong>Ждёт проверки учителя</strong>
            <p>
              {challenge.submitted_at ? `Отправлено ${formatRelative(challenge.submitted_at)}. ` : ''}
              XP будут начислены после подтверждения.
            </p>
            {challenge.proof ? <blockquote>{challenge.proof}</blockquote> : null}
            {challenge.proof_url ? (
              <p>
                Ссылка:{' '}
                <a href={challenge.proof_url} target="_blank" rel="noreferrer">
                  {challenge.proof_url}
                </a>
              </p>
            ) : null}
          </div>
        ) : null}

        {challenge.status === 'approved' ? (
          <div className="st-notice st-notice--approved">
            <strong>Задание выполнено</strong>
            <p>Учитель подтвердил работу, +{formatNumber(challenge.xp)} XP начислены.</p>
            {challenge.proof ? <blockquote>{challenge.proof}</blockquote> : null}
          </div>
        ) : null}

        {challenge.status === 'rejected' ? (
          <div className="st-notice st-notice--rejected">
            <strong>Нужно исправить или дополнить</strong>
            <p>{challenge.reject_reason || 'Учитель попросил дополнить подтверждение.'}</p>
          </div>
        ) : null}

        {canSubmit ? (
          <div className="st-form">
            {hints.length ? (
              <div>
                <span className="st-label">Быстрый ответ</span>
                <div className="st-chips">
                  {hints.map((hint) => (
                    <button key={hint} type="button" className="st-chip" onClick={() => setProof(hint)}>
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div>
              <label className="st-label" htmlFor="st-proof">
                {challenge.status === 'rejected' ? 'Что исправлено' : 'Что вы сделали'}
              </label>
              <textarea
                id="st-proof"
                className="st-input st-textarea"
                value={proof}
                onChange={(e) => setProof(e.target.value)}
                maxLength={300}
                rows={3}
                placeholder="Коротко опишите результат"
              />
              <p className="st-hint">Не меньше 3 символов, до 300.</p>
            </div>

            <div>
              <label className="st-label" htmlFor="st-proof-url">
                Ссылка на работу (необязательно)
              </label>
              <input
                id="st-proof-url"
                type="url"
                className="st-input"
                value={proofUrl}
                onChange={(e) => setProofUrl(e.target.value)}
                placeholder="https://"
              />
            </div>
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}
