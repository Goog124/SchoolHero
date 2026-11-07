import type { ReactNode } from 'react';

/*
 * Пиксель-арт предметов героя на сетке 32x42 (см. HERO_GRID в PixelHero.tsx).
 * Каждый предмет рисуется по id из backend/game.py. Слои (снизу вверх):
 * BackItems (крылья, плащ, сумка) -> тело -> outfit -> лицо -> hair -> face ->
 * accessory -> hat. Чтобы добавить предмет: строка в COSMETICS на бэкенде и
 * запись с этим id ниже (таблицы HATS, FACE, ACCESSORY_FRONT или NewOutfit).
 */

export type Pal = Record<string, string>;
export type Skin = { base: string; shadow: string };

export function R({
  x,
  y,
  w,
  h,
  fill,
  opacity,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
  opacity?: number;
}) {
  return <rect x={x} y={y} width={w} height={h} fill={fill} opacity={opacity} />;
}

/** Спрайт из строк: символ -> цвет по палитре, '.' прозрачный. mirror отражает относительно x=16. */
export function Sprite({
  x,
  y,
  rows,
  pal,
  mirror = false,
}: {
  x: number;
  y: number;
  rows: string[];
  pal: Pal;
  mirror?: boolean;
}) {
  const width = Math.max(...rows.map((r) => r.length));
  const out: ReactNode[] = [];
  const emit = (ox: number, list: string[], tag: string) => {
    list.forEach((row, j) => {
      let i = 0;
      while (i < row.length) {
        const ch = row[i];
        let k = i;
        while (k < row.length && row[k] === ch) k += 1;
        const fill = pal[ch];
        if (ch !== '.' && fill) {
          out.push(
            <rect key={`${tag}${j}-${i}`} x={ox + i} y={y + j} width={k - i} height={1} fill={fill} />,
          );
        }
        i = k;
      }
    });
  };
  emit(x, rows, 'a');
  if (mirror) {
    emit(
      32 - x - width,
      rows.map((r) => r.padEnd(width, '.').split('').reverse().join('')),
      'b',
    );
  }
  return <g>{out}</g>;
}

/** Половина симметричного спрайта: строки прижаты к центру (последний символ = x15). */
export function Half({ w, y, rows, pal }: { w: number; y: number; rows: string[]; pal: Pal }) {
  return <Sprite x={16 - w} y={y} rows={rows.map((r) => r.padStart(w, '.'))} pal={pal} mirror />;
}

/* ---------------- Задние предметы (под телом) ---------------- */

function CapeBack({ main, dark }: { main: string; dark: string }) {
  return (
    <g>
      <R x={6} y={19} w={20} h={2} fill={dark} />
      <R x={5} y={21} w={22} h={11} fill={main} />
      <R x={4} y={32} w={24} h={6} fill={main} />
      <R x={4} y={38} w={24} h={1} fill={dark} />
      <R x={5} y={21} w={1} h={11} fill={dark} />
      <R x={26} y={21} w={1} h={11} fill={dark} />
      <R x={4} y={32} w={1} h={6} fill={dark} />
      <R x={27} y={32} w={1} h={6} fill={dark} />
      <R x={9} y={33} w={1} h={5} fill={dark} opacity={0.5} />
      <R x={22} y={33} w={1} h={5} fill={dark} opacity={0.5} />
    </g>
  );
}

const WING_ROWS = [
  '.gww.....',
  '.gwww....',
  'gwwwww...',
  'gwwwwww..',
  'gwwwwwww.',
  'gwlwwwwww',
  '.gwlwwwww',
  '..gwlwwww',
  '...gwlwww',
  '....gglww',
  '.....ggww',
];

export function BackItems({ outfit, accessory }: { outfit: string; accessory: string }) {
  return (
    <g>
      {accessory === 'wings' ? (
        <Sprite x={0} y={8} rows={WING_ROWS} pal={{ w: '#f8fafc', l: '#cbd5e1', g: '#94a3b8' }} mirror />
      ) : null}
      {outfit === 'hero_suit' ? <CapeBack main="#dc2626" dark="#7f1d1d" /> : null}
      {accessory === 'cape' ? <CapeBack main="#dc2626" dark="#7f1d1d" /> : null}
      {accessory === 'backpack' ? (
        <Sprite
          x={2}
          y={19}
          rows={['.ogg', 'oggg', 'oggg', 'oggg', 'oggg', 'oggg', 'oggg', 'oggg', 'oggg', 'oggg', '.ogg']}
          pal={{ o: '#14532d', g: '#16a34a' }}
          mirror
        />
      ) : null}
    </g>
  );
}

