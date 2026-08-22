import type {
  PromptBoard,
  PromptFormValues,
  PromptItem,
  PromptPage,
  PromptStatus,
} from './types'

type ApiErrorBody = {
  detail?: string
}

export class PromptApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'PromptApiError'
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let message = '요청을 처리하지 못했습니다.'
    try {
      const body = (await response.json()) as ApiErrorBody
      if (body.detail) message = body.detail
    } catch {
      message = `요청을 처리하지 못했습니다. (${response.status})`
    }
    throw new PromptApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export const promptApi = {
  board: (pageSize: number) =>
    request<PromptBoard>(`/api/prompts/board?pageSize=${pageSize}`),

  list: (status: PromptStatus, page: number, pageSize: number) =>
    request<PromptPage>(
      `/api/prompts?status=${status}&page=${page}&pageSize=${pageSize}`,
    ),

  create: (values: PromptFormValues) =>
    request<PromptItem>('/api/prompts', {
      method: 'POST',
      body: JSON.stringify(values),
    }),

  update: (id: string, values: PromptFormValues) =>
    request<PromptItem>(`/api/prompts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(values),
    }),

  delete: (id: string) =>
    request<void>(`/api/prompts/${id}`, {
      method: 'DELETE',
    }),

  execute: (id: string) =>
    request<PromptItem>(`/api/prompts/${id}/execute`, {
      method: 'POST',
    }),
}
