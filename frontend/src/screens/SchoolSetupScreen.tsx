import { useState, type FormEvent } from 'react';
import { api } from '../api';
import { CityInput } from '../components/CityInput';
import { useConfirm } from '../components/ConfirmDialog';
import { Icon } from '../components/Icon';
import { JoinRequestsList } from '../components/JoinRequestsList';
import { formatShortDate } from '../components/PrintReport';
import type {
  GameState,
  ManagedClass,
  ManagedTeacher,
  ManagedSchool,
  NewSchoolPayload,
  SchoolAdminData,
  TimezoneOption,
} from '../types';
import '../styles/onboarding.css';
import '../styles/setup.css';

export type Notify = (message: string, tone?: 'success' | 'info' | 'error') => void;

/** Возвращает текст ошибки или null, если действие выполнено. */
export type ActionResult = Promise<string | null>;

const MAX_CLASSES = 40;
const GRADES = Array.from({ length: 11 }, (_, i) => i + 1);
const LETTERS = ['А', 'Б', 'В', 'Г', 'Д'];
const PRESETS = [
  { label: '1–4', from: 1, to: 4 },
  { label: '5–9', from: 5, to: 9 },
  { label: '10–11', from: 10, to: 11 },
  { label: '1–11', from: 1, to: 11 },
];
const CLASS_NAME_RE = /^[\p{L}\p{N}_][\p{L}\p{N}_ .\-/]*$/u;
const CITY_RE = /^\p{L}(?:[\p{L} .'’-])*$/u;

const MSG_NAME = 'Название школы: от 3 до 80 символов, должно содержать буквы';
const MSG_CITY = 'Город: от 2 до 60 символов, только буквы, пробел, дефис и точка';
const MSG_CLASS_NAME = 'Название класса: от 1 до 12 символов, например 8А';
const MSG_GOAL = 'Цель недели: от 100 до 20 000';

async function copyText(text: string, notify: Notify) {
  try {
    await navigator.clipboard.writeText(text);
    notify('Код скопирован', 'info');
  } catch {
    notify('Не удалось скопировать. Выделите код и скопируйте вручную.', 'error');
  }
}

function cleanName(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(' ');
}

function validClassName(value: string): boolean {
  return value.length >= 1 && value.length <= 12 && CLASS_NAME_RE.test(value);
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

type FieldErrors = Partial<Record<'name' | 'city' | 'classes', string>>;

function fieldOfError(message: string): keyof FieldErrors | null {
  if (/уже зарегистрирована|Название школы/.test(message)) return 'name';
  if (/^Город/.test(message)) return 'city';
  if (/[Кк]ласс/.test(message)) return 'classes';
  return null;
}

function Chip({
  pressed,
  onClick,
  children,
  label,
}: {
  pressed: boolean;
  onClick: () => void;
  children: string;
  label?: string;
}) {
  return (
    <button type="button" className="su-chip" aria-pressed={pressed} aria-label={label} onClick={onClick}>
      {children}
    </button>
  );
}

const DEFAULT_ZONE = 'Europe/Moscow';

const foldCity = (text: string) => text.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();

export function NewSchoolForm({
  busy,
  timezones,
  onSubmit,
  onCancel,
  onUseTeacherCode,
  submitLabel = 'Создать школу',
}: {
  busy: boolean;
  timezones: TimezoneOption[];
  onSubmit: (payload: NewSchoolPayload) => ActionResult;
  onCancel?: () => void;
  onUseTeacherCode?: () => void;
  submitLabel?: string;
}) {
  const { confirm, dialog } = useConfirm();
  const [zone, setZone] = useState(DEFAULT_ZONE);
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [grades, setGrades] = useState<number[]>([]);
  const [letters, setLetters] = useState<string[]>(['А']);
  const [custom, setCustom] = useState('');
  const [extras, setExtras] = useState<string[]>([]);
  const [removed, setRemoved] = useState<string[]>([]);
  const [extraInput, setExtraInput] = useState('');
  const [extraError, setExtraError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const customLetters = Array.from(new Set(Array.from(custom.toUpperCase().replace(/[^\p{L}]/gu, ''))))
    .filter((l) => !LETTERS.includes(l))
    .slice(0, 12);
  const activeLetters = [...LETTERS.filter((l) => letters.includes(l)), ...customLetters];
  const generated = [...grades]
    .sort((a, b) => a - b)
    .flatMap((g) => activeLetters.map((l) => `${g}${l}`));
  const seen = new Set<string>();
  const classNames = [...generated, ...extras].filter((n) => {
    const key = n.toLowerCase();
    if (seen.has(key) || removed.includes(key)) return false;
    seen.add(key);
    return true;
  });
  const tooMany = classNames.length > MAX_CLASSES;

  const unremove = (match: (key: string) => boolean) =>
    setRemoved((prev) => prev.filter((key) => !match(key)));
  const gradeOf = (key: string) => /^(\d+)\p{L}$/u.exec(key)?.[1];
  const letterOf = (key: string) => /^\d+(\p{L})$/u.exec(key)?.[1];

  const toggleGrade = (g: number) => {
    if (grades.includes(g)) setGrades(grades.filter((x) => x !== g));
    else {
      setGrades([...grades, g]);
      unremove((k) => gradeOf(k) === String(g));
    }
  };
  const toggleLetter = (l: string) => {
    if (letters.includes(l)) setLetters(letters.filter((x) => x !== l));
    else {
      setLetters([...letters, l]);
      unremove((k) => letterOf(k) === l.toLowerCase());
    }
  };
  const applyPreset = (from: number, to: number) => {
    const range = GRADES.filter((g) => g >= from && g <= to);
    setGrades(range);
    unremove((k) => range.includes(Number(gradeOf(k))));
  };
  const presetActive = (from: number, to: number) => {
    const range = GRADES.filter((g) => g >= from && g <= to);
    return range.length === grades.length && range.every((g) => grades.includes(g));
  };
  const changeCustom = (value: string) => {
    setCustom(value);
    const next = Array.from(value.toLowerCase().replace(/[^\p{L}]/gu, ''));
    unremove((k) => next.includes(letterOf(k) ?? ''));
  };

  const removeClass = (className: string) => {
    const key = className.toLowerCase();
    setExtras((prev) => prev.filter((n) => n.toLowerCase() !== key));
    setRemoved((prev) => (prev.includes(key) ? prev : [...prev, key]));
  };

  const addExtra = () => {
    const value = cleanName(extraInput);
    if (!validClassName(value)) return setExtraError(MSG_CLASS_NAME);
    if (classNames.some((n) => n.toLowerCase() === value.toLowerCase())) {
      return setExtraError('Такой класс уже есть в списке');
    }
    if (classNames.length >= MAX_CLASSES) return setExtraError(`Не больше ${MAX_CLASSES} классов`);
    setExtraError(null);
    setExtras((prev) => [...prev, value]);
    unremove((k) => k === value.toLowerCase());
    setExtraInput('');
  };

  const validate = (): FieldErrors => {
    const next: FieldErrors = {};
    const n = cleanName(name);
    const c = cleanName(city);
    if (n.length < 3 || n.length > 80 || !/\p{L}/u.test(n)) next.name = MSG_NAME;
    if (c.length < 2 || c.length > 60 || !CITY_RE.test(c)) next.city = MSG_CITY;
    if (classNames.length < 1) next.classes = 'Добавьте от 1 до 40 классов: выберите параллели и буквы';
    else if (tooMany) next.classes = `Не больше ${MAX_CLASSES} классов. Уберите лишние.`;
    return next;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const problems = validate();
    setErrors(problems);
    const first = Object.values(problems)[0];
    if (first) {
      setFormError(first);
      return;
    }
    setFormError(null);
    const cityName = cleanName(city);
    // Города нет ни в справочнике, ни среди школ платформы: спрашиваем, прежде чем создавать.
    const known = await api
      .searchCities(cityName, 20, 'all')
      .then((res) => res.cities.some((c) => foldCity(c.name) === foldCity(cityName)))
      .catch(() => true);
    if (!known) {
      const ok = await confirm({
        title: 'Такого города нет в справочнике',
        message: `Такого города нет в справочнике — использовать «${cityName}» как есть?`,
        confirmLabel: 'Использовать',
      });
      if (!ok) return;
    }
    const error = await onSubmit({
      name: cleanName(name),
      city: cityName,
      timezone: zone,
      classes: classNames.map((n) => ({ name: n })),
    });
    if (error) {
      setFormError(error);
      const field = fieldOfError(error);
      setErrors(field ? { [field]: error } : {});
    }
  };

  const duplicate = Boolean(formError && /уже зарегистрирована/.test(formError));

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
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errors.name ? 'su-name-err' : undefined}
          onChange={(e) => setName(e.target.value)}
        />
        {errors.name && <span id="su-name-err" className="ob-error">{errors.name}</span>}
      </div>

      <div className="ob-field">
        <label className="ob-label" htmlFor="su-city">Город</label>
        <CityInput
          id="su-city"
          value={city}
          onChange={setCity}
          placeholder="Начните вводить"
          scope="all"
          invalid={Boolean(errors.city)}
          describedBy={errors.city ? 'su-city-err' : 'su-city-hint'}
        />
        {errors.city ? (
          <span id="su-city-err" className="ob-error">{errors.city}</span>
        ) : (
          <span id="su-city-hint" className="ob-hint">
            Выберите город из подсказок. Если вашего населённого пункта нет в списке, введите его
            название вручную.
          </span>
        )}
      </div>

      <div className="ob-field">
        <label className="ob-label" htmlFor="su-tz">Часовой пояс</label>
        <select id="su-tz" className="ob-select" value={zone} onChange={(e) => setZone(e.target.value)}>
          {timezones.map((tz) => (
            <option key={tz.id} value={tz.id}>{tz.label}</option>
          ))}
        </select>
        <span className="ob-hint">
          По нему считаются «сегодня», недели и сроки заданий. Позже пояс можно сменить в управлении школой.
        </span>
      </div>

      <fieldset className="su-classes" aria-describedby={errors.classes ? 'su-classes-err' : undefined}>
        <legend className="ob-label">Классы школы</legend>
        <p className="ob-hint">
          Выберите параллели и буквы, список классов соберётся сам. Для каждого класса будут
          созданы код ученика и код педагога.
        </p>

        <div className="su-group">
          <span className="ob-label" id="su-grades-label">Параллели</span>
          <div className="su-chips" role="group" aria-labelledby="su-grades-label">
            {GRADES.map((g) => (
              <Chip key={g} pressed={grades.includes(g)} onClick={() => toggleGrade(g)} label={`${g} классы`}>
                {String(g)}
              </Chip>
            ))}
          </div>
          <div className="su-chips su-chips--presets" role="group" aria-label="Быстрый выбор параллелей">
            {PRESETS.map((p) => (
              <Chip key={p.label} pressed={presetActive(p.from, p.to)} onClick={() => applyPreset(p.from, p.to)}>
                {p.label}
              </Chip>
            ))}
          </div>
        </div>

        <div className="su-group">
          <span className="ob-label" id="su-letters-label">Буквы</span>
          <div className="su-chips" role="group" aria-labelledby="su-letters-label">
            {LETTERS.map((l) => (
              <Chip key={l} pressed={letters.includes(l)} onClick={() => toggleLetter(l)}>
                {l}
              </Chip>
            ))}
          </div>
          <label className="ob-label" htmlFor="su-custom">Свои буквы</label>
          <input
            id="su-custom"
            className="ob-input"
            value={custom}
            maxLength={30}
            placeholder="Е, Ж"
            autoComplete="off"
            onChange={(e) => changeCustom(e.target.value)}
          />
        </div>

        <div className="su-group">
          <div className="su-count" aria-live="polite">
            <span className="ob-label">Классов: {classNames.length}</span>
            {tooMany && <span className="ob-error">Максимум {MAX_CLASSES}</span>}
          </div>
          {classNames.length === 0 ? (
            <p className="ob-hint">Пока пусто. Выберите хотя бы одну параллель и букву.</p>
          ) : (
            <ul className="su-tags">
              {classNames.map((n) => (
                <li key={n.toLowerCase()}>
                  <button type="button" className="su-tag" aria-label={`Убрать класс ${n}`} onClick={() => removeClass(n)}>
                    {n}
                    <Icon name="x" size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="su-group">
          <label className="ob-label" htmlFor="su-extra">Другое название класса</label>
          <div className="ob-row">
            <input
              id="su-extra"
              className="ob-input"
              value={extraInput}
              maxLength={12}
              placeholder="10 физмат"
              autoComplete="off"
              aria-invalid={Boolean(extraError)}
              onChange={(e) => {
                setExtraInput(e.target.value);
                setExtraError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addExtra();
                }
              }}
            />
            <button type="button" className="ob-btn ob-btn--ghost" onClick={addExtra}>
              <Icon name="plus" size={16} />
              Добавить класс
            </button>
          </div>
          {extraError && <span className="ob-error" role="alert">{extraError}</span>}
        </div>
        {errors.classes && <span id="su-classes-err" className="ob-error">{errors.classes}</span>}
      </fieldset>

      {formError && (
        <div className="ob-notice ob-notice--error" role="alert">
          <Icon name="alert" size={16} />
          <span>{formError}</span>
        </div>
      )}
      {duplicate && (
        <div className="ob-notice">
          <Icon name="info" size={16} />
          <span>
            Если это ваша школа, войдите по коду педагога: его выдаёт директор.
            {onUseTeacherCode && (
              <>
                {' '}
                <button type="button" className="su-link" onClick={onUseTeacherCode}>
                  Ввести код педагога
                </button>
              </>
            )}
          </span>
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
      {dialog}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Регистрация представителя школы (до получения роли)
// ---------------------------------------------------------------------------

/** Поле кода педагога: регистрация представителя школы и педагог без класса. */
export function TeacherCodeForm({
  busy,
  onJoinTeacher,
}: {
  busy: boolean;
  onJoinTeacher: (code: string) => ActionResult;
}) {
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
        {codeError ?? 'Код педагога привязывает вас к одному классу. Его выдаёт директор школы.'}
      </span>
    </div>
  );
}

export function SchoolRegisterScreen({
  busy,
  timezones,
  onBack,
  onCreate,
  onJoinTeacher,
}: {
  busy: boolean;
  timezones: TimezoneOption[];
  onBack: () => void;
  onCreate: (payload: NewSchoolPayload) => ActionResult;
  onJoinTeacher: (code: string) => ActionResult;
}) {
  const [mode, setMode] = useState<'new' | 'code'>('new');

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
            <NewSchoolForm busy={busy} timezones={timezones} onSubmit={onCreate} onUseTeacherCode={() => setMode('code')} />
          ) : (
            <TeacherCodeForm busy={busy} onJoinTeacher={onJoinTeacher} />
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

/** Педагог без класса (отключён директором или из списка TEACHER_MAX_IDS без привязки). */
export function TeacherNoClassScreen({
  busy,
  onJoinTeacher,
}: {
  busy: boolean;
  onJoinTeacher: (code: string) => ActionResult;
}) {
  return (
    <div className="su">
      <section className="ob-card" aria-labelledby="su-nocls-h">
        <div>
          <h1 className="ob-title" id="su-nocls-h">Класс не назначен</h1>
          <p className="ob-lead">
            Аккаунт педагога не привязан к классу. Введите код педагога, который выдал директор
            школы.
          </p>
        </div>
        <TeacherCodeForm busy={busy} onJoinTeacher={onJoinTeacher} />
      </section>
    </div>
  );
}

/** Директор без школы (например, из списка DIRECTOR_MAX_IDS): регистрация школы. */
export function DirectorNoSchoolScreen({
  busy,
  timezones,
  onCreate,
}: {
  busy: boolean;
  timezones: TimezoneOption[];
  onCreate: (payload: NewSchoolPayload) => ActionResult;
}) {
  return (
    <div className="su">
      <section className="ob-card" aria-labelledby="su-nosch-h">
        <div>
          <h1 className="ob-title" id="su-nosch-h">Школа не подключена</h1>
          <p className="ob-lead">
            Аккаунт директора не привязан к школе. Зарегистрируйте школу: для каждого класса будут
            созданы коды ученика и педагога.
          </p>
        </div>
        <NewSchoolForm busy={busy} timezones={timezones} onSubmit={onCreate} />
      </section>
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
  onDisconnect,
  onDelete,
  onUpdate,
}: {
  cls: ManagedClass;
  busy: boolean;
  notify: Notify;
  onReset: (classId: number, kind: 'student' | 'teacher', disconnectTeachers: boolean) => void;
  onDisconnect: (classId: number, teacherId: number) => void;
  onDelete: (classId: number) => void;
  onUpdate: (classId: number, patch: { name?: string; weekly_goal?: number }) => ActionResult;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cls.name);
  const [goal, setGoal] = useState(String(cls.weekly_goal));
  const [error, setError] = useState<string | null>(null);

  const { confirm, dialog } = useConfirm();

  const confirmReset = async (kind: 'student' | 'teacher') => {
    const what = kind === 'student' ? 'код ученика' : 'код педагога';
    // Значение флажка читается после закрытия диалога.
    let disconnect = false;
    const withTeachers = kind === 'teacher' && cls.teachers.length > 0;
    const ok = await confirm({
      title: `Выпустить новый ${what}?`,
      message: withTeachers ? (
        <>
          Класс {cls.name}. Старый код перестанет работать, но уже подключённые педагоги сохранят
          доступ.
          <label className="su-check">
            <input
              type="checkbox"
              onChange={(e) => {
                disconnect = e.target.checked;
              }}
            />
            <span>Отключить всех текущих педагогов класса</span>
          </label>
        </>
      ) : (
        `Класс ${cls.name}. Старый код перестанет работать.`
      ),
      confirmLabel: 'Выпустить',
    });
    if (ok) onReset(cls.id, kind, withTeachers && disconnect);
  };

  const confirmDisconnect = async (teacher: ManagedTeacher) => {
    const ok = await confirm({
      title: `Отключить педагога ${teacher.name}?`,
      message: `Педагог потеряет доступ к классу ${cls.name}: ученики, проверка работ и задания станут недоступны. Вернуться он сможет только по коду педагога; если код мог попасть к посторонним, выпустите новый.`,
      confirmLabel: 'Отключить',
      danger: true,
    });
    if (ok) onDisconnect(cls.id, teacher.id);
  };

  const confirmDelete = async () => {
    const ok = await confirm({
      title: 'Удалить класс?',
      message: `Класс ${cls.name} будет удалён вместе с его кодами.`,
      confirmLabel: 'Удалить',
      danger: true,
    });
    if (ok) onDelete(cls.id);
  };

  const startEdit = () => {
    setName(cls.name);
    setGoal(String(cls.weekly_goal));
    setError(null);
    setEditing(true);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const nextName = cleanName(name);
    const nextGoal = Number(goal);
    if (!validClassName(nextName)) return setError(MSG_CLASS_NAME);
    if (!Number.isInteger(nextGoal) || nextGoal < 100 || nextGoal > 20000) return setError(MSG_GOAL);
    const patch: { name?: string; weekly_goal?: number } = {};
    if (nextName !== cls.name) patch.name = nextName;
    if (nextGoal !== cls.weekly_goal) patch.weekly_goal = nextGoal;
    if (!patch.name && !patch.weekly_goal) {
      setEditing(false);
      return;
    }
    const problem = await onUpdate(cls.id, patch);
    if (problem) setError(problem);
    else setEditing(false);
  };

  return (
    <li className="su-class">
      <div className="su-class__head">
        <h3 className="su-class__name">{cls.name}</h3>
        <span className="su-class__meta">Учеников: {cls.members}</span>
      </div>

      {editing ? (
        <form className="su-edit" onSubmit={(e) => void save(e)} noValidate>
          <div className="ob-field">
            <label className="ob-label" htmlFor={`su-en-${cls.id}`}>Название класса</label>
            <input
              id={`su-en-${cls.id}`}
              className="ob-input"
              value={name}
              maxLength={12}
              aria-invalid={Boolean(error)}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="ob-field">
            <label className="ob-label" htmlFor={`su-eg-${cls.id}`}>Цель недели, XP</label>
            <input
              id={`su-eg-${cls.id}`}
              className="ob-input"
              inputMode="numeric"
              value={goal}
              aria-invalid={Boolean(error)}
              onChange={(e) => setGoal(e.target.value.replace(/\D/g, ''))}
            />
            <span className="ob-hint">От 100 до 20 000 XP.</span>
          </div>
          {error && <span className="ob-error" role="alert">{error}</span>}
          <div className="su-actions">
            <button type="button" className="ob-btn ob-btn--ghost" onClick={() => setEditing(false)} disabled={busy}>
              Отмена
            </button>
            <button type="submit" className="ob-btn" disabled={busy}>
              Сохранить
            </button>
          </div>
        </form>
      ) : (
        <div className="su-goal">
          <div className="su-goal__row">
            <span className="su-goal__value">Цель недели: {cls.weekly_goal} XP</span>
            <button type="button" className="su-link" onClick={startEdit} disabled={busy}>
              Изменить
            </button>
          </div>
          <p className="su-goal__hint">
            Сколько XP класс должен набрать вместе за неделю. По этой цели строится шкала на
            главной у учеников и в отчётах. Можно изменить.
          </p>
        </div>
      )}

      <CodeLine
        label="Код ученика"
        value={cls.invite_code}
        busy={busy}
        onCopy={() => void copyText(cls.invite_code, notify)}
        onReset={() => void confirmReset('student')}
      />
      <CodeLine
        label="Код педагога"
        value={cls.teacher_code}
        busy={busy}
        onCopy={() => void copyText(cls.teacher_code, notify)}
        onReset={() => void confirmReset('teacher')}
      />
      {cls.teachers.length === 0 ? (
        <p className="su-class__teachers">Педагог пока не подключён</p>
      ) : (
        <ul className="su-teachers" aria-label={`Педагоги класса ${cls.name}`}>
          {cls.teachers.map((teacher) => (
            <li key={teacher.id} className="su-teachers__item">
              <div className="su-teachers__text">
                <strong>{teacher.name || 'Педагог'}</strong>
                <span className="su-class__meta">
                  {teacher.since ? `подключён ${formatShortDate(teacher.since)}` : 'дата подключения неизвестна'}
                </span>
              </div>
              <button
                type="button"
                className="su-link su-link--danger"
                disabled={busy}
                onClick={() => void confirmDisconnect(teacher)}
              >
                Отключить
              </button>
            </li>
          ))}
        </ul>
      )}
      {cls.members === 0 && (
        <button type="button" className="su-link su-link--danger" onClick={() => void confirmDelete()} disabled={busy}>
          Удалить класс
        </button>
      )}
      {dialog}
    </li>
  );
}

export function SchoolSetupScreen({
  state,
  admin,
  busy,
  notify,
  onAddClass,
  onUpdateClass,
  onDeleteClass,
  onResetCode,
  onDisconnectTeacher,
  onDecideJoin,
  onSelectSchool,
  onSetTimezone,
  onCreateSchool,
}: {
  state: GameState;
  admin: SchoolAdminData;
  busy: boolean;
  notify: Notify;
  onAddClass: (schoolId: number, name: string) => ActionResult;
  onUpdateClass: (classId: number, patch: { name?: string; weekly_goal?: number }) => ActionResult;
  onDeleteClass: (classId: number) => Promise<boolean>;
  onResetCode: (classId: number, kind: 'student' | 'teacher', disconnectTeachers: boolean) => Promise<boolean>;
  onDisconnectTeacher: (classId: number, teacherId: number) => Promise<boolean>;
  onDecideJoin: (requestId: number, action: 'approve' | 'decline') => Promise<boolean>;
  onSelectSchool: (schoolId: number) => Promise<boolean>;
  onSetTimezone: (schoolId: number, timezone: string) => Promise<boolean>;
  onCreateSchool: (payload: NewSchoolPayload) => ActionResult;
}) {
  const school: ManagedSchool | undefined =
    admin.schools.find((s) => s.id === admin.active_school_id) ?? admin.schools[0];
  const [newName, setNewName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  if (!school) return null;

  const addClass = async (event: FormEvent) => {
    event.preventDefault();
    const name = cleanName(newName);
    if (!validClassName(name)) return setFormError(MSG_CLASS_NAME);
    setFormError(null);
    const problem = await onAddClass(school.id, name);
    if (problem) setFormError(problem);
    else setNewName('');
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
            {school.status === 'rejected' && school.reject_reason ? (
              <>
                {' '}
                Причина: {school.reject_reason}
              </>
            ) : null}
          </span>
        </div>
      )}

      <JoinRequestsList
        requests={admin.join_requests.filter((r) => r.school_id === school.id)}
        showClass
        onDecide={onDecideJoin}
      />

      <section className="ob-card" aria-labelledby="su-tz-h">
        <div>
          <h2 className="su-h2" id="su-tz-h">Часовой пояс школы</h2>
          <p className="ob-lead">
            Сейчас: {state.timezones.find((t) => t.id === school.timezone)?.label ?? state.timezone_label}.
            По поясу считаются «сегодня», недели и сроки заданий.
          </p>
        </div>
        <div className="ob-field">
          <label className="ob-label" htmlFor="su-tz-edit">Сменить пояс</label>
          <select
            id="su-tz-edit"
            className="ob-select"
            value={school.timezone}
            disabled={busy}
            onChange={(e) => void onSetTimezone(school.id, e.target.value)}
          >
            {state.timezones.map((tz) => (
              <option key={tz.id} value={tz.id}>{tz.label}</option>
            ))}
          </select>
        </div>
      </section>

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
              key={`${cls.id}-${cls.name}-${cls.weekly_goal}`}
              cls={cls}
              busy={busy}
              notify={notify}
              onReset={(id, kind, disconnect) => void onResetCode(id, kind, disconnect)}
              onDisconnect={(id, teacherId) => void onDisconnectTeacher(id, teacherId)}
              onUpdate={onUpdateClass}
              onDelete={(id) => void onDeleteClass(id)}
            />
          ))}
        </ul>

        {school.classes.length < admin.max_classes && (
          <form className="su-add" onSubmit={(e) => void addClass(e)} noValidate>
            <label className="ob-label" htmlFor="su-add-name">Добавить класс</label>
            <div className="ob-row">
              <input
                id="su-add-name"
                className="ob-input"
                maxLength={12}
                placeholder="9В"
                value={newName}
                aria-invalid={Boolean(formError)}
                onChange={(e) => {
                  setNewName(e.target.value);
                  setFormError(null);
                }}
              />
              <button type="submit" className="ob-btn" disabled={busy}>
                Добавить
              </button>
            </div>
            <span className="ob-hint">Цель недели по умолчанию 1600 XP, её можно изменить у класса.</span>
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
              timezones={state.timezones}
              onCancel={() => setCreating(false)}
              onSubmit={async (payload) => {
                const problem = await onCreateSchool(payload);
                if (!problem) setCreating(false);
                return problem;
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
