import { useEffect, useState } from 'react';
import { api } from '../api';
import { AvatarFrame } from '../components/AvatarFrame';
import { Icon } from '../components/Icon';
import { PixelHero } from '../components/PixelHero';
import type { AvatarConfig, Cosmetic, GameState, SchoolCatalog } from '../types';
import '../styles/onboarding.css';
import '../styles/setup.css';

type OnboardingScreenProps = {
  state: GameState;
  onComplete: (
    firstName: string,
    avatar: Record<string, string>,
    lastName?: string,
    classId?: number,
    inviteCode?: string,
  ) => Promise<boolean>;
  /** Ученик без класса: только выбор класса, без имени и героя. */
  joinOnly?: boolean;
  onJoin?: (classId?: number, inviteCode?: string) => Promise<boolean>;
  onBack?: () => void;
};

type ClassChoice = {
  class_id: number;
  class_name: string;
  school_name: string;
  city: string;
  teacher_name?: string;
  invite_code?: string;
  kind?: 'student' | 'teacher';
};

type AvatarTab = 'skin' | 'hair' | 'outfit' | 'accessory';

const TOTAL_STEPS = 3;
const NAME_RE = /^[\p{L}][\p{L}\- ]*$/u;

const AVATAR_TABS: { id: AvatarTab; label: string }[] = [
  { id: 'skin', label: 'Кожа' },
  { id: 'hair', label: 'Волосы' },
  { id: 'outfit', label: 'Одежда' },
  { id: 'accessory', label: 'Очки' },
];

function nameError(value: string, label: string, max: number): string | null {
  const v = value.trim();
  if (v.length === 0) return `Введите ${label}`;
  if (v.length < 2) return `${label[0].toUpperCase()}${label.slice(1)} — минимум 2 буквы`;
  if (v.length > max) return `Слишком длинно: не больше ${max} символов`;
  if (!NAME_RE.test(v)) return 'Используйте только буквы, пробел или дефис';
  return null;
}

function readCodeFromUrl(): string {
  try {
    return (new URLSearchParams(window.location.search).get('code') || '').toUpperCase().trim();
  } catch {
    return '';
  }
}

