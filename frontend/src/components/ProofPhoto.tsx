import { useEffect, useState } from 'react';
import { getUploadBlob } from '../api';

type ProofPhotoProps = {
  uploadId: number;
  alt: string;
};

/** Фото работы: загрузка с авторизацией -> blob -> objectURL; по нажатию открывается на весь экран. */
export function ProofPhoto({ uploadId, alt }: ProofPhotoProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [full, setFull] = useState(false);

  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    setSrc(null);
    setFailed(false);
    setFull(false);
    getUploadBlob(uploadId)
      .then((blob) => {
        if (!alive) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [uploadId]);

  useEffect(() => {
    if (!full) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFull(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [full]);

  if (failed) return <p className="tc-alert tc-alert--warn">Фото не удалось загрузить.</p>;
  if (!src) return <p className="tc-muted">Загружаем фото…</p>;

  return (
    <>
      <button type="button" className="proof-photo" onClick={() => setFull(true)} aria-label="Открыть фото на весь экран">
        <img className="proof-photo__img" src={src} alt={alt} />
      </button>
      {full ? (
        <div className="proof-photo__full" role="dialog" aria-modal="true" aria-label={alt}>
          <img className="proof-photo__full-img" src={src} alt={alt} />
          <button type="button" className="proof-photo__close" onClick={() => setFull(false)}>
            Закрыть
          </button>
        </div>
      ) : null}
    </>
  );
}
