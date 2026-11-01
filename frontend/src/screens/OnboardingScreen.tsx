import { useMemo, useState, type CSSProperties } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { Chip } from '../components/Chip';
import { Icon } from '../components/Icon';
import { Starfield } from '../components/Starfield';
import { firstName } from '../game';
import type { AvatarConfig, Cosmetic, GameState } from '../types';

type OnboardingScreenProps = {
  state: GameState;
  onComplete: (firstName: string, avatar: Record<string, string>) => Promise<boolean>;
};

const STEPS = ['Имя', 'Герой', 'Старт'];

export function OnboardingScreen({ state, onComplete }: OnboardingScreenProps) {
  const initial = state.viewer.first_name === 'Герой' ? '' : state.viewer.first_name;
  const [step, setStep] = useState(0);
  const [name, setName] = useState(initial);
  const [avatar, setAvatar] = useState<AvatarConfig>({ ...state.viewer.avatar });
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);

  const cosmetics = state.cosmetics;
  const pick = (type: Cosmetic['type'], ids?: string[]) =>
    cosmetics.filter(
      (item) =>
        item.type === type &&
        item.price === 0 &&
        item.unlock_level <= 1 &&
        (!ids || ids.includes(item.id)),
    );

  const skins = pick('skin');
  const hairs = pick('hair');
  const colors = pick('hair_color');
  const outfits = pick('outfit');
  const accessories = pick('accessory', ['none', 'glasses']);

  const trimmed = name.trim();
  const displayName = firstName(trimmed);
  const nameValid = trimmed.length >= 2 && trimmed.length <= 24;
  const canContinue = step === 0 ? nameValid : true;
  const previewAvatar = useMemo(() => avatar, [avatar]);

  const handleNext = () => {
    setTouched(true);
    if (step === 0 && !nameValid) return;
    setStep((current) => Math.min(2, current + 1));
  };

  const handleComplete = async () => {
    if (!nameValid) {
      setStep(0);
      return;
    }
    setBusy(true);
    await onComplete(trimmed, avatar);
    setBusy(false);
  };

  return (
    <div className="onboarding">
      <Starfield dense />
      <div className="onboarding__glow" aria-hidden="true" />

      <header className="onboarding__head">
        <span className="brand__mark">
          <Icon name="sword" size={19} />
          <span className="brand__spark" aria-hidden="true" />
        </span>
        <span className="brand__name">ШКОЛЬНЫЙ ГЕРОЙ</span>
      </header>

      <div className="onboarding__progress" aria-label="Шаги знакомства">
        {STEPS.map((label, index) => (
          <div
            key={label}
            className={`onboarding-step ${index === step ? 'is-active' : ''} ${
              index < step ? 'is-done' : ''
            }`.trim()}
          >
            <span className="onboarding-step__num">
              {index < step ? <Icon name="check" size={12} /> : index + 1}
            </span>
            <span className="onboarding-step__label">{label}</span>
          </div>
        ))}
      </div>

      <main className="onboarding__body">
        {step === 0 ? (
          <section className="onboarding__panel">
            <span className="onboarding__eyebrow">Знакомимся</span>
            <h1>
              Как тебя зовут, <span>герой</span>?
            </h1>
            <p className="onboarding__lead">
              Имя увидят одноклассники в рейтинге. Никаких фамилий и лишних данных —
              только то, что нужно для игры.
            </p>
            <label className="field">
              <span>Имя</span>
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setTouched(true);
                }}
                maxLength={24}
                placeholder="Например, Глеб"
                autoComplete="given-name"
                className={touched && !nameValid ? 'is-invalid' : ''}
              />
              <small>
                {touched && !nameValid
                  ? 'Нужно от 2 до 24 символов'
                  : 'Так тебя будут видеть в классе и рейтинге'}
              </small>
            </label>
            <div className="onboarding__preview">
              <AvatarFrame avatar={previewAvatar} size={92} decorative />
              <div>
                <strong>{nameValid ? displayName : 'Твой герой'}</strong>
                <span>1 уровень · Новичок</span>
                <span>{state.viewer.class_name} · {state.viewer.school_name}</span>
              </div>
            </div>
          </section>
        ) : null}

        {step === 1 ? (
          <section className="onboarding__panel">
            <span className="onboarding__eyebrow">Внешность</span>
            <h1>Собери своего героя</h1>
            <p className="onboarding__lead">
              Всё можно поменять позже в гардеробе. Новые образы откроются с уровнями.
            </p>

            <div className="onboarding__hero-preview">
              <span className="onboarding__hero-glow" aria-hidden="true" />
              <AvatarFrame avatar={previewAvatar} size={118} animate />
            </div>

            <div className="picker-block">
              <h3>Оттенок кожи</h3>
              <div className="swatch-row">
                {skins.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`swatch ${avatar.skin === item.id ? 'is-active' : ''}`.trim()}
                    style={{ '--swatch': item.swatch } as CSSProperties}
                    onClick={() => setAvatar((prev) => ({ ...prev, skin: item.id }))}
                    aria-label={item.name}
                    title={item.name}
                  >
                    <span />
                    {avatar.skin === item.id ? <Icon name="check" size={13} /> : null}
                  </button>
                ))}
              </div>
            </div>

            <div className="picker-block">
              <h3>Причёска</h3>
              <div className="hair-row">
                {hairs.map((item) => {
                  const preview = { ...avatar, hair: item.id };
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`hair-option ${avatar.hair === item.id ? 'is-active' : ''}`.trim()}
                      onClick={() => setAvatar((prev) => ({ ...prev, hair: item.id }))}
                    >
                      <AvatarFrame avatar={preview} size={44} decorative />
                      <span>{item.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="picker-block">
              <h3>Цвет волос</h3>
              <div className="swatch-row">
                {colors.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`swatch ${avatar.hairColor === item.id ? 'is-active' : ''}`.trim()}
                    style={{ '--swatch': item.swatch } as CSSProperties}
                    onClick={() => setAvatar((prev) => ({ ...prev, hairColor: item.id }))}
                    aria-label={item.name}
                    title={item.name}
                  >
                    <span />
                    {avatar.hairColor === item.id ? <Icon name="check" size={13} /> : null}
                  </button>
                ))}
              </div>
            </div>

            <div className="picker-block">
              <h3>Аксессуар</h3>
              <div className="option-row">
                {accessories.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`option-pill ${avatar.accessory === item.id ? 'is-active' : ''}`.trim()}
                    onClick={() => setAvatar((prev) => ({ ...prev, accessory: item.id }))}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="picker-block">
              <h3>Одежда</h3>
              <div className="option-row">
                {outfits.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`option-pill ${avatar.outfit === item.id ? 'is-active' : ''}`.trim()}
                    onClick={() => setAvatar((prev) => ({ ...prev, outfit: item.id }))}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
              <p className="picker-note">
                <Icon name="lock" size={13} /> Ещё 6 образов откроются на уровнях 2–5.
              </p>
            </div>
          </section>
        ) : null}

        {step === 2 ? (
          <section className="onboarding__panel onboarding__panel--ready">
            <span className="onboarding__eyebrow">Готово к старту</span>
            <h1>
              Герой готов, <span>{displayName}</span>!
            </h1>
            <p className="onboarding__lead">
              Первый уровень уже твой. Выполняй задания, помогай классу и собирай искры.
            </p>

            <div className="ready-card">
              <Starfield />
              <span className="ready-card__glow" aria-hidden="true" />
              <AvatarFrame avatar={previewAvatar} size={152} level={1} animate />
              <div className="ready-card__name">{displayName}</div>
              <div className="ready-card__chips">
                <Chip icon="star" tone="violet" size="sm">
                  Новичок
                </Chip>
                <Chip icon="users" tone="cyan" size="sm">
                  {state.viewer.class_name}
                </Chip>
                <Chip icon="spark" tone="gold" size="sm">
                  40 искр
                </Chip>
              </div>
            </div>

            <div className="ready-facts">
              <div>
                <Icon name="target" size={18} />
                <span>
                  <strong>Твоя цель</strong>
                  <small>100 XP до второго уровня</small>
                </span>
              </div>
              <div>
                <Icon name="shield" size={18} />
                <span>
                  <strong>Педагог рядом</strong>
                  <small>Подтвердит задания в один тап</small>
                </span>
              </div>
              <div>
                <Icon name="trophy" size={18} />
                <span>
                  <strong>Класс в игре</strong>
                  <small>{state.class_sprint.members} учеников уже в спринте</small>
                </span>
              </div>
            </div>
          </section>
        ) : null}
      </main>

      <footer className="onboarding__footer">
        {step > 0 ? (
          <button
            type="button"
            className="btn btn--ghost onboarding__back"
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={busy}
          >
            <Icon name="arrowLeft" size={17} />
            Назад
          </button>
        ) : (
          <span className="onboarding__hint">
            <Icon name="shield" size={14} /> Безопасно и без лишних данных
          </span>
        )}
        {step < 2 ? (
          <button
            type="button"
            className="btn onboarding__next"
            onClick={handleNext}
            disabled={!canContinue}
          >
            Дальше
            <Icon name="chevronRight" size={17} />
          </button>
        ) : (
          <button
            type="button"
            className="btn onboarding__next"
            onClick={handleComplete}
            disabled={busy}
          >
            {busy ? 'Создаём героя…' : 'Начать путь'}
            {!busy ? <Icon name="play" size={16} /> : null}
          </button>
        )}
      </footer>
    </div>
  );
}
