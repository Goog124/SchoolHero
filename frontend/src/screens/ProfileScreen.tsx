import { useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Chip } from '../components/Chip';
import { Icon, type IconName } from '../components/Icon';
import { ProgressBar } from '../components/ProgressBar';
import { ScreenTitle } from '../components/ScreenTitle';
import { Sheet } from '../components/Sheet';
import { StatTile } from '../components/StatTile';
import {
  CATEGORY_META,
  RANK_TITLES,
  formatNumber,
  formatXp,
  plural,
} from '../game';
import { isHapticsEnabled, setHapticsEnabled } from '../max';
import type { ChallengeCategory, GameState, TabId } from '../types';

const XP_RULES: { category: ChallengeCategory; xp: number }[] = [
  { category: 'homework', xp: 20 },
  { category: 'club', xp: 30 },
  { category: 'help', xp: 40 },
  { category: 'weekly', xp: 50 },
  { category: 'olympiad', xp: 100 },
  { category: 'event', xp: 30 },
  { category: 'streak', xp: 50 },
];

const LEVELS = [
  { level: 1, title: 'Новичок', xp: 0 },
  { level: 2, title: 'Ученик', xp: 100 },
  { level: 3, title: 'Знаток', xp: 250 },
  { level: 4, title: 'Мастер', xp: 450 },
  { level: 5, title: 'Легенда школы', xp: 700 },
];

type ProfileScreenProps = {
  state: GameState;
  onSwitchRole: (role: 'student' | 'teacher') => Promise<boolean>;
  onResetDemo: () => Promise<boolean>;
  onShare: () => void;
  onNavigate: (tab: TabId) => void;
};

