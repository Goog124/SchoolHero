type ProgressBarProps = {
  value: number;
  max: number;
  tone?: 'violet' | 'cyan' | 'gold' | 'lime' | 'pink';
  height?: number;
  label?: string;
  className?: string;
};

export function ProgressBar({
  value,
  max,
  tone = 'violet',
  height = 10,
  label,
  className = '',
}: ProgressBarProps) {
  const safeMax = Math.max(1, max);
  const percent = Math.max(0, Math.min(100, (value / safeMax) * 100));
  return (
    <div
      className={`progress progress--${tone} ${className}`.trim()}
      style={{ height }}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={Math.max(0, Math.min(value, safeMax))}
      aria-label={label}
    >
      <div className="progress__fill" style={{ width: `${percent}%` }} />
      <div className="progress__segments" aria-hidden="true" />
    </div>
  );
}
