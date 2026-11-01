import { useMemo, useState } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Chip } from '../components/Chip';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { Segmented, type SegmentOption } from '../components/Segmented';
import { Sheet } from '../components/Sheet';
import { Starfield } from '../components/Starfield';
import { formatNumber } from '../game';
import type { AvatarConfig, Cosmetic, GameState } from '../types';

type WardrobeTab = 'skin' | 'hair' | 'hair_color' | 'outfit' | 'accessory' | 'frame';

const TABS: SegmentOption<WardrobeTab>[] = [
  { id: 'skin', label: 'Кожа' },
  { id: 'hair', label: 'Причёска' },
  { id: 'hair_color', label: 'Цвет' },
  { id: 'outfit', label: 'Одежда' },
  { id: 'accessory', label: 'Аксессуар' },
  { id: 'frame', label: 'Рама' },
];

const AVATAR_KEY: Record<WardrobeTab, keyof AvatarConfig> = {
  skin: 'skin',
  hair: 'hair',
  hair_color: 'hairColor',
  outfit: 'outfit',
  accessory: 'accessory',
  frame: 'frame',
};

const TYPE_LABEL: Record<WardrobeTab, string> = {
  skin: 'Оттенок кожи',
  hair: 'Причёска',
  hair_color: 'Цвет волос',
  outfit: 'Одежда',
  accessory: 'Аксессуар',
  frame: 'Рама героя',
};

type WardrobeScreenProps = {
  state: GameState;
  onEquip: (key: string, itemId: string) => Promise<boolean>;
  onBuy: (itemId: string) => Promise<boolean>;
  busyItem: string | null;
};

