import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useConfirm } from '../components/ConfirmDialog';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { BlockInfo, SchoolStatusesInfo } from '../components/infoTexts';
import { formatShortDate } from '../components/PrintReport';
import type {
  AdminSchoolDetail,
  AdminSchoolItem,
  AdminSummary,
  AdminUserItem,
  DeletedSchoolSummary,
  GameState,
  SchoolStatus,
} from '../types';
import '../styles/admin.css';

type Notify = (message: string, tone?: 'success' | 'info' | 'error') => void;

const STATUS_LABEL: Record<SchoolStatus, string> = {
  pending: 'Ожидает',
  active: 'Активна',
  rejected: 'Отклонена',
};

const ROLE_LABEL = { student: 'Ученик', teacher: 'Педагог', director: 'Директор' } as const;

type Filter = SchoolStatus | 'all';

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/** Поле поиска с задержкой: запрос уходит, когда пользователь перестал печатать. */
function useDebounced(value: string, delay = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function SearchField({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder: string;
}) {
  return (
    <label className="ad-search">
      <span className="ad-search__icon" aria-hidden="true">
        <Icon name="search" size={18} />
      </span>
      <input
        type="search"
        className="ad-search__input"
        value={value}
        maxLength={80}
        aria-label={label}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function Tile({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="ad-tile">
      <span className="ad-tile__value">{value}</span>
      <span className="ad-tile__label">{label}</span>
      {hint ? <span className="ad-tile__hint">{hint}</span> : null}
    </div>
  );
}

function SummaryBlock({ summary }: { summary: AdminSummary | null }) {
  if (!summary) return null;
  const { schools, users } = summary;
  return (
    <section className="ad-summary" aria-label="Сводка платформы">
      <Tile
        label="Школ"
        value={schools.total}
        hint={`ожидают ${schools.pending} · активны ${schools.active} · отклонены ${schools.rejected}`}
      />
      <Tile
        label="Пользователей"
        value={users.total}
        hint={`учеников ${users.student} · педагогов ${users.teacher} · директоров ${users.director}`}
      />
      <Tile label="Активных учеников за 7 дней" value={summary.active_students_week} />
      <Tile label="Работ на проверке" value={summary.pending_works} />
      <Tile label="Администраторов" value={summary.admins} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Школы
// ---------------------------------------------------------------------------

type SchoolsProps = {
  busy: boolean;
  notify: Notify;
  onSetStatus: (schoolId: number, status: 'active' | 'rejected', reason: string) => Promise<boolean>;
  onDelete: (schoolId: number, confirmName: string) => Promise<DeletedSchoolSummary | null>;
};

export function AdminSchoolsScreen({ busy, notify, onSetStatus, onDelete }: SchoolsProps) {
  const { confirm, ask, dialog } = useConfirm();
  const [filter, setFilter] = useState<Filter>('pending');
  const [query, setQuery] = useState('');
  const search = useDebounced(query.trim());
  const [items, setItems] = useState<AdminSchoolItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);
  const requestId = useRef(0);

  const load = useCallback(
    async (offset = 0) => {
      const id = ++requestId.current;
      setLoading(true);
      setError('');
      try {
        const page = await api.adminSchools({ status: filter, q: search, offset });
        if (id !== requestId.current) return;
        setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
        setTotal(page.total);
        setHasMore(page.has_more);
        setSummary(page.summary);
      } catch (e) {
        if (id !== requestId.current) return;
        setError(errorText(e, 'Не удалось загрузить список школ'));
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [filter, search],
  );

  useEffect(() => {
    void load(0);
  }, [load]);

  const approve = async (school: AdminSchoolItem) => {
    const ok = await confirm({
      title: 'Подтвердить школу?',
      message: `«${school.name}», ${school.city}. Школа появится в списке для учеников и педагогов.`,
      confirmLabel: 'Подтвердить',
    });
    if (ok && (await onSetStatus(school.id, 'active', ''))) await load(0);
  };

  const restore = async (school: AdminSchoolItem) => {
    const ok = await confirm({
      title: 'Вернуть школу?',
      message: `«${school.name}» снова станет активной, причина отклонения будет удалена.`,
      confirmLabel: 'Вернуть',
    });
    if (ok && (await onSetStatus(school.id, 'active', ''))) await load(0);
  };

  const reject = async (school: AdminSchoolItem) => {
    const reason = await ask({
      title: 'Отклонить школу?',
      message: `«${school.name}», ${school.city}. Ученики и педагоги не смогут присоединиться, директор не сможет менять классы.`,
      confirmLabel: 'Отклонить',
      danger: true,
      input: { label: 'Причина (необязательно, увидит директор)', maxLength: 200 },
    });
    if (reason !== null && (await onSetStatus(school.id, 'rejected', reason))) await load(0);
  };

  const remove = async (school: AdminSchoolItem): Promise<boolean> => {
    const typed = await ask({
      title: 'Удалить школу навсегда?',
      message: `Будут удалены классы, задания, работы с фото, заявки и история опыта школы «${school.name}». Ученики и педагоги останутся без класса, директор потеряет школу. Действие нельзя отменить. Для подтверждения введите название школы.`,
      confirmLabel: 'Удалить навсегда',
      danger: true,
      input: { label: `Название: ${school.name}`, match: school.name, maxLength: 120 },
    });
    if (typed === null) return false;
    const result = await onDelete(school.id, typed);
    if (!result) return false;
    notify(
      `Школа удалена: классов ${result.classes}, работ ${result.completions}, фото ${result.files_removed}`,
      'info',
    );
    await load(0);
    return true;
  };

  if (openId !== null) {
    return (
      <>
        <AdminSchoolView
          schoolId={openId}
          busy={busy}
          onBack={() => setOpenId(null)}
          onApprove={approve}
          onRestore={restore}
          onReject={reject}
          onDelete={async (school) => {
            if (await remove(school)) setOpenId(null);
          }}
        />
        {dialog}
      </>
    );
  }

  const filters: Array<{ id: Filter; label: string; count?: number }> = [
    { id: 'pending', label: 'Ожидают', count: summary?.schools.pending },
    { id: 'active', label: 'Активные', count: summary?.schools.active },
    { id: 'rejected', label: 'Отклонённые', count: summary?.schools.rejected },
    { id: 'all', label: 'Все', count: summary?.schools.total },
  ];

  return (
    <div className="ad">
      <header className="ad-head">
        <h1 className="ad-title">
          Школы{' '}
          <span className="info-nw">
            платформы
            <InfoButton title="Статусы школ и удаление">
              <SchoolStatusesInfo />
            </InfoButton>
          </span>
        </h1>
        <p className="ad-sub">Все школы, модерация и удаление.</p>
      </header>

      <SummaryBlock summary={summary} />

      <div className="ad-filters" role="tablist" aria-label="Статус школ">
        {filters.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={`ad-filter ${filter === f.id ? 'is-active' : ''}`.trim()}
            onClick={() => setFilter(f.id)}
          >
            <span>{f.label}</span>
            {f.count ? <span className="ad-filter__count">{f.count}</span> : null}
          </button>
        ))}
      </div>

      <SearchField
        value={query}
        onChange={setQuery}
        label="Поиск школы"
        placeholder="Название или город"
      />

      {error ? (
        <div className="ob-notice ob-notice--error" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      {!loading && !error && items.length === 0 ? (
        <div className="ob-notice" role="status">
          <Icon name="info" size={16} />
          <span>{search ? 'Ничего не найдено.' : 'Школ в этом разделе нет.'}</span>
        </div>
      ) : null}

      <ul className="ad-list">
        {items.map((school) => (
          <li key={school.id} className="ad-card">
            <div className="ad-card__head">
              <h3 className="ad-card__name">{school.name}</h3>
              <span className={`ad-status ad-status--${school.status}`}>{STATUS_LABEL[school.status]}</span>
            </div>
            <p className="ad-card__meta">
              {school.city} · {school.timezone}
            </p>
            <dl className="ad-facts">
              <div>
                <dt>Директор</dt>
                <dd>{school.director || '—'}</dd>
              </div>
              <div>
                <dt>Зарегистрирована</dt>
                <dd>{formatShortDate(school.created_at) || '—'}</dd>
              </div>
              <div>
                <dt>Классов</dt>
                <dd>{school.classes}</dd>
              </div>
              <div>
                <dt>Учеников</dt>
                <dd>{school.students}</dd>
              </div>
              <div>
                <dt>Педагогов</dt>
                <dd>{school.teachers}</dd>
              </div>
              <div>
                <dt>Активных за неделю</dt>
                <dd>{school.active_week}</dd>
              </div>
            </dl>
            {school.status === 'rejected' && school.reject_reason ? (
              <p className="ad-card__reason">Причина отклонения: {school.reject_reason}</p>
            ) : null}
            <SchoolActions
              school={school}
              busy={busy}
              onOpen={() => setOpenId(school.id)}
              onApprove={approve}
              onRestore={restore}
              onReject={reject}
              onDelete={remove}
            />
          </li>
        ))}
      </ul>

      {loading ? <p className="ad-sub" role="status">Загрузка…</p> : null}
      {hasMore && !loading ? (
        <button type="button" className="btn btn--secondary ad-more" onClick={() => void load(items.length)}>
          Показать ещё ({total - items.length})
        </button>
      ) : null}
      {dialog}
    </div>
  );
}

function SchoolActions({
  school,
  busy,
  onOpen,
  onApprove,
  onRestore,
  onReject,
  onDelete,
}: {
  school: AdminSchoolItem;
  busy: boolean;
  onOpen?: () => void;
  onApprove: (school: AdminSchoolItem) => void;
  onRestore: (school: AdminSchoolItem) => void;
  onReject: (school: AdminSchoolItem) => void;
  onDelete: (school: AdminSchoolItem) => void;
}) {
  return (
    <div className="ad-actions">
      {onOpen ? (
        <button type="button" className="btn btn--secondary btn--sm" onClick={onOpen}>
          Открыть
        </button>
      ) : null}
      {school.status !== 'active' && school.status !== 'rejected' ? (
        <button type="button" className="btn btn--sm" disabled={busy} onClick={() => onApprove(school)}>
          Подтвердить
        </button>
      ) : null}
      {school.status === 'rejected' ? (
        <button type="button" className="btn btn--sm" disabled={busy} onClick={() => onRestore(school)}>
          Вернуть
        </button>
      ) : (
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => onReject(school)}>
          Отклонить
        </button>
      )}
      <button type="button" className="btn btn--danger btn--sm" disabled={busy} onClick={() => onDelete(school)}>
        Удалить
      </button>
    </div>
  );
}

function AdminSchoolView({
  schoolId,
  busy,
  onBack,
  onApprove,
  onRestore,
  onReject,
  onDelete,
}: {
  schoolId: number;
  busy: boolean;
  onBack: () => void;
  onApprove: (school: AdminSchoolItem) => Promise<void>;
  onRestore: (school: AdminSchoolItem) => Promise<void>;
  onReject: (school: AdminSchoolItem) => Promise<void>;
  onDelete: (school: AdminSchoolItem) => Promise<void>;
}) {
  const [detail, setDetail] = useState<AdminSchoolDetail | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .adminSchoolDetail(schoolId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e, 'Не удалось загрузить школу'));
      });
    return () => {
      cancelled = true;
    };
  }, [schoolId, version]);

  const wrap = (action: (school: AdminSchoolItem) => Promise<void>) => async (school: AdminSchoolItem) => {
    await action(school);
    setVersion((v) => v + 1);
  };

  const school = detail?.school;
  return (
    <div className="ad">
      <button type="button" className="ad-back" onClick={onBack}>
        <Icon name="arrowLeft" size={18} />
        <span>К списку школ</span>
      </button>
      {error ? (
        <div className="ob-notice ob-notice--error" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      ) : null}
      {school ? (
        <>
          <header className="ad-head">
            <h1 className="ad-title">{school.name}</h1>
            <p className="ad-sub">
              {school.city} · {school.timezone} ·{' '}
              <span className={`ad-status ad-status--${school.status}`}>{STATUS_LABEL[school.status]}</span>
            </p>
          </header>
          <dl className="ad-facts ad-facts--card">
            <div>
              <dt>Директор</dt>
              <dd>{school.director || '—'}</dd>
            </div>
            <div>
              <dt>Зарегистрирована</dt>
              <dd>{formatShortDate(school.created_at) || '—'}</dd>
            </div>
            <div>
              <dt>Учеников</dt>
              <dd>{school.students}</dd>
            </div>
            <div>
              <dt>Педагогов</dt>
              <dd>{school.teachers}</dd>
            </div>
            <div>
              <dt>Активных за неделю</dt>
              <dd>{school.active_week}</dd>
            </div>
          </dl>
          {school.status === 'rejected' && school.reject_reason ? (
            <p className="ad-card__reason">Причина отклонения: {school.reject_reason}</p>
          ) : null}
          <SchoolActions
            school={school}
            busy={busy}
            onApprove={(s) => void wrap(onApprove)(s)}
            onRestore={(s) => void wrap(onRestore)(s)}
            onReject={(s) => void wrap(onReject)(s)}
            onDelete={(s) => void onDelete(s)}
          />
          <h2 className="ad-h2">Классы ({detail.classes.length})</h2>
          <p className="ad-sub">Только просмотр. Коды классов администратору платформы не показываются.</p>
          {detail.classes.length === 0 ? (
            <div className="ob-notice" role="status">
              <Icon name="info" size={16} />
              <span>В школе нет классов.</span>
            </div>
          ) : (
            <ul className="ad-list">
              {detail.classes.map((cls) => (
                <li key={cls.id} className="ad-card">
                  <h3 className="ad-card__name">{cls.name}</h3>
                  <p className="ad-card__meta">
                    Учеников: {cls.students} · педагогов: {cls.teachers}
                  </p>
                  {cls.teacher_names.length > 0 ? (
                    <p className="ad-card__meta">Педагоги: {cls.teacher_names.join(', ')}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : !error ? (
        <p className="ad-sub" role="status">Загрузка…</p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Пользователи
// ---------------------------------------------------------------------------

export function AdminUsersScreen({
  notify,
  onStateChange,
}: {
  notify: Notify;
  onStateChange?: (state: GameState) => void;
}) {
  const { confirm, ask, dialog } = useConfirm();
  const [query, setQuery] = useState('');
  const search = useDebounced(query.trim());
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [working, setWorking] = useState<number | null>(null);
  const requestId = useRef(0);

  const load = useCallback(
    async (offset = 0) => {
      const id = ++requestId.current;
      setLoading(true);
      setError('');
      try {
        const page = await api.adminUsers({ q: search, offset, blocked: blockedOnly });
        if (id !== requestId.current) return;
        setItems((prev) => (offset ? [...prev, ...page.items] : page.items));
        setTotal(page.total);
        setHasMore(page.has_more);
        setSummary(page.summary);
      } catch (e) {
        if (id !== requestId.current) return;
        setError(errorText(e, 'Не удалось загрузить пользователей'));
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [search, blockedOnly],
  );

  useEffect(() => {
    void load(0);
  }, [load]);

  const replace = (user: AdminUserItem) =>
    setItems((prev) => prev.map((item) => (item.id === user.id ? user : item)));

  const block = async (user: AdminUserItem) => {
    const reason = await ask({
      title: 'Заблокировать пользователя?',
      message: `${user.name}. Пользователь потеряет доступ ко всему приложению, данные сохранятся.`,
      confirmLabel: 'Заблокировать',
      danger: true,
      input: { label: 'Причина (от 3 символов)', minLength: 3, maxLength: 200 },
    });
    if (reason === null) return;
    setWorking(user.id);
    try {
      const response = await api.adminBlockUser(user.id, reason);
      replace(response.user);
      notify('Пользователь заблокирован', 'info');
      void load(0);
    } catch (e) {
      notify(errorText(e, 'Не удалось заблокировать'), 'error');
    } finally {
      setWorking(null);
    }
  };

  const toggleAdmin = async (user: AdminUserItem) => {
    const enable = !user.is_admin;
    const ok = await confirm({
      title: enable ? 'Сделать администратором?' : 'Снять права администратора?',
      message: enable
        ? `${user.name} сможет подтверждать и удалять школы, блокировать пользователей и назначать других администраторов. Роль в школе не изменится.`
        : user.is_self
          ? 'Вы потеряете доступ к вкладкам администратора. Роль в школе не изменится.'
          : `${user.name} потеряет доступ к вкладкам администратора. Роль в школе не изменится.`,
      confirmLabel: enable ? 'Сделать администратором' : 'Снять права',
      danger: !enable,
    });
    if (!ok) return;
    setWorking(user.id);
    try {
      const response = await api.adminSetAdmin(user.id, enable);
      replace(response.user);
      onStateChange?.(response.state);
      notify(enable ? 'Права администратора выданы' : 'Права администратора сняты', 'info');
      void load(0);
    } catch (e) {
      notify(errorText(e, 'Не удалось изменить права'), 'error');
    } finally {
      setWorking(null);
    }
  };

  const unblock = async (user: AdminUserItem) => {
    const ok = await confirm({
      title: 'Разблокировать пользователя?',
      message: `${user.name} снова получит доступ к приложению.`,
      confirmLabel: 'Разблокировать',
    });
    if (!ok) return;
    setWorking(user.id);
    try {
      const response = await api.adminUnblockUser(user.id);
      replace(response.user);
      notify('Пользователь разблокирован', 'info');
      void load(0);
    } catch (e) {
      notify(errorText(e, 'Не удалось разблокировать'), 'error');
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="ad">
      <header className="ad-head">
        <h1 className="ad-title">
          Пользователи
          <InfoButton title="Блокировка пользователя">
            <BlockInfo />
          </InfoButton>
        </h1>
        <p className="ad-sub">Поиск по имени или идентификатору. Блокировка защищает от спама.</p>
      </header>

      <SummaryBlock summary={summary} />

      <SearchField
        value={query}
        onChange={setQuery}
        label="Поиск пользователя"
        placeholder="Имя, MAX id или client id"
      />
      <label className="ad-check">
        <input type="checkbox" checked={blockedOnly} onChange={(e) => setBlockedOnly(e.target.checked)} />
        <span>
          Только заблокированные{summary && summary.blocked_users ? ` (${summary.blocked_users})` : ''}
        </span>
      </label>

      {error ? (
        <div className="ob-notice ob-notice--error" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <div className="ob-notice" role="status">
          <Icon name="info" size={16} />
          <span>Никого не найдено.</span>
        </div>
      ) : null}

      <ul className="ad-list">
        {items.map((user) => (
          <li key={user.id} className={`ad-card ${user.blocked ? 'ad-card--blocked' : ''}`.trim()}>
            <div className="ad-card__head">
              <h3 className="ad-card__name">{user.name}</h3>
              <span className="ad-status ad-status--role">{ROLE_LABEL[user.role]}</span>
            </div>
            {user.is_admin ? (
              <p className="ad-card__meta">
                <strong>Администратор платформы</strong>
                {user.admin_from_env ? ' (из настроек сервера)' : ''}
              </p>
            ) : null}
            <p className="ad-card__meta ad-card__id">{user.external_id || 'без идентификатора'}</p>
            <dl className="ad-facts">
              <div>
                <dt>Школа, класс</dt>
                <dd>
                  {user.school ? user.school : '—'}
                  {user.class_name ? `, ${user.class_name}` : ''}
                </dd>
              </div>
              <div>
                <dt>Регистрация</dt>
                <dd>{formatShortDate(user.created_at) || '—'}</dd>
              </div>
              <div>
                <dt>Последний активный день</dt>
                <dd>{formatShortDate(user.last_active) || '—'}</dd>
              </div>
            </dl>
            {user.blocked ? (
              <p className="ad-card__reason">
                Заблокирован{user.blocked_at ? ` ${formatShortDate(user.blocked_at)}` : ''}
                {user.blocked_reason ? `. Причина: ${user.blocked_reason}` : ''}
              </p>
            ) : null}
            <div className="ad-actions">
              {user.is_admin || user.is_self ? (
                <span className="ad-card__meta">
                  {user.is_self ? 'Это вы' : 'Администратора'}: заблокировать нельзя
                </span>
              ) : user.blocked ? (
                <button type="button" className="btn btn--secondary btn--sm" disabled={working === user.id} onClick={() => void unblock(user)}>
                  Разблокировать
                </button>
              ) : (
                <button type="button" className="btn btn--danger btn--sm" disabled={working === user.id} onClick={() => void block(user)}>
                  Заблокировать
                </button>
              )}
              {user.admin_from_env ? null : user.is_admin ? (
                <button type="button" className="btn btn--secondary btn--sm" disabled={working === user.id} onClick={() => void toggleAdmin(user)}>
                  Снять права администратора
                </button>
              ) : user.blocked ? null : (
                <button type="button" className="btn btn--secondary btn--sm" disabled={working === user.id} onClick={() => void toggleAdmin(user)}>
                  Сделать администратором
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {loading ? <p className="ad-sub" role="status">Загрузка…</p> : null}
      {hasMore && !loading ? (
        <button type="button" className="btn btn--secondary ad-more" onClick={() => void load(items.length)}>
          Показать ещё ({total - items.length})
        </button>
      ) : null}
      {dialog}
    </div>
  );
}
