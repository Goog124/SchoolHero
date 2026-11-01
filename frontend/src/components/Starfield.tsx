const STARS = [
  { x: 6, y: 18, s: 2, d: 0.2 },
  { x: 14, y: 9, s: 1, d: 1.4 },
  { x: 21, y: 26, s: 2, d: 2.2 },
  { x: 30, y: 13, s: 1, d: 0.8 },
  { x: 38, y: 7, s: 2, d: 1.9 },
  { x: 47, y: 20, s: 1, d: 0.4 },
  { x: 56, y: 11, s: 2, d: 2.7 },
  { x: 64, y: 24, s: 1, d: 1.1 },
  { x: 73, y: 8, s: 2, d: 0.6 },
  { x: 82, y: 17, s: 1, d: 2.1 },
  { x: 91, y: 10, s: 2, d: 1.6 },
  { x: 96, y: 29, s: 1, d: 0.9 },
  { x: 9, y: 39, s: 1, d: 2.5 },
  { x: 25, y: 45, s: 2, d: 1.2 },
  { x: 43, y: 36, s: 1, d: 0.3 },
  { x: 60, y: 42, s: 1, d: 2.9 },
  { x: 77, y: 37, s: 2, d: 1.7 },
  { x: 89, y: 44, s: 1, d: 2.3 },
  { x: 68, y: 34, s: 1, d: 0.5 },
  { x: 18, y: 53, s: 1, d: 1.3 },
];

export function Starfield({ dense = false }: { dense?: boolean }) {
  const stars = dense ? STARS : STARS.slice(0, 14);
  return (
    <div className="starfield" aria-hidden="true">
      {stars.map((star, index) => (
        <span
          key={index}
          style={{
            left: `${star.x}%`,
            top: `${star.y}%`,
            width: star.s * 2,
            height: star.s * 2,
            animationDelay: `${star.d}s`,
          }}
        />
      ))}
    </div>
  );
}
