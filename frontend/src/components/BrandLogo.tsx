type BrandLogoProps = {
  compact?: boolean;
  size?: 'sm' | 'md' | 'lg';
  subtitle?: string;
  className?: string;
};

export function BrandLogo({
  compact = false,
  size = 'md',
  subtitle,
  className = '',
}: BrandLogoProps) {
  return (
    <div className={`brand brand--${size} ${className}`.trim()}>
      {!compact ? (
        <div className="brand__text">
          <span className="brand__name">Школьный герой</span>
          {subtitle ? <span className="brand__sub">{subtitle}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
