import type { AvatarConfig } from '../types';
import {
  AccessoryFront,
  BackItems,
  FaceLayer,
  HatLayer,
  NewOutfit,
  R,
  isNewOutfit,
} from './heroItems';

type Palette = {
  base: string;
  shadow: string;
  line: string;
  blush: string;
};

const SKIN: Record<string, Palette> = {
  skin_light: { base: '#f7d4b7', shadow: '#e3b08a', line: '#c88a63', blush: '#ef9a92' },
  skin_warm: { base: '#edbb8e', shadow: '#d09463', line: '#b5764a', blush: '#e0867e' },
  skin_tan: { base: '#cb8c62', shadow: '#a86c45', line: '#8b5331', blush: '#cc6f67' },
  skin_deep: { base: '#96613f', shadow: '#74462d', line: '#5d3521', blush: '#b25c53' },
};

const HAIR: Record<string, { base: string; dark: string; light: string }> = {
  hair_dark: { base: '#2e2038', dark: '#1a1125', light: '#4d3a5d' },
  hair_brown: { base: '#6b3f2b', dark: '#472719', light: '#91603f' },
  hair_ginger: { base: '#c25a2e', dark: '#85361a', light: '#e88250' },
  hair_blonde: { base: '#e7c56a', dark: '#b18d36', light: '#f7e3a5' },
  hair_violet: { base: '#8b5cf6', dark: '#5f35c4', light: '#c0a9ff' },
  hair_blue: { base: '#3b82f6', dark: '#1d4ed8', light: '#9bc6ff' },
  hair_pink: { base: '#ec4899', dark: '#9d174d', light: '#f9a8d4' },
  hair_white: { base: '#e5e7eb', dark: '#9ca3af', light: '#ffffff' },
  hair_green: { base: '#22c55e', dark: '#15803d', light: '#86efac' },
  hair_teal: { base: '#14b8a6', dark: '#0f766e', light: '#5eead4' },
};

const OUTFIT: Record<
  string,
  { main: string; dark: string; light: string; accent: string }
> = {
  hoodie_violet: { main: '#8b5cf6', dark: '#5b2ea6', light: '#bda7ff', accent: '#f0abfc' },
  hoodie_red: { main: '#ef4444', dark: '#991b1b', light: '#fca5a5', accent: '#fde68a' },
  hoodie_green: { main: '#22c55e', dark: '#15803d', light: '#86efac', accent: '#fef08a' },
  armor_bronze: { main: '#b87333', dark: '#6b3a15', light: '#e6a468', accent: '#fbbf24' },
  armor_gold: { main: '#fbbf24', dark: '#a16207', light: '#fef08a', accent: '#ef4444' },
  hoodie_cyan: { main: '#22d3ee', dark: '#0e7490', light: '#89ecf8', accent: '#fef08a' },
  sweater_gold: { main: '#fbbf24', dark: '#a85c08', light: '#fde68a', accent: '#78350f' },
  jacket_blue: { main: '#3b82f6', dark: '#1e40af', light: '#93c5fd', accent: '#e0f2fe' },
  cloak_violet: { main: '#7c3aed', dark: '#4c1d95', light: '#c4b5fd', accent: '#fbbf24' },
  armor_silver: { main: '#cbd5e1', dark: '#5b6b80', light: '#f1f5f9', accent: '#a855f7' },
  suit_cosmic: { main: '#312e81', dark: '#1e1b4b', light: '#818cf8', accent: '#f0abfc' },
};

/** Сетка пиксельного героя (viewBox 0 0 32 42): ширина и высота в клетках. */
export const HERO_GRID = { w: 32, h: 42 } as const;

/**
 * Рамки частей тела в клетках сетки (x0,y0 включительно, x1,y1 исключительно),
 * вычислены по реальным rect-ам ниже: голова y0..18 (причёски: хвост до x=29, каре до y=19),
 * торс с руками y17..32, ноги y31..41. Используются «камерой» гардероба.
 */
export const HERO_PARTS = {
  head: { x0: 4, y0: 0, x1: 29, y1: 20 },
  face: { x0: 7, y0: 2, x1: 25, y1: 19 },
  neck: { x0: 6, y0: 9, x1: 26, y1: 27 },
  torso: { x0: 3, y0: 17, x1: 29, y1: 33 },
  body: { x0: 0, y0: 0, x1: 32, y1: 42 },
} as const;

const HERO_VIEWS = HERO_PARTS;

const OUTLINE = '#180c29';
const PANTS = '#2a1b3e';
const PANTS_DARK = '#1b1029';
const SHOE = '#120a1d';
const EYE = '#291a36';
const MOUTH = '#a34f58';

