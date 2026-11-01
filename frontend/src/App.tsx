import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { AppHeader } from './components/AppHeader';
import { AvatarFrame } from './components/AvatarFrame';
import { ChallengeSheet } from './components/ChallengeSheet';
import { Icon } from './components/Icon';
import { LoadingScreen } from './components/LoadingScreen';
import { Sheet } from './components/Sheet';
import { TabBar, type TabItem } from './components/TabBar';
import { Toast, type ToastData, type ToastTone } from './components/Toast';
import {
  applyPlatformClass,
  applyViewport,
  errorHaptic,
  shareText,
  successHaptic,
  tapHaptic,
  waitForBridge,
} from './max';
import { ChallengesScreen } from './screens/ChallengesScreen';
import { HeroScreen } from './screens/HeroScreen';
import { LeaderboardScreen } from './screens/LeaderboardScreen';
import { OnboardingScreen } from './screens/OnboardingScreen';
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
  ReviewResult,
  SubmitResult,
  TabId,
} from './types';

type LevelUpData = {
  name: string;
  level: LevelInfo;
  xp: number;
  avatar: AvatarConfig;
};

const STUDENT_TABS: TabId[] = ['hero', 'challenges', 'leaderboard', 'wardrobe', 'profile'];
const TEACHER_TABS: TabId[] = ['teacher-class', 'teacher-review', 'teacher-challenges', 'profile'];

