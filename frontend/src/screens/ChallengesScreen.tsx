import { useMemo, useState } from 'react';
import { ChallengeCard } from '../components/ChallengeCard';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { Segmented, type SegmentOption } from '../components/Segmented';
import { formatNumber } from '../game';
import type { Challenge, GameState } from '../types';

type FilterId = 'all' | 'daily' | 'weekly' | 'event' | 'pending';

const FILTERS: SegmentOption<FilterId>[] = [
  { id: 'all', label: 'Все' },
  { id: 'daily', label: 'Сегодня' },
  { id: 'weekly', label: 'Неделя' },
  { id: 'event', label: 'События' },
  { id: 'pending', label: 'Проверка' },
];

function matches(challenge: Challenge, filter: FilterId): boolean {
  if (filter === 'all') return true;
  if (filter === 'pending') return challenge.status === 'pending';
  return challenge.kind === filter;
}

type ChallengesScreenProps = {
  state: GameState;
  onOpenChallenge: (id: number) => void;
};

export function ChallengesScreen({ state, onOpenChallenge }: ChallengesScreenProps) {
  const [filter, setFilter] = useState<FilterId>('all');
  const available = state.challenges.filter((item) => item.status === 'available');
  const pending = state.challenges.filter((item) => item.status === 'pending');
  const availableXp = available.reduce((sum, item) => sum + item.xp, 0);

  const visible = useMemo(
    () =>
      state.challenges
        .filter((challenge) => matches(challenge, filter))
        .slice()
        .sort((a, b) => {
          const weight: Record<Challenge['status'], number> = {
            available: 0,
            rejected: 1,
            pending: 2,
            approved: 3,
            expired: 4,
          };
          return weight[a.status] - weight[b.status] || a.id - b.id;
        }),
    [state.challenges, filter],
  );

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Арена заданий"
        title="Челленджи"
        subtitle="Выполняй, отправляй подтверждение и получай опыт после проверки педагога."
      />

      <div className="challenge-summary">
        <div className="challenge-summary__cell">
          <span>Доступно</span>
          <strong>{available.length}</strong>
        </div>
        <div className="challenge-summary__cell challenge-summary__cell--accent">
          <span>Можно заработать</span>
          <strong>
            {formatNumber(availableXp)} <small>XP</small>
          </strong>
        </div>
        <div className="challenge-summary__cell">
          <span>На проверке</span>
          <strong>{pending.length}</strong>
        </div>
      </div>

      <Segmented
        options={FILTERS}
        value={filter}
        onChange={setFilter}
        ariaLabel="Фильтр заданий"
        scrollable
      />

      {visible.length ? (
        <div className="challenge-list challenge-list--roomy">
          {visible.map((challenge) => (
            <ChallengeCard key={challenge.id} challenge={challenge} onOpen={onOpenChallenge} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon="sparkles"
          title="Здесь пока пусто"
          text={
            filter === 'pending'
              ? 'Ты ещё не отправлял работы на проверку. Выбери задание и расскажи, что сделал.'
              : 'В этой подборке пока нет заданий. Загляни в другие разделы.'
          }
        />
      )}

      <section className="how-card">
        <div className="how-card__head">
          <span className="panel-eyebrow">Правила арены</span>
          <h2>Как получить XP</h2>
        </div>
        <ol className="how-steps">
          <li>
            <span className="how-steps__num">01</span>
            <div>
              <strong>Выбери задание</strong>
              <p>Домашка, кружок, помощь другу или школьное событие.</p>
            </div>
          </li>
          <li>
            <span className="how-steps__num">02</span>
            <div>
              <strong>Отправь подтверждение</strong>
              <p>Пара слов, фото или ссылка — педагог увидит это в кабинете.</p>
            </div>
          </li>
          <li>
            <span className="how-steps__num">03</span>
            <div>
              <strong>Получи опыт</strong>
              <p>Один тап педагога — и XP идёт тебе и в копилку класса.</p>
            </div>
          </li>
        </ol>
        <div className="how-card__note">
          <Icon name="info" size={16} />
          <span>Опыт начисляется только после подтверждения. Честная игра — это важно.</span>
        </div>
      </section>
    </div>
  );
}
