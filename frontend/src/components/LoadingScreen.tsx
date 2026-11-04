import { BrandLogo } from './BrandLogo';

type LoadingScreenProps = {
  label?: string;
  error?: string;
  onRetry?: () => void;
};

export function LoadingScreen({ label = 'Загрузка…', error, onRetry }: LoadingScreenProps) {
  return (
    <div className="loading" role={error ? 'alert' : 'status'}>
      <BrandLogo size="lg" />
      {error ? (
        <>
          <p className="loading__error">{error}</p>
          {onRetry ? (
            <button type="button" className="btn btn--sm" onClick={onRetry}>
              Повторить
            </button>
          ) : null}
        </>
      ) : (
        <>
          <span className="loading__spinner" aria-hidden="true" />
          <p className="loading__label">{label}</p>
        </>
      )}
    </div>
  );
}
