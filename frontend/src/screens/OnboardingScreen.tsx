import { useEffect, useState } from 'react';
import { api } from '../api';
import { AvatarFrame } from '../components/AvatarFrame';
import { CityInput, type CityStatus } from '../components/CityInput';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { JoinModeInfo } from '../components/infoTexts';
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
  ) => Promise<string | null>;
  /** Ученик без класса: только выбор класса, без имени и героя. */
  joinOnly?: boolean;
  onJoin?: (classId?: number, inviteCode?: string) => Promise<string | null>;
  /** Подсказка над выбором класса (например, об исключении). */
  notice?: string;
  /** Сразу открыть ввод кода (например, вместо ожидания заявки). */
  initialMode?: 'code' | 'list';
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

type AvatarTab = 'skin' | 'hair' | 'outfit' | 'face';

const TOTAL_STEPS = 3;
const SCHOOLS_PAGE = 20;
/** Поле поиска школы нужно, если в городе больше этого числа школ. */
const SEARCH_FROM = 8;
const NAME_RE = /^[\p{L}][\p{L}\- ]*$/u;

const AVATAR_TABS: { id: AvatarTab; label: string }[] = [
  { id: 'skin', label: 'Кожа' },
  { id: 'hair', label: 'Волосы' },
  { id: 'outfit', label: 'Одежда' },
  { id: 'face', label: 'Очки' },
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

export function OnboardingScreen({ state, onComplete, joinOnly = false, onJoin, notice, initialMode, onBack }: OnboardingScreenProps) {
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
  const [mode, setMode] = useState<'code' | 'list'>(
    initialMode ?? (readCodeFromUrl() ? 'code' : 'list'),
  );
  const [code, setCode] = useState(readCodeFromUrl);
  const [checking, setChecking] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [codeClass, setCodeClass] = useState<ClassChoice | null>(null);

  // Выбор из списка: город (чип) - школа - класс. Школы без города не показываются.
  const [city, setCity] = useState('');
  const [cityText, setCityText] = useState('');
  const [cityInfo, setCityInfo] = useState<CityStatus>({ status: 'loading', total: -1, query: '', names: [] });
  const [citiesTick, setCitiesTick] = useState(0);
  const [schoolQuery, setSchoolQuery] = useState('');
  const [schools, setSchools] = useState<SchoolCatalog['schools']>([]);
  const [allClasses, setAllClasses] = useState<SchoolCatalog['classes']>([]);
  const [hasMore, setHasMore] = useState(false);
  const [cityTotal, setCityTotal] = useState(0);
  const [schoolState, setSchoolState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [loadingMore, setLoadingMore] = useState(false);
  const [schoolsTick, setSchoolsTick] = useState(0);
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
  const glasses = pick('face', ['face_none', 'glasses', 'glasses_round']);

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
    if (code) void verifyCode(code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Города и школы могли появиться уже после открытия экрана: перезапрашиваем
  // при переходе на вкладку «Из списка» и при возврате к окну.
  const refreshLists = () => {
    setCitiesTick((n) => n + 1);
    setSchoolsTick((n) => n + 1);
  };

  useEffect(() => {
    if (mode === 'list') refreshLists();
  }, [mode]);

  useEffect(() => {
    if (mode !== 'list') return undefined;
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshLists();
    };
    window.addEventListener('focus', onVisible);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('focus', onVisible);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [mode]);

  const onCityStatus = (info: CityStatus) => {
    setCityInfo(info);
    // Единственный город в каталоге выбирается сам.
    if (info.status === 'ready' && info.query === '' && info.total === 1 && info.names[0]) {
      setCity((current) => current || info.names[0]);
    }
  };

  const changeCity = () => {
    setCity('');
    setCityText('');
    setSchoolQuery('');
    setSchools([]);
    setAllClasses([]);
    setSchoolId(null);
    setClassId(null);
    setSchoolState('idle');
  };

  // Школы выбранного города: серверный поиск по названию, страницы по 20.
  useEffect(() => {
    if (mode !== 'list' || !city) return undefined;
    let alive = true;
    setSchoolState('loading');
    const timer = window.setTimeout(() => {
      api
        .getSchoolCatalog({ city, q: schoolQuery.trim(), limit: SCHOOLS_PAGE })
        .then((res) => {
          if (!alive) return;
          setSchools(res.schools);
          setAllClasses(res.classes);
          setHasMore(Boolean(res.has_more));
          if (!schoolQuery.trim()) setCityTotal(res.total ?? res.schools.length);
          setSchoolState('ready');
        })
        .catch(() => {
          if (alive) setSchoolState('error');
        });
    }, schoolQuery ? 250 : 0);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [mode, city, schoolQuery, schoolsTick]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const res = await api.getSchoolCatalog({
        city,
        q: schoolQuery.trim(),
        limit: SCHOOLS_PAGE,
        offset: schools.length,
      });
      setSchools((prev) => [...prev, ...res.schools]);
      setAllClasses((prev) => [...prev, ...res.classes]);
      setHasMore(Boolean(res.has_more));
    } catch {
      setSchoolState('error');
    } finally {
      setLoadingMore(false);
    }
  };

  const classes = allClasses.filter((c) => c.school_id === schoolId);

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
    const problem =
      mode === 'code'
        ? await onJoin(undefined, chosen.invite_code)
        : await onJoin(chosen.class_id, undefined);
    setBusy(false);
    if (problem) setSubmitError(problem);
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
    const problem = await onComplete(
      firstName.trim(),
      avatar,
      lastName.trim(),
      mode === 'code' ? undefined : chosen?.class_id,
      mode === 'code' ? chosen?.invite_code : undefined,
    );
    setBusy(false);
    if (problem) {
      setSubmitError(problem);
      // Ошибка про класс (например, отчисление) показывается на шаге выбора класса.
      if (/класс/i.test(problem)) setStep(1);
    }
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
              <h1 className="ob-title" id="ob-h-class">
                Ваш класс
                <InfoButton title="Заявка или код класса">
                  <JoinModeInfo />
                </InfoButton>
              </h1>
              <p className="ob-lead">
                По коду класса вы войдёте сразу. Из списка школ отправляется заявка: войти в класс
                можно будет после того, как её примет педагог.
              </p>
            </div>

            {notice && (
              <div className="ob-notice" role="status">
                <Icon name="info" size={16} />
                <span>{notice}</span>
              </div>
            )}

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
              <div className="ob-fields">
                {!city ? (
                  <div className="ob-field">
                    <label className="ob-label" htmlFor="ob-city">Город</label>
                    <CityInput
                      id="ob-city"
                      value={cityText}
                      onChange={setCityText}
                      onPick={(name) => setCity(name)}
                      onStatus={onCityStatus}
                      refreshKey={citiesTick}
                      placeholder="Начните вводить название города"
                    />
                    {cityInfo.status === 'loading' && <span className="ob-hint">Ищем города…</span>}
                    {cityInfo.status === 'error' && (
                      <div className="ob-notice ob-notice--error" role="alert">
                        <Icon name="alert" size={16} />
                        <span>
                          Не удалось загрузить города. Проверьте соединение.{' '}
                          <button type="button" className="su-link" onClick={refreshLists}>
                            Повторить
                          </button>
                        </span>
                      </div>
                    )}
                    {cityInfo.status === 'ready' && cityInfo.query === '' && cityInfo.total === 0 && (
                      <div className="ob-notice">
                        <Icon name="info" size={16} />
                        <span>
                          Школы ещё не зарегистрированы. Введите код приглашения или попросите
                          директора добавить школу. Если школу только что создали, нажмите
                          «Обновить».{' '}
                          <button type="button" className="su-link" onClick={refreshLists}>
                            Обновить
                          </button>
                        </span>
                      </div>
                    )}
                    {cityInfo.status === 'ready' && cityInfo.query !== '' && cityInfo.total === 0 && (
                      <span className="ob-hint">Такого города нет в списке. Проверьте написание или введите код.</span>
                    )}
                    {cityInfo.status === 'ready' && cityInfo.query === '' && cityInfo.total > 0 && (
                      <span className="ob-hint">Выберите город из подсказок.</span>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="ob-field">
                      <span className="ob-label">Город</span>
                      <div className="su-selected">
                        <span className="su-selected__text">{city}</span>
                        <button type="button" className="su-link" onClick={changeCity}>
                          Сменить
                        </button>
                      </div>
                    </div>

                    <div className="ob-field">
                      {cityTotal > SEARCH_FROM && (
                        <>
                          <label className="ob-label" htmlFor="ob-search">Название школы</label>
                          <input
                            id="ob-search"
                            className="ob-input"
                            type="search"
                            autoComplete="off"
                            placeholder="Начните вводить название"
                            value={schoolQuery}
                            onChange={(e) => {
                              setSchoolQuery(e.target.value);
                              setSchoolId(null);
                              setClassId(null);
                            }}
                          />
                        </>
                      )}
                      {cityTotal <= SEARCH_FROM && <span className="ob-label">Школа</span>}
                      {schoolState === 'loading' && <span className="ob-hint">Загружаем школы…</span>}
                      {schoolState === 'error' && (
                        <div className="ob-notice ob-notice--error" role="alert">
                          <Icon name="alert" size={16} />
                          <span>
                            Не удалось загрузить школы. Проверьте соединение.{' '}
                            <button type="button" className="su-link" onClick={refreshLists}>
                              Повторить
                            </button>
                          </span>
                        </div>
                      )}
                      {schoolState === 'ready' && schools.length === 0 && (
                        <span className="ob-hint">
                          {schoolQuery.trim()
                            ? 'Школ с таким названием нет. Попробуйте другое слово.'
                            : 'В этом городе пока нет школ.'}
                        </span>
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
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                      {hasMore && (
                        <button type="button" className="ob-btn ob-btn--ghost" onClick={() => void loadMore()} disabled={loadingMore}>
                          {loadingMore ? 'Загружаем…' : 'Показать ещё'}
                        </button>
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
                  </>
                )}
              </div>
            )}

            {chosen && (
              <div className="ob-found" aria-live="polite">
                <span className="ob-found__title">
                  {[chosen.class_name, chosen.school_name].filter(Boolean).join(' · ')}
                </span>
                <span className="ob-found__meta">
                  {chosen.kind === 'teacher'
                    ? 'Код педагога: вы войдёте как педагог этого класса'
                    : [
                        chosen.city,
                        chosen.teacher_name ? `Классный руководитель: ${chosen.teacher_name}` : '',
                        mode === 'list' ? 'Будет отправлена заявка педагогу' : 'Вход сразу по коду',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                </span>
              </div>
            )}

            {submitError && (
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

              {tab === 'face' && (
                <div className="ob-opts">
                  {glasses.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ob-opt"
                      aria-pressed={avatar.face === item.id}
                      onClick={() => set({ face: item.id })}
                    >
                      <span>{item.id === 'face_none' ? 'Без очков' : item.name}</span>
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
