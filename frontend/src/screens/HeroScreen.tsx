import { useMemo, useState } from 'react';
import '../styles/student.css';
import type { GameState, TabId } from '../types';
import { AvatarFrame } from '../components/AvatarFrame';
import { ChallengeCard } from '../components/ChallengeCard';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { ClassGoalInfo, LevelInfo, PlaceInfo, StreakInfo } from '../components/infoTexts';
import { ProgressBar } from '../components/ProgressBar';
import { StatTile } from '../components/StatTile';
import { formatLongDate, formatNumber, formatRelative, greeting, plural } from '../game';

type HeroScreenProps = {
  state: GameState;
  onOpenChallenge: (id: number) => void;
  onNavigate: (tab: TabId) => void;
  /** Не используется: кнопки «Поделиться» на экране нет. */
  onShare?: () => void;
};

const TASKS_LIMIT = 3;

export function HeroScreen({ state, onOpenChallenge, onNavigate }: HeroScreenProps) {
  const { viewer, class_sprint: sprint, challenges, week, feed, leaderboard } = state;
  const [showAll, setShowAll] = useState(false);

  // Сначала то, что нужно исправить, затем доступные задания.
  const nextTasks = useMemo(() => {
    const rejected = challenges.filter((c) => c.status === 'rejected');
    const available = challenges.filter((c) => c.status === 'available');
    return [...rejected, ...available].slice(0, TASKS_LIMIT);
  }, [challenges]);

  const contributors = useMemo(
    () =>
      [...leaderboard.students].sort((a, b) => b.weekly_xp - a.weekly_xp || b.xp - a.xp),
    [leaderboard.students],
  );
  const shownContributors = showAll ? contributors : contributors.slice(0, 3);

  const level = viewer.level;
  const classLine = [viewer.class_name, viewer.school_name].filter(Boolean).join(' · ');
  const hasSprint = Boolean(sprint && sprint.goal > 0);

  return (
    <div className="st-page">
      <header className="st-head">
        <h1>
          {greeting()}, {viewer.first_name}
        </h1>
        <p>{formatLongDate()}</p>
      </header>

      <div className="st-stats st-stats--4">
        <StatTile
          label="Место в классе"
          info={
            <InfoButton title="Место в классе">
              <PlaceInfo />
            </InfoButton>
          }
          value={viewer.personal_rank > 0 ? `${viewer.personal_rank}` : '—'}
          hint={
            leaderboard.students.length
              ? `из ${leaderboard.students.length}`
              : undefined
          }
        />
        <StatTile
          label="Серия"
          info={
            <InfoButton title="Серия дней">
              <StreakInfo />
            </InfoButton>
          }
          value={`${viewer.streak} ${plural(viewer.streak, 'день', 'дня', 'дней')}`}
        />
        <StatTile label="Принято" value={viewer.stats.confirmed} hint="заданий" />
        <StatTile label="На проверке" value={viewer.stats.pending} hint="заданий" />
      </div>

      <div className="st-grid st-grid--2">
        <div className="st-col">
          <section className="st-card" aria-labelledby="st-profile-title">
            <div className="st-profile">
              <button
                type="button"
                className="st-profile__avatar"
                onClick={() => onNavigate('wardrobe')}
                aria-label="Изменить внешний вид героя"
              >
                <AvatarFrame avatar={viewer.avatar} size={80} level={level.level} />
              </button>
              <div className="st-profile__info">
                <h2 className="st-profile__name" id="st-profile-title">
                  {viewer.name}
                </h2>
                {classLine ? <p className="st-profile__meta">{classLine}</p> : null}
                <p className="st-profile__meta">
                  Уровень {level.level} ·{' '}
                  <span className="info-nw">
                    {level.title}
                    <InfoButton title="XP и уровень">
                      <LevelInfo />
                    </InfoButton>
                  </span>
                </p>
              </div>
            </div>

            <div className="st-level">
              <div className="st-level__row">
                <span>
                  <strong>{formatNumber(viewer.xp)} XP</strong> всего
                </span>
                {level.is_max ? (
                  <span className="st-muted">Максимальный уровень</span>
                ) : (
                  <span className="st-muted">
                    {formatNumber(level.xp_in_level)} / {formatNumber(level.xp_for_level)} XP
                  </span>
                )}
              </div>
              <ProgressBar
                value={level.xp_in_level}
                max={level.xp_for_level || 1}
                height={8}
                label="Прогресс до следующего уровня"
              />
              {!level.is_max ? (
                <p className="st-level__note">
                  До следующего уровня: {formatNumber(viewer.to_next)} XP
                </p>
              ) : null}
            </div>
          </section>

          <section aria-labelledby="st-next-title">
            <div className="st-card__head">
              <h2 className="st-h2" id="st-next-title">
                Что сделать
              </h2>
              <button type="button" className="st-link" onClick={() => onNavigate('challenges')}>
                Все задания
                <Icon name="chevronRight" size={14} />
              </button>
            </div>
            {nextTasks.length ? (
              <div className="st-list">
                {nextTasks.map((challenge) => (
                  <ChallengeCard
                    key={challenge.id}
                    challenge={challenge}
                    onOpen={onOpenChallenge}
                    compact
                  />
                ))}
              </div>
            ) : (
              <div className="st-empty">
                <h3>Новых заданий нет</h3>
                <p>Когда учитель добавит задания, они появятся здесь.</p>
              </div>
            )}
          </section>
        </div>

        <div className="st-col">
          {hasSprint ? (
            <section className="st-card" aria-labelledby="st-sprint-title">
              <div className="st-card__head">
                <h2 className="st-h2" id="st-sprint-title">
                  Цель класса на{' '}
                  <span className="info-nw">
                    неделю
                    <InfoButton title="Цель класса на неделю">
                      <ClassGoalInfo />
                    </InfoButton>
                  </span>
                </h2>
                {sprint.rank > 0 ? (
                  <span className="st-muted">{sprint.rank} место среди классов</span>
                ) : null}
              </div>
              <div className="st-level__row">
                <strong>{formatNumber(sprint.xp)} XP</strong>
                <span className="st-muted">цель {formatNumber(sprint.goal)} XP</span>
              </div>
              <ProgressBar
                value={sprint.xp}
                max={sprint.goal}
                height={8}
                label="Прогресс класса к цели недели"
              />
              <p className="st-level__note">
                {sprint.xp >= sprint.goal
                  ? 'Цель недели достигнута'
                  : `Осталось ${formatNumber(sprint.goal - sprint.xp)} XP`}
              </p>

              {contributors.length ? (
                <div className="st-level">
                  <div className="st-level__row">
                    <h3 className="st-h2" style={{ fontSize: 15 }}>
                      Вклад за неделю
                    </h3>
                    {contributors.length > 3 ? (
                      <button
                        type="button"
                        className="st-link"
                        onClick={() => setShowAll((prev) => !prev)}
                        aria-expanded={showAll}
                      >
                        {showAll ? 'Свернуть' : 'Показать всех'}
                      </button>
                    ) : null}
                  </div>
                  <ol className="st-rows">
                    {shownContributors.map((c, idx) => (
                      <li key={c.id} className="st-row">
                        <span className="st-row__rank">{idx + 1}</span>
                        <AvatarFrame avatar={c.avatar} size={32} decorative />
                        <span className="st-row__main">
                          <span className="st-row__name">
                            {c.name}
                            {c.id === viewer.id ? ' (вы)' : ''}
                          </span>
                        </span>
                        <span className="st-row__val">+{formatNumber(c.weekly_xp)} XP</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
            </section>
          ) : null}

          {week.length ? (
            <section className="st-card" aria-labelledby="st-week-title">
              <div className="st-card__head">
                <h2 className="st-h2" id="st-week-title">
                  Неделя
                </h2>
                <span className="st-muted">
                  Серия: {viewer.streak} {plural(viewer.streak, 'день', 'дня', 'дней')}
                </span>
              </div>
              <ul className="st-week">
                {week.map((day) => (
                  <li
                    key={day.date}
                    className={`st-day${day.active ? ' st-day--active' : ''}${
                      day.is_today ? ' st-day--today' : ''
                    }${day.is_future ? ' st-day--future' : ''}`}
                    aria-label={`${day.label}: ${day.active ? 'есть активность' : 'нет активности'}`}
                  >
                    <span>{day.label}</span>
                    <span aria-hidden="true">{day.active ? <Icon name="check" size={14} /> : '·'}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="st-card" aria-labelledby="st-feed-title">
            <h2 className="st-h2" id="st-feed-title" style={{ marginBottom: 8 }}>
              События класса
            </h2>
            {feed.length ? (
              <ul className="st-rows">
                {feed.slice(0, 6).map((item) => (
                  <li key={item.id} className="st-row">
                    <AvatarFrame avatar={item.avatar} size={32} decorative />
                    <span className="st-row__main">
                      <span className="st-row__name">{item.name}</span>
                      <span className="st-row__sub">
                        {item.reason}
                        {item.created_at ? ` · ${formatRelative(item.created_at)}` : ''}
                      </span>
                    </span>
                    <span className="st-row__val">+{formatNumber(item.amount)} XP</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="st-empty st-empty--inline">
                <p>Пока нет событий. Здесь появятся принятые работы класса.</p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
