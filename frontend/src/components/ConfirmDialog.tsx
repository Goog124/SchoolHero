import { useCallback, useState, type ReactNode } from 'react';
import { Sheet } from './Sheet';

export type ConfirmInput = {
  label: string;
  placeholder?: string;
  maxLength?: number;
  /** Текст должен совпасть с этим значением (подтверждение вводом названия). */
  match?: string;
  /** Минимальная длина текста (после обрезки пробелов). */
  minLength?: number;
};

export type ConfirmOptions = {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Необратимое действие: кнопка подтверждения красная. */
  danger?: boolean;
  /** Поле ввода под текстом: ответ возвращает `ask`. */
  input?: ConfirmInput;
};

type Pending = { options: ConfirmOptions; resolve: (value: string | null) => void };

const norm = (value: string) => value.split(/\s+/).filter(Boolean).join(' ');

function inputValid(input: ConfirmInput | undefined, text: string): boolean {
  if (!input) return true;
  const value = norm(text);
  if (input.match !== undefined) return value === norm(input.match);
  return value.length >= (input.minLength ?? 0);
}

/**
 * Замена window.confirm: `if (await confirm({ title: 'Удалить класс?' })) ...`.
 * `ask` — то же с полем ввода (причина, название для подтверждения):
 * вернёт введённый текст или null при отмене.
 * Нужно один раз вывести `dialog` в разметке экрана.
 */
export function useConfirm() {
  const [pending, setPending] = useState<Pending | null>(null);
  const [text, setText] = useState('');

  const ask = useCallback(
    (options: ConfirmOptions) =>
      new Promise<string | null>((resolve) => {
        setText('');
        setPending({ options, resolve });
      }),
    [],
  );

  const confirm = useCallback(
    async (options: ConfirmOptions) => (await ask(options)) !== null,
    [ask],
  );

  const close = useCallback(
    (accepted: boolean) => {
      pending?.resolve(accepted ? text.trim() : null);
      setPending(null);
    },
    [pending, text],
  );

  const options = pending?.options;
  const input = options?.input;
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
            disabled={!inputValid(input, text)}
            onClick={() => close(true)}
          >
            {options?.confirmLabel ?? 'Подтвердить'}
          </button>
        </div>
      }
    >
      {options?.message ? <p className="confirm__text">{options.message}</p> : null}
      {input ? (
        <label className="confirm__field">
          <span className="confirm__label">{input.label}</span>
          <input
            className="confirm__input"
            type="text"
            value={text}
            maxLength={input.maxLength ?? 200}
            placeholder={input.placeholder}
            autoComplete="off"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && inputValid(input, text)) close(true);
            }}
          />
        </label>
      ) : null}
    </Sheet>
  );

  return { confirm, ask, dialog };
}
