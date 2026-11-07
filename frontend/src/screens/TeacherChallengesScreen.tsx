import { useId, useState } from 'react';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { DeadlineInfo, RewardXpInfo } from '../components/infoTexts';
import { ScreenTitle } from '../components/ScreenTitle';
import { Sheet } from '../components/Sheet';
import { daysFromNow, formatDeadline, formatNumber, plural } from '../game';
import type {
  ChallengeCategory,
  ChallengeKind,
  GameState,
  TeacherChallenge,
  TeacherData,
} from '../types';
import '../styles/teacher.css';

type ProofType = 'text' | 'link' | 'photo';

type FormState = {
  title: string;
  description: string;
  category: ChallengeCategory;
  subject: string;
  xp: string;
  subjectOther: string;
  term: Term;
  deadline: string;
  proof_type: ProofType;
};

type FormErrors = Partial<Record<'title' | 'xp' | 'deadline' | 'description' | 'subject', string>>;

const initialForm = (): FormState => ({
  title: '',
  description: '',
  category: 'homework',
  subject: '',
  xp: '50',
  subjectOther: '',
  term: 'week',
  deadline: daysFromNow(3),
  proof_type: 'text',
});

// Значение списка предметов для темы вне списка: сервер ждёт текст в subject_other.
const SUBJECT_OTHER = 'Другое';

const CATEGORIES: { id: ChallengeCategory; label: string }[] = [
  { id: 'homework', label: 'Учебное задание' },
  { id: 'olympiad', label: 'Олимпиада или конкурс' },
  { id: 'club', label: 'Кружок и внеурочная деятельность' },
  { id: 'help', label: 'Волонтёрство и взаимопомощь' },
  { id: 'weekly', label: 'Задание недели' },
  { id: 'event', label: 'Школьное событие' },
];

type Term = 'today' | 'week' | 'date';

// «Срок» вместо периодичности: kind сохраняется как раньше, дедлайн без даты подставляет сервер.
const TERMS: { id: Term; label: string; kind: ChallengeKind }[] = [
  { id: 'today', label: 'Сегодня', kind: 'daily' },
  { id: 'week', label: 'До конца недели', kind: 'weekly' },
  { id: 'date', label: 'Своя дата', kind: 'event' },
];

const PROOF_TYPES: { id: ProofType; label: string }[] = [
  { id: 'text', label: 'Текст' },
  { id: 'link', label: 'Ссылка' },
  { id: 'photo', label: 'Фото' },
];

