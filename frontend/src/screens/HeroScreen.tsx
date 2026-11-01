import type { IconName } from '../components/Icon';
import type { GameState, TabId } from '../types';
import { AvatarFrame } from '../components/AvatarFrame';
import { ChallengeCard } from '../components/ChallengeCard';
import { Chip } from '../components/Chip';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ProgressBar } from '../components/ProgressBar';
import { Starfield } from '../components/Starfield';
import { StatTile } from '../components/StatTile';
import {
  RANK_TITLES,
  formatLongDate,
  formatNumber,
  formatRelative,
  greeting,
  plural,
} from '../game';

type HeroScreenProps = {
  state: GameState;
  onOpenChallenge: (id: number) => void;
  onNavigate: (tab: TabId) => void;
  onShare: () => void;
};

export function HeroScreen({ state, onOpenChallenge, onNavigate, onShare }: HeroScreenProps) {
  const { viewer, class_sprint: sprint, challenges, week, feed, achievements } = state;
  const available = challenges.filter((challenge) => challenge.status === 'available');
  const pending = challenges.filter((challenge) => challenge.status === 'pending');
  const featured = (available.length ? available : pending).slice(0, 3);
  const nextTitle = viewer.next_level ? RANK_TITLES[viewer.next_level - 1] : null;
  const unlocked = achievements.filter((item) => item.unlocked).length;

  return (
    <div className="screen screen--hero">
      <div className="hero-greet">
        <span className="hero-greet__eyebrow">{formatLongDate()}</span>
        <h1>
          {greeting()}, <span>{viewer.first_name}</span>!
        </h1>
        <p>Твой герой растёт вместе с тобой. Один шаг — и XP уже в копилке.</p>
      </div>

      <section className="hero-stage">
        <Starfield dense />
        <div className="hero-stage__grid" aria-hidden="true" />
        <div className="hero-stage__top">
          <Chip icon="flame" tone="orange">
            {viewer.streak} {plural(viewer.streak, 'день', 'дня', 'дней')} подряд
          </Chip>
          <div className="hero-stage__actions">
            <Chip icon="spark" tone="gold">
              {formatNumber(viewer.sparks)}
            </Chip>
            <button
              type="button"
              className="icon-btn icon-btn--soft"
              onClick={onShare}
              aria-label="Поделиться героем"
            >
              <Icon name="share" size={17} />
            </button>
          </div>
        </div>

        <div className="hero-stage__figure">
          <span className="hero-stage__glow" aria-hidden="true" />
          <span className="hero-stage__pixel hero-stage__pixel--a" aria-hidden="true" />
          <span className="hero-stage__pixel hero-stage__pixel--b" aria-hidden="true" />
          <AvatarFrame
            avatar={viewer.avatar}
            size={182}
            level={viewer.level.level}
            animate
          />
        </div>

        <div className="hero-stage__identity">
          <span className="hero-stage__name">{viewer.name}</span>
          <span className="hero-stage__rank">
            Уровень {viewer.level.level} · {viewer.level.title}
          </span>
        </div>

        <div className="hero-stage__progress">
          <div className="hero-stage__xp">
            <span>{formatNumber(viewer.xp)} XP</span>
            <span>
              {viewer.level.is_max
                ? 'Максимальный уровень'
                : `${formatNumber(viewer.level.xp_in_level)} / ${formatNumber(viewer.level.xp_for_level)}`}
            </span>
          </div>
          <ProgressBar
            value={viewer.level.xp_in_level}
            max={viewer.level.xp_for_level || 1}
            tone="violet"
            height={12}
            label="Опыт внутри уровня"
          />
          <p className="hero-stage__next">
            {viewer.level.is_max ? (
              <>
                Ты — <strong>легенда школы</strong>. Теперь помогай другим добраться до вершины.
              </>
            ) : (
              <>
                Ещё <strong>{formatNumber(viewer.to_next)} XP</strong> до уровня «{nextTitle}»
              </>
            )}
          </p>
        </div>
      </section>

      <div className="stat-grid stat-grid--three">
        <StatTile
          icon="trophy"
          label="место в классе"
          value={`#${viewer.personal_rank}`}
          tone="gold"
        />
        <StatTile
          icon="check"
          label="подтверждено"
          value={viewer.stats.confirmed}
          tone="lime"
        />
        <StatTile
          icon="clock"
          label="на проверке"
          value={viewer.stats.pending}
          tone="cyan"
        />
      </div>

      <section className="panel sprint-card">
        <div className="panel-head">
          <div>
            <span className="panel-eyebrow">Классный спринт недели</span>
            <h2>
              {sprint.name} <span className="panel-head__muted">· {sprint.school}</span>
            </h2>
          </div>
          <span className="rank-badge">#{sprint.rank}</span>
        </div>
        <div className="sprint-card__numbers">
          <strong>{formatNumber(sprint.xp)} XP</strong>
          <span>цель {formatNumber(sprint.goal)} XP</span>
        </div>
        <ProgressBar value={sprint.xp} max={sprint.goal} tone="cyan" height={12} />
        <div className="sprint-card__foot">
          <span>{sprint.percent}% цели</span>
          <span>
            {sprint.xp >= sprint.goal
              ? 'Цель недели взята!'
              : `ещё ${formatNumber(sprint.goal - sprint.xp)} XP`}
          </span>
        </div>
        <div className="sprint-card__top">
          {sprint.top ? (
            <>
              <AvatarFrame avatar={sprint.top.avatar} size={36} decorative />
              <div className="sprint-card__leader">
                <span>Лидер недели</span>
                <strong>{sprint.top.name}</strong>
              </div>
              <span className="sprint-card__leader-xp">+{formatNumber(sprint.top.xp)} XP</span>
            </>
          ) : (
            <div className="sprint-card__leader">
              <span>На этой неделе</span>
              <strong>Ещё нет активности</strong>
            </div>
          )}
          <button
            type="button"
            className="link-btn"
            onClick={() => onNavigate('leaderboard')}
          >
            Рейтинг <Icon name="chevronRight" size={14} />
          </button>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Задания для тебя</h2>
            <p>{available.length ? `${available.length} можно выполнить прямо сейчас` : 'Всё отправлено на проверку'}</p>
          </div>
          <button type="button" className="link-btn" onClick={() => onNavigate('challenges')}>
            Все задания <Icon name="chevronRight" size={14} />
          </button>
        </div>
        {featured.length ? (
          <div className="challenge-list">
            {featured.map((challenge) => (
              <ChallengeCard
                key={challenge.id}
                challenge={challenge}
                onOpen={onOpenChallenge}
                compact
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon="check"
            title="На сегодня всё закрыто"
            text="Новые задания появятся завтра. А пока загляни в рейтинг или гардероб."
            compact
          />
        )}
      </section>

      <section className="panel streak-card">
        <div className="panel-head">
          <div>
            <span className="panel-eyebrow">Серия дней</span>
            <h2>{viewer.streak} дней подряд</h2>
          </div>
          <Chip icon="flame" tone="orange">
            +50 XP за неделю
          </Chip>
        </div>
        <div className="week-strip">
          {week.map((day) => (
            <div
              key={day.date}
              className={`week-day ${day.active ? 'is-active' : ''} ${
                day.is_today ? 'is-today' : ''
              }`.trim()}
            >
              <span className="week-day__label">{day.label}</span>
              <span className="week-day__dot">
                {day.active ? <Icon name="flame" size={15} filled /> : <span />}
              </span>
            </div>
          ))}
        </div>
        <p className="streak-card__hint">
          Заходи каждый день и отмечай хотя бы одно задание. Серия не любит пропусков.
        </p>
      </section>

      <section className="panel achievements-panel">
        <div className="panel-head">
          <div>
            <span className="panel-eyebrow">Достижения</span>
            <h2>{unlocked} из {achievements.length} открыто</h2>
          </div>
          <button type="button" className="link-btn" onClick={() => onNavigate('profile')}>
            Все <Icon name="chevronRight" size={14} />
          </button>
        </div>
        <div className="achievement-badges">
          {achievements.slice(0, 4).map((achievement) => (
            <div
              key={achievement.id}
              className={`achievement-badge ${achievement.unlocked ? 'is-unlocked' : ''}`.trim()}
            >
              <span className="achievement-badge__icon">
                <Icon
                  name={achievement.icon as IconName}
                  size={18}
                  filled={achievement.unlocked}
                />
              </span>
              <span>{achievement.title}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Лента класса</h2>
            <p>Кто и за что получил опыт</p>
          </div>
        </div>
        <div className="panel feed-panel">
          {feed.length ? (
            feed.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className={`feed-item ${item.user_id === viewer.id ? 'is-viewer' : ''}`.trim()}
              >
                <AvatarFrame avatar={item.avatar} size={38} decorative />
                <div className="feed-item__text">
                  <span>
                    <strong>{item.name}</strong> · {item.reason}
                  </span>
                  <small>{formatRelative(item.created_at)}</small>
                </div>
                <span className="feed-item__xp">+{item.amount}</span>
              </div>
            ))
          ) : (
            <EmptyState
              icon="users"
              title="Лента пока пустая"
              text="Стань первым, кто получит опыт на этой неделе."
              compact
            />
          )}
        </div>
      </section>
    </div>
  );
}
