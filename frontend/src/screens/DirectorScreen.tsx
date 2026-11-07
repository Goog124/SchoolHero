import { useId, useMemo, useState } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { DirectorKpiInfo, SocialIndexInfo } from '../components/infoTexts';
import { ScreenTitle } from '../components/ScreenTitle';
import { formatNumber, plural } from '../game';
import type { ClassEntry, DirectorData, GameState } from '../types';
import { PrintHint, PrintSheet, formatPrintDate, printDocument } from '../components/PrintReport';
import '../styles/teacher.css';

type DirectorTab = 'summary' | 'classes' | 'directions';
/** Раздел нижнего меню: «Школа» (сводка, параллели, направления) или «Классы» (сравнение классов). */
export type DirectorSection = 'school' | 'classes';
type ClassSort = 'rank' | 'name' | 'members' | 'xp' | 'weekly_xp' | 'progress';

// Внутренние вкладки раздела «Школа». Сравнение классов — отдельный раздел меню.
const TABS: { id: DirectorTab; label: string }[] = [
  { id: 'summary', label: 'Параллели' },
  { id: 'directions', label: 'Направления' },
];

const LOW_ENGAGEMENT = 40;

type DirectorScreenProps = {
  state: GameState;
  director: DirectorData;
  section?: DirectorSection;
};

