import { useState, type FormEvent } from 'react';
import { Icon } from '../components/Icon';
import type {
  GameState,
  ManagedClass,
  ManagedSchool,
  NewSchoolPayload,
  PlatformAdminData,
  SchoolAdminData,
} from '../types';
import '../styles/onboarding.css';
import '../styles/setup.css';

export type Notify = (message: string, tone?: 'success' | 'info' | 'error') => void;

const GOAL_DEFAULT = 1600;

type ClassRow = { key: number; name: string; goal: string };

let rowKey = 0;
const newRow = (name = '', goal = String(GOAL_DEFAULT)): ClassRow => ({
  key: (rowKey += 1),
  name,
  goal,
});

async function copyText(text: string, notify: Notify) {
  try {
    await navigator.clipboard.writeText(text);
    notify('Код скопирован', 'info');
  } catch {
    notify('Не удалось скопировать. Выделите код и скопируйте вручную.', 'error');
  }
}

// ---------------------------------------------------------------------------
// Выбор: ученик или представитель школы
// ---------------------------------------------------------------------------

export function AudienceChoice({
  onStudent,
  onSchool,
}: {
  onStudent: () => void;
  onSchool: () => void;
}) {
  return (
    <div className="ob">
      <header className="ob-top">
        <span className="ob-brand">Школьный герой</span>
      </header>
      <main className="ob-main">
        <section className="ob-card" aria-labelledby="su-aud-h">
          <div>
            <h1 className="ob-title" id="su-aud-h">Кто вы?</h1>
            <p className="ob-lead">От этого зависит, какие настройки понадобятся дальше.</p>
          </div>
          <div className="su-choice">
            <button type="button" className="su-choice__btn" onClick={onStudent}>
              <Icon name="user" size={22} />
              <span className="su-choice__text">
                <strong>Я ученик</strong>
                <span>Выбрать школу и класс или ввести код от учителя</span>
              </span>
              <Icon name="chevronRight" size={18} />
            </button>
            <button type="button" className="su-choice__btn" onClick={onSchool}>
              <Icon name="shield" size={22} />
              <span className="su-choice__text">
                <strong>Я представляю школу</strong>
                <span>Директор или педагог: добавить школу или войти по коду педагога</span>
              </span>
              <Icon name="chevronRight" size={18} />
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Форма новой школы
// ---------------------------------------------------------------------------

function validateSchool(name: string, city: string, rows: ClassRow[]): string | null {
  if (name.trim().length < 3) return 'Название школы: не короче 3 символов';
  if (city.trim().length < 2) return 'Укажите город';
  const filled = rows.filter((r) => r.name.trim());
  if (filled.length === 0) return 'Добавьте хотя бы один класс';
  const seen = new Set<string>();
  for (const row of filled) {
    const key = row.name.trim().toLowerCase();
    if (seen.has(key)) return `Класс «${row.name.trim()}» указан дважды`;
    seen.add(key);
    const goal = Number(row.goal);
    if (!Number.isInteger(goal) || goal < 100 || goal > 20000) {
      return `Класс «${row.name.trim()}»: цель недели от 100 до 20 000 XP`;
    }
  }
  return null;
}

export function NewSchoolForm({
  busy,
  onSubmit,
  onCancel,
  submitLabel = 'Создать школу',
}: {
  busy: boolean;
  onSubmit: (payload: NewSchoolPayload) => Promise<boolean>;
  onCancel?: () => void;
  submitLabel?: string;
}) {
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [rows, setRows] = useState<ClassRow[]>(() => [newRow()]);
  const [grade, setGrade] = useState('');
  const [letters, setLetters] = useState('');
  const [error, setError] = useState<string | null>(null);

  const setRow = (key: number, patch: Partial<ClassRow>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const addParallel = () => {
    const g = grade.trim();
    const chars = Array.from(letters.replace(/[^\p{L}]/gu, '').toUpperCase());
    if (!/^\d{1,2}$/.test(g) || chars.length === 0) {
      setError('Параллель: номер, например 8, и буквы, например АБВ');
      return;
    }
    setError(null);
    setRows((prev) => {
      const have = new Set(prev.map((r) => r.name.trim().toLowerCase()));
      const fresh = chars
        .map((c) => `${g}${c}`)
        .filter((n) => !have.has(n.toLowerCase()))
        .map((n) => newRow(n));
      const merged = [...prev.filter((r) => r.name.trim()), ...fresh].slice(0, 40);
      return merged.length > 0 ? merged : [newRow()];
    });
    setLetters('');
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const problem = validateSchool(name, city, rows);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    const ok = await onSubmit({
      name: name.trim(),
      city: city.trim(),
      classes: rows
        .filter((r) => r.name.trim())
        .map((r) => ({ name: r.name.trim(), weekly_goal: Number(r.goal) })),
    });
    if (!ok) setError('Не удалось создать школу. Проверьте данные и повторите попытку.');
  };

  return (
    <form className="su-form" onSubmit={(e) => void submit(e)} noValidate>
      <div className="ob-field">
        <label className="ob-label" htmlFor="su-name">Название школы</label>
        <input
          id="su-name"
          className="ob-input"
          value={name}
          maxLength={80}
          placeholder="Например, Гимназия №5"
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="ob-field">
        <label className="ob-label" htmlFor="su-city">Город</label>
        <input
          id="su-city"
          className="ob-input"
          value={city}
          maxLength={60}
          autoComplete="address-level2"
          onChange={(e) => setCity(e.target.value)}
        />
      </div>

      <fieldset className="su-classes">
        <legend className="ob-label">Классы</legend>
        <p className="ob-hint">
          Для каждого класса сервер создаст код ученика и код педагога. Цель недели в XP
          можно оставить по умолчанию.
        </p>
        <ul className="su-rows">
          {rows.map((row, index) => (
            <li key={row.key} className="su-row">
              <input
                className="ob-input su-row__name"
                aria-label={`Класс ${index + 1}`}
                value={row.name}
                maxLength={12}
                placeholder="8А"
                onChange={(e) => setRow(row.key, { name: e.target.value })}
              />
              <input
                className="ob-input su-row__goal"
                aria-label={`Цель недели, класс ${index + 1}`}
                inputMode="numeric"
                value={row.goal}
                onChange={(e) => setRow(row.key, { goal: e.target.value.replace(/\D/g, '') })}
              />
              <button
                type="button"
                className="su-icon-btn"
                aria-label={`Удалить класс ${row.name || index + 1}`}
                disabled={rows.length === 1}
                onClick={() => setRows((prev) => prev.filter((r) => r.key !== row.key))}
              >
                <Icon name="x" size={18} />
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="ob-btn ob-btn--ghost"
          disabled={rows.length >= 40}
          onClick={() => setRows((prev) => [...prev, newRow()])}
        >
          <Icon name="plus" size={16} />
          Добавить класс
        </button>

        <div className="su-parallel">
          <span className="ob-label">Добавить параллель</span>
          <div className="ob-row">
            <input
              className="ob-input su-parallel__grade"
              aria-label="Номер параллели"
              inputMode="numeric"
              maxLength={2}
              placeholder="8"
              value={grade}
              onChange={(e) => setGrade(e.target.value.replace(/\D/g, ''))}
            />
            <input
              className="ob-input"
              aria-label="Буквы классов"
              maxLength={10}
              placeholder="АБВ"
              value={letters}
              onChange={(e) => setLetters(e.target.value)}
            />
            <button type="button" className="ob-btn" onClick={addParallel}>
              Добавить
            </button>
          </div>
        </div>
      </fieldset>

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
          {busy ? 'Создаём…' : submitLabel}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Регистрация представителя школы (до получения роли)
// ---------------------------------------------------------------------------

export function SchoolRegisterScreen({
  busy,
  onBack,
  onCreate,
  onJoinTeacher,
}: {
  busy: boolean;
  onBack: () => void;
  onCreate: (payload: NewSchoolPayload) => Promise<boolean>;
  onJoinTeacher: (code: string) => Promise<string | null>;
}) {
  const [mode, setMode] = useState<'new' | 'code'>('new');
  const [code, setCode] = useState('');
  const [codeError, setCodeError] = useState<string | null>(null);

  const join = async () => {
    if (!code.trim()) {
      setCodeError('Введите код педагога');
      return;
    }
    setCodeError(null);
    const problem = await onJoinTeacher(code.trim());
    if (problem) setCodeError(problem);
  };

  return (
    <div className="ob">
      <header className="ob-top">
        <span className="ob-brand">Школьный герой</span>
      </header>
      <main className="ob-main">
        <section className="ob-card" aria-labelledby="su-reg-h">
          <div>
            <h1 className="ob-title" id="su-reg-h">Школа</h1>
            <p className="ob-lead">
              Директор регистрирует школу и получает коды для учеников и педагогов. Педагог
              входит по коду, который выдал директор.
            </p>
          </div>
          <div className="ob-seg" role="group" aria-label="Что нужно сделать">
            <button type="button" className="ob-seg__btn" aria-pressed={mode === 'new'} onClick={() => setMode('new')}>
              Новая школа
            </button>
            <button type="button" className="ob-seg__btn" aria-pressed={mode === 'code'} onClick={() => setMode('code')}>
              Код педагога
            </button>
          </div>

          {mode === 'new' ? (
            <NewSchoolForm busy={busy} onSubmit={onCreate} />
          ) : (
            <div className="ob-field">
              <label className="ob-label" htmlFor="su-tcode">Код педагога</label>
              <div className="ob-row">
                <input
                  id="su-tcode"
                  className="ob-input ob-input--code"
                  autoCapitalize="characters"
                  autoComplete="off"
                  spellCheck={false}
                  value={code}
                  aria-invalid={!!codeError}
                  aria-describedby="su-tcode-msg"
                  onChange={(e) => {
                    setCode(e.target.value.toUpperCase());
                    setCodeError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void join();
                    }
                  }}
                />
                <button type="button" className="ob-btn" onClick={() => void join()} disabled={busy}>
                  {busy ? 'Проверяем…' : 'Войти'}
                </button>
              </div>
              <span id="su-tcode-msg" className={codeError ? 'ob-error' : 'ob-hint'} role={codeError ? 'alert' : undefined}>
                {codeError ?? 'Код педагога привязывает вас к одному классу.'}
              </span>
            </div>
          )}
        </section>
      </main>
      <footer className="ob-actions">
        <button type="button" className="ob-btn ob-btn--ghost" onClick={onBack} disabled={busy}>
          <Icon name="arrowLeft" size={16} />
          Назад
        </button>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Управление школой (директор)
// ---------------------------------------------------------------------------

const STATUS_TEXT: Record<ManagedSchool['status'], string> = {
  active: 'Подтверждена',
  pending: 'Ожидает подтверждения',
  rejected: 'Отклонена',
};

function CodeLine({
  label,
  value,
  onCopy,
  onReset,
  busy,
}: {
  label: string;
  value: string;
  onCopy: () => void;
  onReset: () => void;
  busy: boolean;
}) {
  return (
    <div className="su-code">
      <div className="su-code__main">
        <span className="su-code__label">{label}</span>
        <code className="su-code__value">{value || '—'}</code>
      </div>
      <button type="button" className="su-icon-btn" aria-label={`Скопировать: ${label}`} onClick={onCopy} disabled={!value}>
        <Icon name="share" size={18} />
      </button>
      <button type="button" className="su-icon-btn" aria-label={`Выпустить новый: ${label}`} onClick={onReset} disabled={busy}>
        <Icon name="refresh" size={18} />
      </button>
    </div>
  );
}

function ClassCard({
  cls,
  busy,
  notify,
  onReset,
  onDelete,
}: {
  cls: ManagedClass;
  busy: boolean;
  notify: Notify;
  onReset: (classId: number, kind: 'student' | 'teacher') => void;
  onDelete: (classId: number) => void;
}) {
  const confirmReset = (kind: 'student' | 'teacher') => {
    const what = kind === 'student' ? 'код ученика' : 'код педагога';
    if (window.confirm(`Выпустить новый ${what} для класса ${cls.name}? Старый код перестанет работать.`)) {
      onReset(cls.id, kind);
    }
  };
  return (
    <li className="su-class">
      <div className="su-class__head">
        <h3 className="su-class__name">{cls.name}</h3>
        <span className="su-class__meta">
          Учеников: {cls.members} · цель {cls.weekly_goal} XP
        </span>
      </div>
      <CodeLine
        label="Код ученика"
        value={cls.invite_code}
        busy={busy}
        onCopy={() => void copyText(cls.invite_code, notify)}
        onReset={() => confirmReset('student')}
      />
      <CodeLine
        label="Код педагога"
        value={cls.teacher_code}
        busy={busy}
        onCopy={() => void copyText(cls.teacher_code, notify)}
        onReset={() => confirmReset('teacher')}
      />
      <p className="su-class__teachers">
        {cls.teachers.length > 0 ? `Педагог: ${cls.teachers.join(', ')}` : 'Педагог пока не подключён'}
      </p>
      {cls.members === 0 && (
        <button type="button" className="su-link su-link--danger" onClick={() => onDelete(cls.id)} disabled={busy}>
          Удалить класс
        </button>
      )}
    </li>
  );
}

export function SchoolSetupScreen({
  admin,
  busy,
  notify,
  onAddClass,
  onDeleteClass,
  onResetCode,
  onSelectSchool,
  onCreateSchool,
}: {
  state: GameState;
  admin: SchoolAdminData;
  busy: boolean;
  notify: Notify;
  onAddClass: (schoolId: number, name: string, goal: number) => Promise<boolean>;
  onDeleteClass: (classId: number) => Promise<boolean>;
  onResetCode: (classId: number, kind: 'student' | 'teacher') => Promise<boolean>;
  onSelectSchool: (schoolId: number) => Promise<boolean>;
  onCreateSchool: (payload: NewSchoolPayload) => Promise<boolean>;
}) {
  const school: ManagedSchool | undefined =
    admin.schools.find((s) => s.id === admin.active_school_id) ?? admin.schools[0];
  const [newName, setNewName] = useState('');
  const [newGoal, setNewGoal] = useState(String(GOAL_DEFAULT));
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  if (!school) return null;

  const addClass = async (event: FormEvent) => {
    event.preventDefault();
    const name = newName.trim();
    const goal = Number(newGoal);
    if (!name) return setFormError('Введите название класса');
    if (!Number.isInteger(goal) || goal < 100 || goal > 20000) {
      return setFormError('Цель недели: от 100 до 20 000 XP');
    }
    setFormError(null);
    const ok = await onAddClass(school.id, name, goal);
    if (ok) setNewName('');
  };

  return (
    <div className="su">
      <header className="su-head">
        <h1 className="su-title">Управление школой</h1>
        {admin.schools.length > 1 ? (
          <div className="ob-field">
            <label className="ob-label" htmlFor="su-school">Школа</label>
            <select
              id="su-school"
              className="ob-select"
              value={school.id}
              onChange={(e) => void onSelectSchool(Number(e.target.value))}
            >
              {admin.schools.map((s) => (
                <option key={s.id} value={s.id}>{s.name}, {s.city}</option>
              ))}
            </select>
          </div>
        ) : (
          <p className="su-sub">{school.name}, {school.city}</p>
        )}
      </header>

      {school.status !== 'active' && (
        <div className="ob-notice" role="status">
          <Icon name="info" size={16} />
          <span>
            {STATUS_TEXT[school.status]}.{' '}
            {school.status === 'pending'
              ? 'Пока школа не подтверждена администратором платформы, ученики не видят её в списке, а коды не работают.'
              : 'Ученики и педагоги не могут присоединиться к этой школе.'}
          </span>
        </div>
      )}

      <section className="ob-card" aria-labelledby="su-codes-h">
        <div>
          <h2 className="su-h2" id="su-codes-h">Классы и коды</h2>
          <p className="ob-lead">
            Код ученика передайте классу, код педагога только педагогу этого класса.
          </p>
        </div>
        <ul className="su-classes-list">
          {school.classes.map((cls) => (
            <ClassCard
              key={cls.id}
              cls={cls}
              busy={busy}
              notify={notify}
              onReset={(id, kind) => void onResetCode(id, kind)}
              onDelete={(id) => {
                if (window.confirm(`Удалить класс ${cls.name}?`)) void onDeleteClass(id);
              }}
            />
          ))}
        </ul>

        {school.classes.length < admin.max_classes && (
          <form className="su-add" onSubmit={(e) => void addClass(e)} noValidate>
            <span className="ob-label">Добавить класс</span>
            <div className="ob-row">
              <input
                className="ob-input"
                aria-label="Название класса"
                maxLength={12}
                placeholder="9В"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <input
                className="ob-input su-row__goal"
                aria-label="Цель недели, XP"
                inputMode="numeric"
                value={newGoal}
                onChange={(e) => setNewGoal(e.target.value.replace(/\D/g, ''))}
              />
              <button type="submit" className="ob-btn" disabled={busy}>
                Добавить
              </button>
            </div>
            {formError && <span className="ob-error" role="alert">{formError}</span>}
          </form>
        )}
      </section>

      {admin.schools_left > 0 && (
        <section className="ob-card" aria-labelledby="su-new-h">
          <div>
            <h2 className="su-h2" id="su-new-h">Ещё одна школа</h2>
            <p className="ob-lead">Можно добавить школ: {admin.schools_left}.</p>
          </div>
          {creating ? (
            <NewSchoolForm
              busy={busy}
              onCancel={() => setCreating(false)}
              onSubmit={async (payload) => {
                const ok = await onCreateSchool(payload);
                if (ok) setCreating(false);
                return ok;
              }}
            />
          ) : (
            <button type="button" className="ob-btn ob-btn--ghost" onClick={() => setCreating(true)}>
              <Icon name="plus" size={16} />
              Добавить школу
            </button>
          )}
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Подтверждение школ (администратор платформы)
// ---------------------------------------------------------------------------

export function AdminSchoolsScreen({
  data,
  busy,
  onSetStatus,
}: {
  data: PlatformAdminData;
  busy: boolean;
  onSetStatus: (schoolId: number, status: 'active' | 'rejected') => Promise<boolean>;
}) {
  return (
    <div className="su">
      <header className="su-head">
        <h1 className="su-title">Заявки школ</h1>
        <p className="su-sub">
          Режим регистрации: {data.approval_mode === 'manual' ? 'с подтверждением' : 'автоматический'}
        </p>
      </header>
      {data.pending.length === 0 ? (
        <div className="ob-notice" role="status">
          <Icon name="info" size={16} />
          <span>Новых заявок нет.</span>
        </div>
      ) : (
        <ul className="su-classes-list">
          {data.pending.map((item) => (
            <li key={item.id} className="su-class">
              <div className="su-class__head">
                <h3 className="su-class__name">{item.name}</h3>
                <span className="su-class__meta">
                  {item.city} · классов: {item.classes}
                  {item.created_by ? ` · ${item.created_by}` : ''}
                </span>
              </div>
              <div className="su-actions">
                <button type="button" className="ob-btn ob-btn--ghost" disabled={busy} onClick={() => void onSetStatus(item.id, 'rejected')}>
                  Отклонить
                </button>
                <button type="button" className="ob-btn" disabled={busy} onClick={() => void onSetStatus(item.id, 'active')}>
                  Подтвердить
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
