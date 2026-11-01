import { PixelHero } from './PixelHero';
import type { AvatarConfig } from '../types';

const LOADING_AVATAR: AvatarConfig = {
  skin: 'skin_warm',
  hair: 'hair_curls',
  hairColor: 'hair_brown',
  outfit: 'hoodie_violet',
  accessory: 'headphones',
  frame: 'frame_neon',
};

type LoadingScreenProps = {
  label?: string;
  error?: string;
  onRetry?: () => void;
};

export function LoadingScreen({ label = 'Собираем твоего героя', error, onRetry }: LoadingScreenProps) {
  return (
    <div className="loading">
      <div className="loading__stars" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className={`loading__figure ${error ? 'loading__figure--sad' : ''}`.trim()}>
        <div className="loading__halo" aria-hidden="true" />
        <PixelHero avatar={LOADING_AVATAR} animate={!error} decorative />
      </div>
      <div className="loading__brand">ШКОЛЬНЫЙ ГЕРОЙ</div>
      {error ? (
        <>
          <p className="loading__error">{error}</p>
          {onRetry ? (
            <button type="button" className="btn btn--sm" onClick={onRetry}>
              Попробовать снова
            </button>
          ) : null}
        </>
      ) : (
        <>
          <p className="loading__label">{label}</p>
          <div className="loading__bar" aria-hidden="true">
            <span />
          </div>
        </>
      )}
    </div>
  );
}