type PixelHeroProps = {
  avatar: AvatarConfig;
  size?: number;
  className?: string;
  decorative?: boolean;
  animate?: boolean;
  /** Кадр: целиком (по умолчанию) или часть героя для миниатюр предметов. */
  view?: keyof typeof HERO_VIEWS;
};

function BackHair({ style, colors }: { style: string; colors: { base: string; dark: string; light: string } }) {
  if (style === 'hair_bob') {
    return (
      <g>
        <R x={6} y={7} w={4} h={14} fill={OUTLINE} />
        <R x={22} y={7} w={4} h={14} fill={OUTLINE} />
        <R x={7} y={8} w={2} h={12} fill={colors.base} />
        <R x={23} y={8} w={2} h={12} fill={colors.base} />
        <R x={7} y={15} w={2} h={4} fill={colors.dark} />
        <R x={23} y={15} w={2} h={4} fill={colors.dark} />
      </g>
    );
  }
  if (style === 'hair_pony') {
    return (
      <g>
        <R x={23} y={4} w={5} h={3} fill={OUTLINE} />
        <R x={25} y={6} w={4} h={10} fill={OUTLINE} />
        <R x={24} y={15} w={4} h={3} fill={OUTLINE} />
        <R x={24} y={5} w={3} h={2} fill={colors.base} />
        <R x={26} y={7} w={2} h={8} fill={colors.base} />
        <R x={25} y={15} w={2} h={2} fill={colors.dark} />
        <R x={27} y={8} w={1} h={5} fill={colors.light} />
      </g>
    );
  }
  if (style === 'hair_long') {
    return (
      <g>
        <R x={6} y={7} w={4} h={19} fill={OUTLINE} />
        <R x={22} y={7} w={4} h={19} fill={OUTLINE} />
        <R x={7} y={8} w={2} h={17} fill={colors.base} />
        <R x={23} y={8} w={2} h={17} fill={colors.base} />
        <R x={7} y={18} w={2} h={6} fill={colors.dark} />
        <R x={23} y={18} w={2} h={6} fill={colors.dark} />
      </g>
    );
  }
  if (style === 'hair_afro') {
    return (
      <g>
        <R x={10} y={0} w={12} h={1} fill={OUTLINE} />
        <R x={7} y={1} w={18} h={1} fill={OUTLINE} />
        <R x={5} y={2} w={22} h={2} fill={OUTLINE} />
        <R x={4} y={4} w={24} h={9} fill={OUTLINE} />
        <R x={5} y={13} w={22} h={2} fill={OUTLINE} />
        <R x={11} y={1} w={10} h={1} fill={colors.base} />
        <R x={8} y={2} w={16} h={1} fill={colors.base} />
        <R x={6} y={3} w={20} h={2} fill={colors.base} />
        <R x={5} y={5} w={22} h={8} fill={colors.base} />
        <R x={6} y={13} w={20} h={1} fill={colors.dark} />
        <R x={7} y={6} w={1} h={1} fill={colors.dark} />
        <R x={24} y={8} w={1} h={1} fill={colors.dark} />
        <R x={6} y={10} w={1} h={1} fill={colors.dark} />
        <R x={25} y={11} w={1} h={1} fill={colors.dark} />
        <R x={9} y={2} w={3} h={1} fill={colors.light} opacity={0.5} />
      </g>
    );
  }
  if (style === 'hair_curls') {
    return (
      <g>
        <R x={6} y={7} w={4} h={5} fill={OUTLINE} />
        <R x={22} y={7} w={4} h={5} fill={OUTLINE} />
        <R x={7} y={8} w={2} h={3} fill={colors.base} />
        <R x={23} y={8} w={2} h={3} fill={colors.base} />
        <R x={7} y={10} w={2} h={2} fill={colors.dark} />
        <R x={23} y={10} w={2} h={2} fill={colors.dark} />
      </g>
    );
  }
  return null;
}

