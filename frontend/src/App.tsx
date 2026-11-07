import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import { AppHeader } from './components/AppHeader';
import { AvatarFrame } from './components/AvatarFrame';
import { ChallengeSheet } from './components/ChallengeSheet';
import { DesktopSidebar } from './components/DesktopSidebar';
import { JoinRequestScreen } from './components/JoinRequestScreen';
import { NameScreen } from './components/NameScreen';
import { LoadingScreen } from './components/LoadingScreen';
import { SandboxBar } from './components/SandboxBar';
import { Sheet } from './components/Sheet';
import { TabBar, type TabItem } from './components/TabBar';
import { Toast, type ToastData, type ToastTone } from './components/Toast';
import { EmptyState } from './components/EmptyState';
import {
  applyPlatformClass,
  applyViewport,
  errorHaptic,
  isMaxEnvironment,
  successHaptic,
  tapHaptic,
  waitForBridge,
} from './max';
import {
  activeSandboxClientId,
  addSandboxUser,
  enableSandbox,
  listSandboxUsers,
  setSandboxDetail,
  switchSandboxUser,
  syncSandboxBoot,
  type SandboxUser,
} from './sandbox';
import { ChallengesScreen } from './screens/ChallengesScreen';
import { DirectorScreen } from './screens/DirectorScreen';
import { HeroScreen } from './screens/HeroScreen';
import { LeaderboardScreen } from './screens/LeaderboardScreen';
import { OnboardingScreen } from './screens/OnboardingScreen';
import { AdminSchoolsScreen, AdminUsersScreen } from './screens/AdminScreens';
import {
  AudienceChoice,
  DirectorNoSchoolScreen,
  SchoolRegisterScreen,
  SchoolSetupScreen,
  TeacherNoClassScreen,
} from './screens/SchoolSetupScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { TeacherChallengesScreen } from './screens/TeacherChallengesScreen';
import { TeacherClassScreen } from './screens/TeacherClassScreen';
import { TeacherReviewScreen } from './screens/TeacherReviewScreen';
import { WardrobeScreen } from './screens/WardrobeScreen';
import type {
  AvatarConfig,
  BatchReviewResult,
  DeletedSchoolSummary,
  GameState,
  LevelInfo,
  MutationResponse,
  NewSchoolPayload,
  ReviewResult,
  SubmitResult,
  TabId,
} from './types';

type LevelUpData = {
  level: LevelInfo;
  avatar: AvatarConfig;
};

type Theme = 'light' | 'dark';

const STUDENT_TABS: TabId[] = ['hero', 'challenges', 'leaderboard', 'wardrobe', 'profile'];
const TEACHER_TABS: TabId[] = ['teacher-class', 'teacher-review', 'teacher-challenges', 'profile'];
const DIRECTOR_TABS: TabId[] = ['director-overview', 'director-classes', 'director-setup', 'profile'];
// Администратор платформы, не зарегистрированный ни учеником, ни сотрудником школы.
const ADMIN_TABS: TabId[] = ['admin-schools', 'admin-users'];
const ADMIN_ONLY_TABS: TabId[] = [...ADMIN_TABS, 'profile'];

/** Админ платформы без класса и роли в школе: регистрация ученика ему не нужна. */
function isAdminOnly(state: GameState): boolean {
  return (
    Boolean(state.platform_admin) &&
    state.viewer.role === 'student' &&
    (!state.viewer.onboarded || !state.viewer.class_id)
  );
}

function tabFromPath(pathname: string): TabId | null {
  const route = pathname.replace(/\/+$/, '') || '/';
  const routes: Record<string, TabId> = {
    '/student': 'hero',
    '/student/overview': 'hero',
    '/student/challenges': 'challenges',
    '/student/leaderboard': 'leaderboard',
    '/student/wardrobe': 'wardrobe',
    '/student/profile': 'profile',
    '/teacher': 'teacher-class',
    '/teacher/class': 'teacher-class',
    '/teacher/review': 'teacher-review',
    '/teacher/challenges': 'teacher-challenges',
    '/teacher/profile': 'profile',
    '/director': 'director-overview',
    '/director/overview': 'director-overview',
    '/director/classes': 'director-classes',
    '/director/setup': 'director-setup',
    '/admin/schools': 'admin-schools',
    '/admin/users': 'admin-users',
    '/director/profile': 'profile',
  };
  return routes[route] ?? null;
}

function pathForTab(tab: TabId, role: 'student' | 'teacher' | 'director' = 'student'): string {
  const routes: Record<TabId, string> = {
    hero: '/student/overview',
    challenges: '/student/challenges',
    leaderboard: '/student/leaderboard',
    wardrobe: '/student/wardrobe',
    profile: role === 'director' ? '/director/profile' : role === 'teacher' ? '/teacher/profile' : '/student/profile',
    'teacher-class': '/teacher/class',
    'teacher-review': '/teacher/review',
    'teacher-challenges': '/teacher/challenges',
    'director-overview': '/director/overview',
    'director-classes': '/director/classes',
    'director-setup': '/director/setup',
    'admin-schools': '/admin/schools',
    'admin-users': '/admin/users',
  };
  return routes[tab] || '/';
}

