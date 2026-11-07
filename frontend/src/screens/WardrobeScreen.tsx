import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent } from 'react';
import { AvatarFrame, frameUnit } from '../components/AvatarFrame';
import { HERO_GRID, HERO_PARTS, PixelHero } from '../components/PixelHero';
import { ScreenTitle } from '../components/ScreenTitle';
import { formatSparks } from '../game';
import { tapHaptic } from '../max';
import type { AvatarConfig, Cosmetic, GameState } from '../types';
import '../styles/wardrobe.css';

export type WardrobeZone =
  | 'hair'
  | 'hair_color'
  | 'outfit'
  | 'hat'
  | 'face'
  | 'accessory'
  | 'skin'
  | 'frame';

const ZONES: { id: WardrobeZone; label: string; avatarKey: keyof AvatarConfig }[] = [
  { id: 'hair', label: 'Причёска', avatarKey: 'hair' },
  { id: 'hair_color', label: 'Цвет волос', avatarKey: 'hairColor' },
  { id: 'skin', label: 'Кожа', avatarKey: 'skin' },
  { id: 'outfit', label: 'Одежда', avatarKey: 'outfit' },
  { id: 'hat', label: 'Шапки', avatarKey: 'hat' },
  { id: 'face', label: 'Лицо', avatarKey: 'face' },
  { id: 'accessory', label: 'Аксессуары', avatarKey: 'accessory' },
  { id: 'frame', label: 'Рамки', avatarKey: 'frame' },
];

/* ---------- Камера ----------
 * Мир камеры = квадрат AvatarFrame со стороной S = min(ширина, высота сцены).
 * Рамка отступает t = 4·frameUnit(S) px с каждой стороны (styles/frames.css), внутри
 * область I = S - 2t; герой занимает 72% ширины I, центрирован по горизонтали и
 * прижат к низу с отступом 5% I. Размер клетки сетки героя u = 0.72·I / HERO_GRID.w,
 * левый верх героя = (t + 0.14·I, t + 0.005·I).
 * Прямоугольник интереса (в клетках) переводим в пиксели мира, масштаб k подбираем
 * так, чтобы он вписался в сцену с запасом PAD, и сдвигаем его центр в центр сцены.
 */
type Rect = { x0: number; y0: number; x1: number; y1: number };
type Box = { w: number; h: number };

const CAMERA_PAD = 0.92;
const MAX_SCALE = 4;

function cameraTransform(rect: Rect | 'portrait', box: Box): { world: CSSProperties; side: number } {
  const S = Math.max(1, Math.min(box.w, box.h));
  const left = (box.w - S) / 2;
  const top = (box.h - S) / 2;
  let px0 = 0;
  let py0 = 0;
  let px1 = S;
  let py1 = S;
  let pad = 1;
  if (rect !== 'portrait') {
    const t = 4 * frameUnit(S);
    const I = S - 2 * t;
    const u = (0.72 * I) / HERO_GRID.w;
    const ox = t + 0.14 * I;
    const oy = t + 0.005 * I;
    px0 = ox + rect.x0 * u;
    px1 = ox + rect.x1 * u;
    py0 = oy + rect.y0 * u;
    py1 = oy + rect.y1 * u;
    pad = CAMERA_PAD;
  }
  const k = Math.min(
    MAX_SCALE,
    Math.max(1, pad * Math.min(box.w / (px1 - px0), box.h / (py1 - py0))),
  );
  const cx = (px0 + px1) / 2;
  const cy = (py0 + py1) / 2;
  const tx = box.w / 2 - left - k * cx;
  const ty = box.h / 2 - top - k * cy;
  return {
    side: S,
    world: {
      left,
      top,
      width: S,
      height: S,
      transform: `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${k.toFixed(4)})`,
    },
  };
}

const NECK_ITEMS = ['scarf', 'bowtie', 'tie', 'necklace', 'medal', 'badge'];
const BODY_ITEMS = ['wings', 'cape', 'backpack'];

/** Какой частью героя показывать предмет: и для камеры, и для миниатюры. */
function viewFor(zone: WardrobeZone, itemId: string): keyof typeof HERO_PARTS | 'portrait' {
  switch (zone) {
    case 'hair':
    case 'hair_color':
    case 'hat':
      return 'head';
    case 'face':
    case 'skin':
      return 'face';
    case 'outfit':
      return 'torso';
    case 'accessory':
      if (NECK_ITEMS.includes(itemId)) return 'neck';
      if (BODY_ITEMS.includes(itemId)) return 'body';
      return 'head';
    default:
      return 'portrait';
  }
}

