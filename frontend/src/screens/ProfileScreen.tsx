import { AvatarFrame } from '../components/AvatarFrame';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { formatNumber, formatXp } from '../game';
import { tapHaptic } from '../max';
import type { GameState, TabId } from '../types';
import '../styles/profile.css';

type ProfileScreenProps = {
  state: GameState;
  onShare?: () => void;
  onNavigate: (tab: TabId) => void;
  theme?: 'light' | 'dark';
  onThemeChange?: (theme: 'light' | 'dark') => void;
  // Демо-переключатели рисует оболочка; экран их не использует.
  onSwitchRole?: (role: 'student' | 'teacher' | 'director') => Promise<boolean>;
  onResetDemo?: () => Promise<boolean>;
};

const ROLE_LABEL: Record<string, string> = {
  student: 'Ученик',
  teacher: 'Учитель',
  director: 'Администрация школы',
};

export function ProfileScreen({
  state,
  onNavigate,
  theme,
  onThemeChange,
}: ProfileScreenProps) {
  const { viewer, achievements } = state;
  const isStudent = viewer.role === 'student';
  const unlocked = achievements.filter((a) => a.unlocked).length;

  const place = [viewer.class_name ? `${viewer.class_name} класс` : '', viewer.school_name, viewer.city]
    .filter(Boolean)
    .join(' · ');

  const levelPercent = viewer.level.is_max
    ? 100
    : Math.max(0, Math.min(100, (viewer.level.xp_in_level / Math.max(1, viewer.level.xp_for_level)) * 100));

  return (
    <div className="screen pf">
      <ScreenTitle title="Профиль" />

      <section className="pf-card" aria-label="Мой профиль">
        <div className="pf-head">
          {isStudent && (
            <AvatarFrame avatar={viewer.avatar} size={88} level={viewer.level.level} decorative />
          )}
          <div className="pf-head__text">
            <h2 className="pf-name">{viewer.name}</h2>
            <div className="pf-muted">{ROLE_LABEL[viewer.role] ?? ''}</div>
            <div className="pf-muted">{place || (isStudent ? 'Класс не выбран' : '')}</div>
          </div>
        </div>

        {isStudent && (
          <div className="pf-level">
            <div className="pf-level__row">
              <strong>
                {viewer.level.level} уровень · {viewer.level.title}
              </strong>
              <span className="pf-muted">
                {viewer.level.is_max
                  ? 'Максимальный уровень'
                  : `${formatNumber(viewer.level.xp_in_level)} из ${formatNumber(viewer.level.xp_for_level)} XP`}
              </span>
            </div>
            <div
              className="pf-bar"
              role="progressbar"
              aria-label="Прогресс до следующего уровня"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(levelPercent)}
            >
              <div className="pf-bar__fill" style={{ width: `${levelPercent}%` }} />
            </div>
            <div className="pf-muted">Всего {formatXp(viewer.xp)}</div>
          </div>
        )}

        <div className="pf-actions">
          {isStudent && (
            <button
              type="button"
              className="pf-btn pf-btn--primary"
              onClick={() => {
                tapHaptic();
                onNavigate('wardrobe');
              }}
            >
              <Icon name="shirt" size={16} />
              Изменить героя
            </button>
          )}
          {theme && onThemeChange && (
            <button
              type="button"
              className="pf-btn"
              onClick={() => {
                tapHaptic();
                onThemeChange(theme === 'dark' ? 'light' : 'dark');
              }}
            >
              {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
            </button>
          )}
        </div>
      </section>

      {isStudent && (
        <>
          <dl className="pf-stats" aria-label="Показатели">
            <div className="pf-stat">
              <dt>Место в классе</dt>
              <dd>{viewer.personal_rank > 0 ? viewer.personal_rank : '—'}</dd>
            </div>
            <div className="pf-stat">
              <dt>Дней подряд</dt>
              <dd>{viewer.streak}</dd>
            </div>
            <div className="pf-stat">
              <dt>Подтверждено заданий</dt>
              <dd>{viewer.stats.confirmed}</dd>
            </div>
            <div className="pf-stat">
              <dt>На проверке</dt>
              <dd>{viewer.stats.pending}</dd>
            </div>
          </dl>

          <section className="pf-card" aria-labelledby="pf-ach-h">
            <div className="pf-level__row">
              <h2 className="pf-h" id="pf-ach-h">Достижения</h2>
              {achievements.length > 0 && (
                <span className="pf-muted">
                  {unlocked} из {achievements.length}
                </span>
              )}
            </div>

            {achievements.length === 0 ? (
              <p className="pf-empty">Достижений пока нет. Они появятся, когда вы начнёте выполнять задания.</p>
            ) : (
              <ul className="pf-list">
                {achievements.map((item) => {
                  const pct = Math.max(0, Math.min(100, (item.progress / Math.max(1, item.target)) * 100));
                  return (
                    <li key={item.id} className={`pf-ach${item.unlocked ? ' pf-ach--done' : ''}`}>
                      <div className="pf-ach__row">
                        <span className="pf-ach__title">{item.title}</span>
                        <span className="pf-ach__count">
                          {item.unlocked ? 'Получено' : `${item.progress} из ${item.target}`}
                        </span>
                      </div>
                      {item.description && <span className="pf-muted">{item.description}</span>}
                      {!item.unlocked && (
                        <div
                          className="pf-bar"
                          role="progressbar"
                          aria-label={item.title}
                          aria-valuemin={0}
                          aria-valuemax={item.target}
                          aria-valuenow={Math.min(item.progress, item.target)}
                        >
                          <div className="pf-bar__fill" style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
