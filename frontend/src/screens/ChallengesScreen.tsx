import { useMemo, useState } from 'react';
import '../styles/student.css';
import { ChallengeCard } from '../components/ChallengeCard';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { TaskStatusInfo } from '../components/infoTexts';
import { formatNumber } from '../game';
import { tapHaptic } from '../max';
import type { Challenge, GameState } from '../types';

type StatusFilter = 'all' | 'available' | 'pending' | 'approved';
type SortOption = 'default' | 'xp-desc' | 'xp-asc' | 'deadline';

const STATUS_OPTIONS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'available', label: 'Доступные' },
  { id: 'pending', label: 'На проверке' },
  { id: 'approved', label: 'Выполненные' },
];

const STATUS_WEIGHT: Record<Challenge['status'], number> = {
  available: 0,
  rejected: 1,
  pending: 2,
  approved: 3,
  expired: 4,
};

type ChallengesScreenProps = {
  state: GameState;
  onOpenChallenge: (id: number) => void;
};

export function ChallengesScreen({ state, onOpenChallenge }: ChallengesScreenProps) {
  const [query, setQuery] = useState('');
  const [subject, setSubject] = useState('all');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [sort, setSort] = useState<SortOption>('default');

  const all = state.challenges;
  const counts = useMemo(
    () => ({
      all: all.length,
      available: all.filter((c) => c.status === 'available').length,
      pending: all.filter((c) => c.status === 'pending').length,
      approved: all.filter((c) => c.status === 'approved').length,
    }),
    [all],
  );

  // Предметы берём из самих заданий, без жёстко заданного списка.
  const subjects = useMemo(
    () => Array.from(new Set(all.map((c) => c.subject).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ru')),
    [all],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = all.filter((c) => {
      if (q && !`${c.title} ${c.description} ${c.subject}`.toLowerCase().includes(q)) return false;
      if (status !== 'all' && c.status !== status) return false;
      if (subject !== 'all' && c.subject !== subject) return false;
      return true;
    });

    if (sort === 'xp-desc') return list.sort((a, b) => b.xp - a.xp);
    if (sort === 'xp-asc') return list.sort((a, b) => a.xp - b.xp);
    if (sort === 'deadline') {
      return list.sort((a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime());
    }
    return list.sort((a, b) => STATUS_WEIGHT[a.status] - STATUS_WEIGHT[b.status] || b.xp - a.xp);
  }, [all, query, status, subject, sort]);

  const hasFilters = query !== '' || subject !== 'all' || status !== 'all' || sort !== 'default';

  const reset = () => {
    tapHaptic();
    setQuery('');
    setSubject('all');
    setStatus('all');
    setSort('default');
  };

  return (
    <div className="st-page">
      <header className="st-head">
        <h1>
          Задания
          <InfoButton title="Статусы заданий">
            <TaskStatusInfo />
          </InfoButton>
        </h1>
        <p>Выполните задание и отправьте результат учителю. После проверки начисляются XP.</p>
      </header>

      {all.length === 0 ? (
        <div className="st-empty">
          <h3>Заданий пока нет</h3>
          <p>Когда учитель добавит задания для класса, они появятся здесь.</p>
        </div>
      ) : (
        <>
          <div className="st-search" role="search">
            <Icon name="search" size={18} />
            <input
              type="search"
              className="st-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск по названию или предмету"
              aria-label="Поиск заданий"
            />
            {query ? (
              <button type="button" className="st-clear" onClick={() => setQuery('')} aria-label="Очистить поиск">
                ×
              </button>
            ) : null}
          </div>

          <div className="st-filters">
            <div className="st-tabs" role="group" aria-label="Фильтр по статусу">
              {STATUS_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="st-tab"
                  aria-pressed={status === opt.id}
                  onClick={() => {
                    tapHaptic();
                    setStatus(opt.id);
                  }}
                >
                  {opt.label}
                  <small>{counts[opt.id]}</small>
                </button>
              ))}
            </div>

            <div className="st-field">
              {subjects.length > 1 ? (
                <select
                  className="st-input"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  aria-label="Предмет"
                >
                  <option value="all">Все предметы</option>
                  {subjects.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              ) : null}
              <select
                className="st-input"
                value={sort}
                onChange={(e) => setSort(e.target.value as SortOption)}
                aria-label="Сортировка"
              >
                <option value="default">По статусу</option>
                <option value="xp-desc">Больше XP</option>
                <option value="xp-asc">Меньше XP</option>
                <option value="deadline">По сроку</option>
              </select>
            </div>
          </div>

          {visible.length ? (
            <section aria-label="Список заданий" className="st-col" style={{ gap: 8 }}>
              <div className="st-count">
                <span>
                  Найдено: {formatNumber(visible.length)}
                </span>
                {hasFilters ? (
                  <button type="button" className="st-link" onClick={reset}>
                    Сбросить
                  </button>
                ) : null}
              </div>
              <div className="st-list">
                {visible.map((challenge) => (
                  <ChallengeCard key={challenge.id} challenge={challenge} onOpen={onOpenChallenge} />
                ))}
              </div>
            </section>
          ) : (
            <div className="st-empty">
              <h3>Ничего не найдено</h3>
              <p>По выбранным условиям заданий нет.</p>
              {hasFilters ? (
                <button type="button" className="st-btn st-btn--ghost" onClick={reset}>
                  Сбросить фильтры
                </button>
              ) : null}
            </div>
          )}

          <section className="st-card" aria-labelledby="st-how-title">
            <h2 className="st-h2" id="st-how-title" style={{ marginBottom: 8 }}>
              Как это работает
            </h2>
            <ol className="st-steps">
              <li>
                <strong>Выберите задание.</strong> Откройте карточку и прочитайте условие.
              </li>
              <li>
                <strong>Отправьте результат.</strong> Напишите, что сделано, или приложите ссылку.
              </li>
              <li>
                <strong>Дождитесь проверки.</strong> Учитель подтвердит работу, и XP попадут в рейтинг.
              </li>
            </ol>
          </section>
        </>
      )}
    </div>
  );
}