/* ---------------- Одежда ---------------- */

const NEW_OUTFIT: Record<string, { main: string; dark: string; light: string }> = {
  uniform_school: { main: '#1e3a8a', dark: '#172554', light: '#3b82f6' },
  tshirt_print: { main: '#e2e8f0', dark: '#94a3b8', light: '#ffffff' },
  tracksuit: { main: '#1d4ed8', dark: '#1e3a8a', light: '#60a5fa' },
  labcoat: { main: '#f1f5f9', dark: '#94a3b8', light: '#ffffff' },
  sweater_deer: { main: '#b91c1c', dark: '#7f1d1d', light: '#fca5a5' },
  kimono: { main: '#0e7490', dark: '#164e63', light: '#67e8f9' },
  pirate_coat: { main: '#7f1d1d', dark: '#450a0a', light: '#b91c1c' },
  hero_suit: { main: '#2563eb', dark: '#1e3a8a', light: '#93c5fd' },
  spacesuit: { main: '#e5e7eb', dark: '#9ca3af', light: '#ffffff' },
};

export function isNewOutfit(id: string): boolean {
  return id in NEW_OUTFIT;
}

function Top({
  c,
  skin,
  short = false,
  cuff,
}: {
  c: { main: string; dark: string; light: string };
  skin: Skin;
  short?: boolean;
  cuff?: string;
}) {
  return (
    <g>
      <R x={8} y={20} w={16} h={11} fill={c.dark} />
      <R x={8} y={21} w={16} h={9} fill={c.main} />
      <R x={9} y={20} w={14} h={2} fill={c.main} />
      <R x={8} y={29} w={16} h={1} fill={c.dark} />
      {short ? (
        <g>
          <R x={5} y={21} w={3} h={4} fill={c.main} />
          <R x={24} y={21} w={3} h={4} fill={c.main} />
          <R x={5} y={24} w={3} h={1} fill={c.dark} />
          <R x={24} y={24} w={3} h={1} fill={c.dark} />
          <R x={5} y={25} w={3} h={6} fill={skin.base} />
          <R x={24} y={25} w={3} h={6} fill={skin.base} />
        </g>
      ) : (
        <g>
          <R x={5} y={21} w={3} h={8} fill={c.main} />
          <R x={24} y={21} w={3} h={8} fill={c.main} />
          <R x={5} y={27} w={3} h={2} fill={cuff ?? c.dark} />
          <R x={24} y={27} w={3} h={2} fill={cuff ?? c.dark} />
          <R x={5} y={29} w={3} h={2} fill={skin.base} />
          <R x={24} y={29} w={3} h={2} fill={skin.base} />
        </g>
      )}
      <R x={9} y={21} w={1} h={5} fill={c.light} opacity={0.5} />
    </g>
  );
}

