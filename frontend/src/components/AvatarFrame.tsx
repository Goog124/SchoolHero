import type { CSSProperties } from 'react';
import type { AvatarConfig } from '../types';
import { PixelHero } from './PixelHero';
import '../styles/frames.css';

type AvatarFrameProps = {
  avatar: AvatarConfig;
  size?: number;
  className?: string;
  level?: number;
  animate?: boolean;
  decorative?: boolean;
};

/** «Пиксельная единица» рамки в px: растёт ступенями, чтобы линии оставались чёткими. */
export function frameUnit(size: number): number {
  if (size < 64) return 1;
  if (size < 140) return 2;
  return 3;
}

/**
 * Рамка героя. Стиль каждой рамки (id из backend/game.py, тип frame) лежит в
 * styles/frames.css под классом `.avatar-frame--<id>`: цвета и SVG-плитка узора.
 * Отступ героя от края = 4 единицы (frameUnit); его использует камера гардероба.
 */
export function AvatarFrame({
  avatar,
  size = 96,
  className = '',
  level,
  animate = false,
  decorative = false,
}: AvatarFrameProps) {
  const style = { width: size, height: size, '--af-u': `${frameUnit(size)}px` } as CSSProperties;
  return (
    <div className={`avatar-frame avatar-frame--${avatar.frame} ${className}`.trim()} style={style}>
      <div className="avatar-frame__ring" aria-hidden="true" />
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