function rectFor(zone: WardrobeZone, itemId: string): Rect | 'portrait' {
  const view = viewFor(zone, itemId);
  return view === 'portrait' ? 'portrait' : HERO_PARTS[view];
}

const RARITY_LABEL: Record<string, string> = {
  common: 'Обычное',
  rare: 'Редкое',
  epic: 'Эпическое',
  legendary: 'Легендарное',
};

/** Ширина миниатюры (px) так, чтобы кадр влез в 100x64. */
function thumbSize(view: keyof typeof HERO_PARTS): number {
  const p = HERO_PARTS[view];
  const w = p.x1 - p.x0;
  const h = p.y1 - p.y0;
  return Math.round(Math.min(100, (64 * w) / h));
}

type WardrobeScreenProps = {
  state: GameState;
  onEquip: (key: string, itemId: string) => Promise<boolean>;
  onBuy: (itemId: string) => Promise<boolean>;
  busyItem: string | null;
  onShare?: () => void;
};

export function WardrobeScreen({ state, onEquip, onBuy, busyItem }: WardrobeScreenProps) {
  const [zoneId, setZoneId] = useState<WardrobeZone>('hair');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hop, setHop] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const sceneRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const { viewer, cosmetics } = state;

  const zone = ZONES.find((z) => z.id === zoneId) ?? ZONES[0];
  // Порядок задаёт сервер (cosmetic_sort_key в backend/game.py), фильтр его сохраняет.
  const items = useMemo(() => cosmetics.filter((c) => c.type === zone.id), [cosmetics, zone.id]);
  const equippedId =
    viewer.avatar[zone.avatarKey] ?? (zone.id === 'hat' ? 'hat_none' : zone.id === 'face' ? 'face_none' : '');
  const selected = items.find((c) => c.id === selectedId) ?? null;
  const preview: AvatarConfig = selected
    ? { ...viewer.avatar, [zone.avatarKey]: selected.id }
    : viewer.avatar;
  // На вкладках волос головной убор временно снимаем, чтобы была видна причёска.
  const hairZone = zone.id === 'hair' || zone.id === 'hair_color';
  const hatHidden = hairZone && (viewer.avatar.hat ?? 'hat_none') !== 'hat_none';
  const sceneAvatar: AvatarConfig = hairZone ? { ...preview, hat: 'hat_none' } : preview;

  useLayoutEffect(() => {
    const el = sceneRef.current;
    if (!el) return undefined;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const focusId = String(preview[zone.avatarKey] ?? '');
  const camera = box ? cameraTransform(rectFor(zone.id, focusId), box) : null;

  const canBuy = (item: Cosmetic) =>
    !item.unlocked && !item.owned && item.price > 0 && viewer.level.level >= item.unlock_level;

  const changeZone = (id: WardrobeZone) => {
    tapHaptic();
    setZoneId(id);
    setSelectedId(null);
  };

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = ZONES.findIndex((z) => z.id === zone.id);
    let next = -1;
    if (e.key === 'ArrowRight') next = (idx + 1) % ZONES.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + ZONES.length) % ZONES.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = ZONES.length - 1;
    if (next < 0) return;
    e.preventDefault();
    const target = ZONES[next];
    changeZone(target.id);
    tabRefs.current[target.id]?.focus();
  };

  const equip = async (item: Cosmetic) => {
    tapHaptic();
    if (await onEquip(zone.avatarKey, item.id)) setSelectedId(null);
  };

  const buy = async (item: Cosmetic) => {
    tapHaptic();
    if (await onBuy(item.id)) {
      await onEquip(zone.avatarKey, item.id);
      setSelectedId(null);
    }
  };

  const statusOf = (item: Cosmetic): { text: string; on: boolean } => {
    if (item.id === equippedId) return { text: 'Надето', on: true };
    if (item.unlocked) return { text: 'Доступно', on: false };
    if (viewer.level.level < item.unlock_level) {
      return { text: `С ${item.unlock_level} уровня`, on: false };
    }
    if (item.price > 0) return { text: formatSparks(item.price), on: false };
    return { text: 'Недоступно', on: false };
  };

  const isColorZone = zone.id === 'hair_color' || zone.id === 'skin';
  const trying = selected && selected.id !== equippedId ? selected : null;

  return (
    <div className="screen wd">
      <ScreenTitle title="Стиль" />

      <div className="wd-layout">
        <section className="wd-stage" aria-label="Предпросмотр героя">
          <div
            ref={sceneRef}
            className="wd-scene"
            role="img"
            aria-label={`Герой, камера: ${zone.label}`}
          >
            <div className="wd-world" style={camera ? camera.world : undefined}>
              <div className="wd-hop" key={hop}>
                <AvatarFrame
                  avatar={sceneAvatar}
                  size={camera ? camera.side : 240}
                  level={zone.id === 'frame' ? viewer.level.level : undefined}
                  decorative
                />
              </div>
            </div>
            <div className="wd-balance">
              <span>Искры</span>
              <strong>{formatSparks(viewer.sparks)}</strong>
            </div>
            {hatHidden ? <p className="wd-note">Шапка скрыта на время примерки</p> : null}
          </div>

          <div className="wd-tryon" data-active={trying ? 'true' : 'false'}>
            <p className="wd-tryon__text" role="status" aria-live="polite">
              {trying ? (
                <>
                  Примерка: <strong>{trying.name}</strong>
                </>
              ) : (
                'Выберите предмет, чтобы примерить'
              )}
            </p>
            {trying && (
              <div className="wd-tryon__actions">
                <button type="button" className="wd-btn" onClick={() => setSelectedId(null)}>
                  Отмена
                </button>
                {trying.unlocked ? (
                  <button
                    type="button"
                    className="wd-btn wd-btn--primary"
                    onClick={() => void equip(trying)}
                    disabled={busyItem === trying.id}
                  >
                    {busyItem === trying.id ? 'Сохраняем…' : 'Надеть'}
                  </button>
                ) : canBuy(trying) ? (
                  <button
                    type="button"
                    className="wd-btn wd-btn--primary"
                    onClick={() => void buy(trying)}
                    disabled={busyItem === trying.id || viewer.sparks < trying.price}
                  >
                    {viewer.sparks < trying.price
                      ? `Не хватает искр (${trying.price})`
                      : `Купить за ${trying.price}`}
                  </button>
                ) : null}
              </div>
            )}
          </div>
        </section>

        <section className="wd-catalog" aria-label="Каталог">
          <div
            className="wd-tabs"
            role="tablist"
            aria-label="Что менять"
            aria-orientation="horizontal"
            onKeyDown={onTabKey}
          >
            {ZONES.map((z) => (
              <button
                key={z.id}
                ref={(el) => {
                  tabRefs.current[z.id] = el;
                }}
                id={`wd-tab-${z.id}`}
                type="button"
                role="tab"
                aria-selected={zone.id === z.id}
                aria-controls="wd-panel"
                tabIndex={zone.id === z.id ? 0 : -1}
                className="wd-tab"
                onClick={() => changeZone(z.id)}
              >
                {z.label}
              </button>
            ))}
          </div>

          <div id="wd-panel" role="tabpanel" aria-labelledby={`wd-tab-${zone.id}`}>
            {items.length === 0 ? (
              <p className="wd-empty">В этой категории пока нет предметов.</p>
            ) : (
              <div className="wd-items">
                {items.map((item) => {
                  const status = statusOf(item);
                  const thumbAvatar = hairZone
                    ? { ...viewer.avatar, hat: 'hat_none', face: 'face_none', [zone.avatarKey]: item.id }
                    : { ...viewer.avatar, [zone.avatarKey]: item.id };
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className="wd-item"
                      aria-pressed={item.id === (selected?.id ?? equippedId)}
                      onClick={() => {
                        tapHaptic();
                        setSelectedId(item.id === equippedId ? null : item.id);
                        setHop((n) => n + 1);
                      }}
                    >
                      <span className="wd-item__thumb">
                        {isColorZone ? (
                          <span className="wd-swatch" style={{ backgroundColor: item.swatch }} />
                        ) : zone.id === 'frame' ? (
                          <AvatarFrame avatar={thumbAvatar} size={56} decorative />
                        ) : (
                          (() => {
                            const v = viewFor(zone.id, item.id);
                            const view = v === 'portrait' ? 'body' : v;
                            return (
                              <PixelHero
                                avatar={thumbAvatar}
                                size={thumbSize(view)}
                                view={view}
                                decorative
                              />
                            );
                          })()
                        )}
                      </span>
                      <span className="wd-item__name">{item.name}</span>
                      <span className={`wd-item__state${status.on ? ' wd-item__state--on' : ''}`}>
                        {status.text}
                      </span>
                      <span className={`wd-item__rarity wd-item__rarity--${item.rarity ?? 'common'}`}>
                        {RARITY_LABEL[item.rarity ?? 'common']}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