export function NewOutfit({ id, skin }: { id: string; skin: Skin }) {
  const c = NEW_OUTFIT[id];
  if (!c) return null;

  if (id === 'uniform_school') {
    return (
      <g>
        <Top c={c} skin={skin} />
        <Sprite x={13} y={20} rows={['wwwwww', 'wwwwww', '.wwww.', '.wwww.', '..ww..', '..ww..']} pal={{ w: '#f8fafc' }} />
        <Sprite x={15} y={21} rows={['rr', 'rr', 'rr', 'rr', 'rr', '.r']} pal={{ r: '#dc2626' }} />
        <R x={13} y={22} w={1} h={7} fill={c.dark} />
        <R x={18} y={22} w={1} h={7} fill={c.dark} />
        <R x={20} y={23} w={2} h={2} fill="#fbbf24" />
        <R x={20} y={27} w={1} h={1} fill="#fbbf24" />
      </g>
    );
  }
  if (id === 'tshirt_print') {
    return (
      <g>
        <Top c={c} skin={skin} short />
        <R x={12} y={20} w={8} h={1} fill={c.dark} />
        <Sprite
          x={13}
          y={23}
          rows={['.yyyy.', 'ykyyky', 'yyyyyy', 'ykkkky', '.yyyy.']}
          pal={{ y: '#facc15', k: '#451a03' }}
        />
      </g>
    );
  }
  if (id === 'tracksuit') {
    return (
      <g>
        <Top c={c} skin={skin} />
        <R x={8} y={21} w={1} h={9} fill="#f8fafc" />
        <R x={23} y={21} w={1} h={9} fill="#f8fafc" />
        <R x={6} y={21} w={1} h={7} fill="#f8fafc" />
        <R x={25} y={21} w={1} h={7} fill="#f8fafc" />
        <R x={12} y={20} w={8} h={1} fill={c.dark} />
        <R x={15} y={21} w={2} h={9} fill={c.light} />
        <R x={15} y={21} w={1} h={9} fill="#e2e8f0" />
        <R x={10} y={26} w={1} h={3} fill={c.dark} />
        <R x={21} y={26} w={1} h={3} fill={c.dark} />
      </g>
    );
  }
  if (id === 'labcoat') {
    return (
      <g>
        <Top c={c} skin={skin} cuff={c.light} />
        <R x={14} y={20} w={4} h={10} fill="#38bdf8" />
        <R x={13} y={20} w={1} h={10} fill={c.dark} />
        <R x={18} y={20} w={1} h={10} fill={c.dark} />
        <R x={12} y={20} w={2} h={2} fill="#ffffff" />
        <R x={18} y={20} w={2} h={2} fill="#ffffff" />
        <R x={9} y={25} w={4} h={3} fill={c.light} />
        <R x={9} y={25} w={4} h={1} fill={c.dark} />
        <R x={10} y={24} w={1} h={2} fill="#2563eb" />
        <R x={8} y={29} w={16} h={1} fill={c.dark} />
      </g>
    );
  }
  if (id === 'sweater_deer') {
    return (
      <g>
        <Top c={c} skin={skin} cuff="#f8fafc" />
        <R x={8} y={22} w={16} h={1} fill="#f8fafc" />
        <R x={8} y={29} w={16} h={1} fill="#f8fafc" />
        <Sprite x={14} y={24} rows={['w..w', 'wwww', '.nn.', '.nn.', '.rr.']} pal={{ w: '#f8fafc', n: '#92400e', r: '#ef4444' }} />
        <Sprite
          x={9}
          y={24}
          rows={['w.w', '.w.', 'w.w']}
          pal={{ w: '#fca5a5' }}
          mirror
        />
      </g>
    );
  }
  if (id === 'kimono') {
    return (
      <g>
        <Top c={c} skin={skin} />
        <R x={4} y={27} w={4} h={3} fill={c.main} />
        <R x={24} y={27} w={4} h={3} fill={c.main} />
        <Sprite x={12} y={20} rows={['ww..', '.ww.', '..ww', '..ww']} pal={{ w: '#f8fafc' }} mirror />
        <R x={8} y={26} w={16} h={3} fill="#fbbf24" />
        <R x={8} y={26} w={16} h={1} fill="#b45309" />
        <R x={8} y={28} w={16} h={1} fill="#b45309" />
        <R x={18} y={26} w={3} h={5} fill="#f59e0b" />
        <R x={18} y={26} w={3} h={1} fill="#b45309" />
      </g>
    );
  }
  if (id === 'pirate_coat') {
    return (
      <g>
        <Top c={c} skin={skin} cuff="#fef3c7" />
        <Sprite x={13} y={20} rows={['cccccc', 'cccccc', '.cccc.', '..cc..']} pal={{ c: '#fef3c7' }} />
        <R x={13} y={24} w={1} h={6} fill="#fbbf24" />
        <R x={18} y={24} w={1} h={6} fill="#fbbf24" />
        <R x={12} y={24} w={1} h={1} fill="#fbbf24" />
        <R x={19} y={24} w={1} h={1} fill="#fbbf24" />
        <R x={12} y={26} w={1} h={1} fill="#fbbf24" />
        <R x={19} y={26} w={1} h={1} fill="#fbbf24" />
        <R x={8} y={28} w={16} h={1} fill="#111827" />
        <R x={15} y={28} w={2} h={1} fill="#fbbf24" />
      </g>
    );
  }
  if (id === 'hero_suit') {
    return (
      <g>
        <Top c={c} skin={skin} cuff="#dc2626" />
        <Sprite x={14} y={23} rows={['.yy.', 'yrry', 'yrry', '.yy.']} pal={{ y: '#fbbf24', r: '#dc2626' }} />
        <R x={8} y={29} w={16} h={1} fill="#fbbf24" />
        <R x={5} y={27} w={3} h={2} fill="#dc2626" />
        <R x={24} y={27} w={3} h={2} fill="#dc2626" />
      </g>
    );
  }
  // spacesuit
  return (
    <g>
      <Top c={c} skin={skin} cuff="#f97316" />
      <R x={9} y={20} w={14} h={1} fill={c.dark} />
      <R x={12} y={23} w={8} h={4} fill="#6b7280" />
      <R x={13} y={24} w={1} h={1} fill="#ef4444" />
      <R x={15} y={24} w={1} h={1} fill="#22c55e" />
      <R x={17} y={25} w={2} h={1} fill="#fde047" />
      <R x={8} y={29} w={16} h={1} fill="#f97316" />
    </g>
  );
}

