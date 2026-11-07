import { useState } from 'react';
import type { JoinRequestInfo } from '../types';
import { useConfirm } from './ConfirmDialog';
import { Icon } from './Icon';
import '../styles/onboarding.css';
import '../styles/setup.css';

type JoinRequestScreenProps = {
  request: JoinRequestInfo;
  onCancel: () => Promise<boolean>;
  onUseCode: () => void;
  onRefresh: () => void;
};

/** Ученик ждёт подтверждения заявки: в класс он пока не входит. */
export function JoinRequestScreen({ request, onCancel, onUseCode, onRefresh }: JoinRequestScreenProps) {
  const { confirm, dialog } = useConfirm();
  const [busy, setBusy] = useState(false);

  const cancel = async () => {
    const ok = await confirm({
      title: 'Отменить заявку?',
      message: `Заявка в класс ${request.class_name} будет отозвана. Можно будет выбрать другой класс или войти по коду.`,
      confirmLabel: 'Отменить заявку',
      cancelLabel: 'Не отменять',
    });
    if (!ok) return;
    setBusy(true);
    await onCancel();
    setBusy(false);
  };

  return (
    <div className="ob">
      <header className="ob-top">
        <span className="ob-brand">Школьный герой</span>
      </header>
      <main className="ob-main">
        <section className="ob-card" aria-labelledby="jr-h">
          <div>
            <h1 className="ob-title" id="jr-h">
              Заявка отправлена в {request.class_name}
            </h1>
            <p className="ob-lead">
              {request.school_name}. Ждём подтверждения педагога. Когда заявку примут, откроются
              задания и рейтинг класса.
            </p>
          </div>
          <div className="ob-notice" role="status">
            <Icon name="clock" size={16} />
            <span>Если у вас есть код класса, войдите по нему: заявка тогда не нужна.</span>
          </div>
          <div className="su-actions su-actions--stack">
            <button type="button" className="ob-btn" onClick={onUseCode} disabled={busy}>
              Ввести код вместо этого
            </button>
            <button type="button" className="ob-btn ob-btn--ghost" onClick={onRefresh} disabled={busy}>
              <Icon name="refresh" size={16} />
              Проверить статус
            </button>
            <button type="button" className="ob-btn ob-btn--ghost" onClick={() => void cancel()} disabled={busy}>
              {busy ? 'Отменяем…' : 'Отменить заявку'}
            </button>
          </div>
        </section>
      </main>
      {dialog}
    </div>
  );
}