function FrontHair({
  style,
  colors,
  skin,
}: {
  style: string;
  colors: { base: string; dark: string; light: string };
  skin: string;
}) {
  if (style === 'hair_bald') {
    return (
      <g>
        <R x={10} y={4} w={12} h={1} fill={skin} />
        <R x={12} y={5} w={3} h={1} fill="#ffffff" opacity={0.22} />
      </g>
    );
  }
  if (style === 'hair_mohawk') {
    return (
      <g>
        <R x={10} y={4} w={12} h={1} fill={skin} />
        <R x={10} y={5} w={4} h={2} fill={colors.dark} opacity={0.3} />
        <R x={18} y={5} w={4} h={2} fill={colors.dark} opacity={0.3} />
        <R x={13} y={0} w={6} h={1} fill={OUTLINE} />
        <R x={13} y={1} w={1} h={7} fill={OUTLINE} />
        <R x={18} y={1} w={1} h={7} fill={OUTLINE} />
        <R x={14} y={1} w={4} h={7} fill={colors.base} />
        <R x={17} y={3} w={1} h={5} fill={colors.dark} />
        <R x={14} y={1} w={1} h={4} fill={colors.light} opacity={0.7} />
      </g>
    );
  }
  if (style === 'hair_long' || style === 'hair_braids') {
    return (
      <g>
        <ShortFront colors={colors} />
        {style === 'hair_long' ? (
          <g>
            <R x={7} y={17} w={4} h={10} fill={OUTLINE} />
            <R x={21} y={17} w={4} h={10} fill={OUTLINE} />
            <R x={8} y={17} w={2} h={9} fill={colors.base} />
            <R x={22} y={17} w={2} h={9} fill={colors.base} />
            <R x={8} y={22} w={2} h={4} fill={colors.dark} />
            <R x={22} y={22} w={2} h={4} fill={colors.dark} />
          </g>
        ) : (
          <g>
            {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
              <g key={i}>
                <R x={6} y={12 + i * 2} w={3} h={2} fill={OUTLINE} />
                <R x={23} y={12 + i * 2} w={3} h={2} fill={OUTLINE} />
                <R x={7} y={12 + i * 2} w={1} h={2} fill={i % 2 ? colors.dark : colors.base} />
                <R x={24} y={12 + i * 2} w={1} h={2} fill={i % 2 ? colors.dark : colors.base} />
                <R x={8} y={12 + i * 2} w={1} h={2} fill={i % 2 ? colors.base : colors.dark} />
                <R x={23} y={12 + i * 2} w={1} h={2} fill={i % 2 ? colors.base : colors.dark} />
              </g>
            ))}
            <R x={6} y={28} w={3} h={1} fill="#f472b6" />
            <R x={23} y={28} w={3} h={1} fill="#f472b6" />
          </g>
        )}
      </g>
    );
  }
  if (style === 'hair_buzz') {
    return (
      <g>
        <R x={11} y={3} w={10} h={1} fill={colors.dark} />
        <R x={10} y={4} w={12} h={2} fill={colors.base} />
        <R x={9} y={6} w={2} h={3} fill={colors.base} />
        <R x={21} y={6} w={2} h={3} fill={colors.base} />
        <R x={12} y={4} w={6} h={1} fill={colors.light} opacity={0.45} />
      </g>
    );
  }
  if (style === 'hair_curls') {
    return (
      <g>
        <R x={11} y={1} w={3} h={2} fill={OUTLINE} />
        <R x={14} y={0} w={4} h={2} fill={OUTLINE} />
        <R x={18} y={1} w={3} h={2} fill={OUTLINE} />
        <R x={9} y={3} w={14} h={2} fill={OUTLINE} />
        <R x={8} y={5} w={2} h={4} fill={colors.dark} />
        <R x={22} y={5} w={2} h={4} fill={colors.dark} />
        <R x={11} y={1} w={3} h={1} fill={colors.base} />
        <R x={14} y={0} w={4} h={1} fill={colors.base} />
        <R x={18} y={1} w={3} h={1} fill={colors.base} />
        <R x={10} y={3} w={12} h={2} fill={colors.base} />
        <R x={9} y={5} w={2} h={3} fill={colors.base} />
        <R x={21} y={5} w={2} h={3} fill={colors.base} />
        <R x={8} y={9} w={2} h={2} fill={colors.base} />
        <R x={22} y={9} w={2} h={2} fill={colors.base} />
        <R x={8} y={10} w={1} h={1} fill={colors.dark} />
        <R x={23} y={10} w={1} h={1} fill={colors.dark} />
        <R x={11} y={5} w={3} h={2} fill={colors.base} />
        <R x={18} y={5} w={3} h={2} fill={colors.base} />
        <R x={11} y={7} w={2} h={1} fill={colors.dark} />
        <R x={15} y={7} w={2} h={1} fill={colors.dark} />
        <R x={19} y={7} w={2} h={1} fill={colors.dark} />
        <R x={12} y={2} w={6} h={1} fill={colors.light} opacity={0.55} />
      </g>
    );
  }
  if (style === 'hair_bob') {
    return (
      <g>
        <R x={10} y={3} w={12} h={1} fill={colors.dark} />
        <R x={9} y={4} w={14} h={2} fill={colors.base} />
        <R x={8} y={6} w={3} h={13} fill={colors.dark} />
        <R x={21} y={6} w={3} h={13} fill={colors.dark} />
        <R x={9} y={6} w={2} h={12} fill={colors.base} />
        <R x={21} y={6} w={2} h={12} fill={colors.base} />
        <R x={10} y={6} w={4} h={2} fill={colors.base} />
        <R x={18} y={6} w={4} h={2} fill={colors.base} />
        <R x={11} y={7} w={2} h={1} fill={colors.dark} />
        <R x={15} y={7} w={2} h={1} fill={colors.dark} />
        <R x={19} y={7} w={2} h={1} fill={colors.dark} />
        <R x={10} y={4} w={4} h={1} fill={colors.light} opacity={0.5} />
        <R x={8} y={15} w={2} h={3} fill={colors.dark} />
        <R x={22} y={15} w={2} h={3} fill={colors.dark} />
      </g>
    );
  }
  if (style === 'hair_pony') {
    return (
      <g>
        <R x={10} y={3} w={12} h={1} fill={colors.dark} />
        <R x={9} y={4} w={14} h={2} fill={colors.base} />
        <R x={8} y={6} w={2} h={5} fill={colors.dark} />
        <R x={22} y={6} w={2} h={5} fill={colors.dark} />
        <R x={9} y={6} w={1} h={4} fill={colors.base} />
        <R x={22} y={6} w={1} h={4} fill={colors.base} />
        <R x={10} y={6} w={5} h={2} fill={colors.base} />
        <R x={17} y={6} w={5} h={2} fill={colors.base} />
        <R x={11} y={7} w={3} h={1} fill={colors.dark} />
        <R x={16} y={7} w={2} h={1} fill={colors.dark} />
        <R x={19} y={7} w={2} h={1} fill={colors.dark} />
        <R x={22} y={7} w={2} h={2} fill={colors.base} />
        <R x={22} y={8} w={2} h={1} fill="#f6c453" />
        <R x={11} y={4} w={4} h={1} fill={colors.light} opacity={0.6} />
      </g>
    );
  }
  // short (и афро: объём сзади)
  return <ShortFront colors={colors} />;
}

