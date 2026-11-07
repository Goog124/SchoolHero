import { useState } from 'react';
import type { ClassJoinRequest } from '../types';
import { useConfirm } from './ConfirmDialog';
import { formatShortDate } from './PrintReport';
import '../styles/onboarding.css';
import '../styles/setup.css';

type JoinRequestsListProps = {
  requests: ClassJoinRequest[];
  /** Показывать класс у каждой заявки (директору: заявки всей школы). */
  showClass?: boolean;
  onDecide: (requestId: number, action: 'approve' | 'decline') => Promise<boolean>;
  title?: string;
};

/** Заявки учеников, выбравших класс из списка школ: принять или отклонить. */
export function JoinRequestsList({
  requests,
  showClass = false,
  onDecide,
  title = 'Заявки на вступление',
}: JoinRequestsListProps) {
  const { confirm, dialog } = useConfirm();
  const [busyId, setBusyId] = useState<number | null>(null);

  if (requests.length === 0) return null;

  const run = async (request: ClassJoinRequest, action: 'approve' | 'decline') => {
    if (action === 'decline') {
      const ok = await confirm({
        title: `Отклонить заявку: ${request.name}?`,
        message:
          'Ученик увидит, что заявку отклонили, и сможет выбрать другой класс или войти по коду.',
        confirmLabel: 'Отклонить',
        danger: true,
      });
      if (!ok) return;
    }
    setBusyId(request.id);
    await onDecide(request.id, action);
    setBusyId(null);
  };

  return (
    <section className="su-req" aria-labelledby="su-req-h">
      <div className="su-req__head">
        <h2 className="su-h2" id="su-req-h">
          {title}
        </h2>
        <span className="su-req__count">{requests.length}</span>
      </div>
      <p className="su-req__hint">
        Ученики выбрали класс из списка школ. Принимайте только тех, кого знаете: принятый
        ученик увидит одноклассников и рейтинг. По коду класса ученики входят без заявки.
      </p>
      <ul className="su-req__list">
        {requests.map((request) => (
          <li key={request.id} className="su-req__item">
            <div className="su-req__text">
              <strong className="su-req__name">{request.name || 'Без имени'}</strong>
              <span className="su-req__meta">
                {[
                  showClass ? `в ${request.class_name}` : '',
                  `подана ${formatShortDate(request.created_at)}`,
                  request.current_class ? `сейчас в ${request.current_class}` : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </div>
            <div className="su-req__actions">
              <button
                type="button"
                className="ob-btn ob-btn--ghost"
                disabled={busyId !== null}
                onClick={() => void run(request, 'decline')}
              >
                Отклонить
              </button>
              <button
                type="button"
                className="ob-btn"
                disabled={busyId !== null}
                onClick={() => void run(request, 'approve')}
              >
                {busyId === request.id ? 'Сохраняем…' : 'Принять'}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {dialog}
    </section>
  );
}
