import '../styles/student.css';

type ProgressBarProps = {
  value: number;
  max: number;
  /** Оставлено для совместимости; цвет шкалы единый. */
  tone?: 'violet' | 'cyan' | 'gold' | 'lime' | 'pink';
  height?: number;
  label?: string;
  className?: string;
};

export function ProgressBar({ value, max, height = 8, label, className = '' }: ProgressBarProps) {
  const safeMax = Math.max(1, max);
  const percent = Math.max(0, Math.min(100, (value / safeMax) * 100));

  return (
    <div
      className={`st-progress ${className}`.trim()}
      style={{ height }}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={Math.max(0, Math.min(value, safeMax))}
      aria-label={label}
    >
      <div className="st-progress__fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
