import { useId, useMemo, useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { useConfirm } from '../components/ConfirmDialog';
import { JoinRequestsList } from '../components/JoinRequestsList';
import { Sheet } from '../components/Sheet';
import { formatNumber, formatRelative } from '../game';
import type { GameState, TeacherStudent } from '../types';
import { PrintHint, PrintSheet, formatPrintDate, formatShortDate, printDocument } from '../components/PrintReport';
import '../styles/teacher.css';

type SortKey = 'rank' | 'name' | 'xp' | 'weekly_xp' | 'streak' | 'pending_count';
type FilterKey = 'all' | 'attention' | 'active';

const REWARD_REASONS = ['Работа на уроке', 'Помощь классу', 'Участие в мероприятии'];
const REWARD_MIN = 10;
const REWARD_MAX = 300;

const STATUS_LABEL = {
  approved: 'Принято',
  pending: 'На проверке',
  rejected: 'Возвращено',
  available: 'Доступно',
  expired: 'Просрочено',
} as const;

type TeacherClassScreenProps = {
  state: GameState;
  onReview: () => void;
  onRewardStudent?: (studentId: number, amount: number, reason: string) => Promise<boolean>;
  onRemoveStudent?: (studentId: number, reason: string) => Promise<boolean>;
  onRestoreStudent?: (studentId: number) => Promise<boolean>;
  /** Заявки учеников, выбравших класс из списка. */
  onDecideJoin?: (requestId: number, action: 'approve' | 'decline') => Promise<boolean>;
};

function csvCell(value: string | number): string {
  return `"${String(value).replace(/"/g, '""')}"`;
}

export function TeacherClassScreen({
  state,
  onReview,
  onRewardStudent,
  onRemoveStudent,
  onRestoreStudent,
  onDecideJoin,
}: TeacherClassScreenProps) {
  const { viewer, teacher, class_sprint: sprint } = state;
  const uid = useId();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<FilterKey>('all');
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [rewardErrors, setRewardErrors] = useState<{ amount?: string; reason?: string }>({});
  const [rewarding, setRewarding] = useState(false);
  const [rewardDone, setRewardDone] = useState('');
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);
  const [removeReason, setRemoveReason] = useState('');
  const [removing, setRemoving] = useState(false);
  const [excludedOpen, setExcludedOpen] = useState(false);
  const { confirm, dialog } = useConfirm();
  const excluded = teacher?.excluded ?? [];

  const startRemove = async () => {
    if (!selected || !onRemoveStudent) return;
    const ok = await confirm({
      title: `Исключить ${selected.name} из класса?`,
      message:
        'Ученик пропадёт из рейтингов и списка класса и не увидит задания. XP и достижения сохранятся. Он сможет вступить в другой класс, а в этот только после того, как вы вернёте его.',
      confirmLabel: 'Исключить',
      danger: true,
    });
    if (!ok) return;
    setRemoving(true);
    const done = await onRemoveStudent(selected.id, removeReason.trim());
    setRemoving(false);
    if (done) {
      setRemoveReason('');
      setSelectedId(null);
    }
  };

  const startRestore = async (studentId: number, name: string) => {
    if (!onRestoreStudent) return;
    const ok = await confirm({
      title: `Вернуть ${name}?`,
      message:
        'Запрет будет снят: ученик сможет снова вступить в класс по коду или из списка. В класс он автоматически не вернётся.',
      confirmLabel: 'Вернуть',
    });
    if (ok) await onRestoreStudent(studentId);
  };

  const all = teacher?.students ?? [];
  const selected = all.find((s) => s.id === selectedId) ?? null;

  const attentionCount = all.filter((s) => s.at_risk).length;
  const activeCount = all.filter((s) => s.weekly_xp > 0).length;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = all.filter((s) => {
      if (filter === 'attention' && !s.at_risk) return false;
      if (filter === 'active' && s.weekly_xp <= 0) return false;
      return !q || s.name.toLowerCase().includes(q);
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    list.sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name, 'ru') * dir;
      return (a[sortKey] - b[sortKey]) * dir;
    });
    return list;
  }, [all, filter, query, sortKey, sortDir]);

  if (!teacher) {
    return (
      <div className="screen tc-page">
        <EmptyState
          icon="shield"
          title="Кабинет педагога недоступен"
          text="Для этого аккаунта нет данных класса."
        />
      </div>
    );
  }

  const inviteCode = teacher.invite_code || viewer.invite_code || '';
  const chartMax = Math.max(1, ...teacher.chart.map((d) => d.xp));
  const chartTotal = teacher.chart.reduce((sum, d) => sum + d.xp, 0);
  const goalPercent =
    sprint && sprint.goal > 0
      ? Math.min(100, Math.round((teacher.stats.weekly_xp / sprint.goal) * 100))
      : null;

  const changeSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'rank' || key === 'name' ? 'asc' : 'desc');
    }
  };

  const ariaSort = (key: SortKey): 'ascending' | 'descending' | 'none' =>
    key === sortKey ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none';

  const sortHead = (k: SortKey, label: string, right?: boolean) => (
    <th key={k} scope="col" className={right ? 'tc-r' : undefined} aria-sort={ariaSort(k)}>
      <button type="button" className="tc-sort" data-active={k === sortKey} onClick={() => changeSort(k)}>
        {label}
        {k === sortKey ? <Icon name={sortDir === 'asc' ? 'arrowUp' : 'arrowDown'} size={12} /> : null}
      </button>
    </th>
  );

  const openStudent = (student: TeacherStudent) => {
    setSelectedId(student.id);
    setAmount('');
    setReason('');
    setRewardErrors({});
    setRewardDone('');
  };

  const submitReward = async () => {
    if (!selected || !onRewardStudent) return;
    const errs: { amount?: string; reason?: string } = {};
    const value = Number(amount);
    if (!Number.isInteger(value) || value < REWARD_MIN || value > REWARD_MAX) {
      errs.amount = `Целое число от ${REWARD_MIN} до ${REWARD_MAX}.`;
    }
    if (reason.trim().length < 3) errs.reason = 'Укажите причину — она попадёт в ленту класса.';
    setRewardErrors(errs);
    if (errs.amount || errs.reason) return;
    setRewarding(true);
    const ok = await onRewardStudent(selected.id, value, reason.trim());
    setRewarding(false);
    if (ok) {
      setRewardDone(`Начислено ${value} XP: ${selected.name}`);
      setAmount('');
      setReason('');
    }
  };

  const copy = async (text: string, what: 'code' | 'link') => {
    try {
      await navigator.clipboard?.writeText(text);
      setCopied(what);
      window.setTimeout(() => setCopied(null), 2500);
    } catch {
      // буфер недоступен
    }
  };

  const exportCsv = () => {
    const header = [
      'Место',
      'Ученик',
      'Уровень',
      'XP всего',
      'XP за неделю',
      'Серия, дн.',
      'На проверке',
      'Последняя активность',
      'Требует внимания',
      'Причины',
    ];
    const body = all.map((s) =>
      [
        s.rank,
        csvCell(s.name),
        csvCell(`${s.level_title} (${s.level})`),
        s.xp,
        s.weekly_xp,
        s.streak,
        s.pending_count,
        csvCell(s.last_active),
        s.at_risk ? 'да' : 'нет',
        csvCell((s.risk_reasons ?? []).join('; ')),
      ].join(';'),
    );
    const blob = new Blob(['﻿' + [header.join(';'), ...body].join('\r\n')], {
      type: 'text/csv;charset=utf-8;',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Класс_${viewer.class_name}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const weekDates = (state.week ?? []).map((d) => d.date).filter(Boolean);
  const periodText =
    weekDates.length > 1
      ? `${formatShortDate(weekDates[0])} – ${formatShortDate(weekDates[weekDates.length - 1])}`
      : 'текущая учебная неделя';
  const printStudents = [...all].sort((a, b) => a.rank - b.rank);
  const doneWorks = all
    .flatMap((s) =>
      (s.recent_works ?? []).filter((w) => w.status === 'approved').map((w) => ({ ...w, student: s.name })),
    )
    .sort((a, b) => (a.date < b.date ? 1 : -1));

  const inviteLink = inviteCode ? `${window.location.origin}/?code=${encodeURIComponent(inviteCode)}` : '';
  const subtitle = [viewer.school_name, viewer.city].filter(Boolean).join(' · ');

  return (
    <div className="screen tc-page">
      <ScreenTitle
        title={`Класс ${viewer.class_name}`}
        subtitle={subtitle}
        action={
          <div className="tc-toolbar">
            <button type="button" className="tc-btn" onClick={exportCsv} disabled={all.length === 0}>
              <Icon name="archive" size={16} />
              <span>Выгрузить CSV</span>
            </button>
            <button type="button" className="tc-btn" onClick={printDocument} disabled={all.length === 0}>
              <Icon name="book" size={16} />
              <span>Печать</span>
            </button>
          </div>
        }
      />
      {all.length > 0 ? <PrintHint /> : null}

      {onDecideJoin ? (
        <JoinRequestsList requests={teacher.join_requests ?? []} onDecide={onDecideJoin} />
      ) : null}

      <div className="tc-stats">
        <div className="tc-stat">
          <span className="tc-stat__label">Учеников</span>
          <span className="tc-stat__value">{teacher.stats.students}</span>
          <span className="tc-stat__hint">активны на неделе: {teacher.stats.active_week}</span>
        </div>
        <button
          type="button"
          className={`tc-stat ${teacher.stats.pending ? 'tc-stat--warn' : ''}`}
          onClick={onReview}
        >
          <span className="tc-stat__label">На проверке</span>
          <span className="tc-stat__value">{teacher.stats.pending}</span>
          <span className="tc-stat__hint">открыть очередь</span>
        </button>
        <div className="tc-stat">
          <span className="tc-stat__label">XP за неделю</span>
          <span className="tc-stat__value">{formatNumber(teacher.stats.weekly_xp)}</span>
          <span className="tc-stat__hint">
            в среднем на ученика: {formatNumber(teacher.stats.avg_weekly_xp)}
          </span>
        </div>
        <button
          type="button"
          className={`tc-stat ${teacher.stats.at_risk ? 'tc-stat--danger' : ''}`}
          onClick={() => setFilter(filter === 'attention' ? 'all' : 'attention')}
          aria-pressed={filter === 'attention'}
        >
          <span className="tc-stat__label">Требуют внимания</span>
          <span className="tc-stat__value">{teacher.stats.at_risk}</span>
          <span className="tc-stat__hint">{filter === 'attention' ? 'показать всех' : 'показать в списке'}</span>
        </button>
      </div>

      <section className="tc-panel" aria-labelledby={`${uid}-invite`}>
        <div className="tc-invite">
          <div className="tc-invite__text">
            <h2 className="tc-h2" id={`${uid}-invite`}>
              Код приглашения
            </h2>
            <p className="tc-muted" style={{ margin: 0 }}>
              {inviteCode
                ? 'Ученик вводит код при входе и попадает в этот класс.'
                : 'Код приглашения для этого класса не получен.'}
            </p>
          </div>
          {inviteCode ? (
            <>
              <span className="tc-code" aria-label={`Код приглашения: ${inviteCode}`}>
                {inviteCode}
              </span>
              <button type="button" className="tc-btn" onClick={() => void copy(inviteCode, 'code')}>
                <Icon name={copied === 'code' ? 'check' : 'share'} size={16} />
                {copied === 'code' ? 'Скопировано' : 'Копировать код'}
              </button>
              <button type="button" className="tc-btn" onClick={() => void copy(inviteLink, 'link')}>
                <Icon name={copied === 'link' ? 'check' : 'share'} size={16} />
                {copied === 'link' ? 'Скопировано' : 'Копировать ссылку'}
              </button>
            </>
          ) : null}
        </div>
      </section>

      <section className="tc-panel" aria-labelledby={`${uid}-week`}>
        <div className="tc-panel__head">
          <h2 className="tc-h2" id={`${uid}-week`}>
            Активность класса за неделю
          </h2>
          <span className="tc-muted tc-num">{formatNumber(chartTotal)} XP</span>
        </div>
        {teacher.chart.length > 0 ? (
          <div className="tc-bars" role="list" aria-label="XP класса по дням">
            {teacher.chart.map((d) => (
              <div className="tc-bars__col" role="listitem" key={d.date} aria-label={`${d.label}: ${d.xp} XP`}>
                <span className="tc-bars__value">{d.xp}</span>
                <div className="tc-bars__track">
                  <div
                    className="tc-bars__fill"
                    style={{ height: d.xp > 0 ? `${Math.max(4, Math.round((d.xp / chartMax) * 100))}%` : 0 }}
                  />
                </div>
                <span className="tc-faint">{d.label}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="tc-muted" style={{ margin: 0 }}>
            Данных об активности за неделю нет.
          </p>
        )}
        {goalPercent !== null && sprint ? (
          <div className="tc-meter-row" style={{ marginTop: 16 }}>
            <div className="tc-meter-row__head">
              <span>Цель недели</span>
              <span className="tc-num">
                {formatNumber(teacher.stats.weekly_xp)} из {formatNumber(sprint.goal)} XP · {goalPercent}%
              </span>
            </div>
            <div
              className="tc-meter"
              role="progressbar"
              aria-label="Выполнение цели недели"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={goalPercent}
            >
              <div className="tc-meter__fill" style={{ width: `${goalPercent}%` }} />
            </div>
            <span className="tc-faint">Место среди классов школы: {sprint.rank}</span>
          </div>
        ) : null}
      </section>

      <section className="tc-section" aria-label="Ученики">
        <div className="tc-toolbar" role="search">
          <div className="tc-search">
            <label htmlFor={`${uid}-q`} className="tc-sr">
              Поиск ученика
            </label>
            <input
              id={`${uid}-q`}
              type="search"
              className="tc-input"
              placeholder="Поиск по имени"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select
            className="tc-select"
            aria-label="Показать"
            value={filter}
            onChange={(e) => setFilter(e.target.value as FilterKey)}
          >
            <option value="all">Все ({all.length})</option>
            <option value="attention">Требуют внимания ({attentionCount})</option>
            <option value="active">Активны на неделе ({activeCount})</option>
          </select>
          <select
            className="tc-select tc-sort-select"
            aria-label="Сортировка"
            value={`${sortKey}:${sortDir}`}
            onChange={(e) => {
              const [k, d] = e.target.value.split(':');
              setSortKey(k as SortKey);
              setSortDir(d as 'asc' | 'desc');
            }}
          >
            <option value="rank:asc">По месту в классе</option>
            <option value="name:asc">По имени</option>
            <option value="xp:desc">По XP всего</option>
            <option value="weekly_xp:desc">По XP за неделю</option>
            <option value="streak:desc">По серии дней</option>
            <option value="pending_count:desc">По числу работ на проверке</option>
          </select>
        </div>

        {all.length === 0 ? (
          <EmptyState
            icon="users"
            title="В классе пока нет учеников"
            text={
              inviteCode
                ? 'Передайте ученикам код приглашения — они появятся здесь после входа.'
                : 'Ученики появятся здесь после подключения к классу.'
            }
          />
        ) : rows.length === 0 ? (
          <EmptyState icon="search" title="Никого не найдено" text="Измените запрос или фильтр." />
        ) : (
          <div className="tc-panel tc-panel--flush">
            <div className="tc-table-wrap">
              <table className="tc-table">
                <caption>Ученики класса {viewer.class_name}</caption>
                <thead>
                  <tr>
                    {sortHead('rank', '№')}
                    {sortHead('name', 'Ученик')}
                    {sortHead('xp', 'XP всего', true)}
                    {sortHead('weekly_xp', 'За неделю', true)}
                    {sortHead('streak', 'Серия', true)}
                    {sortHead('pending_count', 'На проверке', true)}
                    <th scope="col">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => (
                    <tr key={s.id}>
                      <td data-label="Место в классе" className="tc-num">
                        {s.rank}
                      </td>
                      <td className="tc-cell--main">
                        <div className="tc-person">
                          <AvatarFrame avatar={s.avatar} size={36} decorative />
                          <div className="tc-person__text">
                            <button
                              type="button"
                              className="tc-link-btn"
                              onClick={() => openStudent(s)}
                              aria-label={`Открыть карточку ученика: ${s.name}`}
                            >
                              {s.name}
                            </button>
                            <span className="tc-faint">
                              {s.level_title}
                              {s.last_active ? ` · ${s.last_active}` : ''}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td data-label="XP всего" className="tc-r tc-num">
                        {formatNumber(s.xp)}
                      </td>
                      <td data-label="За неделю" className="tc-r tc-num">
                        {s.weekly_xp > 0 ? `+${formatNumber(s.weekly_xp)}` : '0'}
                      </td>
                      <td data-label="Серия, дн." className="tc-r tc-num">
                        {s.streak}
                      </td>
                      <td data-label="На проверке" className="tc-r tc-num">
                        {s.pending_count}
                      </td>
                      <td data-label="Статус">
                        {s.at_risk ? (
                          <span className="tc-badge tc-badge--danger">
                            {s.risk_reasons?.[0] ?? 'Требует внимания'}
                          </span>
                        ) : (
                          <span className="tc-faint">В норме</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {excluded.length > 0 ? (
        <section className="tc-section" aria-label="Исключённые ученики">
          <button
            type="button"
            className="tc-btn tc-btn--ghost tc-excl-toggle"
            aria-expanded={excludedOpen}
            onClick={() => setExcludedOpen((v) => !v)}
          >
            <span>Исключённые: {excluded.length}</span>
            <Icon name={excludedOpen ? 'chevronDown' : 'chevronRight'} size={16} />
          </button>
          {excludedOpen ? (
            <div className="tc-panel">
              <p className="tc-muted" style={{ marginTop: 0 }}>
                После возврата ученик сможет снова вступить в класс по коду или из списка.
              </p>
              <ul className="tc-excl-list">
                {excluded.map((item) => (
                  <li key={item.id} className="tc-excl-item">
                    <div className="tc-excl-item__text">
                      <strong>{item.name}</strong>
                      <span className="tc-faint">
                        {[formatShortDate(item.removed_at), item.reason].filter(Boolean).join(' · ')}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="tc-btn"
                      onClick={() => void startRestore(item.id, item.name)}
                    >
                      Вернуть
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {dialog}

      <Sheet
        open={Boolean(selected)}
        onClose={() => setSelectedId(null)}
        title={selected?.name ?? ''}
        subtitle={selected ? `${selected.level_title} · место в классе: ${selected.rank}` : ''}
      >
        {selected ? (
          <div className="tc-form">
            <dl className="tc-dl">
              <dt>XP всего</dt>
              <dd className="tc-num">{formatNumber(selected.xp)}</dd>
              <dt>За неделю</dt>
              <dd className="tc-num">{formatNumber(selected.weekly_xp)}</dd>
              <dt>Серия</dt>
              <dd className="tc-num">{selected.streak} дн.</dd>
              <dt>На проверке</dt>
              <dd className="tc-num">{selected.pending_count}</dd>
              {selected.approved_count !== undefined ? (
                <>
                  <dt>Принято</dt>
                  <dd className="tc-num">{selected.approved_count}</dd>
                </>
              ) : null}
              {selected.rejected_count !== undefined ? (
                <>
                  <dt>Возвращено</dt>
                  <dd className="tc-num">{selected.rejected_count}</dd>
                </>
              ) : null}
              {selected.last_active ? (
                <>
                  <dt>Активность</dt>
                  <dd>{selected.last_active}</dd>
                </>
              ) : null}
            </dl>

            {selected.at_risk ? (
              <div className="tc-alert tc-alert--danger" role="note">
                <strong>Требует внимания</strong>
                {selected.risk_reasons?.length ? (
                  <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
                    {selected.risk_reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {onRewardStudent ? (
              <form
                className="tc-form"
                noValidate
                onSubmit={(e) => {
                  e.preventDefault();
                  void submitReward();
                }}
                aria-labelledby={`${uid}-reward`}
              >
                <h3 className="tc-h2" id={`${uid}-reward`}>
                  Начислить баллы вручную
                </h3>
                <div className="tc-field">
                  <label className="tc-label" htmlFor={`${uid}-amount`}>
                    Количество XP
                  </label>
                  <input
                    id={`${uid}-amount`}
                    className="tc-input"
                    type="number"
                    inputMode="numeric"
                    min={REWARD_MIN}
                    max={REWARD_MAX}
                    value={amount}
                    onChange={(e) => {
                      setAmount(e.target.value);
                      setRewardErrors((c) => ({ ...c, amount: undefined }));
                      setRewardDone('');
                    }}
                    aria-invalid={Boolean(rewardErrors.amount)}
                    aria-describedby={rewardErrors.amount ? `${uid}-amount-err` : undefined}
                  />
                  {rewardErrors.amount ? (
                    <p className="tc-error" id={`${uid}-amount-err`} role="alert">
                      {rewardErrors.amount}
                    </p>
                  ) : null}
                </div>
                <div className="tc-chips" role="group" aria-label="Готовые причины">
                  {REWARD_REASONS.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className="tc-chip"
                      aria-pressed={reason === r}
                      onClick={() => {
                        setReason(r);
                        setRewardErrors((c) => ({ ...c, reason: undefined }));
                        setRewardDone('');
                      }}
                    >
                      {r}
                    </button>
                  ))}
                </div>
                <div className="tc-field">
                  <label className="tc-label" htmlFor={`${uid}-reason`}>
                    Причина
                  </label>
                  <input
                    id={`${uid}-reason`}
                    className="tc-input"
                    type="text"
                    maxLength={120}
                    value={reason}
                    onChange={(e) => {
                      setReason(e.target.value);
                      setRewardErrors((c) => ({ ...c, reason: undefined }));
                      setRewardDone('');
                    }}
                    aria-invalid={Boolean(rewardErrors.reason)}
                    aria-describedby={rewardErrors.reason ? `${uid}-reason-err` : undefined}
                  />
                  {rewardErrors.reason ? (
                    <p className="tc-error" id={`${uid}-reason-err`} role="alert">
                      {rewardErrors.reason}
                    </p>
                  ) : null}
                </div>
                <button type="submit" className="tc-btn tc-btn--primary" disabled={rewarding}>
                  {rewarding ? 'Начисляем…' : 'Начислить'}
                </button>
                <p className="tc-alert tc-alert--ok" role="status" hidden={!rewardDone}>
                  {rewardDone}
                </p>
              </form>
            ) : null}

            {onRemoveStudent && !selected.is_viewer ? (
              <section className="tc-form tc-remove" aria-labelledby={`${uid}-remove`}>
                <h3 className="tc-h2" id={`${uid}-remove`}>
                  Исключить из класса
                </h3>
                <p className="tc-muted" style={{ margin: 0 }}>
                  Для случайных и посторонних учеников. XP и достижения сохраняются.
                </p>
                <div className="tc-field">
                  <label className="tc-label" htmlFor={`${uid}-remove-reason`}>
                    Причина (необязательно)
                  </label>
                  <input
                    id={`${uid}-remove-reason`}
                    className="tc-input"
                    maxLength={120}
                    value={removeReason}
                    onChange={(e) => setRemoveReason(e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className="tc-btn tc-btn--danger"
                  disabled={removing}
                  onClick={() => void startRemove()}
                >
                  {removing ? 'Исключаем…' : 'Исключить из класса'}
                </button>
              </section>
            ) : null}

            {selected.subject_stats && selected.subject_stats.length > 0 ? (
              <section>
                <h3 className="tc-h2" style={{ marginBottom: 8 }}>
                  По предметам
                </h3>
                <ul className="tc-muted" style={{ margin: 0, paddingLeft: 20 }}>
                  {selected.subject_stats.map((s) => (
                    <li key={s.subject}>
                      {s.subject}: {s.count} {s.count === 1 ? 'работа' : 'работ'}, {formatNumber(s.xp)} XP
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section>
              <h3 className="tc-h2" style={{ marginBottom: 8 }}>
                Последние работы
              </h3>
              {selected.recent_works && selected.recent_works.length > 0 ? (
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 8 }}>
                  {selected.recent_works.map((w) => (
                    <li key={w.id} className="tc-panel" style={{ padding: 12 }}>
                      <div className="tc-toolbar">
                        <strong style={{ flex: '1 1 160px', overflowWrap: 'anywhere' }}>{w.title}</strong>
                        <span
                          className={`tc-badge ${
                            w.status === 'approved'
                              ? 'tc-badge--ok'
                              : w.status === 'pending'
                                ? 'tc-badge--warn'
                                : w.status === 'rejected'
                                  ? 'tc-badge--danger'
                                  : ''
                          }`}
                        >
                          {STATUS_LABEL[w.status]}
                        </span>
                      </div>
                      <div className="tc-faint">
                        {[w.subject, `${w.xp} XP`, formatRelative(w.date)].filter(Boolean).join(' · ')}
                      </div>
                      {w.reject_reason ? (
                        <div className="tc-muted">Причина возврата: {w.reject_reason}</div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="tc-muted" style={{ margin: 0 }}>
                  Работ пока нет.
                </p>
              )}
            </section>
          </div>
        ) : null}
      </Sheet>

      <PrintSheet>
        <h1 className="pr-title">Отчёт по классу {viewer.class_name}</h1>
        <ul className="pr-meta">
          {viewer.school_name ? <li>Школа: {viewer.school_name}</li> : null}
          {viewer.city ? <li>Город: {viewer.city}</li> : null}
          <li>Период: {periodText}</li>
          <li>Дата формирования: {formatPrintDate()}</li>
          <li>
            Учеников: {teacher.stats.students}, активны на неделе: {teacher.stats.active_week}, XP класса за неделю:{' '}
            {formatNumber(teacher.stats.weekly_xp)}
          </li>
        </ul>

        <h2 className="pr-h2">Ученики</h2>
        <table className="pr-table">
          <thead>
            <tr>
              <th scope="col" className="pr-r">
                №
              </th>
              <th scope="col">Ученик</th>
              <th scope="col">Уровень</th>
              <th scope="col" className="pr-r">
                XP за неделю
              </th>
              <th scope="col" className="pr-r">
                Серия, дн.
              </th>
            </tr>
          </thead>
          <tbody>
            {printStudents.map((s) => (
              <tr key={s.id}>
                <td className="pr-r">{s.rank}</td>
                <td>{s.name}</td>
                <td>
                  {s.level}
                  {s.level_title ? ` · ${s.level_title}` : ''}
                </td>
                <td className="pr-r">{formatNumber(s.weekly_xp)}</td>
                <td className="pr-r">{s.streak}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {doneWorks.length > 0 ? (
          <>
            <h2 className="pr-h2">Выполненные задания</h2>
            <table className="pr-table">
              <thead>
                <tr>
                  <th scope="col">Дата</th>
                  <th scope="col">Ученик</th>
                  <th scope="col">Задание</th>
                  <th scope="col" className="pr-r">
                    XP
                  </th>
                </tr>
              </thead>
              <tbody>
                {doneWorks.map((w) => (
                  <tr key={`${w.student}-${w.id}`}>
                    <td>{formatShortDate(w.date)}</td>
                    <td>{w.student}</td>
                    <td>{w.title}</td>
                    <td className="pr-r">{w.xp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}

        <div className="pr-sign">
          <div className="pr-sign__field">Педагог (подпись, расшифровка)</div>
          <div className="pr-sign__field pr-sign__field--date">Дата</div>
        </div>
      </PrintSheet>
    </div>
  );
}
