import type { AvatarConfig } from '../types';
import { PixelHero } from './PixelHero';

type AvatarFrameProps = {
  avatar: AvatarConfig;
  size?: number;
  className?: string;
  level?: number;
  animate?: boolean;
  decorative?: boolean;
};

export function AvatarFrame({
  avatar,
  size = 96,
  className = '',
  level,
  animate = false,
  decorative = false,
}: AvatarFrameProps) {
  return (
    <div
      className={`avatar-frame avatar-frame--${avatar.frame} ${className}`.trim()}
      style={{ width: size, height: size }}
    >
      <div className="avatar-frame__inner">
        <div className="avatar-frame__art">
          <PixelHero avatar={avatar} decorative={decorative} animate={animate} />
        </div>
      </div>
      {level ? (
        <span className="avatar-frame__level" aria-hidden="true">
          {level}
        </span>
      ) : null}
    </div>
  );
}