export function ProfileScreen({
  state,
  onSwitchRole,
  onResetDemo,
  onShare,
  onNavigate,
}: ProfileScreenProps) {
  const { viewer, achievements } = state;
  const [xpOpen, setXpOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [haptics, setHaptics] = useState(isHapticsEnabled());
  const unlocked = achievements.filter((item) => item.unlocked).length;
  const isTeacher = viewer.role === 'teacher';

  const toggleHaptics = () => {
    const next = !haptics;
    setHaptics(next);
    setHapticsEnabled(next);
  };

  const confirmReset = async () => {
    setBusy(true);
    const ok = await onResetDemo();
    setBusy(false);
    if (ok) setResetOpen(false);
  };

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Личный кабинет"
        title="Профиль"
        subtitle={
          isTeacher
            ? 'Демо-просмотр глазами педагога. Все действия видны ученикам.'
            : 'Твои достижения, настройки и путь героя.'
        }
      />

      <section className="profile-card">
        <div className="profile-card__art">
          <AvatarFrame avatar={viewer.avatar} size={104} level={viewer.level.level} animate />
        </div>
        <div className="profile-card__info">
          <h2>{viewer.name}</h2>
          <p>
            {viewer.class_name} · {viewer.school_name}
          </p>
          <div className="profile-card__chips">
            <Chip icon="star" tone="violet" size="sm">
              {viewer.level.title}
            </Chip>
            {isTeacher ? (
              <Chip icon="shield" tone="lime" size="sm">
                педагог
              </Chip>
            ) : (
              <Chip icon="mapPin" tone="cyan" size="sm">
                {viewer.city}
              </Chip>
            )}
          </div>
        </div>
        <button
          type="button"
          className="icon-btn icon-btn--soft profile-card__share"
          onClick={onShare}
          aria-label="Поделиться профилем"
        >
          <Icon name="share" size={17} />
        </button>
        <div className="profile-card__xp">
          <div>
            <span>{formatXp(viewer.xp)} всего</span>
            <span>
              {viewer.level.is_max
                ? 'Максимум'
                : `${formatNumber(viewer.level.xp_in_level)} / ${formatNumber(viewer.level.xp_for_level)}`}
            </span>
          </div>
          <ProgressBar
            value={viewer.level.xp_in_level}
            max={viewer.level.xp_for_level || 1}
            tone="violet"
          />
        </div>
      </section>

      <div className="stat-grid">
        <StatTile
          icon="trophy"
          label="место в классе"
          value={`#${viewer.personal_rank}`}
          hint={`#${viewer.school_rank} среди классов`}
          tone="gold"
        />
        <StatTile
          icon="flame"
          label="серия"
          value={`${viewer.streak} ${plural(viewer.streak, 'день', 'дня', 'дней')}`}
          hint={`${formatNumber(viewer.sparks)} искр`}
          tone="pink"
        />
        <StatTile
          icon="check"
          label="подтверждено"
          value={viewer.stats.confirmed}
          hint={`${viewer.stats.pending} на проверке`}
          tone="lime"
        />
        <StatTile
          icon="heart"
          label="помощь друзьям"
          value={viewer.stats.help_count}
          hint="задания «Помощь»"
          tone="cyan"
        />
      </div>

      {state.demo_teacher_available ? (
        <section className={`role-card ${isTeacher ? 'role-card--teacher' : ''}`.trim()}>
          <span className="role-card__icon">
            <Icon name={isTeacher ? 'shield' : 'eye'} size={22} />
          </span>
          <div className="role-card__text">
            <span className="panel-eyebrow">{isTeacher ? 'Режим педагога' : 'Демо-режим'}</span>
            <h3>{isTeacher ? 'Ты смотришь кабинет учителя' : 'Посмотри глазами педагога'}</h3>
            <p>
              {isTeacher
                ? 'Проверь работы, создай задание и вернись к герою в один тап.'
                : 'Открой кабинет 8А: заявки учеников, статистика класса и создание заданий.'}
            </p>
          </div>
          <button
            type="button"
            className="btn btn--sm btn--ghost role-card__btn"
            onClick={() => onSwitchRole(isTeacher ? 'student' : 'teacher')}
          >
            {isTeacher ? 'К герою' : 'Открыть кабинет'}
            <Icon name={isTeacher ? 'chevronRight' : 'shield'} size={15} />
          </button>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Достижения</h2>
            <p>{unlocked} из {achievements.length} открыто</p>
          </div>
        </div>
        <div className="panel achievement-list">
          {achievements.map((achievement) => (
            <div
              key={achievement.id}
              className={`achievement-row ${achievement.unlocked ? 'is-unlocked' : ''}`.trim()}
            >
              <span className="achievement-row__icon">
                <Icon
                  name={achievement.icon as IconName}
                  size={19}
                  filled={achievement.unlocked}
                />
              </span>
              <div className="achievement-row__body">
                <div className="achievement-row__top">
                  <strong>{achievement.title}</strong>
                  <span>
                    {achievement.progress} / {achievement.target}
                  </span>
                </div>
                <p>{achievement.description}</p>
                <ProgressBar
                  value={achievement.progress}
                  max={achievement.target}
                  tone={achievement.unlocked ? 'lime' : 'violet'}
                  height={6}
                />
              </div>
              {achievement.unlocked ? (
                <span className="achievement-row__check">
                  <Icon name="check" size={12} />
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Настройки</h2>
            <p>Всё важное — под рукой</p>
          </div>
        </div>
        <div className="panel settings-list">
          <button type="button" className="settings-row" onClick={() => setXpOpen(true)}>
            <span className="settings-row__icon settings-row__icon--gold">
              <Icon name="spark" size={18} filled />
            </span>
            <span className="settings-row__text">
              <strong>Как начисляется XP</strong>
              <small>Правила, уровни и искры</small>
            </span>
            <Icon name="chevronRight" size={17} />
          </button>
          <div className="settings-row settings-row--static">
            <span className="settings-row__icon settings-row__icon--violet">
              <Icon name="bolt" size={18} />
            </span>
            <span className="settings-row__text">
              <strong>Вибрация</strong>
              <small>Тактильный отклик в MAX</small>
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={haptics}
              className={`switch ${haptics ? 'is-on' : ''}`.trim()}
              onClick={toggleHaptics}
              aria-label="Переключить вибрацию"
            >
              <span />
            </button>
          </div>
          <button type="button" className="settings-row" onClick={onShare}>
            <span className="settings-row__icon settings-row__icon--cyan">
              <Icon name="share" size={18} />
            </span>
            <span className="settings-row__text">
              <strong>Поделиться героем</strong>
              <small>Позови друзей в игру</small>
            </span>
            <Icon name="chevronRight" size={17} />
          </button>
          <button type="button" className="settings-row" onClick={() => setAboutOpen(true)}>
            <span className="settings-row__icon settings-row__icon--pink">
              <Icon name="info" size={18} />
            </span>
            <span className="settings-row__text">
              <strong>О приложении</strong>
              <small>Режим, безопасность, MAX</small>
            </span>
            <Icon name="chevronRight" size={17} />
          </button>
          {state.mode === 'demo' ? (
            <button
              type="button"
              className="settings-row settings-row--danger"
              onClick={() => setResetOpen(true)}
            >
              <span className="settings-row__icon settings-row__icon--red">
                <Icon name="refresh" size={18} />
              </span>
              <span className="settings-row__text">
                <strong>Сбросить демо-профиль</strong>
                <small>Вернуть исходные данные</small>
              </span>
              <Icon name="chevronRight" size={17} />
            </button>
          ) : null}
        </div>
      </section>

      <button
        type="button"
        className="profile-wardrobe-cta"
        onClick={() => onNavigate('wardrobe')}
      >
        <span className="profile-wardrobe-cta__icon">
          <Icon name="shirt" size={20} />
        </span>
        <span>
          <strong>Сменить образ</strong>
          <small>В гардеробе {state.cosmetics.filter((item) => item.unlocked).length} доступных вещей</small>
        </span>
        <Icon name="chevronRight" size={18} />
      </button>

      <footer className="app-footer">
        <span className="app-footer__brand">ШКОЛЬНЫЙ ГЕРОЙ</span>
        <span>v1.0 · сделано для MAX</span>
        <span className={state.verified ? 'app-footer__ok' : 'app-footer__demo'}>
          {state.verified ? 'initData проверен' : 'демо-режим'}
        </span>
      </footer>

      <Sheet
        open={xpOpen}
        onClose={() => setXpOpen(false)}
        title="Как начисляется XP"
        subtitle="Опыт приходит только после подтверждения педагога"
      >
        <div className="xp-rules">
          {XP_RULES.map((rule) => {
            const meta = CATEGORY_META[rule.category];
            return (
              <div key={rule.category} className="xp-rule">
                <span className={`category-mark tone-${meta.tone} category-mark--sm`}>
                  <Icon name={meta.icon} size={16} />
                </span>
                <span className="xp-rule__label">{meta.full}</span>
                <span className="xp-rule__value">+{rule.xp} XP</span>
              </div>
            );
          })}
        </div>
        <div className="level-ladder">
          <h3>Уровни героя</h3>
          {LEVELS.map((level) => (
            <div
              key={level.level}
              className={`level-step ${viewer.level.level === level.level ? 'is-current' : ''} ${
                viewer.level.level > level.level ? 'is-passed' : ''
              }`.trim()}
            >
              <span className="level-step__num">{level.level}</span>
              <span className="level-step__title">{level.title}</span>
              <span className="level-step__xp">от {level.xp} XP</span>
              {viewer.level.level === level.level ? <span className="you-tag">сейчас</span> : null}
            </div>
          ))}
        </div>
        <div className="sheet-note">
          <Icon name="spark" size={16} filled />
          <span>
            Каждый новый уровень даёт 25 искр, а подтверждённое задание — ещё 5 искр сверху.
          </span>
        </div>
      </Sheet>

      <Sheet
        open={aboutOpen}
        onClose={() => setAboutOpen(false)}
        title="О приложении"
        subtitle="Школьный герой · v1.0"
      >
        <div className="about-block">
          <p>
            «Школьный герой» — мини-приложение MAX, где учёба, кружки и помощь друзьям
            превращаются в опыт и уровни. Педагог подтверждает достижения в один тап.
          </p>
          <div className="about-facts">
            <div>
              <span>Режим</span>
              <strong>{state.mode === 'demo' ? 'Демо' : 'MAX'}</strong>
            </div>
            <div>
              <span>Проверка initData</span>
              <strong>{state.verified ? 'на сервере' : 'не требуется'}</strong>
            </div>
            <div>
              <span>Данные</span>
              <strong>SQLite на сервере</strong>
            </div>
            <div>
              <span>Класс</span>
              <strong>{viewer.class_name}</strong>
            </div>
          </div>
          <p className="about-muted">
            В боевом режиме приложение читает подписанный initData из MAX, проверяет HMAC на
            сервере и никогда не доверяет данным из браузера. Демо-режим нужен для показа
            без бота.
          </p>
          <div className="about-levels">
            <span>Путь героя</span>
            <strong>{RANK_TITLES.join(' → ')}</strong>
          </div>
        </div>
      </Sheet>

      <Sheet
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        title="Сбросить демо-профиль?"
        subtitle="Вернём Глеба, 420 XP и заявку на проверке"
        footer={
          <div className="sheet-actions">
            <button type="button" className="btn btn--ghost" onClick={() => setResetOpen(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={confirmReset}
              disabled={busy}
            >
              {busy ? 'Сбрасываем…' : 'Да, сбросить'}
            </button>
          </div>
        }
      >
        <p className="confirm-text">
          Все твои действия в демо — отправленные работы, покупки и смена роли — будут
          заменены исходными данными. Это удобно перед новым показом.
        </p>
      </Sheet>
    </div>
  );
}