function ShortFront({ colors }: { colors: { base: string; dark: string; light: string } }) {
  return (
    <g>
      <R x={10} y={3} w={12} h={1} fill={colors.dark} />
      <R x={9} y={4} w={14} h={2} fill={colors.base} />
      <R x={8} y={6} w={2} h={5} fill={colors.dark} />
      <R x={22} y={6} w={2} h={5} fill={colors.dark} />
      <R x={9} y={6} w={1} h={4} fill={colors.base} />
      <R x={22} y={6} w={1} h={4} fill={colors.base} />
      <R x={10} y={6} w={4} h={2} fill={colors.base} />
      <R x={18} y={6} w={4} h={2} fill={colors.base} />
      <R x={11} y={7} w={2} h={1} fill={colors.dark} />
      <R x={15} y={7} w={2} h={1} fill={colors.dark} />
      <R x={19} y={7} w={2} h={1} fill={colors.dark} />
      <R x={11} y={4} w={4} h={1} fill={colors.light} opacity={0.55} />
    </g>
  );
}

function Outfit({
  id,
  skin,
}: {
  id: string;
  skin: Palette;
}) {
  if (isNewOutfit(id)) return <NewOutfit id={id} skin={skin} />;
  const colors = OUTFIT[id] ?? OUTFIT.hoodie_violet;

  if (id === 'cloak_violet') {
    return (
      <g>
        <R x={4} y={20} w={24} h={14} fill={OUTLINE} />
        <R x={5} y={21} w={22} h={12} fill={colors.dark} />
        <R x={6} y={21} w={20} h={11} fill={colors.main} />
        <R x={5} y={31} w={4} h={2} fill={colors.dark} />
        <R x={23} y={31} w={4} h={2} fill={colors.dark} />
        <R x={8} y={21} w={16} h={10} fill={colors.main} />
        <R x={7} y={20} w={18} h={2} fill={colors.dark} />
        <R x={9} y={19} w={14} h={3} fill={colors.dark} />
        <R x={10} y={19} w={12} h={2} fill={colors.main} />
        <R x={9} y={22} w={2} h={7} fill={colors.light} opacity={0.4} />
        <R x={21} y={22} w={2} h={7} fill={colors.dark} opacity={0.45} />
        <R x={8} y={28} w={16} h={2} fill={colors.dark} />
        <R x={15} y={20} w={2} h={2} fill={colors.accent} />
        <R x={15} y={20} w={1} h={1} fill="#fff0b3" />
        <R x={5} y={21} w={3} h={7} fill={colors.main} />
        <R x={24} y={21} w={3} h={7} fill={colors.main} />
        <R x={5} y={27} w={3} h={2} fill={colors.dark} />
        <R x={24} y={27} w={3} h={2} fill={colors.dark} />
        <R x={5} y={29} w={3} h={2} fill={skin.base} />
        <R x={24} y={29} w={3} h={2} fill={skin.base} />
      </g>
    );
  }

  if (id.startsWith('armor_')) {
    return (
      <g>
        <R x={8} y={20} w={16} h={11} fill={colors.dark} />
        <R x={8} y={21} w={16} h={9} fill={colors.main} />
        <R x={9} y={22} w={14} h={6} fill={colors.light} />
        <R x={10} y={23} w={12} h={4} fill={colors.main} />
        <R x={11} y={24} w={10} h={2} fill={colors.light} opacity={0.65} />
        <R x={15} y={23} w={2} h={4} fill={colors.accent} />
        <R x={15} y={24} w={1} h={1} fill="#f9d5ff" />
        <R x={6} y={20} w={4} h={4} fill={colors.dark} />
        <R x={22} y={20} w={4} h={4} fill={colors.dark} />
        <R x={7} y={20} w={2} h={3} fill={colors.main} />
        <R x={23} y={20} w={2} h={3} fill={colors.main} />
        <R x={8} y={28} w={16} h={2} fill={colors.dark} />
        <R x={15} y={28} w={2} h={2} fill="#fbbf24" />
        <R x={5} y={21} w={3} h={8} fill={colors.main} />
        <R x={24} y={21} w={3} h={8} fill={colors.main} />
        <R x={5} y={27} w={3} h={2} fill={colors.dark} />
        <R x={24} y={27} w={3} h={2} fill={colors.dark} />
        <R x={5} y={29} w={3} h={2} fill={skin.base} />
        <R x={24} y={29} w={3} h={2} fill={skin.base} />
        <R x={8} y={21} w={1} h={7} fill={colors.light} opacity={0.5} />
      </g>
    );
  }

  if (id === 'suit_cosmic') {
    return (
      <g>
        <R x={8} y={20} w={16} h={11} fill={colors.dark} />
        <R x={8} y={21} w={16} h={9} fill={colors.main} />
        <R x={9} y={20} w={14} h={2} fill={colors.accent} opacity={0.85} />
        <R x={9} y={29} w={14} h={1} fill={colors.light} />
        <R x={12} y={22} w={1} h={1} fill="#fff8ff" />
        <R x={19} y={23} w={1} h={1} fill="#fef08a" />
        <R x={16} y={25} w={1} h={1} fill="#fff8ff" />
        <R x={21} y={27} w={1} h={1} fill="#f0abfc" />
        <R x={10} y={26} w={1} h={1} fill="#f0abfc" />
        <R x={15} y={21} w={2} h={2} fill={colors.accent} />
        <R x={15} y={28} w={2} h={2} fill={colors.accent} />
        <R x={5} y={21} w={3} h={8} fill={colors.main} />
        <R x={24} y={21} w={3} h={8} fill={colors.main} />
        <R x={5} y={27} w={3} h={2} fill={colors.dark} />
        <R x={24} y={27} w={3} h={2} fill={colors.dark} />
        <R x={5} y={29} w={3} h={2} fill={skin.base} />
        <R x={24} y={29} w={3} h={2} fill={skin.base} />
        <R x={6} y={22} w={1} h={4} fill={colors.light} opacity={0.75} />
      </g>
    );
  }

  if (id === 'sweater_gold') {
    return (
      <g>
        <R x={8} y={20} w={16} h={11} fill={colors.dark} />
        <R x={8} y={21} w={16} h={9} fill={colors.main} />
        <R x={9} y={20} w={14} h={2} fill={colors.dark} />
        <R x={8} y={23} w={16} h={1} fill={colors.light} />
        <R x={8} y={26} w={16} h={1} fill={colors.dark} />
        <R x={8} y={29} w={16} h={1} fill={colors.light} />
        <R x={14} y={24} w={4} h={1} fill={colors.dark} />
        <R x={16} y={23} w={1} h={3} fill={colors.dark} />
        <R x={16} y={24} w={1} h={1} fill={colors.light} />
        <R x={5} y={21} w={3} h={8} fill={colors.main} />
        <R x={24} y={21} w={3} h={8} fill={colors.main} />
        <R x={5} y={23} w={3} h={1} fill={colors.light} />
        <R x={24} y={23} w={3} h={1} fill={colors.light} />
        <R x={5} y={27} w={3} h={2} fill={colors.dark} />
        <R x={24} y={27} w={3} h={2} fill={colors.dark} />
        <R x={5} y={29} w={3} h={2} fill={skin.base} />
        <R x={24} y={29} w={3} h={2} fill={skin.base} />
      </g>
    );
  }

  if (id === 'jacket_blue') {
    return (
      <g>
        <R x={8} y={20} w={16} h={11} fill={colors.dark} />
        <R x={9} y={21} w={14} h={9} fill={colors.main} />
        <R x={13} y={20} w={6} h={10} fill={colors.accent} />
        <R x={13} y={20} w={1} h={10} fill={colors.dark} />
        <R x={18} y={20} w={1} h={10} fill={colors.dark} />
        <R x={9} y={20} w={4} h={2} fill={colors.dark} />
        <R x={19} y={20} w={4} h={2} fill={colors.dark} />
        <R x={9} y={26} w={3} h={2} fill={colors.dark} />
        <R x={20} y={26} w={3} h={2} fill={colors.dark} />
        <R x={8} y={29} w={16} h={1} fill={colors.dark} />
        <R x={5} y={21} w={3} h={8} fill={colors.main} />
        <R x={24} y={21} w={3} h={8} fill={colors.main} />
        <R x={5} y={27} w={3} h={2} fill={colors.dark} />
        <R x={24} y={27} w={3} h={2} fill={colors.dark} />
        <R x={5} y={29} w={3} h={2} fill={skin.base} />
        <R x={24} y={29} w={3} h={2} fill={skin.base} />
        <R x={9} y={21} w={1} h={5} fill={colors.light} opacity={0.55} />
      </g>
    );
  }

  // hoodie (violet or cyan)
  return (
    <g>
      <R x={9} y={19} w={4} h={3} fill={colors.dark} />
      <R x={19} y={19} w={4} h={3} fill={colors.dark} />
      <R x={8} y={20} w={16} h={11} fill={colors.dark} />
      <R x={8} y={21} w={16} h={9} fill={colors.main} />
      <R x={9} y={20} w={14} h={2} fill={colors.main} />
      <R x={8} y={29} w={16} h={1} fill={colors.dark} />
      <R x={12} y={25} w={8} h={3} fill={colors.dark} />
      <R x={13} y={25} w={6} h={1} fill={colors.light} opacity={0.5} />
      <R x={14} y={20} w={1} h={3} fill={colors.light} />
      <R x={18} y={20} w={1} h={3} fill={colors.light} />
      <R x={19} y={23} w={1} h={1} fill={colors.accent} />
      <R x={5} y={21} w={3} h={8} fill={colors.main} />
      <R x={24} y={21} w={3} h={8} fill={colors.main} />
      <R x={5} y={27} w={3} h={2} fill={colors.dark} />
      <R x={24} y={27} w={3} h={2} fill={colors.dark} />
      <R x={5} y={29} w={3} h={2} fill={skin.base} />
      <R x={24} y={29} w={3} h={2} fill={skin.base} />
      <R x={9} y={21} w={2} h={3} fill={colors.light} opacity={0.4} />
    </g>
  );
}

