import { AvatarFrame } from './AvatarFrame';
import { BrandLogo } from './BrandLogo';
import { Icon } from './Icon';
import { formatNumber } from '../game';
import type { Viewer } from '../types';

type AppHeaderProps = {
  viewer: Viewer;
  onProfile: () => void;
  /** Плашка «Демо»: только при state.mode === 'demo'. */
  demo?: boolean;
};

export function AppHeader({ viewer, onProfile, demo = false }: AppHeaderProps) {
  const isDirector = viewer.role === 'director';
  const roleName =
    viewer.role === 'director' ? 'Администрация' : viewer.role === 'teacher' ? 'Педагог' : '';
  const subtitle = [viewer.class_name, roleName].filter(Boolean).join(' · ');

  return (
    <header className="topbar">
      <BrandLogo size="md" subtitle={subtitle || undefined} />
      <div className="topbar__right">
        {demo ? <span className="badge-demo">Демо</span> : null}
        {!isDirector ? (
          <span className="topbar__sparks" aria-label={`Баллы: ${viewer.sparks}`}>
            <Icon name="spark" size={14} filled />
            {formatNumber(viewer.sparks)}
          </span>
        ) : null}
        <button
          type="button"
          className="topbar__avatar"
          onClick={onProfile}
          aria-label="Открыть профиль"
        >
          <AvatarFrame avatar={viewer.avatar} size={36} decorative />
        </button>
      </div>
    </header>
  );
}