/* ---------------- Головные уборы ---------------- */

type HatDef = { w: number; y: number; rows: string[]; pal: Pal };

const HATS: Record<string, HatDef> = {
  hat_cap: {
    w: 8,
    y: 2,
    rows: ['ooooo', 'orrrrr', 'orrlrrr', 'orrrrrr', 'orrrrrr', 'oddddddd', 'odddd'],
    pal: { o: '#1f1236', r: '#ef4444', l: '#fca5a5', d: '#991b1b' },
  },
  hat_beanie: {
    w: 8,
    y: 0,
    rows: ['ww', 'ww', 'ooooo', 'ommmmm', 'ommlmmm', 'ommmmmm', 'occccccc', 'occccccc'],
    pal: { o: '#1f1236', m: '#14b8a6', l: '#5eead4', c: '#0f766e', w: '#f8fafc' },
  },
  hat_party: {
    w: 6,
    y: 0,
    rows: ['y', 'op', 'opp', 'oppy', 'oypyp', 'oppypp', 'oooooo'],
    pal: { o: '#1f1236', p: '#ec4899', y: '#fde047' },
  },
  hat_chef: {
    w: 8,
    y: 0,
    rows: ['oooo', 'owwlww', 'owwwwwl', 'owwlwww', 'owwwwww', 'olllllll', 'ollllll'],
    pal: { o: '#475569', w: '#ffffff', l: '#e2e8f0' },
  },
  hat_cowboy: {
    w: 12,
    y: 1,
    rows: ['ooooo', 'obbbbbb', 'obbbbbb', 'obbbbbb', 'okkkkkk', 'obbbbbbbbbbb', 'oddddddddd'],
    pal: { o: '#451a03', b: '#b45309', d: '#92400e', k: '#451a03' },
  },
  hat_cat: {
    w: 7,
    y: 1,
    rows: ['..oo...', '.ommo..', 'ommpmo.', 'ooooooo'],
    pal: { o: '#1f1236', m: '#6b7280', p: '#f9a8d4' },
  },
  hat_flowers: {
    w: 8,
    y: 3,
    rows: ['gpgygpg', 'gdgwgdgg', 'dg......', 'g.......'],
    pal: { g: '#65a30d', d: '#3f6212', p: '#f472b6', y: '#fde047', w: '#ffffff' },
  },
  hat_bunny: {
    w: 6,
    y: 0,
    rows: ['.oo...', 'owpo..', 'owpo..', 'owpo..', 'owpo..', 'owpo..', 'owwwww'],
    pal: { o: '#94a3b8', w: '#ffffff', p: '#f9a8d4' },
  },
  hat_wizard: {
    w: 11,
    y: 0,
    rows: ['p', 'dp', 'dpp', 'dppy', 'dpppp', 'dyyyyy', 'bdddddddddd', 'bbbbbbbbbb'],
    pal: { p: '#6d28d9', d: '#4c1d95', y: '#fde047', b: '#2e1065' },
  },
  hat_pirate: {
    w: 11,
    y: 1,
    rows: ['kkk', 'kkkkk', 'kkkkkkw', 'kkkkkkkkw', 'kkkkkkkkkkw', 'ggggggggggg'],
    pal: { k: '#1f2937', w: '#ffffff', g: '#fbbf24' },
  },
  hat_laurel: {
    w: 8,
    y: 3,
    rows: ['....gld.', '..gglgd.', '.gldgg..', '.gdg....', 'gdl.....', 'gg......'],
    pal: { g: '#65a30d', l: '#a3e635', d: '#3f6212' },
  },
};

