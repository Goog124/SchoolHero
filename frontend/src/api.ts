import { getClientId, getInitData } from './max';
import type {
  GameState,
  MutationResponse,
  ReviewResult,
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
  const result: Record<string, string> = {
    Accept: 'application/json',
    'X-Client-Id': getClientId(),
  };
  if (initData) result['X-Max-Init-Data'] = initData;
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
      // Keep the generic message.
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  getState(): Promise<GameState> {
    return request<GameState>('/api/state');
  },

  onboarding(firstName: string, avatar: Record<string, string>): Promise<MutationResponse> {
    return request<MutationResponse>('/api/onboarding', {
      method: 'POST',
      body: JSON.stringify({ first_name: firstName, avatar }),
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

  submit(challengeId: number, proof: string): Promise<MutationResponse<SubmitResult>> {
    return request<MutationResponse<SubmitResult>>(`/api/challenges/${challengeId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ proof }),
    });
  },

  createChallenge(payload: {
    title: string;
    description: string;
    category: string;
    xp: number;
    kind: string;
    deadline: string;
  }): Promise<MutationResponse> {
    return request<MutationResponse>('/api/challenges', {
      method: 'POST',
      body: JSON.stringify(payload),
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

  setRole(role: 'student' | 'teacher'): Promise<MutationResponse> {
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
