import { useId, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import '../styles/info.css';
import { Icon } from './Icon';
import { Sheet } from './Sheet';

type InfoButtonProps = {
  /** Заголовок окна; по нему же строится подпись кнопки «Что такое …». */
  title: string;
  /** Короткий текст: 1-4 предложения или список. */
  children: ReactNode;
  /** Подпись кнопки для скринридера, если «Что такое «title»» не подходит. */
  label?: string;
  className?: string;
};

/**
 * Маленькая кнопка «i» рядом с непонятным пунктом. Стоит в строке текста,
 * нажатие открывает нижнее окно с коротким объяснением. Зона нажатия 44x44 px
 * делается невидимым ::after, поэтому строку кнопка не раздвигает.
 */
export function InfoButton({ title, children, label, className = '' }: InfoButtonProps) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <>
      <button
        type="button"
        className={`info-btn ${className}`.trim()}
        aria-label={label ?? `Что такое «${title}»`}
        aria-haspopup="dialog"
        aria-controls={open ? id : undefined}
        aria-expanded={open}
        onClick={(event) => {
          // Кнопка может стоять внутри кликабельной карточки или подписи.
          event.preventDefault();
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <Icon name="info" size={18} />
      </button>
      {open
        ? createPortal(
            <Sheet
              open
              onClose={() => setOpen(false)}
              title={title}
              className="info-sheet"
              footer={
                <button type="button" className="btn btn--block" onClick={() => setOpen(false)}>
                  Понятно
                </button>
              }
            >
              <div className="info-sheet__body" id={id}>
                {children}
              </div>
            </Sheet>,
            document.body,
          )
        : null}
    </>
  );
}
