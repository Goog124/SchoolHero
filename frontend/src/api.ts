import { getClientId, getInitData } from './max';
import { activeSandboxClientId } from './sandbox';
import type {
  BatchReviewResult,
  GameState,
  MutationResponse,
  NewSchoolPayload,
  ReviewResult,
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
    let message = 'Что-то пошло не так. Попробуй ещё раз.';
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === 'string') message = body.detail;
    } catch {
      // Keep generic error
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health(): Promise<{ mode: 'prod' | 'demo' | 'sandbox' }> {
    return request<{ mode: 'prod' | 'demo' | 'sandbox' }>('/api/health');
  },

  getState(): Promise<GameState> {
    return request<GameState>('/api/state');
  },

  checkInviteCode(code: string): Promise<SchoolClassInfo> {
    return request<SchoolClassInfo>(`/api/school/check-code?code=${encodeURIComponent(code)}`);
  },

  getSchoolCatalog(
    params: { city?: string; q?: string; onlyCities?: boolean } = {},
  ): Promise<SchoolCatalog> {
    const query = new URLSearchParams();
    if (params.city) query.set('city', params.city);
    if (params.q) query.set('q', params.q);
    if (params.onlyCities) query.set('only_cities', 'true');
    const suffix = query.toString();
    return request<SchoolCatalog>(`/api/school/catalog${suffix ? `?${suffix}` : ''}`);
  },

  createSchool(payload: NewSchoolPayload): Promise<MutationResponse> {
    return request<MutationResponse>('/api/school/create', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  addClass(schoolId: number, name: string, weeklyGoal: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/${schoolId}/classes`, {
      method: 'POST',
      body: JSON.stringify({ name, weekly_goal: weeklyGoal }),
    });
  },

  deleteClass(classId: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/classes/${classId}`, { method: 'DELETE' });
  },

  resetCode(classId: number, kind: 'student' | 'teacher'): Promise<MutationResponse> {
    return request<MutationResponse>(`/api/school/classes/${classId}/codes`, {
      method: 'POST',
      body: JSON.stringify({ kind }),
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

  joinSchool(inviteCode?: string, classId?: number): Promise<MutationResponse> {
    return request<MutationResponse>('/api/school/join', {
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

  submit(challengeId: number, proof: string, proofUrl = ''): Promise<MutationResponse<SubmitResult>> {
    return request<MutationResponse<SubmitResult>>(`/api/challenges/${challengeId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ proof, proof_url: proofUrl }),
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