/** Область, где видны волосы под головным убором: [x0, y0, x1, y1]. Нет записи - не режем. */
export const HAT_HAIR_CLIP: Record<string, [number, number, number, number]> = {
  hat_cap: [0, 2, 32, 42],
  hat_beanie: [0, 2, 32, 42],
  hat_party: [0, 4, 32, 42],
  hat_chef: [0, 1, 32, 42],
  hat_cowboy: [0, 2, 32, 42],
  hat_wizard: [0, 6, 32, 42],
  hat_pirate: [0, 3, 32, 42],
  hat_astro: [7, 1, 25, 42],
  headphones: [0, 2, 32, 42],
  cap: [0, 3, 32, 42],
  crown: [0, 2, 32, 42],
};

const GLASS = 'rgba(255, 255, 255, 0.16)';

export function HatLayer({ id }: { id: string }) {
  if (id === 'hat_astro') {
    return (
      <g>
        <R x={8} y={1} w={16} h={1} fill={GLASS} />
        <R x={7} y={2} w={18} h={1} fill={GLASS} />
        <R x={6} y={3} w={20} h={13} fill={GLASS} />
        <R x={9} y={0} w={14} h={1} fill="#e2e8f0" />
        <R x={8} y={1} w={1} h={1} fill="#e2e8f0" />
        <R x={23} y={1} w={1} h={1} fill="#e2e8f0" />
        <R x={7} y={2} w={1} h={1} fill="#e2e8f0" />
        <R x={24} y={2} w={1} h={1} fill="#e2e8f0" />
        <R x={6} y={3} w={1} h={13} fill="#e2e8f0" />
        <R x={25} y={3} w={1} h={13} fill="#e2e8f0" />
        <R x={9} y={3} w={1} h={4} fill="#ffffff" opacity={0.7} />
        <R x={10} y={2} w={3} h={1} fill="#ffffff" opacity={0.7} />
        <R x={5} y={16} w={22} h={3} fill="#e2e8f0" />
        <R x={5} y={18} w={22} h={1} fill="#94a3b8" />
        <R x={14} y={16} w={4} h={2} fill="#f97316" />
      </g>
    );
  }
  const def = HATS[id];
  if (!def) return null;
  return <Half w={def.w} y={def.y} rows={def.rows} pal={def.pal} />;
}

/* ---------------- Лицо ---------------- */

type SpriteDef = { x: number; y: number; rows: string[]; pal: Pal };

const FACE: Record<string, SpriteDef[]> = {
  glasses_round: [
    {
      x: 11,
      y: 10,
      rows: [
        '..ooo...ooo..',
        '.occco.occco.',
        'oocccooocccoo',
        '.occco.occco.',
        '..ooo...ooo..',
      ],
      pal: { o: '#102331', c: GLASS },
    },
  ],
  shades: [
    {
      x: 11,
      y: 10,
      rows: [
        '.kkkkkkkkkkk.',
        '.kwkkk.kwkkk.',
        'kkkkkkkkkkkkk',
        '.kkkkk.kkkkk.',
      ],
      pal: { k: '#111827', w: '#6b7280' },
    },
  ],
  glasses_3d: [
    {
      x: 11,
      y: 10,
      rows: [
        '.wwwwwwwwwww.',
        '.wrrrw.wcccw.',
        'wwrrrwwwcccww',
        '.wrrrw.wcccw.',
        '.wwwwwwwwwww.',
      ],
      pal: { w: '#f8fafc', r: '#ef4444', c: '#22d3ee' },
    },
  ],
  eyepatch: [
    { x: 12, y: 10, rows: ['.kk.', 'kgkk', 'kkkk', 'kkkk', '.kk.'], pal: { k: '#111827', g: '#4b5563' } },
    { x: 9, y: 8, rows: ['s..', '.s.', '..s'], pal: { s: '#111827' } },
    { x: 16, y: 8, rows: ['..ssssss', '.s......', 's.......'], pal: { s: '#111827' } },
  ],
  mustache: [
    { x: 11, y: 14, rows: ['.mmmmmmmmm.', 'm.........m'], pal: { m: '#2b1a12' } },
  ],
  monocle: [
    { x: 18, y: 10, rows: ['.ggg.', 'gcccg', 'gcccg', 'gcccg', '.ggg.'], pal: { g: '#fbbf24', c: GLASS } },
    { x: 23, y: 15, rows: ['g', 'g', 'g'], pal: { g: '#fbbf24' } },
  ],
  mask_hero: [
    {
      x: 10,
      y: 9,
      rows: [
        '.rrrrrrrrrrr.',
        'rrrrrrrrrrrrr',
        'rrwppwrrwppwr',
        'rrwppwrrwppwr',
        'rrwppwrrwppwr',
        '.ddddddddddd.',
      ],
      pal: { r: '#dc2626', d: '#7f1d1d', w: '#ffffff', p: '#291a36' },
    },
  ],
  glasses_pixel: [
    {
      x: 9,
      y: 10,
      rows: ['kkkkkkkkkkkkkkk', '.kwkkkk.kwkkkk.', '..kkkk...kkkk..'],
      pal: { k: '#111827', w: '#f8fafc' },
    },
  ],
};

