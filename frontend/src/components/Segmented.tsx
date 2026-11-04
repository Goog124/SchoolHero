import { useEffect, useRef, useState } from 'react';

export type SegmentOption<T extends string> = {
  id: T;
  label: string;
  badge?: number;
};

type SegmentedProps<T extends string> = {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  scrollable?: boolean;
};

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  scrollable = false,
}: SegmentedProps<T>) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [fade, setFade] = useState({ start: false, end: false });

  useEffect(() => {
    if (!scrollable) {
      setFade({ start: false, end: false });
      return;
    }
    const node = scrollerRef.current;
    if (!node) return;

    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const maxScroll = node.scrollWidth - node.clientWidth;
        setFade({
          start: node.scrollLeft > 2,
          end: maxScroll > 2 && node.scrollLeft < maxScroll - 2,
        });
      });
    };

    update();
    node.addEventListener('scroll', update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(node);
    window.addEventListener('resize', update);
    void document.fonts?.ready.then(update);

    return () => {
      window.cancelAnimationFrame(frame);
      node.removeEventListener('scroll', update);
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [scrollable, options.length]);

  const row = (
    <div
      ref={scrollerRef}
      className={`segmented ${scrollable ? 'segmented--scroll' : ''}`.trim()}
      role="tablist"
      aria-label={ariaLabel}
    >
      {options.map((option) => {
        const active = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`segmented__item ${active ? 'is-active' : ''}`.trim()}
            onClick={() => onChange(option.id)}
          >
            <span>{option.label}</span>
            {option.badge ? (
              <span className="segmented__badge">
                {option.badge}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );

  if (!scrollable) return row;

  return (
    <div
      className={`segmented-wrap ${fade.start ? 'is-start-faded' : ''} ${
        fade.end ? 'is-end-faded' : ''
      }`.trim()}
    >
      {row}
    </div>
  );
}
