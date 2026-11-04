import { useState, type FormEvent } from 'react';
import { Icon } from './Icon';
import '../styles/onboarding.css';
import '../styles/setup.css';

const NAME_RE = /^[\p{L}][\p{L}\- .'’]*$/u;

/** Те же правила, что в онбординге и на сервере. */
function nameError(value: string, label: string, max: number): string | null {
  const v = value.trim();
  if (v.length === 0) return `Введите ${label}`;
  if (v.length < 2) return `${label[0].toUpperCase()}${label.slice(1)}: минимум 2 буквы`;
  if (v.length > max) return `Слишком длинно: не больше ${max} символов`;
  if (!NAME_RE.test(v)) return 'Используйте только буквы, пробел, дефис, точку или апостроф';
  return null;
}

type NameFormProps = {
  initialFirst?: string;
  initialLast?: string;
  submitLabel?: string;
  /** Возвращает текст ошибки или null, если имя сохранено. */
  onSubmit: (firstName: string, lastName: string) => Promise<string | null>;
  onCancel?: () => void;
};

export function NameForm({
  initialFirst = '',
  initialLast = '',
  submitLabel = 'Продолжить',
  onSubmit,
  onCancel,
}: NameFormProps) {
  const [first, setFirst] = useState(initialFirst);
  const [last, setLast] = useState(initialLast);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstErr = nameError(first, 'имя', 24);
  const lastErr = nameError(last, 'фамилию', 32);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    const problem = firstErr ?? lastErr;
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setBusy(true);
    const result = await onSubmit(first.trim(), last.trim());
    setBusy(false);
    if (result) setError(result);
  };

  return (
    <form className="su-form" onSubmit={(e) => void submit(e)} noValidate>
      <div className="ob-fields ob-fields--two">
        <div className="ob-field">
          <label className="ob-label" htmlFor="nm-first">Имя</label>
          <input
            id="nm-first"
            className="ob-input"
            autoComplete="given-name"
            maxLength={24}
            value={first}
            aria-invalid={touched && Boolean(firstErr)}
            onChange={(e) => setFirst(e.target.value)}
          />
          {touched && firstErr && <span className="ob-error">{firstErr}</span>}
        </div>
        <div className="ob-field">
          <label className="ob-label" htmlFor="nm-last">Фамилия</label>
          <input
            id="nm-last"
            className="ob-input"
            autoComplete="family-name"
            maxLength={32}
            value={last}
            aria-invalid={touched && Boolean(lastErr)}
            onChange={(e) => setLast(e.target.value)}
          />
          {touched && lastErr && <span className="ob-error">{lastErr}</span>}
        </div>
      </div>

      {error && (
        <div className="ob-notice ob-notice--error" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="su-actions">
        {onCancel && (
          <button type="button" className="ob-btn ob-btn--ghost" onClick={onCancel} disabled={busy}>
            Отмена
          </button>
        )}
        <button type="submit" className="ob-btn" disabled={busy}>
          {busy ? 'Сохраняем…' : submitLabel}
        </button>
      </div>
    </form>
  );
}

/** Экран для педагога и директора, у которых нет имени. */
export function NameScreen({
  onSubmit,
  initialFirst,
  initialLast,
}: Pick<NameFormProps, 'onSubmit' | 'initialFirst' | 'initialLast'>) {
  return (
    <div className="ob">
      <header className="ob-top">
        <span className="ob-brand">Школьный герой</span>
      </header>
      <main className="ob-main">
        <section className="ob-card" aria-labelledby="nm-h">
          <div>
            <h1 className="ob-title" id="nm-h">Как вас зовут?</h1>
            <p className="ob-lead">Так вас увидят ученики и коллеги.</p>
          </div>
          <NameForm initialFirst={initialFirst} initialLast={initialLast} onSubmit={onSubmit} />
        </section>
      </main>
    </div>
  );
}
