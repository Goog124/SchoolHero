import { useMemo, useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Chip } from '../components/Chip';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ProgressBar } from '../components/ProgressBar';
import { ScreenTitle } from '../components/ScreenTitle';
import { Sheet } from '../components/Sheet';
import { formatNumber } from '../game';
import type { GameState, TeacherStudent } from '../types';

type TeacherClassScreenProps = {
  state: GameState;
  onReview: () => void;
};

export function TeacherClassScreen({ state, onReview }: TeacherClassScreenProps) {
  const { viewer, teacher } = state;
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<TeacherStudent | null>(null);
  const classStudents = teacher?.students ?? [];

  const students = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return classStudents;
    return classStudents.filter((student) =>
      student.name.toLowerCase().includes(normalized),
    );
  }, [classStudents, query]);

  if (!teacher) {
    return (
      <div className="screen">
        <EmptyState
          icon="shield"
          title="Кабинет педагога недоступен"
          text="Вернись в профиль и включи демо-режим педагога."
        />
      </div>
    );
  }

  const maxXp = Math.max(1, ...teacher.chart.map((item) => item.xp));
  const totalWeek = teacher.chart.reduce((sum, item) => sum + item.xp, 0);

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Кабинет педагога"
        title={`Класс ${viewer.class_name}`}
        subtitle={`${viewer.school_name} · ${viewer.city}`}
        action={
          <Chip icon="shield" tone="lime" size="sm">
            педагог
          </Chip>
        }
      />

      <section className="teacher-banner">
        <div className="teacher-banner__main">
          <span className="panel-eyebrow">Спринт недели</span>
          <h2>
            {formatNumber(teacher.stats.weekly_xp)} <span>XP</span>
          </h2>
          <p>
            из цели {formatNumber(state.class_sprint.goal)} XP · {state.class_sprint.percent}%
          </p>
          <ProgressBar
            value={teacher.stats.weekly_xp}
            max={state.class_sprint.goal}
            tone="cyan"
            height={10}
          />
        </div>
        <div className="teacher-banner__rank">
          <span>место</span>
          <strong>#{state.class_sprint.rank}</strong>
          <small>среди классов</small>
        </div>
      </section>

      <div className="stat-grid">
        <div className="stat-tile stat-tile--violet">
          <span className="stat-tile__icon">
            <Icon name="users" size={16} />
          </span>
          <span className="stat-tile__value">{teacher.stats.students}</span>
          <span className="stat-tile__label">учеников</span>
          <span className="stat-tile__hint">{teacher.stats.active_week} активны на неделе</span>
        </div>
        <button type="button" className="stat-tile stat-tile--gold stat-tile--button" onClick={onReview}>
          <span className="stat-tile__icon">
            <Icon name="clock" size={16} />
          </span>
          <span className="stat-tile__value">{teacher.stats.pending}</span>
          <span className="stat-tile__label">на проверке</span>
          <span className="stat-tile__hint">открыть работы</span>
        </button>
        <div className="stat-tile stat-tile--cyan">
          <span className="stat-tile__icon">
            <Icon name="star" size={16} />
          </span>
          <span className="stat-tile__value">{teacher.stats.avg_level}</span>
          <span className="stat-tile__label">средний уровень</span>
          <span className="stat-tile__hint">{formatNumber(teacher.stats.avg_weekly_xp)} XP в неделю</span>
        </div>
        <div className={`stat-tile ${teacher.stats.at_risk ? 'stat-tile--red' : 'stat-tile--lime'}`}>
          <span className="stat-tile__icon">
            <Icon name="alert" size={16} />
          </span>
          <span className="stat-tile__value">{teacher.stats.at_risk}</span>
          <span className="stat-tile__label">без активности</span>
          <span className="stat-tile__hint">3+ дня без заданий</span>
        </div>
      </div>

      <section className="panel chart-panel">
        <div className="panel-head">
          <div>
            <span className="panel-eyebrow">Активность класса</span>
            <h2>{formatNumber(totalWeek)} XP за неделю</h2>
          </div>
          <Chip icon="calendar" size="sm">
            Пн–Вс
          </Chip>
        </div>
        <div className="activity-chart">
          {teacher.chart.map((item) => (
            <div key={item.date} className="activity-chart__col">
              <span className="activity-chart__value">{item.xp ? item.xp : ''}</span>
              <span className="activity-chart__track">
                <span
                  className="activity-chart__bar"
                  style={{ height: `${Math.max(4, Math.round((item.xp / maxXp) * 100))}%` }}
                >
                  <span />
                </span>
              </span>
              <span className="activity-chart__label">{item.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Ученики</h2>
            <p>Нажми на ученика, чтобы увидеть детали</p>
          </div>
          <Chip icon="chart" size="sm">
            по XP
          </Chip>
        </div>

        <div className="search-field">
          <Icon name="search" size={17} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти ученика"
            aria-label="Поиск ученика"
          />
          {query ? (
            <button type="button" onClick={() => setQuery('')} aria-label="Очистить поиск">
              <Icon name="x" size={15} />
            </button>
          ) : null}
        </div>

        <div className="panel student-list">
          {students.length ? (
            students.map((student) => (
              <button
                key={student.id}
                type="button"
                className={`student-row ${student.at_risk ? 'is-risk' : ''}`.trim()}
                onClick={() => setSelected(student)}
              >
                <span className={`student-row__rank ${student.rank <= 3 ? 'is-top' : ''}`.trim()}>
                  {student.rank}
                </span>
                <AvatarFrame avatar={student.avatar} size={38} decorative />
                <span className="student-row__info">
                  <span className="student-row__name">
                    {student.name}
                    {student.is_viewer ? <span className="you-tag">ты</span> : null}
                  </span>
                  <span className="student-row__meta">
                    {student.level_title} · {student.last_active.toLowerCase()}
                    {student.at_risk ? ' · нужен контакт' : ''}
                  </span>
                </span>
                <span className="student-row__xp">
                  <strong>{formatNumber(student.weekly_xp)}</strong>
                  <small>XP нед.</small>
                </span>
                {student.pending_count ? (
                  <span className="student-row__pending" title="Работы на проверке">
                    {student.pending_count}
                  </span>
                ) : null}
              </button>
            ))
          ) : (
            <EmptyState
              icon="search"
              title="Ученик не найден"
              text="Попробуй другое имя или очисти поиск."
              compact
            />
          )}
        </div>
      </section>

      {teacher.pending.length ? (
        <button type="button" className="review-cta" onClick={onReview}>
          <span className="review-cta__count">{teacher.pending.length}</span>
          <span className="review-cta__text">
            <strong>Работы ждут проверки</strong>
            <span>Подтверди достижения в один тап</span>
          </span>
          <Icon name="chevronRight" size={20} />
        </button>
      ) : null}

      <Sheet
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected?.name}
        subtitle={selected ? `${selected.level_title} · ${selected.last_active}` : ''}
        footer={
          selected && selected.pending_count ? (
            <button
              type="button"
              className="btn btn--block"
              onClick={() => {
                setSelected(null);
                onReview();
              }}
            >
              Проверить работы ({selected.pending_count})
              <Icon name="chevronRight" size={16} />
            </button>
          ) : undefined
        }
      >
        {selected ? (
          <div className="student-sheet">
            <div className="student-sheet__head">
              <AvatarFrame
                avatar={selected.avatar}
                size={100}
                level={selected.level}
                animate
              />
              <div>
                <h3>{selected.name}</h3>
                <Chip icon="star" tone="violet" size="sm">
                  {selected.level_title}
                </Chip>
                <p>
                  {selected.pending_count
                    ? `${selected.pending_count} работ ждёт вашей проверки`
                    : 'Нет работ на проверке'}
                </p>
              </div>
            </div>
            <div className="student-sheet__stats">
              <div>
                <span>Всего XP</span>
                <strong>{formatNumber(selected.xp)}</strong>
              </div>
              <div>
                <span>За неделю</span>
                <strong>{formatNumber(selected.weekly_xp)}</strong>
              </div>
              <div>
                <span>Серия</span>
                <strong>{selected.streak} дн.</strong>
              </div>
              <div>
                <span>Место</span>
                <strong>#{selected.rank}</strong>
              </div>
            </div>
            {selected.at_risk ? (
              <div className="status-panel status-panel--rejected">
                <span className="status-panel__icon">
                  <Icon name="alert" size={20} />
                </span>
                <div>
                  <strong>Нужен контакт</strong>
                  <p>Ученик не проявлял активности 3 дня или больше. Стоит напомнить о заданиях.</p>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
