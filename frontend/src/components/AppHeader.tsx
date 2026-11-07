import { AvatarFrame } from './AvatarFrame';
import { BrandLogo } from './BrandLogo';
import { Icon } from './Icon';
import { InfoButton } from './InfoButton';
import { SparksInfo } from './infoTexts';
import { formatNumber } from '../game';
import { uiRole, type Viewer } from '../types';

type AppHeaderProps = {
  viewer: Viewer;
  onProfile: () => void;
  /** Плашка «Демо»: только при state.mode === 'demo'. */
  demo?: boolean;
  /** Администратор платформы без роли: героя и баллов у него нет. */
  hideHero?: boolean;
  /** Ручное обновление данных (кнопка в шапке). */
  onRefresh?: () => void;
  refreshing?: boolean;
};

export function AppHeader({
  viewer,
  onProfile,
  demo = false,
  hideHero = false,
  onRefresh,
  refreshing = false,
}: AppHeaderProps) {
  const isStudent = viewer.role === 'student' && !hideHero;
  const role = uiRole(viewer);
  const roleName = role === 'director' ? 'Администрация' : role === 'teacher' ? 'Педагог' : '';
  const subtitle = [viewer.class_name, roleName].filter(Boolean).join(' · ');

  return (
    <header className="topbar">
      <BrandLogo size="md" subtitle={subtitle || undefined} />
      <div className="topbar__right">
        {demo ? <span className="badge-demo">Демо</span> : null}
        {onRefresh ? <RefreshButton onClick={onRefresh} busy={refreshing} /> : null}
        {isStudent ? (
          <span className="topbar__sparks" aria-label={`Баллы: ${viewer.sparks}`}>
            <Icon name="spark" size={14} filled />
            {formatNumber(viewer.sparks)}
          </span>
        ) : null}
        {isStudent ? (
          <InfoButton title="Искры" className="info-btn--bar">
            <SparksInfo />
          </InfoButton>
        ) : null}
        {isStudent ? (
          <button
            type="button"
            className="topbar__avatar"
            onClick={onProfile}
            aria-label="Открыть профиль"
          >
            <AvatarFrame avatar={viewer.avatar} size={36} decorative />
          </button>
        ) : null}
      </div>
    </header>
  );
}

type RefreshButtonProps = { onClick: () => void; busy?: boolean; className?: string };

/** Кнопка «Обновить»: перечитывает данные, не сбрасывая открытый экран. */
export function RefreshButton({ onClick, busy = false, className = '' }: RefreshButtonProps) {
  return (
    <button
      type="button"
      className={`refresh-btn ${className}`.trim()}
      onClick={onClick}
      disabled={busy}
      aria-busy={busy}
      aria-label={busy ? 'Обновляем данные' : 'Обновить данные'}
      title="Обновить"
    >
      <span className={busy ? 'refresh-btn__icon refresh-btn__icon--spin' : 'refresh-btn__icon'}>
        <Icon name="refresh" size={18} />
      </span>
    </button>
  );
}
