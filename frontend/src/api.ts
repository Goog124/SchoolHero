import { setSchoolTimezone } from './game';
import { getClientId, getInitData } from './max';
import { activeSandboxClientId } from './sandbox';
import type {
  BatchReviewResult,
  GameState,
  MutationResponse,
  NewSchoolPayload,
  ReviewResult,
  CitySuggestion,
  SchoolCatalog,
  SchoolClassInfo,
  SubmitResult,
} from './types';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function headers(): HeadersInit {
  const initData = getInitData();
  const result: Record<string, string> = { Accept: 'application/json' };
  // Подпись MAX — единственный способ авторизации в prod.
  // Анонимный идентификатор нужен только демо-режиму вне MAX.
  // В песочнице идентификатор всегда берётся из активного тестового пользователя.
  const sandboxId = activeSandboxClientId();
  if (sandboxId) result['X-Client-Id'] = sandboxId;
  else if (initData) result['X-Max-Init-Data'] = initData;
  else result['X-Client-Id'] = getClientId();
  return result;
}

const FIELD_MESSAGES: Record<string, string> = {
  name: 'Название: проверьте длину и символы',
  city: 'Город: от 2 до 60 символов',
  classes: 'Добавьте от 1 до 40 классов',
  weekly_goal: 'Цель недели: от 100 до 20 000',
  xp: 'Награда: целое число от 10 до 300',
  amount: 'Количество баллов: от 10 до 300',
  title: 'Название задания: от 3 до 80 символов',
  description: 'Описание слишком длинное',
  first_name: 'Имя: от 2 до 24 символов',
  last_name: 'Фамилия слишком длинная',
  invite_code: 'Проверьте код приглашения',
  reason: 'Причина слишком длинная',
  status: 'Неизвестный статус',
  kind: 'Неизвестный тип',
};

type ValidationItem = { loc?: unknown[]; msg?: string; type?: string };

/** Русский текст для ответа 422 (FastAPI отдаёт detail массивом). */
function validationMessage(items: ValidationItem[]): string {
  const messages: string[] = [];
  for (const item of items) {
    const loc = (item.loc ?? []).filter((part) => typeof part === 'string') as string[];
    const field = loc[loc.length - 1] ?? '';
    const underClasses = loc.includes('classes');
    let text: string | undefined;
    if (field === 'name' && underClasses) text = 'Название класса: от 1 до 12 символов';
    else if (field === 'name') text = 'Название слишком короткое или длинное';
    else text = FIELD_MESSAGES[field];
    if (field === 'classes' && item.type === 'too_long') text = 'Не больше 40 классов';
    if (!text) text = 'Проверьте введённые данные';
    if (!messages.includes(text)) messages.push(text);
  }
  return messages.join('. ') || 'Проверьте введённые данные';
}

function statusFallback(status: number): string {
  if (status === 401) return 'Сессия устарела. Откройте приложение заново.';
  if (status === 403) return 'Недостаточно прав для этого действия.';
  if (status === 404) return 'Не найдено.';
  if (status === 429) return 'Слишком много запросов. Подождите немного и повторите.';
  if (status >= 500) return 'Ошибка на сервере. Попробуйте ещё раз чуть позже.';
  return 'Что-то пошло не так. Попробуй ещё раз.';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        ...headers(),
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init?.headers ?? {}),
      },
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError('Нет связи с сервером. Проверь соединение и попробуй ещё раз.', 0);
  }

  if (!response.ok) {
    let message = statusFallback(response.status);
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string' && body.detail.trim()) message = body.detail;
      else if (Array.isArray(body.detail)) message = validationMessage(body.detail as ValidationItem[]);
    } catch {
      // Keep generic error
    }
    throw new ApiError(message, response.status);
  }

  const data = (await response.json()) as T;
  // The state (own or inside a mutation answer) carries the school zone:
  // "today" and deadlines on screen follow it, not the device clock.
  const state = (data as { state?: { timezone?: unknown }; timezone?: unknown } | null) ?? {};
  const zone = typeof state.timezone === 'string' ? state.timezone : state.state?.timezone;
  if (typeof zone === 'string') setSchoolTimezone(zone);
  return data;
}

/**
 * Photo chosen in the challenge sheet, per challenge. submit() sends it as
 * upload_id when the caller does not pass one explicitly.
 */
const stagedUploads = new Map<number, number>();

export function stageUpload(challengeId: number, uploadId: number | null): void {
  if (uploadId) stagedUploads.set(challengeId, uploadId);
  else stagedUploads.delete(challengeId);
}

