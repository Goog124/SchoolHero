import { useEffect, useId, useMemo, useRef, useState, type CSSProperties } from 'react';
import { AvatarFrame } from '../components/AvatarFrame';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { InfoButton } from '../components/InfoButton';
import { ReviewQueueInfo } from '../components/infoTexts';
import { ProofPhoto } from '../components/ProofPhoto';
import { ScreenTitle } from '../components/ScreenTitle';
import { Sheet } from '../components/Sheet';
import { formatNumber, formatRelative, plural } from '../game';
import type { ReviewItem, TeacherData } from '../types';
import '../styles/teacher.css';

const REJECT_TEMPLATES = [
  'Прикрепи ссылку на файл',
  'Ответ неполный',
  'Сдай на следующем уроке',
  'Приложи фото решения из тетради',
  'Работа не соответствует критериям',
];

const PROOF_LABEL: Record<string, string> = {
  text: 'Текст',
  link: 'Ссылка',
  photo: 'Фото',
};

type TeacherReviewScreenProps = {
  teacher: TeacherData;
  busyId: number | null;
  onApprove: (completionId: number) => Promise<boolean>;
  onReject: (completionId: number, reason: string) => Promise<boolean>;
  onBatchApprove?: (completionIds: number[]) => Promise<boolean>;
  /** Необязательно: пакетное отклонение. Если не передано, отклоняем по одной работе. */
  onBatchReject?: (completionIds: number[], reason: string) => Promise<boolean>;
};

function safeUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function proofKind(item: ReviewItem): string {
  if (item.proof_type) return PROOF_LABEL[item.proof_type] ?? 'Текст';
  if (item.proof_url) return 'Ссылка';
  return 'Текст';
}