export default function App() {
  // Явный выбор пользователя хранится в localStorage; без него тема следует
  // за системной (prefers-color-scheme) и меняется вместе с ней.
  const [chosenTheme, setChosenTheme] = useState<Theme | null>(() => {
    try {
      const saved = localStorage.getItem('school-hero:theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      // Storage unavailable
    }
    return null;
  });
  const [systemTheme, setSystemTheme] = useState<Theme>(() =>
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  );
  const theme: Theme = chosenTheme ?? systemTheme;
  const setTheme = useCallback((next: Theme) => {
    setChosenTheme(next);
    try {
      localStorage.setItem('school-hero:theme', next);
    } catch {
      // Storage unavailable: the choice lasts until reload
    }
  }, []);

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!media) return;
    const onChange = (event: MediaQueryListEvent) => setSystemTheme(event.matches ? 'dark' : 'light');
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const [state, setState] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState('');
  const [outsideMax, setOutsideMax] = useState(false);
  const [tab, setTab] = useState<TabId>(() => tabFromPath(window.location.pathname) ?? 'hero');
  const [toast, setToast] = useState<ToastData | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [levelUp, setLevelUp] = useState<LevelUpData | null>(null);
  const [audience, setAudience] = useState<'student' | 'school' | null>(null);
  // Ученик с заявкой решил войти по коду: показываем ввод кода вместо ожидания.
  const [codeInstead, setCodeInstead] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  // Сервер ответил 403 «Доступ к приложению ограничен»: администратор заблокировал пользователя.
  const [blocked, setBlocked] = useState(false);
  const [sandboxReset, setSandboxReset] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [changingClass, setChangingClass] = useState(false);
  const [sandbox, setSandbox] = useState<{ users: SandboxUser[]; active: string } | null>(null);

  const lastStudentTab = useRef<TabId>('hero');
  const lastTeacherTab = useRef<TabId>('teacher-class');
  const lastDirectorTab = useRef<TabId>('director-overview');
  const toastCounter = useRef(0);

  const showToast = useCallback(
    (message: string, tone: ToastTone = 'success', icon?: ToastData['icon']) => {
      toastCounter.current += 1;
      setToast({ id: toastCounter.current, message, tone, icon });
      if (tone === 'success') successHaptic();
      else if (tone === 'error') errorHaptic();
      else tapHaptic();
    },
    [],
  );

  // 401 в боевом режиме: подпись MAX устарела. Повторные запросы не помогут.
  const markExpired = useCallback((error: unknown): boolean => {
    if (error instanceof ApiError && error.blocked) {
      setBlocked(true);
      return true;
    }
    if (error instanceof ApiError && error.status === 401 && activeSandboxClientId() === null) {
      setSessionExpired(true);
      return true;
    }
    return false;
  }, []);

  const load = useCallback(async () => {
    refreshRef.current.stopped = false;
    setLoading(true);
    setBootError('');
    setOutsideMax(false);
    try {
      await waitForBridge();
      applyPlatformClass();
      await applyViewport();
      // В prod вход возможен только изнутри MAX: без подписи запросы не делаем.
      const health = await api.health().catch(() => null);
      if (health?.mode === 'sandbox') {
        if (syncSandboxBoot(health.boot_id)) setSandboxReset(true);
        enableSandbox();
        setSandbox({ users: listSandboxUsers(), active: activeSandboxClientId() ?? '' });
      } else if (health?.mode === 'prod' && !isMaxEnvironment()) {
        setOutsideMax(true);
        return;
      }
      const data = await api.getState();
      setState(data);
    } catch (error) {
      if (markExpired(error)) return;
      setBootError(
        error instanceof Error
          ? error.message
          : 'Не удалось загрузить приложение. Проверьте соединение.',
      );
    } finally {
      setLoading(false);
    }
  }, [markExpired]);

  // Тихое обновление данных: подменяет state, не трогая вкладку, шторки и прокрутку.
  const refreshRef = useRef({ last: 0, failures: 0, nextAllowed: 0, inFlight: false, stopped: false });
  const refresh = useCallback(
    async (manual = false): Promise<void> => {
      const r = refreshRef.current;
      const now = Date.now();
      if (r.inFlight || r.stopped) return;
      if (!manual && (now - r.last < 10_000 || now < r.nextAllowed)) return;
      r.inFlight = true;
      r.last = now;
      if (manual) setRefreshing(true);
      try {
        const data = await api.getState();
        r.failures = 0;
        r.nextAllowed = 0;
        setState(data);
      } catch (error) {
        if (markExpired(error)) {
          r.stopped = true;
          return;
        }
        r.failures += 1;
        r.nextAllowed = Date.now() + Math.min(300_000, 30_000 * 2 ** Math.min(r.failures, 4));
        if (manual) showToast('Не удалось обновить. Проверьте соединение.', 'error');
      } finally {
        r.inFlight = false;
        if (manual) setRefreshing(false);
      }
    },
    [markExpired, showToast],
  );

  const hasState = state !== null;
  useEffect(() => {
    if (!hasState) return;
    const tick = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    const timer = window.setInterval(tick, 30_000);
    document.addEventListener('visibilitychange', tick);
    window.addEventListener('focus', tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
      window.removeEventListener('focus', tick);
    };
  }, [hasState, refresh]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onResize = () => {
      void applyViewport();
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (!state) return;
    const role = state.viewer.role;
    const base = role === 'director' ? DIRECTOR_TABS : role === 'teacher' ? TEACHER_TABS : STUDENT_TABS;
    const allowed: TabId[] = isAdminOnly(state)
      ? ADMIN_ONLY_TABS
      : state.platform_admin
      ? [...base, ...ADMIN_TABS]
      : base;
    if (!tabFromPath(window.location.pathname) || !allowed.includes(tab)) {
      const preferred = role === 'director' ? lastDirectorTab.current : role === 'teacher' ? lastTeacherTab.current : lastStudentTab.current;
      const next = allowed.includes(preferred) ? preferred : allowed[0];
      setTab(next);
      window.history.replaceState({}, '', pathForTab(next, role));
    }
  }, [state, tab]);

  // Подпись тестового пользователя в списке песочницы: имя и роль после регистрации.
  useEffect(() => {
    if (!state || state.mode !== 'sandbox') return;
    const active = activeSandboxClientId();
    if (!active) return;
    const roleLabel = { student: 'ученик', teacher: 'педагог', director: 'директор' }[state.viewer.role];
    const registered = state.viewer.onboarded || state.viewer.role !== 'student';
    // «Герой» - имя по умолчанию: для него показываем только роль.
    const named = state.viewer.first_name && state.viewer.first_name !== 'Герой';
    const detail = !registered ? '' : named ? ` — ${state.viewer.first_name}, ${roleLabel}` : `, ${roleLabel}`;
    if (setSandboxDetail(active, detail)) {
      setSandbox({ users: listSandboxUsers(), active });
    }
  }, [state]);

  // Повышение ранга видит только сам ученик у себя.
  useEffect(() => {
    if (!state || state.viewer.role !== 'student' || !state.viewer.onboarded) return;
    const key = `school-hero:level:${state.viewer.id}`;
    const current = state.viewer.level.level;
    let previous: number | null = null;
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) {
        const parsed = Number.parseInt(raw, 10);
        previous = Number.isNaN(parsed) ? null : parsed;
      }
    } catch {
      // Storage unavailable: nothing to compare with.
    }
    if (previous !== current) {
      try {
        localStorage.setItem(key, String(current));
      } catch {
        // Ignore.
      }
    }
    if (previous !== null && current > previous) {
      setLevelUp({ level: state.viewer.level, avatar: state.viewer.avatar });
    }
  }, [state]);

  useEffect(() => {
    const handlePopState = () => {
      const next = tabFromPath(window.location.pathname);
      if (next) setTab(next);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    const role = state?.viewer.role;
    document.title =
      role === 'director'
        ? 'Администрация школы · Школьный герой'
        : role === 'teacher'
        ? 'Кабинет педагога · Школьный герой'
        : 'Школьный герой';
  }, [state?.viewer.role]);

  const navigate = useCallback(
    (next: TabId) => {
      const role = state?.viewer.role ?? 'student';
      if (role === 'director') lastDirectorTab.current = next;
      else if (role === 'teacher') lastTeacherTab.current = next;
      else lastStudentTab.current = next;

      setTab(next);
      window.history.pushState({}, '', pathForTab(next, role));
      setChallengeId(null);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      tapHaptic();
    },
    [state?.viewer.role],
  );

  async function mutate<T>(
    key: string,
    action: () => Promise<MutationResponse<T>>,
  ): Promise<MutationResponse<T> | null> {
    setBusy(key);
    try {
      const response = await action();
      setState(response.state);
      return response;
    } catch (error) {
      if (markExpired(error)) return null;
      showToast(
        error instanceof Error ? error.message : 'Что-то пошло не так. Попробуйте ещё раз.',
        'error',
      );
      return null;
    } finally {
      setBusy(null);
    }
  }

  const handleSubmit = async (id: number, proof: string, proofUrl?: string): Promise<boolean> => {
    const response = await mutate(`submit:${id}`, () => api.submit(id, proof, proofUrl));
    if (!response) return false;
    const result = response.result as SubmitResult | undefined;
    showToast(
      result ? `«${result.challenge_title}» отправлено педагогу` : 'Работа отправлена на проверку',
      'success',
      'send',
    );
    return true;
  };

  const handleEquip = async (key: string, itemId: string): Promise<boolean> => {
    const response = await mutate(`equip:${itemId}`, () => api.equip(key, itemId));
    if (!response) return false;
    showToast('Образ сохранён', 'success', 'shirt');
    return true;
  };

  const handleBuy = async (itemId: string): Promise<boolean> => {
    const response = await mutate(`buy:${itemId}`, () => api.buy(itemId));
    if (!response) return false;
    showToast('Предмет куплен', 'success', 'gift');
    return true;
  };

  const handleApprove = async (completionId: number): Promise<boolean> => {
    const response = await mutate(`review:${completionId}`, () =>
      api.review(completionId, 'approve'),
    );
    if (!response) return false;
    const result = response.result as ReviewResult | undefined;
    if (result) {
      showToast(`${result.student_name}: +${result.xp_awarded} XP`, 'success', 'spark');
    }
    return true;
  };

  /** Тост пакетной проверки по фактическим счётчикам ответа сервера. */
  const batchToast = (result: BatchReviewResult | undefined, fallbackTotal: number) => {
    const approved = result?.counts?.approved ?? result?.approved ?? 0;
    const rejected = result?.counts?.rejected ?? result?.rejected ?? 0;
    const failed = result?.counts?.failed ?? result?.failed ?? 0;
    if (!result) {
      showToast(`Обработано работ: ${fallbackTotal}`, 'info', 'check');
      return;
    }
    const parts: string[] = [];
    if (approved) parts.push(`принято ${approved}`);
    if (rejected) parts.push(`отклонено ${rejected}`);
    if (failed) parts.push(`не удалось ${failed}`);
    let message = parts.length ? parts.join(', ') : 'Ничего не изменилось';
    message = message.charAt(0).toUpperCase() + message.slice(1);
    const reason = result.errors?.[0]?.detail;
    if (failed && reason) message += `. Причина: ${reason}`;
    showToast(message, failed ? (approved || rejected ? 'info' : 'error') : 'success', failed ? 'edit' : 'check');
  };

  const handleBatchApprove = async (completionIds: number[]): Promise<boolean> => {
    const response = await mutate('batch-review', () => api.batchReview(completionIds, 'approve'));
    if (!response) return false;
    batchToast(response.result as BatchReviewResult | undefined, completionIds.length);
    return true;
  };

  const handleBatchReject = async (completionIds: number[], reason: string): Promise<boolean> => {
    const response = await mutate('batch-review', () =>
      api.batchReview(completionIds, 'reject', reason),
    );
    if (!response) return false;
    batchToast(response.result as BatchReviewResult | undefined, completionIds.length);
    return true;
  };

  const handleReject = async (completionId: number, reason: string): Promise<boolean> => {
    const response = await mutate(`review:${completionId}`, () =>
      api.review(completionId, 'reject', reason),
    );
    if (!response) return false;
    showToast('Работа возвращена на доработку', 'info', 'edit');
    return true;
  };

  const handleCreate = async (payload: {
    title: string;
    description: string;
    category: string;
    xp: number;
    kind: string;
    deadline: string;
    subject?: string;
    subject_other?: string;
    proof_type?: 'text' | 'link' | 'photo';
  }): Promise<boolean> => {
    const response = await mutate('create', () => api.createChallenge(payload));
    if (!response) return false;
    showToast('Задание опубликовано', 'success', 'flag');
    return true;
  };

  const handleRemoveStudent = async (studentId: number, reason: string): Promise<boolean> => {
    const response = await mutate(`remove:${studentId}`, () => api.removeStudent(studentId, reason));
    if (!response) return false;
    showToast('Ученик исключён', 'info', 'check');
    return true;
  };

  const handleRestoreStudent = async (studentId: number): Promise<boolean> => {
    const response = await mutate(`restore:${studentId}`, () => api.restoreStudent(studentId));
    if (!response) return false;
    showToast('Запрет снят', 'info', 'check');
    return true;
  };

  const handleRewardStudent = async (
    studentId: number,
    amount = 50,
    reason = 'Активность на уроке',
  ): Promise<boolean> => {
    const response = await mutate(`reward:${studentId}`, () =>
      api.rewardStudent(studentId, amount, reason),
    );
    if (!response) return false;
    showToast(`Начислено: +${amount} XP`, 'success', 'spark');
    return true;
  };

  const handleArchive = async (id: number): Promise<boolean> => {
    const response = await mutate(`archive:${id}`, () => api.archiveChallenge(id));
    if (!response) return false;
    showToast('Задание перемещено в архив', 'info', 'archive');
    return true;
  };

  const handleRole = async (role: 'student' | 'teacher' | 'director'): Promise<boolean> => {
    const response = await mutate('role', () => api.setRole(role));
    if (!response) return false;
    const nextTab: TabId = role === 'director' ? 'director-overview' : role === 'teacher' ? 'teacher-class' : 'hero';
    if (role === 'director') lastDirectorTab.current = nextTab;
    else if (role === 'teacher') lastTeacherTab.current = nextTab;
    else lastStudentTab.current = nextTab;

    setTab(nextTab);
    window.history.pushState({}, '', pathForTab(nextTab, role));
    setChallengeId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });

    const labels = {
      director: 'Роль: директор',
      teacher: 'Роль: педагог',
      student: 'Роль: ученик',
    };
    showToast(labels[role], 'info', 'shield');
    return true;
  };

  const handleReset = async (): Promise<boolean> => {
    const response = await mutate('reset', () => api.resetDemo());
    if (!response) return false;
    lastStudentTab.current = 'hero';
    setTab('hero');
    window.history.pushState({}, '', pathForTab('hero'));
    showToast('Демо-данные сброшены', 'info', 'refresh');
    return true;
  };

  const handleOnboarding = async (
    firstName: string,
    avatar: Record<string, string>,
    lastName = '',
    classId?: number,
    inviteCode?: string,
  ): Promise<string | null> => {
    setBusy('onboarding');
    try {
      const response = await api.onboarding(firstName, avatar, lastName, classId, inviteCode);
      setState(response.state);
      setTab('hero');
      window.history.replaceState({}, '', pathForTab('hero'));
      showToast('Профиль создан', 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось создать профиль.';
    } finally {
      setBusy(null);
    }
  };

  const switchSandbox = (change: () => void) => {
    change();
    setSandboxReset(false);
    lastStudentTab.current = 'hero';
    lastTeacherTab.current = 'teacher-class';
    lastDirectorTab.current = 'director-overview';
    setAudience(null);
    setChallengeId(null);
    setLevelUp(null);
    setTab('hero');
    window.history.replaceState({}, '', '/');
    setSandbox({ users: listSandboxUsers(), active: activeSandboxClientId() ?? '' });
    void load();
  };

  /** Возвращает текст ошибки или null. Имя сохраняется на сервере и не затирается данными MAX. */
  const handleSetName = async (firstName: string, lastName: string): Promise<string | null> => {
    try {
      const response = await api.setName(firstName, lastName);
      setState(response.state);
      showToast('Имя сохранено', 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось сохранить имя.';
    }
  };

  const goToRoleHome = (role: 'student' | 'teacher' | 'director', next?: TabId) => {
    const target: TabId =
      next ?? (role === 'director' ? 'director-overview' : role === 'teacher' ? 'teacher-class' : 'hero');
    if (role === 'director') lastDirectorTab.current = target;
    else if (role === 'teacher') lastTeacherTab.current = target;
    else lastStudentTab.current = target;
    setTab(target);
    window.history.replaceState({}, '', pathForTab(target, role));
    window.scrollTo({ top: 0 });
  };

  /** Возвращает текст ошибки или null: ошибка показывается прямо в форме. */
  const handleCreateSchool = async (payload: NewSchoolPayload): Promise<string | null> => {
    setBusy('school-create');
    try {
      const response = await api.createSchool(payload);
      setState(response.state);
      setAudience(null);
      goToRoleHome('director', 'director-setup');
      showToast('Школа создана', 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось создать школу. Попробуйте ещё раз.';
    } finally {
      setBusy(null);
    }
  };

  /** Возвращает текст ошибки или null при успехе. */
  const handleJoinTeacher = async (code: string): Promise<string | null> => {
    setBusy('join');
    try {
      const response = await api.joinSchool(code);
      setState(response.state);
      setAudience(null);
      goToRoleHome(response.state.viewer.role);
      showToast('Вы подключены к классу', 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось проверить код';
    } finally {
      setBusy(null);
    }
  };

  const handleJoinClass = async (classId?: number, inviteCode?: string): Promise<string | null> => {
    setBusy('join');
    try {
      const response = await api.joinSchool(inviteCode, classId);
      setState(response.state);
      setAudience(null);
      setCodeInstead(false);
      if (response.status === 'requested') {
        showToast('Заявка отправлена педагогу', 'success', 'send');
      } else {
        goToRoleHome(response.state.viewer.role);
        showToast('Класс выбран', 'success', 'check');
      }
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось выбрать класс';
    } finally {
      setBusy(null);
    }
  };

  const handleAddClass = async (schoolId: number, name: string): Promise<string | null> => {
    setBusy('school-class');
    try {
      const response = await api.addClass(schoolId, name);
      setState(response.state);
      showToast(`Класс ${name} добавлен`, 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось добавить класс.';
    } finally {
      setBusy(null);
    }
  };

  const handleUpdateClass = async (
    classId: number,
    patch: { name?: string; weekly_goal?: number },
  ): Promise<string | null> => {
    setBusy('school-class');
    try {
      const response = await api.updateClass(classId, patch);
      setState(response.state);
      showToast('Класс обновлён', 'success', 'check');
      return null;
    } catch (error) {
      if (markExpired(error)) return null;
      return error instanceof Error ? error.message : 'Не удалось сохранить изменения.';
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteClass = async (classId: number): Promise<boolean> => {
    const response = await mutate('school-class', () => api.deleteClass(classId));
    if (!response) return false;
    showToast('Класс удалён', 'info', 'archive');
    return true;
  };

  const handleResetCode = async (
    classId: number,
    kind: 'student' | 'teacher',
    disconnectTeachers = false,
  ): Promise<boolean> => {
    const response = await mutate('school-code', () => api.resetCode(classId, kind, disconnectTeachers));
    if (!response) return false;
    showToast(
      disconnectTeachers ? 'Новый код выпущен, педагоги отключены' : 'Новый код выпущен',
      'info',
      'refresh',
    );
    return true;
  };

  const handleDisconnectTeacher = async (classId: number, teacherId: number): Promise<boolean> => {
    const response = await mutate(`teacher-off:${teacherId}`, () =>
      api.disconnectTeacher(classId, teacherId),
    );
    if (!response) return false;
    showToast('Педагог отключён от класса', 'info', 'check');
    return true;
  };

  const handleDecideJoin = async (
    requestId: number,
    action: 'approve' | 'decline',
  ): Promise<boolean> => {
    const response = await mutate(`join:${requestId}`, () => api.decideJoinRequest(requestId, action));
    if (!response) return false;
    showToast(action === 'approve' ? 'Ученик принят в класс' : 'Заявка отклонена', 'info', 'check');
    return true;
  };

  const handleCancelJoin = async (): Promise<boolean> => {
    const response = await mutate('join-cancel', () => api.cancelJoinRequest());
    if (!response) return false;
    setCodeInstead(false);
    showToast('Заявка отменена', 'info', 'check');
    return true;
  };

  const handleSetTimezone = async (schoolId: number, timezone: string): Promise<boolean> =>
    Boolean(await mutate('school-timezone', () => api.setSchoolTimezone(schoolId, timezone)));

  const handleSelectSchool = async (schoolId: number): Promise<boolean> =>
    Boolean(await mutate('school-select', () => api.selectSchool(schoolId)));

  const handleSchoolStatus = async (
    schoolId: number,
    status: 'active' | 'rejected',
    reason = '',
  ): Promise<boolean> => {
    const response = await mutate('school-status', () =>
      api.setSchoolStatus(schoolId, status, reason),
    );
    if (!response) return false;
    showToast(status === 'active' ? 'Школа активна' : 'Школа отклонена', 'info', 'check');
    return true;
  };

  const handleDeleteSchool = async (
    schoolId: number,
    confirmName: string,
  ): Promise<DeletedSchoolSummary | null> => {
    let deleted: DeletedSchoolSummary | null = null;
    const response = await mutate('school-delete', async () => {
      const result = await api.adminDeleteSchool(schoolId, confirmName);
      deleted = result.deleted;
      return result;
    });
    return response ? deleted : null;
  };

  if (blocked) {
    return (
      <div className="app">
        <div className="gate">
          <div className="gate__box ad-blocked">
            <EmptyState
              icon="lock"
              title="Доступ ограничен"
              text="Доступ к приложению ограничен администратором платформы. Если вы считаете, что это ошибка, обратитесь в администрацию своей школы."
            />
          </div>
        </div>
      </div>
    );
  }

  if (sessionExpired) {
    return (
      <div className="app">
        <div className="gate">
          <div className="gate__box">
            <EmptyState
              icon="clock"
              title="Сессия устарела"
              text="Закройте и снова откройте приложение в MAX."
              action={
                <button type="button" className="btn" onClick={() => window.location.reload()}>
                  Обновить
                </button>
              }
            />
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="app">
        <div className="gate">
          <LoadingScreen label="Загрузка…" />
        </div>
      </div>
    );
  }

  if (outsideMax) {
    return (
      <div className="app">
        <div className="gate">
          <div className="gate__box">
            <EmptyState
              icon="max"
              title="Откройте приложение внутри MAX"
              text="Сервис работает только как мини-приложение в мессенджере MAX. Откройте его из чата или каталога приложений."
            />
          </div>
        </div>
      </div>
    );
  }

  if (bootError || !state) {
    return (
      <div className="app">
        <div className="gate">
          <LoadingScreen
            error={bootError || 'Не удалось загрузить приложение.'}
            onRetry={() => void load()}
          />
        </div>
      </div>
    );
  }

  const sandboxBar =
    sandbox && state.mode === 'sandbox' ? (
      <SandboxBar
        users={sandbox.users}
        active={sandbox.active}
        notice={sandboxReset ? 'Сервер песочницы перезапущен, тестовые пользователи сброшены.' : null}
        onDismissNotice={() => setSandboxReset(false)}
        onSwitch={(id) => switchSandbox(() => switchSandboxUser(id))}
        onNew={() => switchSandbox(() => addSandboxUser())}
        isAdmin={state.viewer.is_platform_admin}
        adminBusy={busy !== null}
        onToggleAdmin={(enabled) => void mutate('sandbox-admin', () => api.setSandboxAdmin(enabled))}
      />
    ) : null;

  // Педагог и директор без имени: имя спрашиваем до остальных экранов.
  // Пользователю без роли (ученику) имя спрашивает онбординг.
  if (state.viewer.needs_name && state.viewer.role !== 'student') {
    return (
      <div className="app">
        <div className="shell">
          {sandboxBar}
          <NameScreen onSubmit={handleSetName} />
        </div>
      </div>
    );
  }

  // Ученик без профиля или без класса проходит регистрацию. В демо класс есть всегда.
  // Администратору платформы регистрация ученика не нужна: сразу заявки школ.
  const adminOnly = isAdminOnly(state);
  const needsRegistration =
    !adminOnly &&
    state.viewer.role === 'student' &&
    (!state.viewer.onboarded || !state.viewer.class_id);
  const joinRequest = state.viewer.join_request;
  if (needsRegistration && joinRequest?.status === 'pending' && !codeInstead) {
    return (
      <div className="app">
        <div className="shell">
          {sandboxBar}
          <JoinRequestScreen
            request={joinRequest}
            onCancel={handleCancelJoin}
            onUseCode={() => setCodeInstead(true)}
            onRefresh={() => void load()}
          />
        </div>
      </div>
    );
  }
  if (needsRegistration) {
    const removedFrom = state.viewer.removed_from;
    const removedNotice = removedFrom
      ? `Вы больше не состоите в классе ${removedFrom.class_name}${removedFrom.school_name ? ` (${removedFrom.school_name})` : ''}. В классы этой школы вернуться можно только после того, как педагог снимет запрет. Можно выбрать другую школу.`
      : joinRequest?.status === 'declined'
      ? `Заявку в класс ${joinRequest.class_name} (${joinRequest.school_name}) отклонили. Выберите другой класс или войдите по коду класса.`
      : undefined;
    // Исключённому ученику сразу показываем выбор класса.
    const chosen = state.mode === 'demo' || removedFrom || codeInstead || joinRequest ? 'student' : audience;
    return (
      <div className="app">
        <div className="shell">
          {sandboxBar}
          {chosen === 'school' ? (
            <SchoolRegisterScreen
              busy={busy !== null}
              timezones={state.timezones}
              onBack={() => setAudience(null)}
              onCreate={handleCreateSchool}
              onJoinTeacher={handleJoinTeacher}
            />
          ) : chosen === 'student' ? (
            <OnboardingScreen
              state={state}
              onComplete={handleOnboarding}
              joinOnly={state.viewer.onboarded}
              onJoin={handleJoinClass}
              notice={removedNotice}
              initialMode={codeInstead ? 'code' : undefined}
              onBack={
                codeInstead
                  ? () => setCodeInstead(false)
                  : state.mode === 'demo' || removedFrom
                  ? undefined
                  : () => setAudience(null)
              }
            />
          ) : (
            <AudienceChoice
              onStudent={() => setAudience('student')}
              onSchool={() => setAudience('school')}
            />
          )}
        </div>
      </div>
    );
  }

  if (changingClass && state.viewer.role === 'student' && !adminOnly) {
    return (
      <div className="app">
        <div className="shell">
          {sandboxBar}
          <OnboardingScreen
            state={state}
            onComplete={handleOnboarding}
            joinOnly
            onJoin={async (classId, inviteCode) => {
              const error = await handleJoinClass(classId, inviteCode);
              if (!error) setChangingClass(false);
              return error;
            }}
            notice="Рейтинг класса не переносится: в новом классе набранные в прежнем классе очки в его рейтинг не войдут."
            onBack={() => setChangingClass(false)}
          />
        </div>
      </div>
    );
  }

  const role = state.viewer.role;
  const isTeacher = role === 'teacher';
  const isDirector = role === 'director';
  const teacher = state.teacher;
  const director = state.director;
  const selectedChallenge = state.challenges.find((item) => item.id === challengeId) ?? null;

  const studentTabs: TabItem[] = [
    { id: 'hero', label: 'Мой трек', icon: 'home' },
    {
      id: 'challenges',
      label: 'Задания',
      icon: 'list',
      // Доступные задания и работы, возвращённые на доработку.
      badge: state.challenges.filter((c) => c.status === 'available' || c.status === 'rejected').length,
    },
    { id: 'leaderboard', label: 'Рейтинг', icon: 'trophy' },
    { id: 'wardrobe', label: 'Стиль', icon: 'shirt' },
    { id: 'profile', label: 'Профиль', icon: 'user' },
  ];

  const teacherTabs: TabItem[] = [
    {
      id: 'teacher-class',
      label: 'Класс',
      icon: 'users',
      // Заявки учеников, выбравших класс из списка.
      badge: teacher?.join_requests?.length ?? 0,
    },
    {
      id: 'teacher-review',
      label: 'Проверка',
      icon: 'shield',
      badge: teacher?.pending.length ?? 0,
    },
    { id: 'teacher-challenges', label: 'Задания', icon: 'list' },
    { id: 'profile', label: 'Профиль', icon: 'user' },
  ];

  const directorTabs: TabItem[] = [
    { id: 'director-overview', label: 'Школа', icon: 'shield' },
    { id: 'director-classes', label: 'Классы', icon: 'users' },
    {
      id: 'director-setup',
      label: 'Коды',
      icon: 'settings',
      badge: state.school_admin?.join_requests?.length ?? 0,
    },
    { id: 'profile', label: 'Профиль', icon: 'user' },
  ];

  const adminTabs: TabItem[] = [
    {
      id: 'admin-schools',
      label: 'Школы',
      icon: 'shield',
      badge: state.platform_admin?.pending.length ?? 0,
    },
    { id: 'admin-users', label: 'Люди', icon: 'users' },
  ];

  const busyItem = busy?.startsWith('equip:')
    ? busy.slice(6)
    : busy?.startsWith('buy:')
    ? busy.slice(4)
    : null;

  const reviewBusyId = busy?.startsWith('review:')
    ? Number.parseInt(busy.slice(7), 10)
    : null;

  const roleTabs = isDirector ? directorTabs : isTeacher ? teacherTabs : studentTabs;
  const currentTabs: TabItem[] = adminOnly
    ? [...adminTabs, { id: 'profile', label: 'Профиль', icon: 'user' }]
    : state.platform_admin
    ? [...roleTabs, ...adminTabs]
    : roleTabs;

  const isDemo = state.mode === 'demo';
  const roleOptions: { id: 'student' | 'teacher' | 'director'; label: string }[] = [
    { id: 'student', label: 'Ученик' },
    { id: 'teacher', label: 'Педагог' },
    { id: 'director', label: 'Директор' },
  ];

  return (
    <div className="app">
      <DesktopSidebar
        tabs={currentTabs}
        active={tab}
        onChange={navigate}
        viewer={state.viewer}
        theme={theme}
        onThemeToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onProfile={() => navigate('profile')}
        hideHero={adminOnly}
      />

      <div className="shell">
        <AppHeader
          viewer={state.viewer}
          onProfile={() => navigate('profile')}
          demo={isDemo}
          hideHero={adminOnly}
          onRefresh={() => void refresh(true)}
          refreshing={refreshing}
        />

        <header className="desk-head">
          <div className="desk-head__crumbs">
            <span>
              {adminOnly ? 'Платформа' : isDirector ? 'Администрация' : isTeacher ? 'Педагог' : 'Ученик'}
            </span>
            <span aria-hidden="true">/</span>
            <strong>{currentTabs.find((t) => t.id === tab)?.label || 'Обзор'}</strong>
          </div>
          <div className="desk-head__meta">
            {isDemo ? <span className="badge-demo">Демо</span> : null}
            {state.viewer.school_name ? <span>{state.viewer.school_name}</span> : null}
          </div>
        </header>

        {sandboxBar}

        {isDemo ? (
          <div className="demo-bar" role="group" aria-label="Демо: выбор роли">
            <span className="demo-bar__label">Демо</span>
            <div className="demo-bar__roles">
              {roleOptions.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={role === option.id}
                  onClick={() => void handleRole(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button type="button" className="demo-bar__reset" onClick={() => void handleReset()}>
              Сбросить
            </button>
          </div>
        ) : null}

        <main className="screen-wrap" key={tab}>
          {tab === 'hero' ? (
            <HeroScreen state={state} onOpenChallenge={setChallengeId} onNavigate={navigate} />
          ) : null}

          {tab === 'challenges' ? (
            <ChallengesScreen state={state} onOpenChallenge={setChallengeId} />
          ) : null}

          {tab === 'leaderboard' ? (
            <LeaderboardScreen
              state={state}
              onNavigateChallenges={() => navigate('challenges')}
            />
          ) : null}

          {tab === 'wardrobe' ? (
            <WardrobeScreen
              state={state}
              onEquip={handleEquip}
              onBuy={handleBuy}
              busyItem={busyItem}
            />
          ) : null}

          {tab === 'profile' ? (
            <ProfileScreen
              state={state}
              onNavigate={navigate}
              onChangeName={handleSetName}
              theme={theme}
              onThemeChange={setTheme}
              adminOnly={adminOnly}
              onChangeClass={state.mode === 'demo' ? undefined : () => setChangingClass(true)}
            />
          ) : null}

          {tab === 'teacher-class' && isTeacher && teacher ? (
            <TeacherClassScreen
              state={state}
              onReview={() => navigate('teacher-review')}
              onRewardStudent={handleRewardStudent}
              onRemoveStudent={handleRemoveStudent}
              onRestoreStudent={handleRestoreStudent}
              onDecideJoin={handleDecideJoin}
            />
          ) : null}

          {tab === 'teacher-review' && isTeacher && teacher ? (
            <TeacherReviewScreen
              teacher={teacher}
              busyId={reviewBusyId}
              onApprove={handleApprove}
              onReject={handleReject}
              onBatchApprove={handleBatchApprove}
              onBatchReject={handleBatchReject}
            />
          ) : null}

          {tab === 'teacher-challenges' && isTeacher && teacher ? (
            <TeacherChallengesScreen
              state={state}
              teacher={teacher}
              onCreate={handleCreate}
              onArchive={handleArchive}
              busy={busy === 'create' || Boolean(busy?.startsWith('archive:'))}
            />
          ) : null}

          {(tab === 'director-overview' || tab === 'director-classes') && isDirector && director ? (
            <DirectorScreen
              state={state}
              director={director}
              section={tab === 'director-classes' ? 'classes' : 'school'}
            />
          ) : null}

          {tab === 'director-setup' && isDirector && state.school_admin ? (
            <SchoolSetupScreen
              state={state}
              admin={state.school_admin}
              busy={busy !== null}
              notify={showToast}
              onAddClass={handleAddClass}
              onUpdateClass={handleUpdateClass}
              onDeleteClass={handleDeleteClass}
              onResetCode={handleResetCode}
              onDisconnectTeacher={handleDisconnectTeacher}
              onDecideJoin={handleDecideJoin}
              onSelectSchool={handleSelectSchool}
              onSetTimezone={handleSetTimezone}
              onCreateSchool={handleCreateSchool}
            />
          ) : null}

          {tab === 'admin-schools' && state.platform_admin ? (
            <AdminSchoolsScreen
              busy={busy !== null}
              notify={showToast}
              onSetStatus={handleSchoolStatus}
              onDelete={handleDeleteSchool}
            />
          ) : null}

          {tab === 'admin-users' && state.platform_admin ? (
            <AdminUsersScreen notify={showToast} />
          ) : null}

          {isDirector && !state.school_admin && !director && tab.startsWith('director-') ? (
            <DirectorNoSchoolScreen busy={busy !== null} timezones={state.timezones} onCreate={handleCreateSchool} />
          ) : null}

          {isTeacher && !teacher && tab.startsWith('teacher-') ? (
            <TeacherNoClassScreen busy={busy !== null} onJoinTeacher={handleJoinTeacher} />
          ) : null}
        </main>

        <TabBar tabs={currentTabs} active={tab} onChange={navigate} />
      </div>

      <ChallengeSheet
        challenge={selectedChallenge}
        onClose={() => setChallengeId(null)}
        onSubmit={handleSubmit}
        busy={busy === `submit:${challengeId}`}
      />

      <Sheet open={Boolean(levelUp)} onClose={() => setLevelUp(null)} title="Новый ранг">
        {levelUp ? (
          <div className="levelup">
            <AvatarFrame avatar={levelUp.avatar} size={96} level={levelUp.level.level} />
            <h2 className="levelup__name">{levelUp.level.title}</h2>
            <p className="levelup__text">Ваш ранг повысился до {levelUp.level.level}</p>
            <button type="button" className="btn btn--block" onClick={() => setLevelUp(null)}>
              Закрыть
            </button>
          </div>
        ) : null}
      </Sheet>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