/** Photo proof: raw image bytes (no multipart); returns the upload id. */
export async function uploadPhoto(blob: Blob): Promise<number> {
  let response: Response;
  try {
    response = await fetch('/api/uploads', {
      method: 'POST',
      headers: { ...headers(), 'Content-Type': blob.type || 'image/jpeg' },
      body: blob,
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError('Нет связи с сервером. Проверь соединение и попробуй ещё раз.', 0);
  }
  if (!response.ok) {
    let message = response.status === 413 ? 'Файл больше 5 МБ.' : statusFallback(response.status);
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string' && body.detail.trim()) message = body.detail;
    } catch {
      // keep fallback
    }
    throw new ApiError(message, response.status);
  }
  return ((await response.json()) as { id: number }).id;
}

/** Photo of a submission as a Blob (the file is behind authorization headers). */
export async function getUploadBlob(id: number): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`/api/uploads/${id}`, { headers: headers(), credentials: 'same-origin' });
  } catch {
    throw new ApiError('Нет связи с сервером. Проверь соединение и попробуй ещё раз.', 0);
  }
  if (!response.ok) throw new ApiError(statusFallback(response.status), response.status);
  return response.blob();
}

export const api = {
  health(): Promise<{ mode: 'prod' | 'demo' | 'sandbox'; boot_id?: string | null }> {
    return request<{ mode: 'prod' | 'demo' | 'sandbox'; boot_id?: string | null }>(
      '/api/health',
    );
  },

  getState(): Promise<GameState> {
    return request<GameState>('/api/state');
  },

  checkInviteCode(code: string): Promise<SchoolClassInfo> {
    // POST: the code stays out of URLs and access logs.
    return request<SchoolClassInfo>('/api/school/check-code', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },

  getSchoolCatalog(
    params: { city?: string; q?: string; onlyCities?: boolean; limit?: number; offset?: number } = {},
  ): Promise<SchoolCatalog> {
    const query = new URLSearchParams();
    if (params.limit) query.set('limit', String(params.limit));
    if (params.offset) query.set('offset', String(params.offset));
    if (params.city) query.set('city', params.city);
    if (params.q) query.set('q', params.q);
    if (params.onlyCities) query.set('only_cities', 'true');
    const suffix = query.toString();
    return request<SchoolCatalog>(`/api/school/catalog${suffix ? `?${suffix}` : ''}`);
  },

  searchCities(
    q: string,
    limit = 10,
    scope: '' | 'all' = '',
  ): Promise<{ cities: CitySuggestion[]; total: number }> {
    const query = new URLSearchParams({ q, limit: String(limit) });
    if (scope) query.set('scope', scope);
    return request<{ cities: CitySuggestion[]; total: number }>(`/api/school/cities?${query}`);
  },

  removeStudent(studentId: number, reason = ''): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/teacher/students/${studentId}/remove`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  restoreStudent(studentId: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/teacher/students/${studentId}/restore`, {
      method: 'POST',
    });
  },

  setName(firstName: string, lastName: string): Promise<MutationResponse> {
    return request<MutationResponse>('/api/profile/name', {
      method: 'POST',
      body: JSON.stringify({ first_name: firstName, last_name: lastName }),
    });
  },

  createSchool(payload: NewSchoolPayload): Promise<MutationResponse> {
    return request<MutationResponse>('/api/school/create', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  addClass(schoolId: number, name: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/${schoolId}/classes`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  updateClass(
    classId: number,
    patch: { name?: string; weekly_goal?: number },
  ): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/classes/${classId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  },

  deleteClass(classId: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/classes/${classId}`, { method: 'DELETE' });
  },

  resetCode(
    classId: number,
    kind: 'student' | 'teacher',
    disconnectTeachers = false,
  ): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/classes/${classId}/codes`, {
      method: 'POST',
      body: JSON.stringify({ kind, disconnect_teachers: disconnectTeachers }),
    });
  },

  disconnectTeacher(classId: number, teacherId: number): Promise<MutationResponse> {
    return request<MutationResponse>(
      `/api/school/classes/${classId}/teachers/${teacherId}/disconnect`,
      { method: 'POST' },
    );
  },

  cancelJoinRequest(): Promise<MutationResponse> {
    return request<MutationResponse>('/api/join-requests/cancel', { method: 'POST' });
  },

  decideJoinRequest(requestId: number, action: 'approve' | 'decline'): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/join-requests/${requestId}`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    });
  },

  setSchoolTimezone(schoolId: number, timezone: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/${schoolId}`, {
      method: 'PATCH',
      body: JSON.stringify({ timezone }),
    });
  },

  /** Только в песочнице: текущий тестовый пользователь становится администратором платформы. */
  setSandboxAdmin(enabled: boolean): Promise<MutationResponse> {
    return request<MutationResponse>('/api/sandbox/admin', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  },

  selectSchool(schoolId: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/${schoolId}/select`, { method: 'POST' });
  },

  setSchoolStatus(schoolId: number, status: 'active' | 'rejected'): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/admin/schools/${schoolId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    });
  },

  /** По коду вступает сразу (status: joined), из списка подаёт заявку (status: requested). */
  joinSchool(
    inviteCode?: string,
    classId?: number,
  ): Promise<MutationResponse & { status?: 'joined' | 'requested' }> {
    return request<MutationResponse & { status?: 'joined' | 'requested' }>('/api/school/join', {
      method: 'POST',
      body: JSON.stringify({ invite_code: inviteCode, class_id: classId }),
    });
  },

  onboarding(
    firstName: string,
    avatar: Record<string, string>,
    lastName = '',
    classId?: number,
    inviteCode?: string,
  ): Promise<MutationResponse> {
    return request<MutationResponse>('/api/onboarding', {
      method: 'POST',
      body: JSON.stringify({
        first_name: firstName,
        last_name: lastName,
        avatar,
        class_id: classId,
        invite_code: inviteCode,
      }),
    });
  },

  equip(key: string, itemId: string): Promise<MutationResponse> {
    return request<MutationResponse>('/api/avatar/equip', {
      method: 'POST',
      body: JSON.stringify({ key, item_id: itemId }),
    });
  },

  buy(itemId: string): Promise<MutationResponse> {
    return request<MutationResponse>('/api/shop/buy', {
      method: 'POST',
      body: JSON.stringify({ item_id: itemId }),
    });
  },

  submit(
    challengeId: number,
    proof: string,
    proofUrl = '',
    uploadId: number | null = null,
  ): Promise<MutationResponse<SubmitResult>> {
    const attached = uploadId ?? stagedUploads.get(challengeId) ?? null;
    return request<MutationResponse<SubmitResult>>(`/api/challenges/${challengeId}/submit`, {
      method: 'POST',
      body: JSON.stringify({
        proof,
        proof_url: proofUrl,
        ...(attached ? { upload_id: attached } : {}),
      }),
    }).then((result) => {
      stagedUploads.delete(challengeId);
      return result;
    });
  },

  createChallenge(payload: {
    title: string;
    description: string;
    category: string;
    xp: number;
    kind: string;
    deadline: string;
    subject?: string;
    subject_other?: string;
    proof_type?: 'text' | 'link' | 'photo';
    class_id?: number;
  }): Promise<MutationResponse> {
    return request<MutationResponse>('/api/challenges', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  rewardStudent(
    studentId: number,
    amount = 50,
    reason = 'Активность на уроке',
  ): Promise<MutationResponse> {
    return request<MutationResponse>('/api/teacher/reward', {
      method: 'POST',
      body: JSON.stringify({ student_id: studentId, amount, reason }),
    });
  },

  archiveChallenge(challengeId: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/challenges/${challengeId}/archive`, {
      method: 'POST',
    });
  },

  review(
    completionId: number,
    action: 'approve' | 'reject',
    reason = '',
  ): Promise<MutationResponse<ReviewResult>> {
    return request<MutationResponse<ReviewResult>>(`/api/reviews/${completionId}`, {
      method: 'POST',
      body: JSON.stringify({ action, reason }),
    });
  },

  batchReview(
    completionIds: number[],
    action: 'approve' | 'reject',
    reason = '',
  ): Promise<MutationResponse<BatchReviewResult>> {
    return request<MutationResponse<BatchReviewResult>>('/api/reviews/batch', {
      method: 'POST',
      body: JSON.stringify({ completion_ids: completionIds, action, reason }),
    });
  },

  setRole(role: 'student' | 'teacher' | 'director'): Promise<MutationResponse> {
    return request<MutationResponse>('/api/demo/role', {
      method: 'POST',
      body: JSON.stringify({ role }),
    });
  },

  resetDemo(): Promise<MutationResponse> {
    return request<MutationResponse>('/api/demo/reset', {
      method: 'POST',
    });
  },
};
