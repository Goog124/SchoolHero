import { useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Chip } from '../components/Chip';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { Sheet } from '../components/Sheet';
import { CATEGORY_META, formatRelative, plural } from '../game';
import type { ReviewItem, TeacherData } from '../types';

const REJECT_HINTS = [
  'Добавь фото или ссылку',
  'Не хватает подробностей',
  'Задание выполнено не до конца',
];

type TeacherReviewScreenProps = {
  teacher: TeacherData;
  busyId: number | null;
  onApprove: (completionId: number) => Promise<boolean>;
  onReject: (completionId: number, reason: string) => Promise<boolean>;
};

export function TeacherReviewScreen({
  teacher,
  busyId,
  onApprove,
  onReject,
}: TeacherReviewScreenProps) {
  const [rejectTarget, setRejectTarget] = useState<ReviewItem | null>(null);
  const [reason, setReason] = useState('');
  const [rejecting, setRejecting] = useState(false);

  const openReject = (item: ReviewItem) => {
    setRejectTarget(item);
    setReason('');
  };

  const confirmReject = async () => {
    if (!rejectTarget) return;
    setRejecting(true);
    const ok = await onReject(rejectTarget.id, reason.trim());
    setRejecting(false);
    if (ok) setRejectTarget(null);
  };

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Один тап — и готово"
        title="Проверка работ"
        subtitle="Подтверждай достижения учеников. Опыт и искры начислятся сразу."
        action={
          <Chip icon={teacher.pending.length ? 'clock' : 'check'} tone={teacher.pending.length ? 'gold' : 'lime'} size="sm">
            {teacher.pending.length
              ? `${teacher.pending.length} ${plural(teacher.pending.length, 'ждёт', 'ждут', 'ждут')}`
              : 'всё проверено'}
          </Chip>
        }
      />

      {teacher.pending.length ? (
        <>
          <div className="review-summary">
            <span className="review-summary__icon">
              <Icon name="shield" size={21} />
            </span>
            <div>
              <strong>Заявки учеников</strong>
              <p>Проверь подтверждение и нажми «Подтвердить». Это займёт секунду.</p>
            </div>
            <span className="review-summary__count">{teacher.pending.length}</span>
          </div>

          <div className="review-list">
            {teacher.pending.map((item) => {
              const meta = CATEGORY_META[item.category];
              const busy = busyId === item.id;
              return (
                <article key={item.id} className="review-card">
                  <header className="review-card__head">
                    <AvatarFrame avatar={item.avatar} size={46} decorative />
                    <div className="review-card__student">
                      <strong>{item.student_name}</strong>
                      <span>
                        {item.student_level_title} · {formatRelative(item.created_at)}
                        {item.is_self ? ' · твоя работа' : ''}
                      </span>
                    </div>
                    <span className={`category-mark tone-${meta.tone} category-mark--sm`}>
                      <Icon name={meta.icon} size={16} />
                    </span>
                  </header>

                  <div className="review-card__challenge">
                    <span className="review-card__category">{item.category_label}</span>
                    <h3>{item.title}</h3>
                    <span className="xp-pill xp-pill--lg">
                      <Icon name="spark" size={13} filled />+{item.xp} XP
                    </span>
                  </div>

                  <blockquote className="review-card__proof">
                    {item.proof ? (
                      <>
                        <Icon name="edit" size={14} />
                        <span>{item.proof}</span>
                      </>
                    ) : (
                      <span className="review-card__no-proof">Без комментария к работе</span>
                    )}
                  </blockquote>

                  <footer className="review-card__actions">
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm review-card__reject"
                      onClick={() => openReject(item)}
                      disabled={busy}
                    >
                      <Icon name="x" size={15} />
                      Отклонить
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm review-card__approve"
                      onClick={() => onApprove(item.id)}
                      disabled={busy}
                    >
                      {busy ? 'Начисляем…' : 'Подтвердить'}
                      {!busy ? <Icon name="check" size={16} /> : null}
                    </button>
                  </footer>
                </article>
              );
            })}
          </div>

          <div className="review-note">
            <Icon name="info" size={16} />
            <span>
              Если работа не подходит, укажи причину — ученик увидит её в задании и сможет
              отправить заново.
            </span>
          </div>
        </>
      ) : (
        <div className="review-empty">
          <EmptyState
            icon="check"
            title="Все работы проверены"
            text="Новые заявки появятся здесь, как только ученики отправят подтверждения. Можно вернуться в класс и посмотреть активность."
          />
        </div>
      )}

      <Sheet
        open={Boolean(rejectTarget)}
        onClose={() => setRejectTarget(null)}
        title="Отклонить работу?"
        subtitle={rejectTarget ? `${rejectTarget.student_name} · ${rejectTarget.title}` : ''}
        footer={
          <div className="sheet-actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setRejectTarget(null)}
              disabled={rejecting}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={confirmReject}
              disabled={rejecting}
            >
              {rejecting ? 'Отклоняем…' : 'Отклонить'}
            </button>
          </div>
        }
      >
        <p className="confirm-text">
          Ученик увидит причину и сможет исправить подтверждение. XP начислен не будет.
        </p>
        <div className="proof-chips">
          {REJECT_HINTS.map((hint) => (
            <button
              key={hint}
              type="button"
              className={`proof-chip ${reason === hint ? 'is-active' : ''}`.trim()}
              onClick={() => setReason(hint)}
            >
              {hint}
            </button>
          ))}
        </div>
        <textarea
          className="reason-input"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          maxLength={200}
          placeholder="Причина (необязательно)"
        />
      </Sheet>
    </div>
  );
}
