import { AvatarFrame } from './AvatarFrame';
import { Icon } from './Icon';
import { formatNumber } from '../game';
import type { Viewer } from '../types';

type AppHeaderProps = {
  viewer: Viewer;
  onProfile: () => void;
};

export function AppHeader({ viewer, onProfile }: AppHeaderProps) {
  const isTeacher = viewer.role === 'teacher';
  return (
    <header className="topbar">
      <div className="brand">
        <span className={`brand__mark ${isTeacher ? 'brand__mark--teacher' : ''}`.trim()}>
          <Icon name={isTeacher ? 'shield' : 'sword'} size={19} />
          <span className="brand__spark" aria-hidden="true" />
        </span>
        <span className="brand__text">
          <span className="brand__name">Школьный герой</span>
          <span className="brand__sub">
            {isTeacher ? 'Кабинет педагога' : `${viewer.class_name} · образовательный сервис`}
            {viewer.is_teacher_preview ? <span className="brand__demo">демо</span> : null}
          </span>
        </span>
      </div>
      <div className="topbar__right">
        <span className="topbar__sparks">
          <Icon name="spark" size={13} filled />
          {formatNumber(viewer.sparks)}
        </span>
        <button
          type="button"
          className="topbar__avatar"
          onClick={onProfile}
          aria-label="Открыть профиль"
        >
          <AvatarFrame avatar={viewer.avatar} size={38} decorative />
        </button>
      </div>
    </header>
  );
}