function formatReportDate(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

export function DirectorScreen({ state, director, section = 'school' }: DirectorScreenProps) {
  const uid = useId();
  const { viewer } = state;
  const { kpi, grades, directions } = director;
  // director.classes приходит с сервера полным: members, xp, weekly_xp, goal, rank, progress
  // посчитаны по классам этой школы (XP, заработанный в классе).
  const classes = useMemo<ClassEntry[]>(() => director.classes ?? [], [director.classes]);
  const goalPercent = (c: ClassEntry) => (c.goal > 0 ? Math.round((c.weekly_xp / c.goal) * 100) : null);
  const [innerTab, setTab] = useState<DirectorTab>('summary');
  const tab: DirectorTab = section === 'classes' ? 'classes' : innerTab;
  const [sortKey, setSortKey] = useState<ClassSort>('rank');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [copied, setCopied] = useState(false);

  const directionRows = useMemo(
    () => Object.entries(directions ?? {}).map(([key, value]) => ({ key, ...value })),
    [directions],
  );
  const directionTotal = directionRows.reduce((sum, d) => sum + d.count, 0);
  const directionMax = Math.max(1, ...directionRows.map((d) => d.count));

  const classRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...classes].sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name, 'ru', { numeric: true }) * dir;
      return (a[sortKey] - b[sortKey]) * dir;
    });
  }, [classes, sortKey, sortDir]);

  const classRowsByName = useMemo(
    () => [...classes].sort((a, b) => a.name.localeCompare(b.name, 'ru', { numeric: true })),
    [classes],
  );

  const maxWeekly = Math.max(1, ...classes.map((c) => c.weekly_xp));

  const changeSort = (key: ClassSort) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'rank' || key === 'name' ? 'asc' : 'desc');
    }
  };

  const sortHead = (k: ClassSort, label: string, right?: boolean) => (
    <th
      key={k}
      scope="col"
      className={right ? 'tc-r' : undefined}
      aria-sort={k === sortKey ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button type="button" className="tc-sort" data-active={k === sortKey} onClick={() => changeSort(k)}>
        {label}
        {k === sortKey ? <Icon name={sortDir === 'asc' ? 'arrowUp' : 'arrowDown'} size={12} /> : null}
      </button>
    </th>
  );

  const copyReport = async () => {
    const lines = [
      `Справка об активности обучающихся`,
      `Организация: ${[viewer.school_name, viewer.city].filter(Boolean).join(', ')}`,
      director.report_generated_at ? `Данные на: ${formatReportDate(director.report_generated_at)}` : '',
      '',
      'Показатели',
      `- Активны за неделю: ${kpi.active_students_week} из ${kpi.total_students} (${kpi.engagement_rate}%)`,
      `- Классов: ${kpi.total_classes}`,
      `- XP за неделю: ${formatNumber(kpi.total_weekly_xp)}, всего: ${formatNumber(kpi.total_school_xp)}`,
      kpi.completed_fop_tasks !== undefined ? `- Подтверждено заданий: ${kpi.completed_fop_tasks}` : '',
      '',
      'Параллели',
      ...grades.map(
        (g) =>
          `- ${g.label}: классов ${g.classes_count}, учеников ${g.students_count}, активных ${g.active_students} (${g.engagement}%), XP за неделю ${formatNumber(g.weekly_xp)}`,
      ),
      '',
      'Направления',
      ...directionRows.map((d) => `- ${d.label}: ${d.count} работ, ${formatNumber(d.xp)} XP`),
    ].filter((line, i, arr) => !(line === '' && arr[i - 1] === ''));
    try {
      await navigator.clipboard?.writeText(lines.join('\n'));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      // буфер недоступен
    }
  };

  const generated = formatReportDate(director.report_generated_at);
  const subtitle = [[viewer.school_name, viewer.city].filter(Boolean).join(' · '), generated && `данные на ${generated}`]
    .filter(Boolean)
    .join(' · ');

  const classMeta = (c: ClassEntry) => (c.is_viewer_class ? <span className="tc-badge">ваш класс</span> : null);

  return (
    <div className="screen tc-page">
      <ScreenTitle
        title={section === 'classes' ? 'Классы' : 'Школа'}
        subtitle={subtitle}
        action={
          <div className="tc-toolbar">
            <button type="button" className="tc-btn" onClick={() => void copyReport()}>
              <Icon name={copied ? 'check' : 'share'} size={16} />
              {copied ? 'Скопировано' : 'Копировать справку'}
            </button>
            <button type="button" className="tc-btn" onClick={printDocument}>
              <Icon name="book" size={16} />
              Печать
            </button>
          </div>
        }
      />
      <PrintHint />

      {section === 'school' ? (
      <div className="tc-stats">
        <div className="tc-stat">
          <span className="tc-stat__label">
            Активны за{' '}
            <span className="info-nw">
              неделю
              <InfoButton title="Показатели сводки">
                <DirectorKpiInfo />
              </InfoButton>
            </span>
          </span>
          <span className="tc-stat__value">{kpi.engagement_rate}%</span>
          <span className="tc-stat__hint">
            {kpi.active_students_week} из {kpi.total_students} учеников
          </span>
        </div>
        <div className="tc-stat">
          <span className="tc-stat__label">Классов</span>
          <span className="tc-stat__value">{kpi.total_classes}</span>
          <span className="tc-stat__hint">
            {kpi.total_students} {plural(kpi.total_students, 'ученик', 'ученика', 'учеников')}
          </span>
        </div>
        <div className="tc-stat">
          <span className="tc-stat__label">XP за неделю</span>
          <span className="tc-stat__value">{formatNumber(kpi.total_weekly_xp)}</span>
          <span className="tc-stat__hint">всего: {formatNumber(kpi.total_school_xp)}</span>
        </div>
        {kpi.completed_fop_tasks !== undefined ? (
          <div className="tc-stat">
            <span className="tc-stat__label">
              Подтверждено{' '}
              <span className="info-nw">
                заданий
                {kpi.social_activity_index !== undefined ? (
                  <InfoButton title="Индекс социальной активности">
                    <SocialIndexInfo />
                  </InfoButton>
                ) : null}
              </span>
            </span>
            <span className="tc-stat__value">{formatNumber(kpi.completed_fop_tasks)}</span>
            {kpi.social_activity_index !== undefined ? (
              <span className="tc-stat__hint">индекс соц. активности: {kpi.social_activity_index}</span>
            ) : null}
          </div>
        ) : kpi.leading_grade ? (
          <div className="tc-stat">
            <span className="tc-stat__label">Самая активная параллель</span>
            <span className="tc-stat__value">{kpi.leading_grade}</span>
          </div>
        ) : null}
      </div>
      ) : null}

      {section === 'school' ? (
      <div className="tc-tabs" role="tablist" aria-label="Разделы">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`${uid}-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`${uid}-panel`}
            tabIndex={tab === t.id ? 0 : -1}
            className="tc-tab"
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
              const i = TABS.findIndex((x) => x.id === tab);
              const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length];
              setTab(next.id);
              document.getElementById(`${uid}-tab-${next.id}`)?.focus();
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      ) : null}

      <div
        role={section === 'school' ? 'tabpanel' : undefined}
        id={`${uid}-panel`}
        aria-labelledby={section === 'school' ? `${uid}-tab-${tab}` : undefined}
        className="tc-section"
      >
        {tab === 'summary' ? (
          grades.length > 0 ? (
            <div className="tc-panel tc-panel--flush">
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <caption>Параллели</caption>
                  <thead>
                    <tr>
                      <th scope="col">Параллель</th>
                      <th scope="col" className="tc-r">
                        Классов
                      </th>
                      <th scope="col" className="tc-r">
                        Учеников
                      </th>
                      <th scope="col" className="tc-r">
                        Активных
                      </th>
                      <th scope="col">Вовлечённость</th>
                      <th scope="col" className="tc-r">
                        XP за неделю
                      </th>
                      <th scope="col" className="tc-r">
                        XP на ученика
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {grades.map((g) => (
                      <tr key={g.grade}>
                        <td className="tc-cell--main">
                          <strong>{g.label}</strong>
                          {g.students_count > 0 && g.engagement < LOW_ENGAGEMENT ? (
                            <>
                              {' '}
                              <span className="tc-badge tc-badge--warn">низкая вовлечённость</span>
                            </>
                          ) : null}
                        </td>
                        <td data-label="Классов" className="tc-r tc-num">
                          {g.classes_count}
                        </td>
                        <td data-label="Учеников" className="tc-r tc-num">
                          {g.students_count}
                        </td>
                        <td data-label="Активных" className="tc-r tc-num">
                          {g.active_students}
                        </td>
                        <td data-label="Вовлечённость">
                          <div className="tc-meter-row" style={{ minWidth: 140 }}>
                            <span className="tc-num">{g.engagement}%</span>
                            <div
                              className="tc-meter"
                              role="progressbar"
                              aria-label={`Вовлечённость, ${g.label}`}
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-valuenow={g.engagement}
                            >
                              <div
                                className="tc-meter__fill"
                                style={{ width: `${Math.min(100, Math.max(0, g.engagement))}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td data-label="XP за неделю" className="tc-r tc-num">
                          {formatNumber(g.weekly_xp)}
                        </td>
                        <td data-label="XP на ученика" className="tc-r tc-num">
                          {formatNumber(g.avg_student_xp)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <EmptyState icon="chart" title="Нет данных по параллелям" text="Данные появятся, когда в школе будут классы с учениками." />
          )
        ) : null}

        {tab === 'classes' ? (
          classRows.length > 0 ? (
            <div className="tc-panel tc-panel--flush">
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <caption>Сравнение классов</caption>
                  <thead>
                    <tr>
                      {sortHead('rank', '№')}
                      {sortHead('name', 'Класс')}
                      {sortHead('members', 'Учеников', true)}
                      {sortHead('xp', 'XP всего', true)}
                      {sortHead('weekly_xp', 'За неделю', true)}
                      {sortHead('progress', 'Цель недели')}
                    </tr>
                  </thead>
                  <tbody>
                    {classRows.map((c) => (
                      <tr key={c.id}>
                        <td data-label="Место" className="tc-num">
                          {c.rank}
                        </td>
                        <td className="tc-cell--main">
                          <strong>{c.name}</strong> {classMeta(c)}
                        </td>
                        <td data-label="Учеников" className="tc-r tc-num">
                          {c.members}
                        </td>
                        <td data-label="XP всего" className="tc-r tc-num">
                          {formatNumber(c.xp)}
                        </td>
                        <td data-label="За неделю" className="tc-r tc-num">
                          <div className="tc-meter-row" style={{ minWidth: 96 }}>
                            <span>{formatNumber(c.weekly_xp)}</span>
                            <div className="tc-meter" aria-hidden="true">
                              <div
                                className="tc-meter__fill"
                                style={{ width: `${Math.round((c.weekly_xp / maxWeekly) * 100)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td data-label="Цель недели">
                          {c.goal > 0 ? (
                            <span className="tc-num">
                              {goalPercent(c)}% из {formatNumber(c.goal)} XP
                            </span>
                          ) : (
                            <span className="tc-faint">не задана</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <EmptyState icon="users" title="Классов нет" text="В школе пока нет классов с учениками." />
          )
        ) : null}

        {tab === 'directions' ? (
          directionRows.length > 0 ? (
            <div className="tc-panel">
              <div className="tc-section" style={{ gap: 16 }}>
                {directionRows.map((d) => (
                  <div className="tc-meter-row" key={d.key}>
                    <div className="tc-meter-row__head">
                      <strong>{d.label}</strong>
                      <span className="tc-num">
                        {d.count} {plural(d.count, 'работа', 'работы', 'работ')} · {formatNumber(d.xp)} XP
                        {directionTotal > 0 ? ` · ${Math.round((d.count / directionTotal) * 100)}%` : ''}
                      </span>
                    </div>
                    <div
                      className="tc-meter"
                      role="progressbar"
                      aria-label={d.label}
                      aria-valuemin={0}
                      aria-valuemax={directionMax}
                      aria-valuenow={d.count}
                    >
                      <div className="tc-meter__fill" style={{ width: `${Math.round((d.count / directionMax) * 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState icon="chart" title="Нет данных по направлениям" text="Данные появятся после первых подтверждённых работ." />
          )
        ) : null}
      </div>

      <PrintSheet>
        <h1 className="pr-title">Справка по школе</h1>
        <ul className="pr-meta">
          {viewer.school_name ? <li>Школа: {viewer.school_name}</li> : null}
          {viewer.city ? <li>Город: {viewer.city}</li> : null}
          <li>Период: текущая учебная неделя (показатели «за неделю»)</li>
          {generated ? <li>Данные на: {generated}</li> : null}
          <li>Дата формирования: {formatPrintDate()}</li>
        </ul>

        <h2 className="pr-h2">Сводные показатели</h2>
        <table className="pr-kpi">
          <tbody>
            <tr>
              <th scope="row">Учеников</th>
              <td>{kpi.total_students}</td>
            </tr>
            <tr>
              <th scope="row">Классов</th>
              <td>{kpi.total_classes}</td>
            </tr>
            <tr>
              <th scope="row">Активных за неделю</th>
              <td>
                {kpi.active_students_week} ({kpi.engagement_rate}%)
              </td>
            </tr>
            <tr>
              <th scope="row">XP за неделю</th>
              <td>{formatNumber(kpi.total_weekly_xp)}</td>
            </tr>
            <tr>
              <th scope="row">XP за всё время</th>
              <td>{formatNumber(kpi.total_school_xp)}</td>
            </tr>
            {kpi.completed_fop_tasks !== undefined ? (
              <tr>
                <th scope="row">Подтверждено заданий</th>
                <td>{formatNumber(kpi.completed_fop_tasks)}</td>
              </tr>
            ) : null}
          </tbody>
        </table>

        {classRowsByName.length > 0 ? (
          <>
            <h2 className="pr-h2">Показатели по классам</h2>
            <table className="pr-table">
              <thead>
                <tr>
                  <th scope="col">Класс</th>
                  <th scope="col" className="pr-r">
                    Учеников
                  </th>
                  <th scope="col" className="pr-r">
                    XP за неделю
                  </th>
                  <th scope="col" className="pr-r">
                    XP всего
                  </th>
                  <th scope="col" className="pr-r">
                    Выполнение цели недели
                  </th>
                </tr>
              </thead>
              <tbody>
                {classRowsByName.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="pr-r">{c.members}</td>
                    <td className="pr-r">{formatNumber(c.weekly_xp)}</td>
                    <td className="pr-r">{formatNumber(c.xp)}</td>
                    <td className="pr-r">
                      {c.goal > 0 ? `${goalPercent(c)}% (цель ${formatNumber(c.goal)} XP)` : 'цель не задана'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}

        {directionRows.length > 0 ? (
          <>
            <h2 className="pr-h2">Направления</h2>
            <table className="pr-table">
              <thead>
                <tr>
                  <th scope="col">Направление</th>
                  <th scope="col" className="pr-r">
                    Работ
                  </th>
                  <th scope="col" className="pr-r">
                    XP
                  </th>
                </tr>
              </thead>
              <tbody>
                {directionRows.map((d) => (
                  <tr key={d.key}>
                    <td>{d.label}</td>
                    <td className="pr-r">{d.count}</td>
                    <td className="pr-r">{formatNumber(d.xp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </PrintSheet>
    </div>
  );
}