function Accessory({ id }: { id: string }) {
  if (id === 'glasses') {
    return (
      <g>
        <R x={12} y={10} w={5} h={1} fill="#102331" />
        <R x={12} y={13} w={5} h={1} fill="#102331" />
        <R x={12} y={11} w={1} h={2} fill="#102331" />
        <R x={16} y={11} w={1} h={2} fill="#102331" />
        <R x={17} y={10} w={5} h={1} fill="#102331" />
        <R x={17} y={13} w={5} h={1} fill="#102331" />
        <R x={17} y={11} w={1} h={2} fill="#102331" />
        <R x={21} y={11} w={1} h={2} fill="#102331" />
        <R x={16} y={11} w={1} h={1} fill="#102331" />
        <R x={13} y={11} w={3} h={2} fill="#7de8f7" opacity={0.3} />
        <R x={18} y={11} w={3} h={2} fill="#7de8f7" opacity={0.3} />
        <R x={13} y={11} w={1} h={1} fill="#ffffff" opacity={0.9} />
        <R x={18} y={11} w={1} h={1} fill="#ffffff" opacity={0.9} />
      </g>
    );
  }
  if (id === 'headphones') {
    return (
      <g>
        <R x={10} y={1} w={12} h={2} fill="#251238" />
        <R x={8} y={3} w={2} h={4} fill="#251238" />
        <R x={22} y={3} w={2} h={4} fill="#251238" />
        <R x={10} y={2} w={11} h={1} fill="#a855f7" />
        <R x={8} y={9} w={3} h={6} fill="#251238" />
        <R x={23} y={9} w={3} h={6} fill="#251238" />
        <R x={9} y={10} w={2} h={4} fill="#8b5cf6" />
        <R x={23} y={10} w={2} h={4} fill="#8b5cf6" />
        <R x={9} y={11} w={1} h={2} fill="#67e8f9" />
        <R x={24} y={11} w={1} h={2} fill="#67e8f9" />
      </g>
    );
  }
  if (id === 'cap') {
    return (
      <g>
        <R x={9} y={2} w={14} h={1} fill="#0e4152" />
        <R x={10} y={3} w={12} h={4} fill="#0e7490" />
        <R x={11} y={3} w={9} h={3} fill="#22d3ee" />
        <R x={7} y={7} w={19} h={2} fill="#0e4152" />
        <R x={8} y={7} w={17} h={1} fill="#67e8f9" />
        <R x={14} y={3} w={2} h={2} fill="#a5f3fc" />
        <R x={15} y={1} w={1} h={2} fill="#0e4152" />
      </g>
    );
  }
  if (id === 'crown') {
    return (
      <g>
        <R x={9} y={2} w={14} h={3} fill="#7a4b08" />
        <R x={10} y={1} w={2} h={2} fill="#7a4b08" />
        <R x={15} y={0} w={2} h={2} fill="#7a4b08" />
        <R x={20} y={1} w={2} h={2} fill="#7a4b08" />
        <R x={10} y={2} w={12} h={2} fill="#fbbf24" />
        <R x={10} y={1} w={1} h={2} fill="#fde68a" />
        <R x={15} y={0} w={1} h={2} fill="#fde68a" />
        <R x={20} y={1} w={1} h={2} fill="#fde68a" />
        <R x={12} y={3} w={1} h={1} fill="#f472b6" />
        <R x={15} y={3} w={1} h={1} fill="#22d3ee" />
        <R x={18} y={3} w={1} h={1} fill="#f472b6" />
      </g>
    );
  }
  if (id === 'halo') {
    return (
      <g>
        <R x={11} y={0} w={10} h={1} fill="#fde68a" opacity={0.5} />
        <R x={9} y={1} w={14} h={1} fill="#fbbf24" />
        <R x={8} y={2} w={2} h={1} fill="#fde68a" />
        <R x={22} y={2} w={2} h={1} fill="#fde68a" />
        <R x={10} y={1} w={12} h={1} fill="#fff7cc" />
      </g>
    );
  }
  if (id === 'scarf') {
    return (
      <g>
        <R x={10} y={17} w={12} h={2} fill="#9d174d" />
        <R x={10} y={17} w={12} h={1} fill="#f472b6" />
        <R x={19} y={19} w={3} h={6} fill="#9d174d" />
        <R x={20} y={19} w={1} h={5} fill="#f472b6" />
        <R x={19} y={24} w={3} h={1} fill="#f9a8d4" />
        <R x={11} y={19} w={1} h={2} fill="#f9a8d4" opacity={0.8} />
      </g>
    );
  }
  return null;
}

