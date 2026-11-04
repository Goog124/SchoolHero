import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import { AppHeader } from './components/AppHeader';
import { AvatarFrame } from './components/AvatarFrame';
import { ChallengeSheet } from './components/ChallengeSheet';
import { DesktopSidebar } from './components/DesktopSidebar';
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
  type SandboxUser,
} from './sandbox';
import { ChallengesScreen } from './screens/ChallengesScreen';
import { DirectorScreen } from './screens/DirectorScreen';
import { HeroScreen } from './screens/HeroScreen';
import { LeaderboardScreen } from './screens/LeaderboardScreen';
import { OnboardingScreen } from './screens/OnboardingScreen';
import {
  AdminSchoolsScreen,
  AudienceChoice,
  SchoolRegisterScreen,
  SchoolSetupScreen,
} from './screens/SchoolSetupScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { TeacherChallengesScreen } from './screens/TeacherChallengesScreen';
import { TeacherClassScreen } from './screens/TeacherClassScreen';
import { TeacherReviewScreen } from './screens/TeacherReviewScreen';
import { WardrobeScreen } from './screens/WardrobeScreen';
import type {
  AvatarConfig,
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
    'director-reports': '/director/reports',
  };
  return routes[tab] || '/';
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('school-hero:theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      // System default
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

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
  const [sessionExpired, setSessionExpired] = useState(false);
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
    if (error instanceof ApiError && error.status === 401 && activeSandboxClientId() === null) {
      setSessionExpired(true);
      return true;
    }
    return false;
  }, []);

  const load = useCallback(async () => {
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

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('school-hero:theme', theme);
    } catch {
      // Fallback
    }
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
    const allowed: TabId[] = state.platform_admin ? [...base, 'admin-schools'] : base;
    if (!tabFromPath(window.location.pathname) || !allowed.includes(tab)) {
      const next = role === 'director' ? lastDirectorTab.current : role === 'teacher' ? lastTeacherTab.current : lastStudentTab.current;
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
    const detail = registered ? `${state.viewer.first_name}, ${roleLabel}` : '';
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

  const handleBatchApprove = async (completionIds: number[]): Promise<boolean> => {
    const response = await mutate('batch-review', () => api.batchReview(completionIds, 'approve'));
    if (!response) return false;
    showToast(`Принято работ: ${completionIds.length}`, 'success', 'check');
    return true;
  };

  const handleBatchReject = async (completionIds: number[], reason: string): Promise<boolean> => {
    const response = await mutate('batch-review', () =>
      api.batchReview(completionIds, 'reject', reason),
    );
    if (!response) return false;
    showToast(`Возвращено на доработку: ${completionIds.length}`, 'info', 'edit');
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
    proof_type?: 'text' | 'link' | 'photo';
  }): Promise<boolean> => {
    const response = await mutate('create', () => api.createChallenge(payload));
    if (!response) return false;
    showToast('Задание опубликовано', 'success', 'flag');
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
  ): Promise<boolean> => {
    setBusy('onboarding');
    try {
      const response = await api.onboarding(firstName, avatar, lastName, classId, inviteCode);
      setState(response.state);
      setTab('hero');
      window.history.replaceState({}, '', pathForTab('hero'));
      showToast('Профиль создан', 'success', 'check');
      return true;
    } catch (error) {
      if (markExpired(error)) return false;
      showToast(
        error instanceof Error ? error.message : 'Не удалось создать профиль.',
        'error',
      );
      return false;
    } finally {
      setBusy(null);
    }
  };

  const switchSandbox = (change: () => void) => {
    change();
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

  const handleJoinClass = async (classId?: number, inviteCode?: string): Promise<boolean> => {
    setBusy('join');
    try {
      const response = await api.joinSchool(inviteCode, classId);
      setState(response.state);
      setAudience(null);
      goToRoleHome(response.state.viewer.role);
      showToast('Класс выбран', 'success', 'check');
      return true;
    } catch (error) {
      if (markExpired(error)) return false;
      showToast(error instanceof Error ? error.message : 'Не удалось выбрать класс', 'error');
      return false;
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

  const handleResetCode = async (classId: number, kind: 'student' | 'teacher'): Promise<boolean> => {
    const response = await mutate('school-code', () => api.resetCode(classId, kind));
    if (!response) return false;
    showToast('Новый код выпущен', 'info', 'refresh');
    return true;
  };

  const handleSelectSchool = async (schoolId: number): Promise<boolean> =>
    Boolean(await mutate('school-select', () => api.selectSchool(schoolId)));

  const handleSchoolStatus = async (
    schoolId: number,
    status: 'active' | 'rejected',
  ): Promise<boolean> => {
    const response = await mutate('school-status', () => api.setSchoolStatus(schoolId, status));
    if (!response) return false;
    showToast(status === 'active' ? 'Школа подтверждена' : 'Заявка отклонена', 'info', 'check');
    return true;
  };

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
        onSwitch={(id) => switchSandbox(() => switchSandboxUser(id))}
        onNew={() => switchSandbox(() => addSandboxUser())}
      />
    ) : null;

  // Ученик без профиля или без класса проходит регистрацию. В демо класс есть всегда.
  const needsRegistration =
    state.viewer.role === 'student' && (!state.viewer.onboarded || !state.viewer.class_id);
  if (needsRegistration) {
    const chosen = state.mode === 'demo' ? 'student' : audience;
    return (
      <div className="app">
        <div className="shell">
          {sandboxBar}
          {chosen === 'school' ? (
            <SchoolRegisterScreen
              busy={busy !== null}
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
              onBack={state.mode === 'demo' ? undefined : () => setAudience(null)}
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

  const role = state.viewer.role;
  const isTeacher = role === 'teacher';
  const isDirector = role === 'director';
  const teacher = state.teacher;
  const director = state.director;
  const selectedChallenge = state.challenges.find((item) => item.id === challengeId) ?? null;

  const studentTabs: TabItem[] = [
    { id: 'hero', label: 'Мой трек', icon: 'home' },
    { id: 'challenges', label: 'Задания', icon: 'list' },
    { id: 'leaderboard', label: 'Рейтинг', icon: 'trophy' },
    { id: 'wardrobe', label: 'Стиль', icon: 'shirt' },
    { id: 'profile', label: 'Профиль', icon: 'user' },
  ];

  const teacherTabs: TabItem[] = [
    { id: 'teacher-class', label: 'Класс', icon: 'users' },
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
    { id: 'director-setup', label: 'Коды', icon: 'settings' },
    { id: 'profile', label: 'Профиль', icon: 'user' },
  ];

  const adminTab: TabItem = {
    id: 'admin-schools',
    label: 'Заявки',
    icon: 'check',
    badge: state.platform_admin?.pending.length ?? 0,
  };

  const busyItem = busy?.startsWith('equip:')
    ? busy.slice(6)
    : busy?.startsWith('buy:')
    ? busy.slice(4)
    : null;

  const reviewBusyId = busy?.startsWith('review:')
    ? Number.parseInt(busy.slice(7), 10)
    : null;

  const roleTabs = isDirector ? directorTabs : isTeacher ? teacherTabs : studentTabs;
  const currentTabs = state.platform_admin ? [...roleTabs, adminTab] : roleTabs;

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
      />

      <div className="shell">
        <AppHeader viewer={state.viewer} onProfile={() => navigate('profile')} demo={isDemo} />

        <header className="desk-head">
          <div className="desk-head__crumbs">
            <span>
              {isDirector ? 'Администрация' : isTeacher ? 'Педагог' : 'Ученик'}
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
              theme={theme}
              onThemeChange={setTheme}
            />
          ) : null}

          {tab === 'teacher-class' && isTeacher ? (
            <TeacherClassScreen
              state={state}
              onReview={() => navigate('teacher-review')}
              onRewardStudent={handleRewardStudent}
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
            <DirectorScreen state={state} director={director} />
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
              onSelectSchool={handleSelectSchool}
              onCreateSchool={handleCreateSchool}
            />
          ) : null}

          {tab === 'admin-schools' && state.platform_admin ? (
            <AdminSchoolsScreen
              data={state.platform_admin}
              busy={busy !== null}
              onSetStatus={handleSchoolStatus}
            />
          ) : null}

          {isDirector && !director && (tab === 'director-overview' || tab === 'director-classes') ? (
            <EmptyState
              icon="shield"
              title="Школа не подключена"
              text="Аккаунт не привязан ни к одной школе. Зарегистрируйте школу или обратитесь к администратору платформы."
            />
          ) : null}

          {isTeacher && !teacher && tab.startsWith('teacher-') ? (
            <EmptyState
              icon="users"
              title="Класс не назначен"
              text="Аккаунт педагога не привязан к классу. Введите код педагога, который выдал директор."
            />
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
