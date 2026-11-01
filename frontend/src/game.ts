import type { IconName } from './components/Icon';
import type { ChallengeCategory, ChallengeStatus, Cosmetic } from './types';

export type CategoryTone = 'violet' | 'cyan' | 'lime' | 'pink' | 'gold' | 'orange';

export const CATEGORY_META: Record<
  ChallengeCategory,
  { label: string; full: string; icon: IconName; tone: CategoryTone }
> = {
  homework: { label: 'Домашка', full: 'Домашнее задание', icon: 'book', tone: 'cyan' },
  club: { label: 'Кружок', full: 'Кружок или секция', icon: 'compass', tone: 'lime' },
  help: { label: 'Помощь', full: 'Помощь однокласснику', icon: 'heart', tone: 'pink' },
  weekly: { label: 'Челлендж', full: 'Недельный челлендж', icon: 'star', tone: 'violet' },
  olympiad: { label: 'Олимпиада', full: 'Олимпиада или конкурс', icon: 'trophy', tone: 'gold' },
  event: { label: 'Событие', full: 'Школьное событие', icon: 'flag', tone: 'orange' },
  streak: { label: 'Серия', full: 'Серия дней', icon: 'flame', tone: 'orange' },
};

export const STATUS_META: Record<
  ChallengeStatus,
  { label: string; short: string }
> = {
  available: { label: 'Можно выполнить', short: 'Доступно' },
  pending: { label: 'Ждёт подтверждения педагога', short: 'На проверке' },
  approved: { label: 'Подтверждено', short: 'Выполнено' },
  rejected: { label: 'Нужно исправить', short: 'Отклонено' },
  expired: { label: 'Срок истёк', short: 'Истекло' },
};

export const RANK_TITLES = ['Новичок', 'Ученик', 'Знаток', 'Мастер', 'Легенда школы'];

export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}

export function formatXp(value: number): string {
  return `${formatNumber(value)} XP`;
}

export function formatSparks(value: number): string {
  return `${formatNumber(value)} ${plural(value, 'искра', 'искры', 'искр')}`;
}

export function formatShortDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
  }).format(date);
}

export function formatLongDate(date = new Date()): string {
  return new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(date);
}

export function formatDeadline(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const isTomorrow =
    date.getFullYear() === tomorrow.getFullYear() &&
    date.getMonth() === tomorrow.getMonth() &&
    date.getDate() === tomorrow.getDate();
  const time = new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
  if (sameDay) return `сегодня до ${time}`;
  if (isTomorrow) return `завтра до ${time}`;
  return `до ${formatShortDate(iso)}`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'только что';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} ${plural(minutes, 'минуту', 'минуты', 'минут')} назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${plural(hours, 'час', 'часа', 'часов')} назад`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'вчера';
  if (days < 7) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`;
  return formatShortDate(iso);
}

export function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return 'Ещё не спишь?';
  if (hour < 12) return 'Доброе утро';
  if (hour < 18) return 'Добрый день';
  return 'Добрый вечер';
}

export function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name;
}

export function challengeActionLabel(status: ChallengeStatus): string {
  switch (status) {
    case 'available':
      return 'Выполнить';
    case 'pending':
      return 'На проверке';
    case 'approved':
      return 'Выполнено';
    case 'rejected':
      return 'Исправить';
    case 'expired':
      return 'Срок истёк';
  }
}

export function unlockablesAtLevel(cosmetics: Cosmetic[], level: number): Cosmetic[] {
  return cosmetics.filter((item) => item.unlock_level === level && item.price === 0);
}

export function nextUnlockLevel(cosmetics: Cosmetic[], level: number): number | null {
  const levels = cosmetics
    .filter((item) => item.unlock_level > level)
    .map((item) => item.unlock_level);
  return levels.length ? Math.min(...levels) : null;
}

export function isToday(iso: string): boolean {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

export function toDateInput(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function daysFromNow(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return toDateInput(date);
}
