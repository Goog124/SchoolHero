import { useState } from 'react';
import { Chip } from '../components/Chip';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { ScreenTitle } from '../components/ScreenTitle';
import { Segmented } from '../components/Segmented';
import { Sheet } from '../components/Sheet';
import {
  CATEGORY_META,
  daysFromNow,
  formatDeadline,
  formatNumber,
  toDateInput,
} from '../game';
import type {
  ChallengeCategory,
  ChallengeKind,
  GameState,
  TeacherChallenge,
  TeacherData,
} from '../types';

type FormState = {
  title: string;
  description: string;
  category: ChallengeCategory;
  xp: number;
  kind: ChallengeKind;
  deadline: string;
};

const initialForm = (): FormState => ({
  title: '',
  description: '',
  category: 'homework',
  xp: 20,
  kind: 'weekly',
  deadline: daysFromNow(3),
});

const CATEGORIES: ChallengeCategory[] = [
  'homework',
  'club',
  'help',
  'weekly',
  'olympiad',
  'event',
];

const XP_OPTIONS = [20, 30, 40, 50, 100];
const KIND_OPTIONS = [
  { id: 'daily' as ChallengeKind, label: 'На сегодня' },
  { id: 'weekly' as ChallengeKind, label: 'На неделю' },
  { id: 'event' as ChallengeKind, label: 'Событие' },
];

type TeacherChallengesScreenProps = {
  state: GameState;
  teacher: TeacherData;
  onCreate: (payload: {
    title: string;
    description: string;
    category: string;
    xp: number;
    kind: string;
    deadline: string;
  }) => Promise<boolean>;
  onArchive: (challengeId: number) => Promise<boolean>;
  busy: boolean;
};