export function TeacherReviewScreen({
  teacher,
  busyId,
  onApprove,
  onReject,
  onBatchApprove,
  onBatchReject,
}: TeacherReviewScreenProps) {
  const uid = useId();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [detail, setDetail] = useState<ReviewItem | null>(null);
  const [rejectIds, setRejectIds] = useState<number[] | null>(null);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState('');
  const [approveBatchOpen, setApproveBatchOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [subjectFilter, setSubjectFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [photoFailed, setPhotoFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const pending = teacher.pending;

  const subjects = useMemo(() => {
    const set = new Set<string>();
    pending.forEach((p) => {
      if (p.subject) set.add(p.subject);
    });
    return Array.from(set);
  }, [pending]);

  const categories = useMemo(() => {
    const map = new Map<string, string>();
    pending.forEach((p) => map.set(p.category, p.category_label));
    return Array.from(map.entries());
  }, [pending]);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return pending.filter((p) => {
      if (subjectFilter !== 'all' && p.subject !== subjectFilter) return false;
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false;
      if (!q) return true;
      return (
        p.student_name.toLowerCase().includes(q) ||
        p.title.toLowerCase().includes(q) ||
        p.proof.toLowerCase().includes(q)
      );
    });
  }, [pending, subjectFilter, categoryFilter, query]);

  const reviewable = useMemo(() => items.filter((p) => !p.is_self), [items]);

  // Выбранные работы, которые ещё в очереди и видимы по фильтру
  const selected = useMemo(() => {
    const visible = new Set(reviewable.map((p) => p.id));
    return selectedIds.filter((id) => visible.has(id));
  }, [selectedIds, reviewable]);

  const selectedItems = useMemo(
    () => reviewable.filter((p) => selected.includes(p.id)),
    [reviewable, selected],
  );
  const selectedXp = selectedItems.reduce((sum, p) => sum + p.xp, 0);

  const allChecked = reviewable.length > 0 && selected.length === reviewable.length;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selected.length > 0 && !allChecked;
    }
  }, [selected.length, allChecked]);

  // Если открытая работа ушла из очереди (проверена) — закрыть окно
  useEffect(() => {
    if (detail && !pending.some((p) => p.id === detail.id)) setDetail(null);
  }, [pending, detail]);

  const toggle = (id: number) =>
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );

  const toggleAll = () => setSelectedIds(allChecked ? [] : reviewable.map((p) => p.id));

  const openReject = (ids: number[]) => {
    setRejectIds(ids);
    setReason('');
    setReasonError('');
  };

  const closeReject = () => {
    if (!working) setRejectIds(null);
  };

  const openDetail = (item: ReviewItem) => {
    setDetail(item);
    setPhotoFailed(false);
    setCopied(false);
  };

  const confirmReject = async () => {
    if (!rejectIds) return;
    const text = reason.trim();
    if (text.length < 3) {
      setReasonError('Укажите причину — ученик увидит её в приложении.');
      return;
    }
    setWorking(true);
    let ok = true;
    if (rejectIds.length > 1 && onBatchReject) {
      ok = await onBatchReject(rejectIds, text);
    } else {
      for (const id of rejectIds) {
        const done = await onReject(id, text);
        if (!done) {
          ok = false;
          break;
        }
      }
    }
    setWorking(false);
    if (ok) {
      setRejectIds(null);
      setSelectedIds((current) => current.filter((id) => !rejectIds.includes(id)));
    }
  };

  const confirmApproveBatch = async () => {
    if (!onBatchApprove || !selected.length) return;
    setWorking(true);
    const ok = await onBatchApprove(selected);
    setWorking(false);
    if (ok) {
      setApproveBatchOpen(false);
      setSelectedIds([]);
    }
  };

  const copyUrl = async (url: string) => {
    try {
      await navigator.clipboard?.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // буфер недоступен — ссылку можно открыть напрямую
    }
  };

  const rejectTargetItems = rejectIds
    ? pending.filter((p) => rejectIds.includes(p.id))
    : [];
  const filtersActive = subjectFilter !== 'all' || categoryFilter !== 'all' || query !== '';

  const detailUrl = detail ? safeUrl(detail.proof_url) : null;
  const detailBusy = detail ? busyId === detail.id : false;

  return (
    <div className="screen tc-page">
      <ScreenTitle
        title="Проверка работ"
        info={
          <InfoButton title="Проверка работ">
            <ReviewQueueInfo />
          </InfoButton>
        }
        subtitle={
          pending.length
            ? `В очереди ${pending.length} ${plural(pending.length, 'работа', 'работы', 'работ')} · ${formatNumber(
                pending.reduce((sum, p) => sum + p.xp, 0),
              )} XP к начислению`
            : 'Очередь пуста'
        }
      />

      {pending.length === 0 ? (
        <EmptyState
          icon="check"
          title="Нет работ на проверке"
          text="Новые работы появятся здесь, когда ученики отправят ответы на задания."
        />
      ) : (
        <>
          <div className="tc-toolbar" role="search" aria-label="Фильтры очереди">
            <div className="tc-search">
              <label htmlFor={`${uid}-q`} style={srOnly}>
                Поиск по ученику, заданию или ответу
              </label>
              <input
                id={`${uid}-q`}
                type="search"
                className="tc-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ученик, задание или текст ответа"
              />
            </div>
            <select
              className="tc-select"
              aria-label="Предмет"
              value={subjectFilter}
              onChange={(e) => setSubjectFilter(e.target.value)}
            >
              <option value="all">Все предметы</option>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="tc-select"
              aria-label="Тип задания"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="all">Все типы</option>
              {categories.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
            {filtersActive ? (
              <button
                type="button"
                className="tc-btn tc-btn--ghost"
                onClick={() => {
                  setSubjectFilter('all');
                  setCategoryFilter('all');
                  setQuery('');
                }}
              >
                Сбросить
              </button>
            ) : null}
          </div>

          {selected.length > 0 ? (
            <div className="tc-batch" role="region" aria-label="Действия с выбранными работами">
              <span className="tc-batch__text" aria-live="polite">
                Выбрано {selected.length} · {formatNumber(selectedXp)} XP
              </span>
              {onBatchApprove ? (
                <button
                  type="button"
                  className="tc-btn tc-btn--ok"
                  onClick={() => setApproveBatchOpen(true)}
                >
                  <Icon name="check" size={16} />
                  Подтвердить
                </button>
              ) : null}
              <button
                type="button"
                className="tc-btn tc-btn--danger"
                onClick={() => openReject(selected)}
              >
                <Icon name="x" size={16} />
                Вернуть на доработку
              </button>
              <button type="button" className="tc-btn" onClick={() => setSelectedIds([])}>
                Снять выбор
              </button>
            </div>
          ) : null}

          {items.length === 0 ? (
            <EmptyState
              icon="filter"
              title="Ничего не найдено"
              text="Измените поиск или сбросьте фильтры."
            />
          ) : (
            <div className="tc-panel tc-panel--flush">
              <div className="tc-table-wrap">
                <table className="tc-table">
                  <caption>Очередь работ на проверку</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="tc-c">
                        <label className="tc-check">
                          <input
                            ref={selectAllRef}
                            type="checkbox"
                            checked={allChecked}
                            onChange={toggleAll}
                            disabled={reviewable.length === 0}
                            aria-label="Выбрать все работы в списке"
                          />
                        </label>
                      </th>
                      <th scope="col">Ученик</th>
                      <th scope="col">Работа</th>
                      <th scope="col">Ответ</th>
                      <th scope="col" className="tc-r">
                        XP
                      </th>
                      <th scope="col">
                        <span style={srOnly}>Действия</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => {
                      const busy = busyId === item.id;
                      const isSelected = selected.includes(item.id);
                      return (
                        <tr key={item.id} className={isSelected ? 'is-selected' : undefined}>
                          <td className="tc-c tc-cell--main">
                            <label className="tc-check">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggle(item.id)}
                                disabled={item.is_self}
                                aria-label={`Выбрать: ${item.student_name}, ${item.title}`}
                              />
                            </label>
                          </td>
                          <td className="tc-cell--main">
                            <div className="tc-person">
                              <AvatarFrame avatar={item.avatar} size={36} decorative />
                              <div className="tc-person__text">
                                <span className="tc-person__name">{item.student_name}</span>
                                <span className="tc-faint">
                                  {item.student_level_title} · {formatRelative(item.created_at)}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="tc-cell--main">
                            <button
                              type="button"
                              className="tc-link-btn"
                              onClick={() => openDetail(item)}
                              aria-label={`Открыть работу: ${item.title}`}
                            >
                              {item.title}
                            </button>
                            <div className="tc-faint">
                              {[item.subject, item.category_label].filter(Boolean).join(' · ')}
                            </div>
                          </td>
                          <td data-label={proofKind(item)} className="tc-cell--main">
                            {item.proof ? (
                              <span className="tc-clamp tc-muted">{item.proof}</span>
                            ) : item.proof_url ? (
                              <span className="tc-muted">Ссылка приложена</span>
                            ) : (
                              <span className="tc-faint">Без текста</span>
                            )}
                            {item.proof && item.proof_url ? (
                              <span className="tc-faint"> · {proofKind(item)}: ссылка</span>
                            ) : null}
                          </td>
                          <td data-label="Награда" className="tc-r tc-num">
                            {item.xp} XP
                          </td>
                          <td className="tc-cell--actions">
                            {item.is_self ? (
                              <span className="tc-badge">Своя работа</span>
                            ) : (
                              <div className="tc-actions">
                                <button
                                  type="button"
                                  className="tc-btn tc-btn--sm tc-btn--danger"
                                  onClick={() => openReject([item.id])}
                                  disabled={busy}
                                  aria-label={`Вернуть на доработку: ${item.student_name}, ${item.title}`}
                                >
                                  Вернуть
                                </button>
                                <button
                                  type="button"
                                  className="tc-btn tc-btn--sm tc-btn--ok"
                                  onClick={() => void onApprove(item.id)}
                                  disabled={busy}
                                  aria-label={`Подтвердить: ${item.student_name}, ${item.title}`}
                                >
                                  {busy ? 'Сохраняем…' : 'Подтвердить'}
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Просмотр работы */}
      <Sheet
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.title ?? ''}
        subtitle={detail ? `${detail.student_name} · ${formatRelative(detail.created_at)}` : ''}
        footer={
          detail && !detail.is_self ? (
            <div className="tc-actions" style={{ width: '100%' }}>
              <button
                type="button"
                className="tc-btn tc-btn--danger"
                onClick={() => {
                  const target = detail;
                  setDetail(null);
                  openReject([target.id]);
                }}
                disabled={detailBusy}
              >
                Вернуть на доработку
              </button>
              <button
                type="button"
                className="tc-btn tc-btn--ok"
                onClick={() => void onApprove(detail.id)}
                disabled={detailBusy}
              >
                {detailBusy ? 'Сохраняем…' : `Подтвердить, +${detail.xp} XP`}
              </button>
            </div>
          ) : undefined
        }
      >
        {detail ? (
          <div className="tc-proof">
            <dl className="tc-dl">
              <dt>Ученик</dt>
              <dd>
                {detail.student_name}, {detail.student_level_title}
              </dd>
              <dt>Задание</dt>
              <dd>{[detail.subject, detail.category_label].filter(Boolean).join(' · ')}</dd>
              <dt>Награда</dt>
              <dd>{detail.xp} XP</dd>
              <dt>Тип ответа</dt>
              <dd>{proofKind(detail)}</dd>
            </dl>
            {detail.proof ? (
              <p className="tc-proof__text">{detail.proof}</p>
            ) : (
              <p className="tc-muted">Текстового ответа нет.</p>
            )}
            {detail.upload_id ? (
              <ProofPhoto uploadId={detail.upload_id} alt={`Фото к работе: ${detail.title}`} />
            ) : null}
            {detailUrl ? (
              <>
                {detail.proof_type === 'photo' && !photoFailed ? (
                  <a href={detailUrl} target="_blank" rel="noreferrer noopener">
                    <img
                      className="tc-proof__img"
                      src={detailUrl}
                      alt={`Фото к работе: ${detail.title}`}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      onError={() => setPhotoFailed(true)}
                    />
                  </a>
                ) : null}
                <div className="tc-toolbar">
                  <a className="tc-a" href={detailUrl} target="_blank" rel="noreferrer noopener">
                    {detail.proof_url}
                  </a>
                  <span className="tc-toolbar__spacer" />
                  <button type="button" className="tc-btn tc-btn--sm" onClick={() => void copyUrl(detailUrl)}>
                    {copied ? 'Скопировано' : 'Копировать'}
                  </button>
                </div>
              </>
            ) : detail.proof_url ? (
              <p className="tc-alert tc-alert--warn">
                Ссылка в ответе небезопасна и не открывается: {detail.proof_url}
              </p>
            ) : null}
            {detail.is_self ? (
              <p className="tc-alert">Это ваша работа: подтвердить её может другой педагог.</p>
            ) : null}
          </div>
        ) : null}
      </Sheet>

      {/* Возврат на доработку */}
      <Sheet
        open={Boolean(rejectIds)}
        onClose={closeReject}
        title="Вернуть на доработку"
        subtitle={
          rejectTargetItems.length === 1
            ? `${rejectTargetItems[0].student_name} · ${rejectTargetItems[0].title}`
            : `${rejectTargetItems.length} ${plural(rejectTargetItems.length, 'работа', 'работы', 'работ')}`
        }
        footer={
          <div className="tc-actions" style={{ width: '100%' }}>
            <button type="button" className="tc-btn" onClick={closeReject} disabled={working}>
              Отмена
            </button>
            <button
              type="button"
              className="tc-btn tc-btn--danger"
              onClick={() => void confirmReject()}
              disabled={working}
            >
              {working ? 'Отправляем…' : 'Вернуть'}
            </button>
          </div>
        }
      >
        <div className="tc-form">
          <p className="tc-muted" style={{ margin: 0 }}>
            Причина будет показана ученику. Баллы за эту работу не начисляются.
          </p>
          <div className="tc-chips" role="group" aria-label="Шаблоны причины">
            {REJECT_TEMPLATES.map((tpl) => (
              <button
                key={tpl}
                type="button"
                className="tc-chip"
                aria-pressed={reason === tpl}
                onClick={() => {
                  setReason(tpl);
                  setReasonError('');
                }}
              >
                {tpl}
              </button>
            ))}
          </div>
          <div className="tc-field">
            <label className="tc-label" htmlFor={`${uid}-reason`}>
              Причина
            </label>
            <textarea
              id={`${uid}-reason`}
              className="tc-textarea"
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setReasonError('');
              }}
              rows={3}
              maxLength={200}
              aria-invalid={Boolean(reasonError)}
              aria-describedby={reasonError ? `${uid}-reason-err` : undefined}
              placeholder="Что нужно исправить"
            />
            <span className="tc-counter">{reason.length}/200</span>
            {reasonError ? (
              <p className="tc-error" id={`${uid}-reason-err`} role="alert">
                {reasonError}
              </p>
            ) : null}
          </div>
        </div>
      </Sheet>

      {/* Подтверждение пакетного одобрения */}
      <Sheet
        open={approveBatchOpen}
        onClose={() => (working ? undefined : setApproveBatchOpen(false))}
        title="Подтвердить выбранные работы"
        subtitle={`${selected.length} ${plural(selected.length, 'работа', 'работы', 'работ')} · ${formatNumber(selectedXp)} XP`}
        footer={
          <div className="tc-actions" style={{ width: '100%' }}>
            <button
              type="button"
              className="tc-btn"
              onClick={() => setApproveBatchOpen(false)}
              disabled={working}
            >
              Отмена
            </button>
            <button
              type="button"
              className="tc-btn tc-btn--primary"
              onClick={() => void confirmApproveBatch()}
              disabled={working || selected.length === 0}
            >
              {working ? 'Сохраняем…' : 'Подтвердить'}
            </button>
          </div>
        }
      >
        <ul className="tc-muted" style={{ margin: 0, paddingLeft: 20 }}>
          {selectedItems.map((p) => (
            <li key={p.id}>
              {p.student_name}: {p.title} (+{p.xp} XP)
            </li>
          ))}
        </ul>
      </Sheet>
    </div>
  );
}

const srOnly: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
};