export function PixelHero({
  avatar,
  size,
  className,
  decorative = false,
  animate = false,
  view,
}: PixelHeroProps) {
  const skin = SKIN[avatar.skin] ?? SKIN.skin_light;
  const hair = HAIR[avatar.hairColor] ?? HAIR.hair_dark;
  const outfitId =
    OUTFIT[avatar.outfit] || isNewOutfit(avatar.outfit) ? avatar.outfit : 'hoodie_violet';
  const hairStyle = [
    'hair_short',
    'hair_curls',
    'hair_bob',
    'hair_pony',
    'hair_buzz',
    'hair_long',
    'hair_bald',
    'hair_afro',
    'hair_braids',
    'hair_mohawk',
  ].includes(avatar.hair)
    ? avatar.hair
    : 'hair_short';
  const hat = avatar.hat && avatar.hat !== 'hat_none' ? avatar.hat : null;
  const face = avatar.face && avatar.face !== 'face_none' ? avatar.face : null;
  // Старые «головные» аксессуары уступают место новым слотам hat и face.
  const legacy =
    (hat && ['cap', 'crown', 'halo'].includes(avatar.accessory)) ||
    (face && avatar.accessory === 'glasses')
      ? 'none'
      : avatar.accessory;
  const crop = view ? HERO_VIEWS[view] : null;
  const vb = crop
    ? { x: crop.x0, y: crop.y0, w: crop.x1 - crop.x0, h: crop.y1 - crop.y0 }
    : { x: 0, y: 0, w: 32, h: 42 };

  return (
    <svg
      viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
      className={className}
      style={{
        width: size ? `${size}px` : '100%',
        height: size ? `${(size * vb.h) / vb.w}px` : 'auto',
        display: 'block',
        overflow: view ? 'hidden' : 'visible',
      }}
      shapeRendering="crispEdges"
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : 'Аватар школьного героя'}
      aria-hidden={decorative ? true : undefined}
    >
      {animate ? (
        <style>{`
          @keyframes pixel-hero-bob {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-1.5px); }
          }
          .pixel-hero-bob { animation: pixel-hero-bob 3.6s ease-in-out infinite; }
          @media (prefers-reduced-motion: reduce) { .pixel-hero-bob { animation: none; } }
        `}</style>
      ) : null}
      <g className={animate ? 'pixel-hero-bob' : undefined}>
        <BackItems outfit={outfitId} accessory={avatar.accessory} />
        <BackHair style={hairStyle} colors={hair} />

        {/* silhouette */}
        <g fill={OUTLINE}>
          <R x={11} y={3} w={10} h={1} fill={OUTLINE} />
          <R x={9} y={4} w={14} h={2} fill={OUTLINE} />
          <R x={8} y={6} w={16} h={11} fill={OUTLINE} />
          <R x={9} y={17} w={14} h={1} fill={OUTLINE} />
          <R x={11} y={18} w={10} h={1} fill={OUTLINE} />
          <R x={13} y={18} w={6} h={3} fill={OUTLINE} />
          <R x={7} y={20} w={18} h={11} fill={OUTLINE} />
          <R x={8} y={31} w={16} h={1} fill={OUTLINE} />
          <R x={4} y={21} w={4} h={9} fill={OUTLINE} />
          <R x={24} y={21} w={4} h={9} fill={OUTLINE} />
          <R x={4} y={29} w={4} h={3} fill={OUTLINE} />
          <R x={24} y={29} w={4} h={3} fill={OUTLINE} />
          <R x={9} y={31} w={7} h={8} fill={OUTLINE} />
          <R x={16} y={31} w={7} h={8} fill={OUTLINE} />
          <R x={8} y={38} w={8} h={3} fill={OUTLINE} />
          <R x={16} y={38} w={8} h={3} fill={OUTLINE} />
        </g>

        {/* legs and shoes */}
        <R x={10} y={31} w={5} h={7} fill={PANTS} />
        <R x={17} y={31} w={5} h={7} fill={PANTS} />
        <R x={10} y={33} w={5} h={1} fill={PANTS_DARK} />
        <R x={17} y={33} w={5} h={1} fill={PANTS_DARK} />
        <R x={9} y={38} w={6} h={2} fill={SHOE} />
        <R x={17} y={38} w={6} h={2} fill={SHOE} />
        <R x={9} y={38} w={6} h={1} fill="#33204a" />
        <R x={17} y={38} w={6} h={1} fill="#33204a" />

        <Outfit id={outfitId} skin={skin} />

        {/* neck */}
        <R x={14} y={17} w={4} h={4} fill={skin.base} />
        <R x={14} y={19} w={4} h={1} fill={skin.shadow} />

        {/* head */}
        <R x={10} y={5} w={12} h={11} fill={skin.base} />
        <R x={11} y={16} w={10} h={1} fill={skin.shadow} />
        <R x={8} y={10} w={2} h={4} fill={skin.base} />
        <R x={22} y={10} w={2} h={4} fill={skin.base} />
        <R x={8} y={11} w={1} h={2} fill={skin.shadow} />
        <R x={23} y={11} w={1} h={2} fill={skin.shadow} />
        <R x={10} y={5} w={1} h={11} fill={skin.shadow} opacity={0.28} />

        {/* eyebrows, eyes, mouth */}
        <R x={12} y={9} w={3} h={1} fill={hair.dark} />
        <R x={18} y={9} w={3} h={1} fill={hair.dark} />
        <R x={13} y={11} w={2} h={3} fill={EYE} />
        <R x={19} y={11} w={2} h={3} fill={EYE} />
        <R x={13} y={11} w={1} h={1} fill="#fff7ff" />
        <R x={19} y={11} w={1} h={1} fill="#fff7ff" />
        <R x={16} y={13} w={1} h={1} fill={skin.line} opacity={0.65} />
        <R x={15} y={15} w={2} h={1} fill={MOUTH} />
        <R x={17} y={15} w={1} h={1} fill={MOUTH} opacity={0.7} />
        <R x={11} y={14} w={2} h={1} fill={skin.blush} opacity={0.7} />
        <R x={21} y={14} w={2} h={1} fill={skin.blush} opacity={0.7} />
        {avatar.hairColor === 'hair_ginger' || avatar.hairColor === 'hair_brown' ? (
          <g fill={skin.line} opacity={0.55}>
            <R x={11} y={13} w={1} h={1} fill={skin.line} />
            <R x={13} y={14} w={1} h={1} fill={skin.line} />
            <R x={21} y={13} w={1} h={1} fill={skin.line} />
            <R x={19} y={14} w={1} h={1} fill={skin.line} />
          </g>
        ) : null}

        <FrontHair style={hairStyle} colors={hair} skin={skin.base} />
        {face ? <FaceLayer id={face} /> : null}
        <Accessory id={legacy} />
        <AccessoryFront id={avatar.accessory} />
        {hat ? <HatLayer id={hat} /> : null}
      </g>
    </svg>
  );
}