const XP_MIN = 10;
const XP_MAX = 300;

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
    subject?: string;
    subject_other?: string;
    proof_type?: ProofType;
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
  const uid = useId();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<FormState>(initialForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [archiveTarget, setArchiveTarget] = useState<TeacherChallenge | null>(null);
  const [archiving, setArchiving] = useState(false);

  const challenges = teacher.challenges;
  const totalPending = challenges.reduce((sum, c) => sum + c.pending_total, 0);
  const totalApproved = challenges.reduce((sum, c) => sum + c.approved_total, 0);

  const openCreate = () => {
    setForm(initialForm());
    setErrors({});
    setCreateOpen(true);
  };

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const validate = (): FormErrors => {
    const next: FormErrors = {};
    const title = form.title.trim();
    if (title.length < 3 || title.length > 80) next.title = 'Название: от 3 до 80 символов.';
    const xp = Number(form.xp);
    if (!Number.isInteger(xp) || xp < XP_MIN || xp > XP_MAX) {
      next.xp = `Награда: целое число от ${XP_MIN} до ${XP_MAX}.`;
    }
    if (form.subject === SUBJECT_OTHER) {
      const other = form.subjectOther.trim();
      if (other.length < 2 || other.length > 40) next.subject = 'Название предмета: от 2 до 40 символов.';
    }
    if (form.term !== 'date') {
      // Срок подставит сервер.
    } else if (!form.deadline) {
      next.deadline = 'Укажите срок сдачи.';
    } else if (form.deadline < daysFromNow(0)) {
      next.deadline = 'Срок сдачи не может быть в прошлом.';
    }
    if (form.description.length > 320) next.description = 'Описание: не более 320 символов.';
    return next;
  };

  const submit = async () => {
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;
    const ok = await onCreate({
      title: form.title.trim(),
      description: form.description.trim(),
      category: form.category,
      xp: Number(form.xp),
      kind: TERMS.find((t) => t.id === form.term)?.kind ?? 'weekly',
      deadline: form.term === 'date' ? form.deadline : '',
      subject: form.subject || undefined,
      subject_other: form.subject === SUBJECT_OTHER ? form.subjectOther.trim() : undefined,
      proof_type: form.proof_type,
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

  const fieldId = (name: string) => `${uid}-${name}`;
  const describe = (name: keyof FormErrors) => (errors[name] ? `${fieldId(name)}-err` : undefined);

  return (
    <div className="screen tc-page">
      <ScreenTitle
        title="Задания"
        subtitle={`Класс ${state.viewer.class_name}`}
        action={
          <button type="button" className="tc-btn tc-btn--primary" onClick={openCreate}>
            <Icon name="plus" size={16} />
            Новое задание
          </button>
        }
      />

      <div className="tc-stats tc-stats--3">
        <div className="tc-stat">
          <span className="tc-stat__label">Активных заданий</span>
          <span className="tc-stat__value">{challenges.length}</span>
        </div>
        <div className={`tc-stat ${totalPending ? 'tc-stat--warn' : ''}`}>
          <span className="tc-stat__label">На проверке</span>
          <span className="tc-stat__value">{totalPending}</span>
        </div>
        <div className="tc-stat">
          <span className="tc-stat__label">Подтверждено</span>
          <span className="tc-stat__value">{totalApproved}</span>
        </div>
      </div>

      {challenges.length > 0 ? (
        <div className="tc-panel tc-panel--flush">
          <div className="tc-table-wrap">
            <table className="tc-table">
              <caption>Активные задания класса</caption>
              <thead>
                <tr>
                  <th scope="col">Задание</th>
                  <th scope="col">Срок</th>
                  <th scope="col" className="tc-r">
                    Награда
                  </th>
                  <th scope="col" className="tc-r">
                    Сдали
                  </th>
                  <th scope="col" className="tc-r">
                    На проверке
                  </th>
                  <th scope="col">
                    <span className="tc-sr">
                      Действия
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {challenges.map((c) => (
                  <tr key={c.id}>
                    <td className="tc-cell--main">
                      <strong>{c.title}</strong>
                      <div className="tc-faint">
                        {[c.subject, c.category_label].filter(Boolean).join(' · ')}
                      </div>
                      {c.description ? (
                        <div className="tc-muted tc-clamp">{c.description}</div>
                      ) : null}
                    </td>
                    <td data-label="Срок">
                      {c.kind_label ? <strong>{c.kind_label}</strong> : null}
                      <div className="tc-faint">{c.deadline ? formatDeadline(c.deadline) : 'Без срока'}</div>
                    </td>
                    <td data-label="Награда" className="tc-r tc-num">
                      {c.xp} XP
                    </td>
                    <td data-label="Сдали" className="tc-r tc-num">
                      {formatNumber(c.participants)}
                    </td>
                    <td data-label="На проверке" className="tc-r tc-num">
                      {c.pending_total > 0 ? (
                        <span className="tc-badge tc-badge--warn">{c.pending_total}</span>
                      ) : (
                        0
                      )}
                    </td>
                    <td className="tc-cell--actions">
                      <div className="tc-actions">
                        <button
                          type="button"
                          className="tc-btn tc-btn--sm"
                          onClick={() => setArchiveTarget(c)}
                          aria-label={`В архив: ${c.title}`}
                        >
                          <Icon name="archive" size={16} />
                          В архив
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <EmptyState
          icon="list"
          title="Нет активных заданий"
          text="Создайте задание: ученики класса увидят его в своём списке."
          action={
            <button type="button" className="tc-btn tc-btn--primary" onClick={openCreate}>
              <Icon name="plus" size={16} />
              Новое задание
            </button>
          }
        />
      )}

      {/* Создание задания */}
      <Sheet
        open={createOpen}
        onClose={() => (busy ? undefined : setCreateOpen(false))}
        title="Новое задание"
        subtitle={`Класс ${state.viewer.class_name}`}
        footer={
          <div className="tc-actions" style={{ width: '100%' }}>
            <button type="button" className="tc-btn" onClick={() => setCreateOpen(false)} disabled={busy}>
              Отмена
            </button>
            <button type="button" className="tc-btn tc-btn--primary" onClick={() => void submit()} disabled={busy}>
              {busy ? 'Сохраняем…' : 'Опубликовать'}
            </button>
          </div>
        }
      >
        <form
          className="tc-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="tc-field">
            <label className="tc-label" htmlFor={fieldId('title')}>
              Название
            </label>
            <input
              id={fieldId('title')}
              className="tc-input"
              type="text"
              value={form.title}
              maxLength={80}
              onChange={(e) => update('title', e.target.value)}
              aria-invalid={Boolean(errors.title)}
              aria-describedby={describe('title')}
              required
            />
            {errors.title ? (
              <p className="tc-error" id={describe('title')} role="alert">
                {errors.title}
              </p>
            ) : null}
          </div>

          <div className="tc-form__row">
            <div className="tc-field">
              <label className="tc-label" htmlFor={fieldId('subject')}>
                Предмет <small>(необязательно)</small>
              </label>
              <select
                id={fieldId('subject')}
                className="tc-select"
                value={form.subject}
                onChange={(e) => update('subject', e.target.value)}
              >
                <option value="">Без предмета</option>
                {(state.subjects ?? []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
                <option value={SUBJECT_OTHER}>{SUBJECT_OTHER}</option>
              </select>
              {form.subject === SUBJECT_OTHER ? (
                <>
                  <input
                    className="tc-input"
                    type="text"
                    aria-label="Название предмета"
                    placeholder="Название предмета"
                    value={form.subjectOther}
                    maxLength={40}
                    onChange={(e) => update('subjectOther', e.target.value)}
                    aria-invalid={Boolean(errors.subject)}
                  />
                  {errors.subject ? (
                    <p className="tc-error" role="alert">
                      {errors.subject}
                    </p>
                  ) : null}
                </>
              ) : null}
            </div>
            <div className="tc-field">
              <label className="tc-label" htmlFor={fieldId('category')}>
                Тип
              </label>
              <select
                id={fieldId('category')}
                className="tc-select"
                value={form.category}
                onChange={(e) => update('category', e.target.value as ChallengeCategory)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="tc-form__row">
            <div className="tc-field">
              <div className="info-label-row">
                <label className="tc-label" htmlFor={fieldId('term')}>
                  Срок
                </label>
                <InfoButton title="Срок задания">
                  <DeadlineInfo />
                </InfoButton>
              </div>
              <select
                id={fieldId('term')}
                className="tc-select"
                value={form.term}
                onChange={(e) => update('term', e.target.value as Term)}
              >
                {TERMS.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="tc-field">
              <label className="tc-label" htmlFor={fieldId('proof')}>
                Как сдаётся
              </label>
              <select
                id={fieldId('proof')}
                className="tc-select"
                value={form.proof_type}
                onChange={(e) => update('proof_type', e.target.value as ProofType)}
              >
                {PROOF_TYPES.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="tc-form__row">
            <div className="tc-field">
              <div className="info-label-row">
                <label className="tc-label" htmlFor={fieldId('xp')}>
                  Награда, XP
                </label>
                <InfoButton title="Награда в XP">
                  <RewardXpInfo />
                </InfoButton>
              </div>
              <input
                id={fieldId('xp')}
                className="tc-input"
                type="number"
                inputMode="numeric"
                min={XP_MIN}
                max={XP_MAX}
                step={5}
                value={form.xp}
                onChange={(e) => update('xp', e.target.value)}
                aria-invalid={Boolean(errors.xp)}
                aria-describedby={describe('xp')}
              />
              {errors.xp ? (
                <p className="tc-error" id={describe('xp')} role="alert">
                  {errors.xp}
                </p>
              ) : null}
            </div>
{form.term === 'date' ? (
            <div className="tc-field">
              <label className="tc-label" htmlFor={fieldId('deadline')}>
                Срок сдачи
              </label>
              <input
                id={fieldId('deadline')}
                className="tc-input"
                type="date"
                min={daysFromNow(0)}
                value={form.deadline}
                onChange={(e) => update('deadline', e.target.value)}
                aria-invalid={Boolean(errors.deadline)}
                aria-describedby={describe('deadline')}
              />
              {errors.deadline ? (
                <p className="tc-error" id={describe('deadline')} role="alert">
                  {errors.deadline}
                </p>
              ) : null}
            </div>
) : null}
          </div>

          <div className="tc-field">
            <label className="tc-label" htmlFor={fieldId('description')}>
              Описание и критерии <small>(необязательно)</small>
            </label>
            <textarea
              id={fieldId('description')}
              className="tc-textarea"
              rows={4}
              maxLength={320}
              value={form.description}
              onChange={(e) => update('description', e.target.value)}
              aria-invalid={Boolean(errors.description)}
              aria-describedby={describe('description')}
            />
            <span className="tc-counter">{form.description.length}/320</span>
            {errors.description ? (
              <p className="tc-error" id={describe('description')} role="alert">
                {errors.description}
              </p>
            ) : null}
          </div>
          <button type="submit" hidden />
        </form>
      </Sheet>

      {/* Архивация */}
      <Sheet
        open={Boolean(archiveTarget)}
        onClose={() => (archiving ? undefined : setArchiveTarget(null))}
        title="Перенести в архив?"
        subtitle={archiveTarget?.title ?? ''}
        footer={
          <div className="tc-actions" style={{ width: '100%' }}>
            <button type="button" className="tc-btn" onClick={() => setArchiveTarget(null)} disabled={archiving}>
              Отмена
            </button>
            <button
              type="button"
              className="tc-btn tc-btn--danger"
              onClick={() => void confirmArchive()}
              disabled={archiving}
            >
              {archiving ? 'Переносим…' : 'В архив'}
            </button>
          </div>
        }
      >
        <p className="tc-muted" style={{ margin: 0 }}>
          Задание исчезнет из списка учеников. Уже отправленные работы
          {archiveTarget && archiveTarget.pending_total > 0
            ? ` (на проверке: ${archiveTarget.pending_total} ${plural(archiveTarget.pending_total, 'работа', 'работы', 'работ')})`
            : ''}{' '}
          и начисленные баллы сохраняются.
        </p>
      </Sheet>
    </div>
  );
}