export function WardrobeScreen({ state, onEquip, onBuy, busyItem }: WardrobeScreenProps) {
  const [tab, setTab] = useState<WardrobeTab>('outfit');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { viewer, cosmetics } = state;
  const avatarKey = AVATAR_KEY[tab];

  const items = useMemo(
    () => cosmetics.filter((item) => item.type === tab),
    [cosmetics, tab],
  );
  const selected = selectedId
    ? (cosmetics.find((item) => item.id === selectedId) ?? null)
    : null;

  const currentId = viewer.avatar[avatarKey];
  const selectedPreview = selected
    ? { ...viewer.avatar, [avatarKey]: selected.id }
    : viewer.avatar;
  const unlockedCount = items.filter((item) => item.unlocked).length;

  const handleEquip = async (item: Cosmetic) => {
    const ok = await onEquip(avatarKey, item.id);
    if (ok) setSelectedId(null);
  };

  const handleBuy = async (item: Cosmetic) => {
    await onBuy(item.id);
  };

  const canBuy = (item: Cosmetic) =>
    !item.owned && item.price > 0 && viewer.level.level >= item.unlock_level;

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Гардероб героя"
        title="Стиль"
        subtitle="Новые образы открываются с уровнями. Искры трать на то, что нравится."
        action={
          <span className="sparks-balance">
            <Icon name="spark" size={15} filled />
            {formatNumber(viewer.sparks)}
          </span>
        }
      />

      <section className="wardrobe-preview">
        <Starfield />
        <div className="wardrobe-preview__figure">
          <span className="wardrobe-preview__glow" aria-hidden="true" />
          <AvatarFrame avatar={viewer.avatar} size={158} level={viewer.level.level} animate />
        </div>
        <div className="wardrobe-preview__info">
          <span className="panel-eyebrow">Сейчас на герое</span>
          <h2>{viewer.name}</h2>
          <p>
            Уровень {viewer.level.level} · {viewer.level.title}
          </p>
          <div className="wardrobe-preview__chips">
            <Chip icon="spark" tone="gold" size="sm">
              {formatNumber(viewer.sparks)} искр
            </Chip>
            <Chip icon="shirt" tone="violet" size="sm">
              {unlockedCount} из {items.length} в разделе
            </Chip>
          </div>
        </div>
      </section>

      <Segmented
        options={TABS}
        value={tab}
        onChange={(next) => {
          setTab(next);
          setSelectedId(null);
        }}
        ariaLabel="Разделы гардероба"
        scrollable
      />

      <div className="cosmetic-grid">
        {items.map((item) => {
          const equipped = item.id === currentId;
          const locked = !item.unlocked && !equipped;
          const preview = { ...viewer.avatar, [avatarKey]: item.id };
          return (
            <button
              key={item.id}
              type="button"
              className={`cosmetic-tile ${equipped ? 'is-equipped' : ''} ${
                locked ? 'is-locked' : ''
              }`.trim()}
              onClick={() => setSelectedId(item.id)}
            >
              <span className="cosmetic-tile__preview">
                <AvatarFrame avatar={preview} size={68} decorative />
                {equipped ? (
                  <span className="cosmetic-tile__check">
                    <Icon name="check" size={12} />
                  </span>
                ) : null}
                {locked && item.unlock_level > viewer.level.level ? (
                  <span className="cosmetic-tile__lock">
                    <Icon name="lock" size={11} /> {item.unlock_level}
                  </span>
                ) : null}
              </span>
              <span className="cosmetic-tile__name">{item.name}</span>
              <span className="cosmetic-tile__price">
                {equipped
                  ? 'Надето'
                  : canBuy(item)
                    ? `${item.price} искр`
                    : locked && item.unlock_level > viewer.level.level
                      ? `с ${item.unlock_level} ур.`
                      : item.price > 0
                        ? 'Куплено'
                        : 'Открыто'}
              </span>
            </button>
          );
        })}
      </div>

      <div className="wardrobe-tip">
        <span className="wardrobe-tip__icon">
          <Icon name="info" size={17} />
        </span>
        <p>
          За каждый новый уровень — <strong>25 искр</strong>, за подтверждённое задание —{' '}
          <strong>+5 искр</strong>. Коллекция не сгорает.
        </p>
      </div>

      <Sheet
        open={Boolean(selected)}
        onClose={() => setSelectedId(null)}
        title={selected?.name}
        subtitle={selected ? TYPE_LABEL[selected.type as WardrobeTab] : ''}
        footer={
          selected ? (
            selected.id === currentId ? (
              <button type="button" className="btn btn--block" disabled>
                <Icon name="check" size={17} /> Уже надето
              </button>
            ) : canBuy(selected) ? (
              <button
                type="button"
                className="btn btn--block"
                disabled={busyItem === selected.id}
                onClick={() => handleBuy(selected)}
              >
                {busyItem === selected.id ? 'Покупаем…' : `Купить за ${selected.price} искр`}
                {busyItem !== selected.id ? <Icon name="spark" size={16} filled /> : null}
              </button>
            ) : !selected.unlocked ? (
              <button type="button" className="btn btn--block" disabled>
                <Icon name="lock" size={16} /> Откроется на {selected.unlock_level} уровне
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--block"
                disabled={busyItem === selected.id}
                onClick={() => handleEquip(selected)}
              >
                {busyItem === selected.id ? 'Надеваем…' : 'Надеть'}
                {busyItem !== selected.id ? <Icon name="shirt" size={17} /> : null}
              </button>
            )
          ) : undefined
        }
      >
        {selected ? (
          <div className="wardrobe-sheet">
            <div className="wardrobe-sheet__art">
              <Starfield />
              <AvatarFrame avatar={selectedPreview} size={132} animate />
            </div>
            <p className="wardrobe-sheet__desc">
              {selected.description ||
                (selected.price === 0
                  ? 'Часть стартовой коллекции героя. Можно надеть в любой момент.'
                  : 'Стильный предмет для твоего героя.')}
            </p>
            <div className="wardrobe-sheet__facts">
              <Chip icon="spark" tone="gold" size="sm">
                {selected.price > 0 ? `${selected.price} искр` : 'Бесплатно'}
              </Chip>
              <Chip icon="lock" tone="violet" size="sm">
                с {selected.unlock_level} уровня
              </Chip>
              {selected.owned ? (
                <Chip icon="check" tone="lime" size="sm">
                  в коллекции
                </Chip>
              ) : null}
            </div>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