export function TeacherChallengesScreen({
  state,
  teacher,
  onCreate,
  onArchive,
  busy,
}: TeacherChallengesScreenProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<FormState>(initialForm);
  const [error, setError] = useState('');
  const [archiveTarget, setArchiveTarget] = useState<TeacherChallenge | null>(null);
  const [archiving, setArchiving] = useState(false);

  const challenges = teacher.challenges;
  const totalPending = challenges.reduce((sum, item) => sum + item.pending_total, 0);
  const totalParticipants = challenges.reduce((sum, item) => sum + item.participants, 0);

  const openCreate = () => {
    setForm(initialForm());
    setError('');
    setCreateOpen(true);
  };

  const update = <K extends keyof FormState,>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError('');
  };

  const submit = async () => {
    if (form.title.trim().length < 3) {
      setError('Название должно быть от 3 до 80 символов');
      return;
    }
    const ok = await onCreate({
      title: form.title.trim(),
      description: form.description.trim(),
      category: form.category,
      xp: form.xp,
      kind: form.kind,
      deadline: form.deadline,
    });
    if (ok) {
      setCreateOpen(false);
      setForm(initialForm());
    }
  };

  const confirmArchive = async () => {
    if (!archiveTarget) return;
    setArchiving(true);
    const ok = await onArchive(archiveTarget.id);
    setArchiving(false);
    if (ok) setArchiveTarget(null);
  };

  return (
    <div className="screen">
      <ScreenTitle
        eyebrow="Конструктор заданий"
        title="Задания класса"
        subtitle={`${state.viewer.class_name} · создавай челленджи и следи за участием`}
        action={
          <button type="button" className="icon-btn icon-btn--accent" onClick={openCreate} aria-label="Создать задание">
            <Icon name="plus" size={19} />
          </button>
        }
      />

      <div className="teacher-stats-strip">
        <div>
          <span>активных</span>
          <strong>{challenges.length}</strong>
        </div>
        <div>
          <span>участников</span>
          <strong>{formatNumber(totalParticipants)}</strong>
        </div>
        <div className={totalPending ? 'is-warn' : ''}>
          <span>ждут проверки</span>
          <strong>{totalPending}</strong>
        </div>
      </div>

      <button type="button" className="create-banner" onClick={openCreate}>
        <span className="create-banner__icon">
          <Icon name="plus" size={20} />
        </span>
        <span>
          <strong>Новое задание</strong>
          <small>Домашка, помощь, олимпиада или событие — за 30 секунд</small>
        </span>
        <Icon name="chevronRight" size={18} />
      </button>

      {challenges.length ? (
        <div className="teacher-challenge-list">
          {challenges.map((challenge) => {
            const meta = CATEGORY_META[challenge.category];
            const progress = challenge.participants
              ? Math.round((challenge.approved_total / challenge.participants) * 100)
              : 0;
            return (
              <article key={challenge.id} className="teacher-challenge">
                <header className="teacher-challenge__head">
                  <span className={`category-mark tone-${meta.tone}`}>
                    <Icon name={meta.icon} size={18} />
                  </span>
                  <div className="teacher-challenge__title">
                    <span>
                      {challenge.category_label} · {challenge.kind_label}
                    </span>
                    <h3>{challenge.title}</h3>
                  </div>
                  <button
                    type="button"
                    className="icon-btn icon-btn--soft"
                    onClick={() => setArchiveTarget(challenge)}
                    aria-label={`Архивировать ${challenge.title}`}
                  >
                    <Icon name="archive" size={16} />
                  </button>
                </header>

                {challenge.description ? (
                  <p className="teacher-challenge__desc">{challenge.description}</p>
                ) : null}

                <div className="teacher-challenge__meta">
                  <Chip icon="clock" size="sm">
                    {formatDeadline(challenge.deadline)}
                  </Chip>
                  <Chip icon="spark" tone="gold" size="sm">
                    +{challenge.xp} XP
                  </Chip>
                  {challenge.pending_total ? (
                    <Chip icon="clock" tone="red" size="sm">
                      {challenge.pending_total} на проверке
                    </Chip>
                  ) : null}
                </div>

                <div className="teacher-challenge__progress">
                  <div>
                    <span>
                      <Icon name="users" size={13} /> {challenge.participants} участн.
                    </span>
                    <span>{challenge.approved_total} подтверждено</span>
                  </div>
                  <div className="micro-progress">
                    <span style={{ width: `${ProgressWidth(progress)}%` }} />
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon="list"
          title="Заданий пока нет"
          text="Создай первое задание — ученики увидят его сразу в своих челленджах."
          action={
            <button type="button" className="btn btn--sm" onClick={openCreate}>
              <Icon name="plus" size={16} /> Создать задание
            </button>
          }
        />
      )}

      <div className="review-note">
        <Icon name="info" size={16} />
        <span>
          Задание видят только ученики твоего класса. После архивации оно исчезает из
          списка, но история остаётся в опыте ребят.
        </span>
      </div>

      <Sheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Новое задание"
        subtitle={`Для класса ${state.viewer.class_name}`}
        footer={
          <button
            type="button"
            className="btn btn--block"
            onClick={submit}
            disabled={busy || form.title.trim().length < 3}
          >
            {busy ? 'Публикуем…' : 'Опубликовать задание'}
            {!busy ? <Icon name="send" size={16} /> : null}
          </button>
        }
      >
        <div className="create-form">
          <label className="field">
            <span>Название</span>
            <input
              value={form.title}
              onChange={(event) => update('title', event.target.value)}
              maxLength={80}
              placeholder="Например, прочитать главу по истории"
            />
            <small>{form.title.length} / 80</small>
          </label>

          <label className="field">
            <span>Описание</span>
            <textarea
              value={form.description}
              onChange={(event) => update('description', event.target.value)}
              maxLength={320}
              rows={3}
              placeholder="Что нужно сделать и как подтвердить результат"
            />
            <small>{form.description.length} / 320</small>
          </label>

          <div className="form-block">
            <span className="form-block__label">Категория</span>
            <div className="option-row option-row--wrap">
              {CATEGORIES.map((category) => {
                const meta = CATEGORY_META[category];
                return (
                  <button
                    key={category}
                    type="button"
                    className={`option-pill option-pill--icon ${
                      form.category === category ? 'is-active' : ''
                    }`.trim()}
                    onClick={() => update('category', category)}
                  >
                    <Icon name={meta.icon} size={14} />
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="form-block">
            <span className="form-block__label">Сколько XP</span>
            <div className="xp-options">
              {XP_OPTIONS.map((xp) => (
                <button
                  key={xp}
                  type="button"
                  className={`xp-option ${form.xp === xp ? 'is-active' : ''}`.trim()}
                  onClick={() => update('xp', xp)}
                >
                  +{xp}
                  <small>XP</small>
                </button>
              ))}
            </div>
          </div>

          <div className="form-block">
            <span className="form-block__label">Срок</span>
            <Segmented
              options={KIND_OPTIONS}
              value={form.kind}
              onChange={(kind) => update('kind', kind)}
              ariaLabel="Тип задания"
            />
          </div>

          <label className="field">
            <span>Выполнить до</span>
            <input
              type="date"
              value={form.deadline}
              min={toDateInput(new Date())}
              onChange={(event) => update('deadline', event.target.value)}
            />
          </label>

          {error ? <p className="form-error">{error}</p> : null}
        </div>
      </Sheet>

      <Sheet
        open={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        title="Архивировать задание?"
        subtitle={archiveTarget?.title}
        footer={
          <div className="sheet-actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setArchiveTarget(null)}
              disabled={archiving}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={confirmArchive}
              disabled={archiving}
            >
              {archiving ? 'Архивируем…' : 'В архив'}
            </button>
          </div>
        }
      >
        <p className="confirm-text">
          Ученики больше не увидят это задание. Уже подтверждённый опыт останется в их
          профилях и рейтинге класса.
        </p>
      </Sheet>
    </div>
  );
}

function ProgressWidth(value: number): number {
  return Math.max(0, Math.min(100, value));
}
