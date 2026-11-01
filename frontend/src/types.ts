export type AvatarConfig = {
  skin: string;
  hair: string;
  hairColor: string;
  outfit: string;
  accessory: string;
  frame: string;
};

export type LevelInfo = {
  level: number;
  title: string;
  min_xp: number;
  next_xp: number | null;
  xp_in_level: number;
  xp_for_level: number;
  progress: number;
  is_max: boolean;
};

export type ViewerStats = {
  confirmed: number;
  pending: number;
  help_count: number;
  weekly_xp: number;
};

export type Viewer = {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  username: string;
  role: 'student' | 'teacher';
  is_teacher_preview: boolean;
  class_id: number;
  class_name: string;
  school_name: string;
  city: string;
  xp: number;
  level: LevelInfo;
  sparks: number;
  streak: number;
  avatar: AvatarConfig;
  owned: string[];
  onboarded: boolean;
  weekly_xp: number;
  class_rank: number;
  school_rank: number;
  personal_rank: number;
  stats: ViewerStats;
  to_next: number;
  next_level: number | null;
};

export type ChallengeStatus =
  | 'available'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'expired';

export type ChallengeCategory =
  | 'homework'
  | 'club'
  | 'help'
  | 'weekly'
  | 'olympiad'
  | 'event'
  | 'streak';

export type ChallengeKind = 'daily' | 'weekly' | 'event';

export type Challenge = {
  id: number;
  title: string;
  description: string;
  category: ChallengeCategory;
  category_label: string;
  xp: number;
  kind: ChallengeKind;
  kind_label: string;
  deadline: string;
  status: ChallengeStatus;
  proof: string;
  submitted_at: string | null;
  reject_reason: string;
  participants: number;
  pending_count: number;
  author: string;
};

export type StudentEntry = {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  avatar: AvatarConfig;
  xp: number;
  weekly_xp: number;
  level: number;
  level_title: string;
  streak: number;
  is_viewer: boolean;
  rank: number;
};

export type ClassEntry = {
  id: number;
  name: string;
  school: string;
  city: string;
  xp: number;
  weekly_xp: number;
  goal: number;
  members: number;
  is_viewer_class: boolean;
  rank: number;
  progress: number;
};

export type SchoolEntry = {
  id: number;
  name: string;
  city: string;
  xp: number;
  weekly_xp: number;
  classes: number;
  members: number;
  is_viewer_school: boolean;
  rank: number;
  progress: number;
};

export type Leaderboard = {
  students: StudentEntry[];
  classes: ClassEntry[];
  schools: SchoolEntry[];
};

export type FeedItem = {
  id: number;
  user_id: number;
  name: string;
  avatar: AvatarConfig;
  amount: number;
  reason: string;
  category: ChallengeCategory | null;
  created_at: string;
};

export type WeekDay = {
  date: string;
  label: string;
  is_today: boolean;
  is_future: boolean;
  active: boolean;
};

export type Achievement = {
  id: string;
  title: string;
  description: string;
  icon: string;
  target: number;
  progress: number;
  unlocked: boolean;
};

export type CosmeticType =
  | 'skin'
  | 'hair'
  | 'hair_color'
  | 'outfit'
  | 'accessory'
  | 'frame';

export type Cosmetic = {
  id: string;
  type: CosmeticType;
  name: string;
  unlock_level: number;
  price: number;
  swatch: string;
  description: string;
  owned: boolean;
  unlocked: boolean;
  equipped: boolean;
};

export type ClassSprint = {
  name: string;
  school: string;
  xp: number;
  goal: number;
  percent: number;
  rank: number;
  members: number;
  top: {
    name: string;
    avatar: AvatarConfig;
    xp: number;
  } | null;
};

export type ReviewItem = {
  id: number;
  student_id: number;
  student_name: string;
  avatar: AvatarConfig;
  student_level: number;
  student_level_title: string;
  title: string;
  category: ChallengeCategory;
  category_label: string;
  kind: ChallengeKind;
  xp: number;
  proof: string;
  created_at: string;
  is_self: boolean;
};

export type TeacherStudent = {
  id: number;
  name: string;
  first_name: string;
  avatar: AvatarConfig;
  xp: number;
  weekly_xp: number;
  level: number;
  level_title: string;
  streak: number;
  pending_count: number;
  last_active: string;
  at_risk: boolean;
  is_viewer: boolean;
  rank: number;
};

export type TeacherChallenge = Challenge & {
  pending_total: number;
  approved_total: number;
};

export type TeacherStats = {
  students: number;
  active_week: number;
  pending: number;
  avg_level: number;
  avg_weekly_xp: number;
  at_risk: number;
  class_xp: number;
  weekly_xp: number;
};

export type TeacherChartItem = {
  date: string;
  label: string;
  xp: number;
};

export type TeacherData = {
  pending: ReviewItem[];
  students: TeacherStudent[];
  stats: TeacherStats;
  chart: TeacherChartItem[];
  challenges: TeacherChallenge[];
};

export type GameState = {
  mode: 'demo' | 'max';
  verified: boolean;
  today: string;
  viewer: Viewer;
  class_sprint: ClassSprint;
  challenges: Challenge[];
  leaderboard: Leaderboard;
  feed: FeedItem[];
  week: WeekDay[];
  achievements: Achievement[];
  cosmetics: Cosmetic[];
  teacher: TeacherData | null;
  demo_teacher_available: boolean;
};

export type ReviewResult = {
  status: 'approved' | 'rejected';
  student_name: string;
  xp_awarded: number;
  student_level?: LevelInfo;
  level_up?: boolean;
};

export type SubmitResult = {
  status: 'pending';
  challenge_title: string;
};

export type MutationResponse<T = unknown> = {
  state: GameState;
  result?: T;
};

export type TabId =
  | 'hero'
  | 'challenges'
  | 'leaderboard'
  | 'wardrobe'
  | 'profile'
  | 'teacher-class'
  | 'teacher-review'
  | 'teacher-challenges';
