import { useMemo, useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { Segmented, type SegmentOption } from '../components/Segmented';
import { formatNumber } from '../game';
import type { AvatarConfig, GameState } from '../types';

type BoardId = 'students' | 'classes' | 'schools';

const BOARDS: SegmentOption<BoardId>[] = [
  { id: 'students', label: 'Мой класс' },
  { id: 'classes', label: 'Классы' },
  { id: 'schools', label: 'Школы' },
];

type Row = {
  id: number;
  name: string;
  xp: number;
  weeklyXp: number;
  meta: string;
  avatar?: AvatarConfig;
  isViewer: boolean;
  rank: number;
};

type LeaderboardScreenProps = {
  state: GameState;
  onNavigateChallenges: () => void;
};

export function LeaderboardScreen({ state, onNavigateChallenges }: LeaderboardScreenProps) {
  const [board, setBoard] = useState<BoardId>('students');
  const { leaderboard, viewer } = state;

  const rows = useMemo<Row[]>(() => {
    if (board === 'students') {
      return leaderboard.students.map((item) => ({
        id: item.id,
        name: item.name,
        xp: item.xp,
        weeklyXp: item.weekly_xp,
        meta: `${item.level_title} · серия ${item.streak} дн.`,
        avatar: item.avatar,
        isViewer: item.is_viewer,
        rank: item.rank,
      }));
    }
    if (board === 'classes') {
      return leaderboard.classes.map((item) => ({
        id: item.id,
        name: `${item.name}`,
        xp: item.xp,
        weeklyXp: item.weekly_xp,
        meta: `${item.school} · ${item.members} учен.`,
        isViewer: item.is_viewer_class,
        rank: item.rank,
      }));
    }
    return leaderboard.schools.map((item) => ({
      id: item.id,
      name: item.name,
      xp: item.xp,
      weeklyXp: item.weekly_xp,
      meta: `${item.city} · ${item.classes} кл. · ${item.members} учен.`,
      isViewer: item.is_viewer_school,
      rank: item.rank,
    }));
  }, [board, leaderboard]);

  const myRank =
    board === 'students'
      ? viewer.personal_rank
      : board === 'classes'
        ? viewer.class_rank
        : viewer.school_rank;
  const myName =
    board === 'students'
      ? viewer.name
      : board === 'classes'
        ? `${viewer.class_name} · ${viewer.school_name}`
        : `${viewer.school_name} · ${viewer.city}`;
  const myRow = rows.find((row) => row.isViewer);
  const top = rows.slice(0, 3);
  const rest = rows.slice(3);
  const podiumOrder = [top[1], top[0], top[2]].filter(Boolean) as Row[];

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Зал славы"
        title="Рейтинг"
        subtitle="Опыт общий, но каждую неделю классы начинают спринт заново."
      />

      <div className="my-rank">
        <span className="my-rank__crown">
          <Icon name="crown" size={20} />
        </span>
        <div className="my-rank__text">
          <span>Твоя позиция</span>
          <strong>{myName}</strong>
        </div>
        <span className="my-rank__place">#{myRank}</span>
      </div>

      <Segmented
        options={BOARDS}
        value={board}
        onChange={setBoard}
        ariaLabel="Выбор рейтинга"
      />

      {top.length ? (
        <div className={`podium podium--${board}`}>
          <span className="podium__glow" aria-hidden="true" />
          {podiumOrder.map((row) => {
            const place = row.rank;
            return (
              <div
                key={`${board}-${row.id}`}
                className={`podium__item podium__item--${place} ${
                  row.isViewer ? 'is-viewer' : ''
                }`.trim()}
              >
                <div className="podium__avatar">
                  {place === 1 ? (
                    <span className="podium__crown">
                      <Icon name="crown" size={20} filled />
                    </span>
                  ) : null}
                  {row.avatar ? (
                    <AvatarFrame
                      avatar={row.avatar}
                      size={place === 1 ? 78 : 60}
                      level={undefined}
                      decorative
                    />
                  ) : (
                    <span className={`podium__crest podium__crest--${board}`}>
                      <Icon name={board === 'schools' ? 'shield' : 'users'} size={place === 1 ? 30 : 24} />
                    </span>
                  )}
                  <span className="podium__place">{place}</span>
                </div>
                <strong className="podium__name">{row.name}</strong>
                <span className="podium__xp">{formatNumber(row.xp)} XP</span>
                <span className="podium__pedestal">
                  <span />
                  <span />
                  <span />
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="panel lb-panel">
        {rest.length ? (
          rest.map((row) => (
            <div
              key={`${board}-${row.id}`}
              className={`lb-row ${row.isViewer ? 'is-viewer' : ''}`.trim()}
            >
              <span className="lb-row__rank">{row.rank}</span>
              {row.avatar ? (
                <AvatarFrame avatar={row.avatar} size={40} decorative />
              ) : (
                <span className="lb-row__crest">
                  <Icon name={board === 'schools' ? 'shield' : 'users'} size={18} />
                </span>
              )}
              <div className="lb-row__info">
                <span className="lb-row__name">
                  {row.name}
                  {row.isViewer ? <span className="you-tag">ты</span> : null}
                </span>
                <span className="lb-row__meta">{row.meta}</span>
              </div>
              <div className="lb-row__xp">
                <strong>{formatNumber(row.xp)}</strong>
                <span>+{formatNumber(row.weeklyXp)} нед.</span>
              </div>
            </div>
          ))
        ) : (
          <div className="lb-panel__empty">
            <Icon name="trophy" size={20} />
            <span>Топ-3 уже на пьедестале. Заработай XP, чтобы подняться выше.</span>
          </div>
        )}
      </div>

      {board !== 'students' && myRow ? (
        <div className="panel lb-note">
          <span className="lb-note__icon">
            <Icon name="info" size={17} />
          </span>
          <p>
            {board === 'classes'
              ? `Класс ${viewer.class_name} сейчас на ${myRank} месте. В зачёт идёт опыт всех учеников класса.`
              : `${viewer.school_name} на ${myRank} месте среди школ города.`}{' '}
            Общий XP растёт после каждого подтверждённого задания.
          </p>
        </div>
      ) : null}

      <button type="button" className="cta-banner" onClick={onNavigateChallenges}>
        <span className="cta-banner__icon">
          <Icon name="bolt" size={20} />
        </span>
        <span className="cta-banner__text">
          <strong>Хочешь выше?</strong>
          <span>Выполни задание — и опыт сразу пойдёт в зачёт.</span>
        </span>
        <Icon name="chevronRight" size={18} />
      </button>
    </div>
  );
}
