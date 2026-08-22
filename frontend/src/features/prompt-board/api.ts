import type {
  PromptBoard,
  PromptItem,
  PromptPage,
  PromptStatus,
  PromptWriteRequest,
} from './types'

type ApiValidationError = {
  msg: string
}

type ApiErrorBody = {
  detail?: string | ApiValidationError[]
}

const REQUEST_TIMEOUT_MS = 15_000

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
  const controller = new AbortController()
  let timedOut = false
  const abortRequest = () => controller.abort(init?.signal?.reason)
  if (init?.signal?.aborted) {
    abortRequest()
  } else {
    init?.signal?.addEventListener('abort', abortRequest, { once: true })
  }
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, REQUEST_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch (error) {
    if (timedOut) {
      throw new PromptApiError('요청 시간이 초과되었습니다.', 408)
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
    init?.signal?.removeEventListener('abort', abortRequest)
  }

  if (!response.ok) {
    let message = '요청을 처리하지 못했습니다.'
    try {
      const body = (await response.json()) as ApiErrorBody
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        message = body.detail[0].msg
      }
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
  board: (pageSize: number, signal?: AbortSignal) =>
    request<PromptBoard>(`/api/prompts/board?pageSize=${pageSize}`, { signal }),

  list: (status: PromptStatus, page: number, pageSize: number) =>
    request<PromptPage>(
      `/api/prompts?status=${status}&page=${page}&pageSize=${pageSize}`,
    ),

  create: (values: PromptWriteRequest) =>
    request<PromptItem>('/api/prompts', {
      method: 'POST',
      body: JSON.stringify(values),
    }),

  update: (id: string, values: PromptWriteRequest) =>
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
