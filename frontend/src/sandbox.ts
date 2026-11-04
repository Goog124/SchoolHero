// Песочница: несколько независимых тестовых пользователей в одном браузере.
// Список хранится в localStorage; если он недоступен, живёт в памяти вкладки.

export type SandboxUser = {
  clientId: string;
  label: string;
  /** Хвост подписи с разделителем: ' — Имя, роль' или ', роль'. */
  detail?: string;
};

const USERS_KEY = 'school-hero:sandbox-users';
const ACTIVE_KEY = 'school-hero:sandbox-active';
const BOOT_KEY = 'school-hero:sandbox-boot';
const ID_RE = /^[A-Za-z0-9_-]{8,64}$/;

let enabled = false;
let users: SandboxUser[] | null = null;
let active = '';

function newClientId(): string {
  const bytes = new Uint8Array(12);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  return `sb${Array.from(bytes, (b) => b.toString(36).padStart(2, '0')).join('')}`;
}

function nextLabel(list: SandboxUser[]): string {
  const max = list.reduce((m, u) => {
    const n = Number.parseInt(u.label.replace(/\D/g, ''), 10);
    return Number.isNaN(n) ? m : Math.max(m, n);
  }, 0);
  return `Пользователь ${max + 1}`;
}

function persist(): void {
  try {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
    localStorage.setItem(ACTIVE_KEY, active);
  } catch {
    // Storage is optional.
  }
}

function load(): void {
  if (users) return;
  let stored: SandboxUser[] = [];
  let storedActive = '';
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(USERS_KEY) || '[]');
    if (Array.isArray(parsed)) {
      stored = parsed.filter(
        (u): u is SandboxUser =>
          typeof u?.clientId === 'string' && ID_RE.test(u.clientId) && typeof u.label === 'string',
      );
    }
    storedActive = localStorage.getItem(ACTIVE_KEY) || '';
  } catch {
    // Start from scratch.
  }
  users = stored;
  if (users.length === 0) {
    users = [{ clientId: newClientId(), label: 'Пользователь 1' }];
  }
  active = users.some((u) => u.clientId === storedActive) ? storedActive : users[0].clientId;
  persist();
}

/**
 * Сверяет запуск сервера песочницы с тем, что помнит браузер. Если сервер
 * перезапущен (база стёрта), старые тестовые пользователи больше не существуют:
 * список сбрасывается. Возвращает true, если сброшены реально существовавшие
 * пользователи (для сообщения в панели).
 */
export function syncSandboxBoot(bootId: string | null | undefined): boolean {
  if (!bootId) return false;
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(BOOT_KEY);
  } catch {
    // Treated as unknown.
  }
  if (stored === bootId) return false;
  let hadUsers = Boolean(users && users.length > 0);
  try {
    const raw = JSON.parse(localStorage.getItem(USERS_KEY) || '[]');
    if (Array.isArray(raw) && raw.length > 0) hadUsers = true;
  } catch {
    // Ignore.
  }
  users = null;
  active = '';
  try {
    localStorage.removeItem(USERS_KEY);
    localStorage.removeItem(ACTIVE_KEY);
    localStorage.setItem(BOOT_KEY, bootId);
  } catch {
    // Ignore.
  }
  return hadUsers;
}

export function enableSandbox(): void {
  enabled = true;
  load();
}

/** Идентификатор активного тестового пользователя; null вне песочницы. */
export function activeSandboxClientId(): string | null {
  return enabled ? active : null;
}

export function listSandboxUsers(): SandboxUser[] {
  load();
  return [...(users ?? [])];
}

export function switchSandboxUser(clientId: string): void {
  load();
  if (users?.some((u) => u.clientId === clientId)) {
    active = clientId;
    persist();
  }
}

export function addSandboxUser(): SandboxUser {
  load();
  const list = users ?? [];
  const created: SandboxUser = { clientId: newClientId(), label: nextLabel(list) };
  users = [...list, created];
  active = created.clientId;
  persist();
  return created;
}

/** Возвращает true, если подпись изменилась. */
export function setSandboxDetail(clientId: string, detail: string): boolean {
  load();
  const user = users?.find((u) => u.clientId === clientId);
  if (!user || (user.detail ?? '') === detail) return false;
  user.detail = detail || undefined;
  persist();
  return true;
}
