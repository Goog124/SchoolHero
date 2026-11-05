export type AvatarConfig = {
  skin: string;
  hair: string;
  hairColor: string;
  outfit: string;
  accessory: string;
  /** Новые слоты: у старых данных могут отсутствовать. */
  hat?: string;
  face?: string;
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
  role: 'student' | 'teacher' | 'director';
  is_teacher_preview: boolean;
  class_id: number | null;
  class_name: string;
  school_id: number | null;
  school_name: string;
  school_status: '' | 'active' | 'pending' | 'rejected';
  city: string;
  invite_code?: string;
  is_platform_admin: boolean;
  /** Педагог или директор без имени: сначала спрашиваем имя. */
  needs_name: boolean;
  /** Класс, из которого ученика исключили (пока он без класса). */
  removed_from?: { class_name: string; school_name: string } | null;
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
  subject: string;
  proof_type: 'text' | 'link' | 'photo';
  status: ChallengeStatus;
  proof: string;
  proof_url?: string;
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
  | 'hat'
  | 'face'
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
  rarity?: 'common' | 'rare' | 'epic' | 'legendary';
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
  proof_url?: string;
  subject?: string;
  proof_type?: 'text' | 'link' | 'photo';
  created_at: string;
  is_self: boolean;
};

export type StudentWorkItem = {
  id: number;
  title: string;
  category: ChallengeCategory;
  subject: string;
  xp: number;
  status: ChallengeStatus;
  date: string;
  proof: string;
  proof_url: string;
  reject_reason: string;
};

export type SubjectStat = {
  subject: string;
  count: number;
  xp: number;
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
  approved_count?: number;
  rejected_count?: number;
  risk_reasons?: string[];
  recent_works?: StudentWorkItem[];
  subject_stats?: SubjectStat[];
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

export type ExcludedStudent = {
  id: number;
  name: string;
  reason: string;
  removed_at: string;
};

export type TeacherData = {
  excluded?: ExcludedStudent[];
  invite_code?: string;
  pending: ReviewItem[];
  students: TeacherStudent[];
  stats: TeacherStats;
  chart: TeacherChartItem[];
  challenges: TeacherChallenge[];
};

export type SchoolClassInfo = {
  valid: boolean;
  kind?: 'student' | 'teacher';
  class_id?: number;
  class_name?: string;
  school_name?: string;
  city?: string;
  teacher_name?: string;
  invite_code?: string;
  detail?: string;
};

export type SchoolCatalog = {
  cities: string[];
  schools: Array<{ id: number; name: string; city: string }>;
  classes: Array<{ id: number; school_id: number; name: string }>;
  total?: number;
  has_more?: boolean;
};

export type CitySuggestion = { name: string; schools: number };

export type ManagedClass = {
  id: number;
  name: string;
  weekly_goal: number;
  members: number;
  invite_code: string;
  teacher_code: string;
  teachers: string[];
};

export type ManagedSchool = {
  id: number;
  name: string;
  city: string;
  status: 'active' | 'pending' | 'rejected';
  classes: ManagedClass[];
};

export type SchoolAdminData = {
  active_school_id: number | null;
  max_schools: number;
  schools_left: number;
  max_classes: number;
  schools: ManagedSchool[];
};

export type PlatformAdminData = {
  approval_mode: 'auto' | 'manual';
  pending: Array<{
    id: number;
    name: string;
    city: string;
    classes: number;
    created_by: string;
    created_at: string;
  }>;
};

export type NewSchoolPayload = {
  name: string;
  city: string;
  classes: Array<{ name: string; weekly_goal?: number }>;
};

export type GradeEntry = {
  grade: string;
  label: string;
  classes_count: number;
  students_count: number;
  total_xp: number;
  weekly_xp: number;
  active_students: number;
  engagement: number;
  avg_student_xp: number;
};

export type DirectionStats = {
  label: string;
  count: number;
  xp: number;
};

export type DirectorKPI = {
  total_students: number;
  total_classes: number;
  active_students_week: number;
  engagement_rate: number;
  total_school_xp: number;
  total_weekly_xp: number;
  completed_fop_tasks?: number;
  social_activity_index?: number;
  leading_grade?: string | null;
};

export type DirectorData = {
  kpi: DirectorKPI;
  grades: GradeEntry[];
  directions: Record<
    'study' | 'olympiads' | 'sport_creative' | 'volunteering' | 'patriotic',
    DirectionStats
  >;
  classes: ClassEntry[];
  report_generated_at: string;
};

export type GameState = {
  mode: 'demo' | 'prod' | 'sandbox';
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
  director?: DirectorData | null;
  school_admin?: SchoolAdminData | null;
  platform_admin?: PlatformAdminData | null;
  demo_teacher_available: boolean;
  demo_director_available?: boolean;
};

export type ReviewResult = {
  status: 'approved' | 'rejected';
  student_name: string;
  xp_awarded: number;
  student_level?: LevelInfo;
  level_up?: boolean;
};

export type BatchReviewResult = {
  action: string;
  approved: number;
  rejected: number;
  failed?: number;
  total: number;
  counts?: { approved: number; rejected: number; failed: number };
  errors?: { id: number; detail: string; status: number }[];
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
  | 'teacher-challenges'
  | 'director-overview'
  | 'director-classes'
  | 'director-setup'
  | 'admin-schools'
  | 'director-reports';
