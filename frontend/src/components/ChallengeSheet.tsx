import { useEffect, useRef, useState } from 'react';
import { stageUpload, uploadPhoto } from '../api';
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

const PHOTO_MAX_SIDE = 1600;

/** Reduces a picked image to at most 1600 px on the long side, JPEG ~0.85. */
async function shrinkImage(file: File): Promise<Blob> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error('decode'));
      el.src = url;
    });
    const scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('canvas');
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('encode'))), 'image/jpeg', 0.85),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

type ChallengeSheetProps = {
  challenge: Challenge | null;
  onClose: () => void;
  onSubmit: (challengeId: number, proof: string, proofUrl?: string) => Promise<boolean>;
  busy: boolean;
};

export function ChallengeSheet({ challenge, onClose, onSubmit, busy }: ChallengeSheetProps) {
  const [proof, setProof] = useState('');
  const [proofUrl, setProofUrl] = useState('');
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoId, setPhotoId] = useState<number | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const photoToken = useRef(0);
  const challengeId = challenge?.id ?? null;

  useEffect(() => {
    setProof(challenge?.status === 'rejected' ? challenge.proof : '');
    setProofUrl(challenge?.proof_url || '');
  }, [challengeId, challenge?.status, challenge?.proof_url, challenge?.proof]);

  // A new challenge starts without a photo; the preview URL is released.
  useEffect(() => {
    photoToken.current += 1;
    setPhotoId(null);
    setPhotoError('');
    setPhotoBusy(false);
    setPhotoUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    if (challengeId !== null) stageUpload(challengeId, null);
  }, [challengeId]);

  const pickPhoto = async (file: File | undefined) => {
    if (!file || challengeId === null) return;
    const token = ++photoToken.current;
    setPhotoError('');
    setPhotoBusy(true);
    try {
      const blob = await shrinkImage(file);
      const id = await uploadPhoto(blob);
      if (token !== photoToken.current) return;
      const preview = URL.createObjectURL(blob);
      setPhotoUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return preview;
      });
      setPhotoId(id);
      stageUpload(challengeId, id);
    } catch (error) {
      if (token !== photoToken.current) return;
      setPhotoId(null);
      stageUpload(challengeId, null);
      setPhotoError(
        error instanceof Error && error.message === 'decode'
          ? 'Не удалось открыть изображение. Выберите другое фото.'
          : error instanceof Error && error.message
            ? error.message
            : 'Не удалось загрузить фото. Попробуйте ещё раз.',
      );
    } finally {
      if (token === photoToken.current) setPhotoBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  if (!challenge) return null;

  const status = STATUS_META[challenge.status]?.short ?? '';
  const canSubmit = challenge.status === 'available' || challenge.status === 'rejected';
  const hints = PROOF_HINTS[challenge.category] ?? [];
  const trimmed = proof.trim();
  const deadline = formatDeadline(challenge.deadline);
  const needsPhoto = challenge.proof_type === 'photo';
  const needsLink = challenge.proof_type === 'link';
  const linkOk = !needsLink || /^https?:\/\/\S+$/i.test(proofUrl.trim());
  const ready = trimmed.length >= 3 && linkOk && (!needsPhoto || photoId !== null) && !photoBusy;

  const handleSubmit = async () => {
    if (!canSubmit || !ready) return;
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
            disabled={busy || !ready}
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

            {needsPhoto ? (
              <div>
                <span className="st-label">Фото работы</span>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  hidden
                  onChange={(e) => void pickPhoto(e.target.files?.[0])}
                />
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt="Выбранное фото"
                    style={{ display: 'block', width: '100%', maxHeight: 260, objectFit: 'contain', borderRadius: 12, marginBottom: 8 }}
                  />
                ) : null}
                <button
                  type="button"
                  className="st-btn st-btn--block"
                  style={{ minHeight: 44 }}
                  onClick={() => fileRef.current?.click()}
                  disabled={photoBusy}
                >
                  {photoBusy ? 'Загружаем фото…' : photoUrl ? 'Выбрать другое фото' : 'Сфотографировать или выбрать'}
                </button>
                {photoError ? (
                  <p className="st-hint" role="alert">
                    {photoError}
                  </p>
                ) : (
                  <p className="st-hint">Фото обязательно. Оно уменьшается перед отправкой.</p>
                )}
              </div>
            ) : null}

            <div>
              <label className="st-label" htmlFor="st-proof-url">
                {needsLink ? 'Ссылка на работу' : 'Ссылка на работу (необязательно)'}
              </label>
              <input
                id="st-proof-url"
                type="url"
                className="st-input"
                value={proofUrl}
                onChange={(e) => setProofUrl(e.target.value)}
                placeholder="https://"
                required={needsLink}
              />
              {needsLink && !linkOk ? (
                <p className="st-hint">Ссылка должна начинаться с http:// или https://</p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}
