import { useMemo, useState } from 'react';
import '../styles/student.css';
import { AvatarFrame } from '../components/AvatarFrame';
import { InfoButton } from '../components/InfoButton';
import { RatingInfo } from '../components/infoTexts';
import { formatNumber, plural } from '../game';
import { tapHaptic } from '../max';
import type { AvatarConfig, GameState } from '../types';

type BoardId = 'students' | 'classes' | 'schools';

type Row = {
  id: number;
  name: string;
  subtitle: string;
  xp: number;
  weeklyXp: number;
  avatar?: AvatarConfig;
  isViewer: boolean;
  rank: number;
};

type LeaderboardScreenProps = {
  state: GameState;
  onNavigateChallenges: () => void;
};

export function LeaderboardScreen({ state, onNavigateChallenges }: LeaderboardScreenProps) {
  const { leaderboard, viewer } = state;
  const [board, setBoard] = useState<BoardId>('students');

  const boards = useMemo(() => {
    const list: { id: BoardId; label: string }[] = [];
    if (leaderboard.students.length) list.push({ id: 'students', label: 'Мой класс' });
    if (leaderboard.classes.length) list.push({ id: 'classes', label: 'Классы' });
    if (leaderboard.schools.length) list.push({ id: 'schools', label: 'Школы' });
    return list;
  }, [leaderboard]);

  const activeBoard = boards.find((b) => b.id === board)?.id ?? boards[0]?.id;

  const rows = useMemo<Row[]>(() => {
    if (activeBoard === 'students') {
      return leaderboard.students.map((s) => ({
        id: s.id,
        name: s.name,
        subtitle: `${s.level_title} · серия ${s.streak} ${plural(s.streak, 'день', 'дня', 'дней')}`,
        xp: s.xp,
        weeklyXp: s.weekly_xp,
        avatar: s.avatar,
        isViewer: s.is_viewer,
        rank: s.rank,
      }));
    }
    if (activeBoard === 'classes') {
      return leaderboard.classes.map((c) => ({
        id: c.id,
        name: c.name,
        subtitle: [c.school, `${c.members} ${plural(c.members, 'ученик', 'ученика', 'учеников')}`]
          .filter(Boolean)
          .join(' · '),
        xp: c.xp,
        weeklyXp: c.weekly_xp,
        isViewer: c.is_viewer_class,
        rank: c.rank,
      }));
    }
    if (activeBoard === 'schools') {
      return leaderboard.schools.map((s) => ({
        id: s.id,
        name: s.name,
        subtitle: [s.city, `${s.classes} ${plural(s.classes, 'класс', 'класса', 'классов')}`]
          .filter(Boolean)
          .join(' · '),
        xp: s.xp,
        weeklyXp: s.weekly_xp,
        isViewer: s.is_viewer_school,
        rank: s.rank,
      }));
    }
    return [];
  }, [activeBoard, leaderboard]);

  const myRow = rows.find((r) => r.isViewer) ?? null;

  return (
    <div className="st-page">
      <header className="st-head">
        <h1>
          Рейтинг
          <InfoButton title="Как считается рейтинг">
            <RatingInfo />
          </InfoButton>
        </h1>
        <p>Места считаются по XP за подтверждённые задания.</p>
      </header>

      {boards.length === 0 ? (
        <div className="st-empty">
          <h3>Рейтинг пока пуст</h3>
          <p>Он появится, когда в классе будут подтверждённые задания.</p>
          <button type="button" className="st-btn" onClick={onNavigateChallenges}>
            К заданиям
          </button>
        </div>
      ) : (
        <>
          {boards.length > 1 ? (
            <div className="st-tabs" role="tablist" aria-label="Вид рейтинга">
              {boards.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  role="tab"
                  className="st-tab"
                  aria-selected={activeBoard === b.id}
                  onClick={() => {
                    tapHaptic();
                    setBoard(b.id);
                  }}
                >
                  {b.label}
                </button>
              ))}
            </div>
          ) : null}

          {myRow && activeBoard === 'students' ? (
            <div className="st-stats">
              <div className="st-stat">
                <span className="st-stat__label">Ваше место</span>
                <span className="st-stat__value">{myRow.rank}</span>
                <span className="st-stat__hint">из {rows.length}</span>
              </div>
              <div className="st-stat">
                <span className="st-stat__label">XP за неделю</span>
                <span className="st-stat__value">+{formatNumber(viewer.weekly_xp)}</span>
                <span className="st-stat__hint">всего {formatNumber(viewer.xp)}</span>
              </div>
            </div>
          ) : null}

          <section className="st-card" aria-label="Таблица рейтинга">
            <ol className="st-rows">
              {rows.map((row) => (
                <li key={`${activeBoard}-${row.id}`} className={`st-row${row.isViewer ? ' st-row--me' : ''}`}>
                  <span className="st-row__rank">{row.rank}</span>
                  {row.avatar ? (
                    <AvatarFrame avatar={row.avatar} size={36} decorative />
                  ) : (
                    <span className="st-row__ph" aria-hidden="true">
                      {row.name.trim().slice(0, 2).toUpperCase()}
                    </span>
                  )}
                  <span className="st-row__main">
                    <span className="st-row__name">
                      {row.name}
                      {row.isViewer && activeBoard === 'students' ? ' (вы)' : ''}
                    </span>
                    <span className="st-row__sub">{row.subtitle}</span>
                  </span>
                  <span className="st-row__val">
                    {formatNumber(row.xp)} XP
                    <small>+{formatNumber(row.weeklyXp)} за неделю</small>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