export default function App() {
  const [state, setState] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootError, setBootError] = useState('');
  const [tab, setTab] = useState<TabId>('hero');
  const [toast, setToast] = useState<ToastData | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [levelUp, setLevelUp] = useState<LevelUpData | null>(null);

  const lastStudentTab = useRef<TabId>('hero');
  const lastTeacherTab = useRef<TabId>('teacher-class');
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

  const load = useCallback(async () => {
    setLoading(true);
    setBootError('');
    try {
      await waitForBridge();
      applyPlatformClass();
      await applyViewport();
      const data = await api.getState();
      setState(data);
    } catch (error) {
      setBootError(
        error instanceof Error
          ? error.message
          : 'Не получилось загрузить героя. Проверь соединение.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

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
    const isTeacher = state.viewer.role === 'teacher';
    const allowed = isTeacher ? TEACHER_TABS : STUDENT_TABS;
    if (!allowed.includes(tab)) {
      setTab(isTeacher ? lastTeacherTab.current : lastStudentTab.current);
    }
  }, [state, tab]);

  useEffect(() => {
    document.title = state?.viewer.role === 'teacher' ? 'Кабинет педагога · Школьный герой' : 'Школьный герой';
  }, [state?.viewer.role]);

  const navigate = useCallback(
    (next: TabId) => {
      if (state?.viewer.role === 'teacher') lastTeacherTab.current = next;
      else lastStudentTab.current = next;
      setTab(next);
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
      showToast(
        error instanceof Error ? error.message : 'Что-то пошло не так. Попробуй ещё раз.',
        'error',
      );
      return null;
    } finally {
      setBusy(null);
    }
  }

  const handleSubmit = async (id: number, proof: string): Promise<boolean> => {
    const response = await mutate(`submit:${id}`, () => api.submit(id, proof));
    if (!response) return false;
    const result = response.result as SubmitResult | undefined;
    showToast(
      result ? `«${result.challenge_title}» отправлено педагогу` : 'Работа отправлена педагогу',
      'success',
      'send',
    );
    return true;
  };

  const handleEquip = async (key: string, itemId: string): Promise<boolean> => {
    const response = await mutate(`equip:${itemId}`, () => api.equip(key, itemId));
    if (!response) return false;
    showToast('Образ обновлён — герой примеряет обновку', 'success', 'shirt');
    return true;
  };

  const handleBuy = async (itemId: string): Promise<boolean> => {
    const response = await mutate(`buy:${itemId}`, () => api.buy(itemId));
    if (!response) return false;
    showToast('Покупка в коллекции. Теперь можно надеть!', 'success', 'gift');
    return true;
  };

  const handleApprove = async (completionId: number): Promise<boolean> => {
    const pendingItem = state?.teacher?.pending.find((item) => item.id === completionId);
    const response = await mutate(`review:${completionId}`, () =>
      api.review(completionId, 'approve'),
    );
    if (!response) return false;
    const result = response.result as ReviewResult | undefined;
    if (result) {
      showToast(`${result.student_name}: +${result.xp_awarded} XP`, 'success', 'spark');
      if (result.level_up && result.student_level) {
        setLevelUp({
          name: result.student_name,
          level: result.student_level,
          xp: result.xp_awarded,
          avatar: pendingItem?.avatar ?? response.state.viewer.avatar,
        });
      }
    }
    return true;
  };

  const handleReject = async (completionId: number, reason: string): Promise<boolean> => {
    const response = await mutate(`review:${completionId}`, () =>
      api.review(completionId, 'reject', reason),
    );
    if (!response) return false;
    showToast('Работа отклонена. Ученик увидит причину и сможет исправить.', 'info', 'edit');
    return true;
  };

  const handleCreate = async (payload: {
    title: string;
    description: string;
    category: string;
    xp: number;
    kind: string;
    deadline: string;
  }): Promise<boolean> => {
    const response = await mutate('create', () => api.createChallenge(payload));
    if (!response) return false;
    showToast(`Задание опубликовано для ${response.state.viewer.class_name}`, 'success', 'flag');
    return true;
  };

  const handleArchive = async (id: number): Promise<boolean> => {
    const response = await mutate(`archive:${id}`, () => api.archiveChallenge(id));
    if (!response) return false;
    showToast('Задание отправлено в архив', 'info', 'archive');
    return true;
  };

  const handleRole = async (role: 'student' | 'teacher'): Promise<boolean> => {
    const response = await mutate('role', () => api.setRole(role));
    if (!response) return false;
    const nextTab: TabId = role === 'teacher' ? 'teacher-class' : 'hero';
    if (role === 'teacher') lastTeacherTab.current = nextTab;
    else lastStudentTab.current = nextTab;
    setTab(nextTab);
    setChallengeId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    showToast(
      role === 'teacher' ? 'Кабинет педагога открыт' : 'Ты снова в образе ученика',
      'success',
      role === 'teacher' ? 'shield' : 'user',
    );
    return true;
  };

  const handleReset = async (): Promise<boolean> => {
    const response = await mutate('reset', () => api.resetDemo());
    if (!response) return false;
    lastStudentTab.current = 'hero';
    setTab('hero');
    showToast('Демо-профиль восстановлен: 420 XP и заявка на проверке', 'success', 'refresh');
    return true;
  };

  const handleOnboarding = async (
    firstName: string,
    avatar: Record<string, string>,
  ): Promise<boolean> => {
    setBusy('onboarding');
    try {
      const response = await api.onboarding(firstName, avatar);
      setState(response.state);
      setTab('hero');
      showToast(`Добро пожаловать в игру, ${firstName}!`, 'success', 'sparkles');
      return true;
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : 'Не получилось создать героя.',
        'error',
      );
      return false;
    } finally {
      setBusy(null);
    }
  };

  const handleShare = async () => {
    if (!state) return;
    const { viewer } = state;
    const text = `Я — ${viewer.name}, ${viewer.level.title} в «Школьном герое». ${viewer.xp} XP, ${viewer.streak} дней серии. А ты сможешь прокачать героя лучше?`;
    const result = await shareText(text);
    if (result === 'clipboard') {
      showToast('Текст скопирован — отправь другу в MAX', 'info', 'share');
    } else if (result === 'failed') {
      showToast('Не удалось поделиться. Попробуй ещё раз.', 'error', 'alert');
    } else if (result === 'max' || result === 'native') {
      showToast('Открыто окно отправки', 'info', 'share');
    }
  };

  if (loading) {
    return (
      <div className="app app--loading">
        <LoadingScreen label="Собираем твоего героя" />
      </div>
    );
  }

  if (bootError || !state) {
    return (
      <div className="app app--loading">
        <LoadingScreen
          error={bootError || 'Не удалось загрузить приложение.'}
          onRetry={() => void load()}
        />
      </div>
    );
  }

  if (!state.viewer.onboarded) {
    return (
      <div className="app app--onboarding">
        <div className="shell shell--onboarding">
          <OnboardingScreen state={state} onComplete={handleOnboarding} />
        </div>
      </div>
    );
  }

  const isTeacher = state.viewer.role === 'teacher';
  const teacher = state.teacher;
  const selectedChallenge = state.challenges.find((item) => item.id === challengeId) ?? null;

  const studentTabs: TabItem[] = [
    { id: 'hero', label: 'Герой', icon: 'home' },
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

  const busyItem = busy?.startsWith('equip:')
    ? busy.slice(6)
    : busy?.startsWith('buy:')
      ? busy.slice(4)
      : null;
  const reviewBusyId = busy?.startsWith('review:')
    ? Number.parseInt(busy.slice(7), 10)
    : null;

  return (
    <div className="app">
      <div className="ambient" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>

      <div className="shell">
        <AppHeader viewer={state.viewer} onProfile={() => navigate('profile')} />

        <main className="screen-wrap" key={tab}>
          {tab === 'hero' ? (
            <HeroScreen
              state={state}
              onOpenChallenge={setChallengeId}
              onNavigate={navigate}
              onShare={() => void handleShare()}
            />
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
              onSwitchRole={handleRole}
              onResetDemo={handleReset}
              onShare={() => void handleShare()}
              onNavigate={navigate}
            />
          ) : null}

          {tab === 'teacher-class' && isTeacher ? (
            <TeacherClassScreen
              state={state}
              onReview={() => navigate('teacher-review')}
            />
          ) : null}

          {tab === 'teacher-review' && isTeacher && teacher ? (
            <TeacherReviewScreen
              teacher={teacher}
              busyId={reviewBusyId}
              onApprove={handleApprove}
              onReject={handleReject}
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
        </main>

        <TabBar
          tabs={isTeacher ? teacherTabs : studentTabs}
          active={tab}
          onChange={navigate}
        />
      </div>

      <ChallengeSheet
        challenge={selectedChallenge}
        onClose={() => setChallengeId(null)}
        onSubmit={handleSubmit}
        busy={busy === `submit:${challengeId}`}
      />

      <Sheet
        open={Boolean(levelUp)}
        onClose={() => setLevelUp(null)}
        title="Новый уровень!"
        className="levelup-sheet"
      >
        {levelUp ? (
          <div className="levelup">
            <div className="levelup__burst" aria-hidden="true">
              <span>✦</span>
              <span>✦</span>
              <span>★</span>
              <span>✦</span>
              <span>✦</span>
            </div>
            <AvatarFrame
              avatar={levelUp.avatar}
              size={132}
              level={levelUp.level.level}
              animate
            />
            <h2>{levelUp.name}</h2>
            <p className="levelup__sub">
              Достиг уровня {levelUp.level.level} — <strong>«{levelUp.level.title}»</strong>
            </p>
            <div className="levelup__rewards">
              <span>
                <Icon name="spark" size={16} filled />+{levelUp.xp} XP
              </span>
              <span>
                <Icon name="gift" size={16} />+25 искр
              </span>
            </div>
            <button type="button" className="btn btn--block" onClick={() => setLevelUp(null)}>
              Забрать награду
              <Icon name="check" size={17} />
            </button>
          </div>
        ) : null}
      </Sheet>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