export function FaceLayer({ id }: { id: string }) {
  if (id === 'vr_headset') {
    return (
      <g>
        <R x={14} y={6} w={4} h={3} fill="#374151" />
        <R x={7} y={10} w={2} h={5} fill="#374151" />
        <R x={23} y={10} w={2} h={5} fill="#374151" />
        <R x={8} y={9} w={16} h={6} fill="#1f2937" />
        <R x={9} y={10} w={14} h={4} fill="#0f172a" />
        <R x={10} y={11} w={5} h={2} fill="#22d3ee" />
        <R x={17} y={11} w={5} h={2} fill="#f472b6" />
        <R x={15} y={14} w={2} h={1} fill="#1f2937" />
        <R x={8} y={9} w={16} h={1} fill="#4b5563" />
      </g>
    );
  }
  const defs = FACE[id];
  if (!defs) return null;
  return (
    <g>
      {defs.map((d, i) => (
        <Sprite key={i} x={d.x} y={d.y} rows={d.rows} pal={d.pal} />
      ))}
    </g>
  );
}

/* ---------------- Аксессуары (шея, грудь, спина) ---------------- */

const ACCESSORY_FRONT: Record<string, SpriteDef & { mirror?: boolean }> = {
  bow: { x: 19, y: 3, rows: ['pp.pp', 'ppkpp', 'pp.pp'], pal: { p: '#ec4899', k: '#9d174d' } },
  badge: { x: 10, y: 24, rows: ['.y.', 'yry', '.y.'], pal: { y: '#fde047', r: '#dc2626' } },
  bowtie: { x: 13, y: 19, rows: ['rr..rr', 'rrkkrr', 'rr..rr'], pal: { r: '#dc2626', k: '#7f1d1d' } },
  tie: {
    x: 13,
    y: 20,
    rows: ['wwrrww', '.wrrw.', '..rr..', '..rl..', '..rr..', '..rr..', '.rrrr.', '.rrrr.', '..rr..'],
    pal: { r: '#dc2626', l: '#f87171', w: '#f8fafc' },
  },
  necklace: {
    x: 13,
    y: 20,
    rows: ['w....w', '.w..w.', '..ww..', '..cc..', '..cc..'],
    pal: { w: '#f8fafc', c: '#22d3ee' },
  },
  medal: { x: 14, y: 24, rows: ['.gg.', 'gyhg', 'gyyg', '.gg.'], pal: { g: '#a16207', y: '#fbbf24', h: '#fef3c7' } },
};

export function AccessoryFront({ id }: { id: string }) {
  if (id === 'medal') {
    return (
      <g>
        <Sprite x={12} y={20} rows={['rr..', '.rr.', '..rr', '...r']} pal={{ r: '#dc2626' }} mirror />
        <Sprite x={14} y={24} rows={ACCESSORY_FRONT.medal.rows} pal={ACCESSORY_FRONT.medal.pal} />
      </g>
    );
  }
  if (id === 'backpack') {
    return (
      <g>
        <Sprite x={9} y={20} rows={['dd', 'dd', 'dd', 'dd', 'dd', 'dd', 'dd', 'dd', 'dd']} pal={{ d: '#14532d' }} mirror />
        <R x={11} y={25} w={10} h={1} fill="#14532d" />
      </g>
    );
  }
  if (id === 'cape') {
    return (
      <g>
        <R x={13} y={21} w={1} h={1} fill="#fbbf24" />
        <R x={18} y={21} w={1} h={1} fill="#fbbf24" />
      </g>
    );
  }
  const d = ACCESSORY_FRONT[id];
  if (!d) return null;
  return <Sprite x={d.x} y={d.y} rows={d.rows} pal={d.pal} />;
}
