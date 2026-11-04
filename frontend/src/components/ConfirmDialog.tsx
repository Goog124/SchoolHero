import { useCallback, useState, type ReactNode } from 'react';
import { Sheet } from './Sheet';

export type ConfirmOptions = {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Необратимое действие: кнопка подтверждения красная. */
  danger?: boolean;
};

type Pending = { options: ConfirmOptions; resolve: (value: boolean) => void };

/**
 * Замена window.confirm: `if (await confirm({ title: 'Удалить класс?' })) ...`.
 * Нужно один раз вывести `dialog` в разметке экрана.
 */
export function useConfirm() {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setPending({ options, resolve });
      }),
    [],
  );

  const close = useCallback(
    (result: boolean) => {
      pending?.resolve(result);
      setPending(null);
    },
    [pending],
  );

  const options = pending?.options;
  const dialog = (
    <Sheet
      open={Boolean(pending)}
      onClose={() => close(false)}
      title={options?.title}
      footer={
        <div className="confirm__actions">
          <button type="button" className="btn btn--secondary" onClick={() => close(false)}>
            {options?.cancelLabel ?? 'Отмена'}
          </button>
          <button
            type="button"
            className={`btn ${options?.danger ? 'btn--danger' : ''}`.trim()}
            onClick={() => close(true)}
          >
            {options?.confirmLabel ?? 'Подтвердить'}
          </button>
        </div>
      }
    >
      {options?.message ? <p className="confirm__text">{options.message}</p> : null}
    </Sheet>
  );

  return { confirm, dialog };
}
