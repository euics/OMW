import type { Page, Route } from '@playwright/test'

export type Status = 'draft' | 'running' | 'completed' | 'failed'
export type Prompt = {
  id: string
  title: string
  prompt: string
  outputFormat: 'markdown' | 'plainText' | 'json'
  status: Status
  createdAt: number
  updatedAt: number
  output?: string
  errorMessage?: string
}

export const now = Date.parse('2026-08-22T00:00:00Z')

export const prompt = (overrides: Partial<Prompt> = {}): Prompt => ({
  id: 'prompt-001',
  title: '고객 피드백 요약',
  prompt: '고객 피드백을 세 줄로 요약해 줘.',
  outputFormat: 'markdown',
  status: 'draft',
  createdAt: now,
  updatedAt: now,
  ...overrides,
})

export function board(items: Prompt[]) {
  const page = (status: Status) => {
    const statusItems = items.filter((item) => item.status === status)
    return {
      items: statusItems,
      page: 1,
      pageSize: 20,
      total: statusItems.length,
      totalPages: statusItems.length ? 1 : 0,
      hasNext: false,
    }
  }
  return {
    columns: {
      draft: page('draft'),
      running: page('running'),
      completed: page('completed'),
      failed: page('failed'),
    },
  }
}

export async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

export async function mockApi(page: Page, initial: Prompt[]) {
  let items = initial
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const execute = url.pathname.match(/^\/api\/prompts\/([^/]+)\/execute$/)
    const itemPath = url.pathname.match(/^\/api\/prompts\/([^/]+)$/)

    if (execute && request.method() === 'POST') {
      const current = items.find((item) => item.id === execute[1])!
      const completed = {
        ...current,
        status: 'completed' as const,
        output: '요약 결과가 준비되었습니다.',
        updatedAt: now + 1_000,
      }
      items = items.map((item) => item.id === current.id ? completed : item)
      return json(route, completed, 202)
    }
    if (itemPath && request.method() === 'PATCH') {
      const values = request.postDataJSON()
      const updated = { ...items.find((item) => item.id === itemPath[1])!, ...values, updatedAt: now + 500 }
      items = items.map((item) => item.id === updated.id ? updated : item)
      return json(route, updated)
    }
    if (url.pathname === '/api/prompts' && request.method() === 'POST') {
      const created = prompt({ id: 'created-001', ...request.postDataJSON() })
      items = [created, ...items]
      return json(route, created, 201)
    }
    if (url.pathname === '/api/prompts/board') return json(route, board(items))
    return json(route, { detail: 'Unexpected test request' }, 404)
  })
}