export function OnboardingScreen({ state, onComplete, joinOnly = false, onJoin, onBack }: OnboardingScreenProps) {
  const { viewer } = state;
  const firstStep = joinOnly ? 1 : 0;
  const lastStep = joinOnly ? 1 : TOTAL_STEPS - 1;
  const [step, setStep] = useState(firstStep);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Шаг 1: имя
  const [firstName, setFirstName] = useState(viewer.first_name === 'Герой' ? '' : viewer.first_name);
  const [lastName, setLastName] = useState(
    viewer.first_name === 'Герой' ? '' : viewer.last_name,
  );
  const [touched, setTouched] = useState({ first: false, last: false });

  // Шаг 2: класс
  const [mode, setMode] = useState<'code' | 'list'>(readCodeFromUrl() ? 'code' : 'list');
  const [code, setCode] = useState(readCodeFromUrl);
  const [checking, setChecking] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [codeClass, setCodeClass] = useState<ClassChoice | null>(null);

  const [cities, setCities] = useState<string[]>([]);
  const [citiesState, setCitiesState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [city, setCity] = useState('');
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<SchoolCatalog | null>(null);
  const [foundState, setFoundState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [schoolId, setSchoolId] = useState<number | null>(null);
  const [classId, setClassId] = useState<number | null>(null);

  // Шаг 3: герой
  const [avatar, setAvatar] = useState<AvatarConfig>({ ...viewer.avatar });
  const [tab, setTab] = useState<AvatarTab>('skin');

  const pick = (type: Cosmetic['type'], ids?: string[]) =>
    state.cosmetics.filter(
      (item) =>
        item.type === type &&
        item.price === 0 &&
        item.unlock_level <= 1 &&
        (!ids || ids.includes(item.id)),
    );
  const skins = pick('skin');
  const hairs = pick('hair');
  const hairColors = pick('hair_color');
  const outfits = pick('outfit');
  const glasses = pick('accessory', ['none', 'glasses']);

  const firstErr = nameError(firstName, 'имя', 24);
  const lastErr = nameError(lastName, 'фамилию', 32);

  const verifyCode = async (raw: string) => {
    const value = raw.trim().toUpperCase();
    if (!value) {
      setCodeError('Введите код приглашения');
      return;
    }
    setChecking(true);
    setCodeError(null);
    try {
      const res = await api.checkInviteCode(value);
      if (res.valid && res.class_id) {
        setCodeClass({
          kind: res.kind ?? 'student',
          class_id: res.class_id,
          class_name: res.class_name ?? '',
          school_name: res.school_name ?? '',
          city: res.city ?? '',
          teacher_name: res.teacher_name,
          invite_code: res.invite_code ?? value,
        });
      } else {
        setCodeClass(null);
        setCodeError(res.detail || 'Такого кода нет. Проверьте, нет ли опечатки, или уточните код у учителя.');
      }
    } catch (err) {
      setCodeClass(null);
      setCodeError(
        err instanceof Error ? err.message : 'Не удалось проверить код. Попробуйте ещё раз.',
      );
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    let alive = true;
    if (code) void verifyCode(code);
    api
      .getSchoolCatalog({ onlyCities: true })
      .then((cat) => {
        if (!alive) return;
        setCities(cat.cities);
        setCitiesState('ready');
        if (cat.cities.length === 1) setCity(cat.cities[0]);
      })
      .catch(() => {
        if (alive) setCitiesState('error');
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Список школ запрашивается у сервера по городу и строке поиска.
  useEffect(() => {
    if (!city && query.trim().length < 2) {
      setFound(null);
      setFoundState('idle');
      return;
    }
    let alive = true;
    setFoundState('loading');
    const timer = window.setTimeout(() => {
      api
        .getSchoolCatalog({ city, q: query.trim() })
        .then((cat) => {
          if (!alive) return;
          setFound(cat);
          setFoundState('ready');
        })
        .catch(() => {
          if (alive) setFoundState('error');
        });
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [city, query]);

  const schools = found?.schools ?? [];
  const classes = (found?.classes ?? []).filter((c) => c.school_id === schoolId);

  const listClass: ClassChoice | null = (() => {
    const cls = classes.find((c) => c.id === classId);
    const school = schools.find((s) => s.id === schoolId);
    if (!cls || !school) return null;
    return {
      class_id: cls.id,
      class_name: cls.name,
      school_name: school.name,
      city: school.city,
      kind: 'student',
    };
  })();

  const chosen = mode === 'code' ? codeClass : listClass;
  const catalogEmpty = citiesState === 'ready' && cities.length === 0;

  const next = () => {
    if (step === 0) {
      setTouched({ first: true, last: true });
      if (firstErr || lastErr) return;
    }
    setStep((s) => Math.min(lastStep, s + 1));
  };

  const join = async () => {
    if (!onJoin || !chosen) return;
    setBusy(true);
    setSubmitError(null);
    const ok =
      mode === 'code'
        ? await onJoin(undefined, chosen.invite_code)
        : await onJoin(chosen.class_id, undefined);
    setBusy(false);
    if (!ok) setSubmitError('Не удалось присоединиться к классу. Попробуйте ещё раз.');
  };

  const finish = async () => {
    if (firstErr || lastErr) {
      setStep(0);
      setTouched({ first: true, last: true });
      return;
    }
    setBusy(true);
    setSubmitError(null);
    // По коду отправляем только код (сервер сам определит ученик или педагог),
    // из списка только идентификатор класса.
    const ok = await onComplete(
      firstName.trim(),
      avatar,
      lastName.trim(),
      mode === 'code' ? undefined : chosen?.class_id,
      mode === 'code' ? chosen?.invite_code : undefined,
    );
    setBusy(false);
    if (!ok) setSubmitError('Не удалось сохранить. Проверьте соединение и попробуйте ещё раз.');
  };

  const summary = [chosen ? chosen.class_name : '', chosen ? chosen.school_name : '']
    .filter(Boolean)
    .join(' · ');

  const set = (patch: Partial<AvatarConfig>) => setAvatar((prev) => ({ ...prev, ...patch }));

  return (
    <div className="ob">
      <header className="ob-top">
        <span className="ob-brand">Школьный герой</span>
        {!joinOnly && (
          <span className="ob-count" aria-live="polite">
            Шаг {step + 1} из {TOTAL_STEPS}
          </span>
        )}
      </header>

      <ol className="ob-steps" aria-hidden="true" hidden={joinOnly}>
        {Array.from({ length: TOTAL_STEPS }, (_, i) => (
          <li
            key={i}
            className={`ob-steps__item${
              i < step ? ' ob-steps__item--done' : i === step ? ' ob-steps__item--current' : ''
            }`}
          />
        ))}
      </ol>

      <main className="ob-main">
        {step === 0 && (
          <section className="ob-card" aria-labelledby="ob-h-name">
            <div>
              <h1 className="ob-title" id="ob-h-name">Как вас зовут?</h1>
              <p className="ob-lead">Так вас увидят учитель и одноклассники.</p>
            </div>
            <div className="ob-fields ob-fields--two">
              <div className="ob-field">
                <label className="ob-label" htmlFor="ob-first">Имя</label>
                <input
                  id="ob-first"
                  className="ob-input"
                  type="text"
                  autoComplete="given-name"
                  maxLength={24}
                  value={firstName}
                  aria-invalid={touched.first && !!firstErr}
                  aria-describedby="ob-first-msg"
                  onChange={(e) => setFirstName(e.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, first: true }))}
                />
                <span id="ob-first-msg" className="ob-error" role={touched.first && firstErr ? 'alert' : undefined}>
                  {touched.first && firstErr ? firstErr : ''}
                </span>
              </div>
              <div className="ob-field">
                <label className="ob-label" htmlFor="ob-last">Фамилия</label>
                <input
                  id="ob-last"
                  className="ob-input"
                  type="text"
                  autoComplete="family-name"
                  maxLength={32}
                  value={lastName}
                  aria-invalid={touched.last && !!lastErr}
                  aria-describedby="ob-last-msg"
                  onChange={(e) => setLastName(e.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, last: true }))}
                />
                <span id="ob-last-msg" className="ob-error" role={touched.last && lastErr ? 'alert' : undefined}>
                  {touched.last && lastErr ? lastErr : ''}
                </span>
              </div>
            </div>
          </section>
        )}

        {step === 1 && (
          <section className="ob-card" aria-labelledby="ob-h-class">
            <div>
              <h1 className="ob-title" id="ob-h-class">Ваш класс</h1>
              <p className="ob-lead">Найдите школу в списке или введите код приглашения.</p>
            </div>

            <div className="ob-seg" role="group" aria-label="Способ выбора класса">
              <button type="button" className="ob-seg__btn" aria-pressed={mode === 'list'} onClick={() => setMode('list')}>
                Из списка
              </button>
              <button type="button" className="ob-seg__btn" aria-pressed={mode === 'code'} onClick={() => setMode('code')}>
                По коду
              </button>
            </div>

            {mode === 'code' && (
              <div className="ob-field">
                <label className="ob-label" htmlFor="ob-code">Код приглашения</label>
                <div className="ob-row">
                  <input
                    id="ob-code"
                    className="ob-input ob-input--code"
                    type="text"
                    autoCapitalize="characters"
                    autoComplete="off"
                    spellCheck={false}
                    value={code}
                    aria-invalid={!!codeError}
                    aria-describedby="ob-code-msg"
                    onChange={(e) => {
                      setCode(e.target.value.toUpperCase());
                      setCodeError(null);
                      setCodeClass(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        void verifyCode(code);
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="ob-btn"
                    onClick={() => void verifyCode(code)}
                    disabled={checking || !code.trim()}
                  >
                    {checking ? 'Проверяем…' : 'Проверить'}
                  </button>
                </div>
                <span id="ob-code-msg" className={codeError ? 'ob-error' : 'ob-hint'} role={codeError ? 'alert' : undefined}>
                  {codeError ?? 'Код выдаёт классный руководитель или администрация школы.'}
                </span>
              </div>
            )}

            {mode === 'list' && (
              <>
                {citiesState === 'loading' && <p className="ob-hint">Загружаем список городов…</p>}
                {citiesState === 'error' && (
                  <div className="ob-notice ob-notice--error" role="alert">
                    <Icon name="alert" size={16} />
                    <span>Не удалось загрузить список школ. Введите код приглашения или попробуйте позже.</span>
                  </div>
                )}
                {catalogEmpty && (
                  <div className="ob-notice">
                    <Icon name="info" size={16} />
                    <span>
                      Школы ещё не зарегистрированы. Введите код приглашения или попросите
                      директора добавить школу.
                    </span>
                  </div>
                )}
                {citiesState === 'ready' && !catalogEmpty && (
                  <div className="ob-fields">
                    <div className="ob-field">
                      <label className="ob-label" htmlFor="ob-city">Город</label>
                      <select
                        id="ob-city"
                        className="ob-select"
                        value={city}
                        onChange={(e) => {
                          setCity(e.target.value);
                          setSchoolId(null);
                          setClassId(null);
                        }}
                      >
                        <option value="">Выберите город</option>
                        {cities.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                    <div className="ob-field">
                      <label className="ob-label" htmlFor="ob-search">Школа</label>
                      <input
                        id="ob-search"
                        className="ob-input"
                        type="search"
                        autoComplete="off"
                        placeholder="Начните вводить название"
                        value={query}
                        onChange={(e) => {
                          setQuery(e.target.value);
                          setSchoolId(null);
                          setClassId(null);
                        }}
                      />
                      {foundState === 'loading' && <span className="ob-hint">Ищем…</span>}
                      {foundState === 'error' && (
                        <span className="ob-error" role="alert">Не удалось загрузить школы</span>
                      )}
                      {foundState === 'ready' && schools.length === 0 && (
                        <span className="ob-hint">Школ не найдено. Попробуйте другое название или введите код.</span>
                      )}
                      {foundState === 'idle' && (
                        <span className="ob-hint">Выберите город или введите не меньше двух букв названия.</span>
                      )}
                      {schools.length > 0 && (
                        <ul className="su-pick-list">
                          {schools.map((s) => (
                            <li key={s.id}>
                              <button
                                type="button"
                                className="su-pick"
                                aria-pressed={schoolId === s.id}
                                onClick={() => {
                                  setSchoolId(s.id);
                                  setClassId(null);
                                }}
                              >
                                <span className="su-pick__name">{s.name}</span>
                                <span className="su-pick__meta">{s.city}</span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    {schoolId !== null && (
                      <div className="ob-field">
                        <span className="ob-label" id="ob-class-label">Класс</span>
                        {classes.length === 0 ? (
                          <span className="ob-hint">В этой школе пока нет классов.</span>
                        ) : (
                          <div className="su-chips" role="group" aria-labelledby="ob-class-label">
                            {classes.map((c) => (
                              <button
                                key={c.id}
                                type="button"
                                className="su-chip"
                                aria-pressed={classId === c.id}
                                onClick={() => setClassId(c.id)}
                              >
                                {c.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {chosen && (
              <div className="ob-found" aria-live="polite">
                <span className="ob-found__title">
                  {[chosen.class_name, chosen.school_name].filter(Boolean).join(' · ')}
                </span>
                <span className="ob-found__meta">
                  {chosen.kind === 'teacher'
                    ? 'Код педагога: вы войдёте как педагог этого класса'
                    : [chosen.city, chosen.teacher_name ? `Классный руководитель: ${chosen.teacher_name}` : '']
                        .filter(Boolean)
                        .join(' · ')}
                </span>
              </div>
            )}

            {joinOnly && submitError && (
              <div className="ob-notice ob-notice--error" role="alert">
                <Icon name="alert" size={16} />
                <span>{submitError}</span>
              </div>
            )}
          </section>
        )}

        {step === 2 && (
          <section className="ob-card" aria-labelledby="ob-h-look">
            <div>
              <h1 className="ob-title" id="ob-h-look">Ваш герой</h1>
              <p className="ob-lead">Внешний вид можно поменять позже во вкладке «Стиль».</p>
            </div>

            <div className="ob-preview">
              <AvatarFrame avatar={avatar} size={96} decorative />
              <div className="ob-preview__text">
                <div className="ob-preview__name">
                  {firstName.trim()} {lastName.trim()}
                </div>
                {summary && <div className="ob-preview__meta">{summary}</div>}
              </div>
            </div>

            <div className="ob-tabs" role="tablist" aria-label="Что изменить">
              {AVATAR_TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  id={`ob-tab-${t.id}`}
                  aria-selected={tab === t.id}
                  aria-controls="ob-tabpanel"
                  className="ob-tab"
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div id="ob-tabpanel" role="tabpanel" aria-labelledby={`ob-tab-${tab}`} className="ob-group">
              {tab === 'skin' && (
                <div className="ob-swatches">
                  {skins.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ob-swatch"
                      style={{ backgroundColor: item.swatch }}
                      aria-label={item.name}
                      aria-pressed={avatar.skin === item.id}
                      onClick={() => set({ skin: item.id })}
                    />
                  ))}
                </div>
              )}

              {tab === 'hair' && (
                <>
                  <div className="ob-opts">
                    {hairs.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className="ob-opt"
                        aria-pressed={avatar.hair === item.id}
                        onClick={() => set({ hair: item.id })}
                      >
                        <PixelHero avatar={{ ...avatar, hair: item.id }} size={28} decorative />
                        <span>{item.name}</span>
                      </button>
                    ))}
                  </div>
                  <div className="ob-label">Цвет волос</div>
                  <div className="ob-swatches">
                    {hairColors.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className="ob-swatch"
                        style={{ backgroundColor: item.swatch }}
                        aria-label={item.name}
                        aria-pressed={avatar.hairColor === item.id}
                        onClick={() => set({ hairColor: item.id })}
                      />
                    ))}
                  </div>
                </>
              )}

              {tab === 'outfit' && (
                <div className="ob-opts">
                  {outfits.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ob-opt"
                      aria-pressed={avatar.outfit === item.id}
                      onClick={() => set({ outfit: item.id })}
                    >
                      <span>{item.name}</span>
                    </button>
                  ))}
                </div>
              )}

              {tab === 'accessory' && (
                <div className="ob-opts">
                  {glasses.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ob-opt"
                      aria-pressed={avatar.accessory === item.id}
                      onClick={() => set({ accessory: item.id })}
                    >
                      <span>{item.id === 'none' ? 'Без очков' : item.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {submitError && (
              <div className="ob-notice ob-notice--error" role="alert">
                <Icon name="alert" size={16} />
                <span>{submitError}</span>
              </div>
            )}
          </section>
        )}
      </main>

      <footer className="ob-actions">
        {(step > firstStep || onBack) && (
          <button
            type="button"
            className="ob-btn ob-btn--ghost"
            onClick={() => (step > firstStep ? setStep((s) => Math.max(firstStep, s - 1)) : onBack?.())}
            disabled={busy}
          >
            <Icon name="arrowLeft" size={16} />
            Назад
          </button>
        )}
        <div className="ob-actions__end">
          {step < lastStep ? (
            <button
              type="button"
              className="ob-btn"
              onClick={next}
              disabled={step === 1 && !chosen}
            >
              Далее
            </button>
          ) : joinOnly ? (
            <button type="button" className="ob-btn" onClick={() => void join()} disabled={busy || !chosen}>
              {busy ? 'Сохраняем…' : 'Готово'}
            </button>
          ) : (
            <button type="button" className="ob-btn" onClick={() => void finish()} disabled={busy}>
              {busy ? 'Сохраняем…' : 'Готово'}
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}
