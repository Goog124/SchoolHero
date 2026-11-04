/**
 * Thin, defensive wrapper around the MAX Bridge.
 *
 * The mini app must stay usable in a normal browser (demo mode), so every
 * bridge call is optional and never blocks rendering.
 */

type MaxPlatform = 'ios' | 'android' | 'desktop' | 'web';

interface MaxBackButton {
  readonly isVisible: boolean;
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

interface MaxHaptics {
  impactOccurred(
    style: 'soft' | 'light' | 'medium' | 'heavy' | 'rigid',
    disableVibrationFallback?: boolean,
  ): unknown;
  notificationOccurred(
    type: 'error' | 'success' | 'warning',
    disableVibrationFallback?: boolean,
  ): unknown;
  selectionChanged(disableVibrationFallback?: boolean): unknown;
}

interface MaxWebAppBridge {
  readonly initData: string;
  readonly platform: MaxPlatform;
  readonly version: string;
  readonly BackButton: MaxBackButton;
  readonly HapticFeedback: MaxHaptics;
  getViewportSize(): Promise<{ height: string; width: string }>;
  shareMaxContent(params: { text?: string; link?: string }): Promise<void>;
  openLink(url: string): void;
  openMaxLink(url: string): void;
  enableClosingConfirmation(): void;
  disableClosingConfirmation(): void;
}

declare global {
  interface Window {
    WebApp?: MaxWebAppBridge;
  }
}

const CLIENT_ID_KEY = 'school-hero:client-id';
const HAPTICS_KEY = 'school-hero:haptics';

let bridge: MaxWebAppBridge | null = null;
let hapticsEnabled = readHapticsSetting();

function readHapticsSetting(): boolean {
  try {
    return localStorage.getItem(HAPTICS_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function setHapticsEnabled(enabled: boolean): void {
  hapticsEnabled = enabled;
  try {
    localStorage.setItem(HAPTICS_KEY, enabled ? 'on' : 'off');
  } catch {
    // Storage can be unavailable in private webviews — the in-memory value holds.
  }
}

export function isHapticsEnabled(): boolean {
  return hapticsEnabled;
}

/**
 * Some MAX bridge methods are typed as void but actually return a request
 * promise. Without a transport (plain browser) that promise rejects after a
 * timeout; swallow it so demo mode stays free of unhandled rejections.
 */
function ignoreBridgeResult(result: unknown): void {
  if (result && typeof (result as Promise<unknown>).catch === 'function') {
    void (result as Promise<unknown>).catch(() => undefined);
  }
}

function generateClientId(): string {
  const random =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `sh-${random}`.slice(0, 64);
}

export function getClientId(): string {
  try {
    const existing = localStorage.getItem(CLIENT_ID_KEY);
    if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
    const created = generateClientId();
    localStorage.setItem(CLIENT_ID_KEY, created);
    return created;
  } catch {
    return generateClientId();
  }
}

export function getBridge(): MaxWebAppBridge | null {
  return bridge ?? (typeof window !== 'undefined' ? window.WebApp ?? null : null);
}

export async function waitForBridge(): Promise<MaxWebAppBridge | null> {
  if (typeof window === 'undefined') return null;
  if (window.WebApp) {
    bridge = window.WebApp;
    return bridge;
  }
  const started = performance.now();
  while (performance.now() - started < 900) {
    await new Promise((resolve) => window.setTimeout(resolve, 40));
    if (window.WebApp) {
      bridge = window.WebApp;
      return bridge;
    }
  }
  return null;
}

export function isMaxEnvironment(): boolean {
  return Boolean(getBridge()?.initData);
}

export function getPlatform(): MaxPlatform {
  return getBridge()?.platform ?? 'web';
}

export function getInitData(): string {
  return getBridge()?.initData ?? '';
}

export function tapHaptic(): void {
  if (!hapticsEnabled) return;
  const current = getBridge();
  if (current?.HapticFeedback) {
    try {
      ignoreBridgeResult(current.HapticFeedback.impactOccurred('light'));
      return;
    } catch {
      // Fall through to the web vibration fallback.
    }
  }
  if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
    navigator.vibrate?.(8);
  }
}

export function successHaptic(): void {
  if (!hapticsEnabled) return;
  const current = getBridge();
  if (current?.HapticFeedback) {
    try {
      ignoreBridgeResult(current.HapticFeedback.notificationOccurred('success'));
      return;
    } catch {
      // Fall through.
    }
  }
  if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
    navigator.vibrate?.([12, 40, 16]);
  }
}

export function errorHaptic(): void {
  if (!hapticsEnabled) return;
  const current = getBridge();
  if (current?.HapticFeedback) {
    try {
      ignoreBridgeResult(current.HapticFeedback.notificationOccurred('error'));
      return;
    } catch {
      // Fall through.
    }
  }
  if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
    navigator.vibrate?.([18, 50, 18]);
  }
}

export function bindBackButton(visible: boolean, handler: () => void): () => void {
  const current = getBridge();
  if (!current?.BackButton) return () => undefined;
  const button = current.BackButton;
  try {
    if (visible) {
      button.onClick(handler);
      button.show();
    } else {
      button.hide();
    }
  } catch {
    // Bridge versions differ; navigation still works via the UI.
  }
  return () => {
    try {
      button.offClick(handler);
      if (visible) button.hide();
    } catch {
      // Ignore.
    }
  };
}

export async function applyViewport(): Promise<void> {
  const current = getBridge();
  let height = `${window.innerHeight}px`;
  let width = `${window.innerWidth}px`;
  if (current?.getViewportSize) {
    try {
      const sizePromise = current.getViewportSize().catch(() => null);
      const timeout = new Promise<null>((resolve) => {
        window.setTimeout(() => resolve(null), 150);
      });
      const size = await Promise.race([sizePromise, timeout]);
      if (size?.height) height = size.height;
      if (size?.width) width = size.width;
    } catch {
      // Use window dimensions (also covers a bridge without a transport).
    }
  }
  const root = document.documentElement;
  root.style.setProperty('--max-vh', height);
  root.style.setProperty('--max-vw', width);
}

export function applyPlatformClass(): void {
  const platform = getPlatform();
  document.documentElement.dataset.maxPlatform = platform;
}

export function enableClosingConfirmation(): void {
  getBridge()?.enableClosingConfirmation();
}

export function disableClosingConfirmation(): void {
  getBridge()?.disableClosingConfirmation();
}
