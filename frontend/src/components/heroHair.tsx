import { Half, R, Sprite } from './heroItems';
import type { Pal } from './heroItems';

/*
 * Причёски героя на сетке 32x42. Голова: кожа x10..21, y5..15; контур головы
 * y3 (x11..20), y4-5 (x9..22), x8/x23 на y6..16; брови y9, глаза y11..13.
 * Передние волосы описаны половинками (Half, w=10: колонки x6..x15, зеркалятся
 * к x16..x25). Символы: o контур, b основной, d тень, l блик, s кожа,
 * h щетина, p резинка. Задний слой (BackHair) рисуется под телом.
 */

export const HAIR_STYLES = [
  'hair_short',
  'hair_buzz',
  'hair_curls',
  'hair_bob',
  'hair_pony',
  'hair_long',
  'hair_bald',
  'hair_afro',
  'hair_braids',
  'hair_mohawk',
] as const;

export type HairColors = { base: string; dark: string; light: string };

const OUTLINE = '#180c29';

type Layer = { y: number; rows: string[] };

const SHORT_TOP = [
  '......oooo',
  '....oobbbb',
  '...obbbblb',
  '...obbbbbb',
  '..obbbbbbb',
  '..obbdbbdb',
];

const FRONT: Record<string, Layer> = {
  // Короткая аккуратная: объём над макушкой, ровная чёлка до y7, бакенбарды.
  hair_short: { y: 2, rows: [...SHORT_TOP, '..obb.....'] },
  // Ёжик: по форме черепа, без объёма, щетина b/d, линия роста на y6.
  hair_buzz: {
    y: 3,
    rows: ['....oooooo', '...odbdbdb', '...obdbdbd', '..obdbdbdb', '..od......', '..od......'],
  },
  // Кудри: пышная шапка с завитками по контуру и объёмом по бокам до ушей.
  hair_curls: {
    y: 0,
    rows: [
      '.....oo.oo',
      '....obbobb',
      '...obbbbbl',
      '..obbdbbbb',
      '.obblbbbdb',
      '.obbbbdbbb',
      'obbdbbbblb',
      'obbbbdbbbb',
      'obbdbb....',
      '.obbb.....',
      'obdb......',
      '.obb......',
      'obbd......',
      '.oo.......',
    ],
  },
  // Каре: ровная густая чёлка с тенью, волосы до подбородка, кончики наружу.
  hair_bob: {
    y: 2,
    rows: [
      '.....ooooo',
      '...oobbbbb',
      '..obblbbbb',
      '..obbbbbbb',
      '.obbbbbbbb',
      '.obbbbbbbb',
      '.obbdddddd',
      '.obb......',
      '.obb......',
      '.obd......',
      '.obd......',
      '.obb......',
      '.obbb.....',
      '..ooo.....',
    ],
  },
  // Хвостик: гладко зачёсано назад, без бакенбард; сам хвост в заднем слое.
  hair_pony: { y: 2, rows: SHORT_TOP },
  // Длинные: короткая чёлка, пряди по бокам лица ниже плеч, кончики сужаются.
  hair_long: {
    y: 2,
    rows: [
      '.....ooooo',
      '...oobbbbb',
      '..obbbblbb',
      '..obbbbbbb',
      '.obbbbbbbb',
      '.obbbdbbdb',
      '.obbb.....',
      '.obb......',
      '.obb......',
      '.obb......',
      '.obd......',
      '.obb......',
      '.obb......',
      '.obb......',
      '.obb......',
      '.obbb.....',
      '.obbb.....',
      '.obdb.....',
      '.obdb.....',
      '.obbb.....',
      '.obbb.....',
      '.obbo.....',
      '..obo.....',
      '..oo......',
    ],
  },
  // Афро: передняя часть без верхнего контура, сливается с объёмом сзади.
  hair_afro: {
    y: 3,
    rows: ['...bbbbbbb', '..bbbbbbbb', '..bbdbbbbb', '..bbbbbbbb', '..bbdbbdbb', '..bb......'],
  },
  // Косички: аккуратный верх, сами косы отдельным спрайтом.
  hair_braids: { y: 2, rows: SHORT_TOP },
  // Ирокез: узкая полоса x14..17, бока выбриты (кожа и лёгкая щетина).
  hair_mohawk: {
    y: 0,
    rows: [
      '........oo',
      '.......obb',
      '.......obl',
      '.......obb',
      '...osssobb',
      '....hhhobb',
      '....hhhobb',
    ],
  },
};

const AFRO_BACK: Layer = {
  y: 0,
  rows: [
    '......ooooooo',
    '....oobbbbbbb',
    '...obbbbdbbbb',
    '..obbdbbbbbbl',
    '.obbbbbbbdbbb',
    '.obdbbbbbbbbb',
    'obbbbbdbbbbbb',
    'obbbbbbbbbbbb',
    'obbdbbbbbbbbb',
    'obbbbbbbbbbbb',
    'obbbbdbbbbbbb',
    '.obbbbbbbbbbb',
    '.obdbbbbbbbbb',
    '..obbbbbbbbbb',
    '...oobbbbbbbb',
    '.....oooooooo',
  ],
};

const PONY_TAIL = [
  '...oo.',
  '..obbo',
  '.obblo',
  '.obbbo',
  '.obbdo',
  '..obbo',
  '..obbo',
  '..obdo',
  '..obbo',
  '...obo',
  '...oo.',
];

const BRAID = [
  '.oo.',
  'obbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'obdo',
  'odbo',
  'oppo',
  'obbo',
  '.oo.',
];

function palette(colors: HairColors, skin: string): Pal {
  return {
    o: OUTLINE,
    b: colors.base,
    d: colors.dark,
    l: colors.light,
    s: skin,
    h: `${colors.dark}55`,
    p: '#f472b6',
  };
}

export function BackHair({ style, colors }: { style: string; colors: HairColors }) {
  const pal = palette(colors, colors.base);
  if (style === 'hair_afro') {
    return <Half w={13} y={AFRO_BACK.y} rows={AFRO_BACK.rows} pal={pal} />;
  }
  if (style === 'hair_pony') {
    return <Sprite x={22} y={4} rows={PONY_TAIL} pal={pal} />;
  }
  return null;
}

export function FrontHair({
  style,
  colors,
  skin,
}: {
  style: string;
  colors: HairColors;
  skin: string;
}) {
  const pal = palette(colors, skin);
  if (style === 'hair_bald') {
    return (
      <g>
        <R x={10} y={4} w={12} h={1} fill={skin} />
        <R x={12} y={5} w={3} h={1} fill="#ffffff" opacity={0.22} />
      </g>
    );
  }
  const layer = FRONT[style] ?? FRONT.hair_short;
  return (
    <g>
      {style === 'hair_mohawk' ? <R x={10} y={4} w={12} h={1} fill={skin} /> : null}
      <Half w={10} y={layer.y} rows={layer.rows} pal={pal} />
      {style === 'hair_braids' ? <Sprite x={6} y={8} rows={BRAID} pal={pal} mirror /> : null}
      {style === 'hair_pony' ? <R x={23} y={6} w={2} h={1} fill="#f6c453" /> : null}
    </g>
  );
}
