import { expect, test, type Page, type Route } from '@playwright/test'

type Status = 'draft' | 'running' | 'completed' | 'failed'
type Prompt = {
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

const now = Date.parse('2026-08-22T00:00:00Z')
const prompt = (overrides: Partial<Prompt> = {}): Prompt => ({
  id: 'prompt-001',
  title: '고객 피드백 요약',
  prompt: '고객 피드백을 세 줄로 요약해 줘.',
  outputFormat: 'markdown',
  status: 'draft',
  createdAt: now,
  updatedAt: now,
  ...overrides,
})

function board(items: Prompt[]) {
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

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockApi(page: Page, initial: Prompt[]) {
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

test('creates and edits a prompt using keyboard-accessible controls', async ({ page }) => {
  await mockApi(page, [])
  await page.goto('/')

  await page.getByRole('button', { name: '프롬프트 작성' }).press('Enter')
  await expect(page.getByRole('dialog', { name: '새 프롬프트 작성' })).toBeVisible()
  await expect(page.getByPlaceholder('예: 주간 고객 피드백 요약')).toBeFocused()
  await page.getByPlaceholder('예: 주간 고객 피드백 요약').fill('새 프롬프트')
  await page.getByPlaceholder(/역할, 필요한 입력/).fill('결과를 간결하게 요약해 줘.')
  await page.getByRole('button', { name: '프롬프트 저장' }).press('Enter')
  await expect(page.getByRole('heading', { name: '새 프롬프트' })).toBeVisible()

  await page.getByRole('button', { name: '수정' }).press('Enter')
  await expect(page.getByRole('dialog', { name: '프롬프트 수정' })).toBeVisible()
  await page.getByPlaceholder('예: 주간 고객 피드백 요약').fill('수정된 프롬프트')
  await page.getByRole('button', { name: '변경사항 저장' }).press('Enter')
  await expect(page.getByRole('heading', { name: '수정된 프롬프트' })).toBeVisible()
})

test('confirms execution, traps dialog focus, and shows completed output', async ({ page }) => {
  await mockApi(page, [prompt()])
  await page.goto('/')

  const runButton = page.getByRole('button', { name: '실행', exact: true })
  await runButton.press('Enter')
  const dialog = page.getByRole('dialog', { name: '이 프롬프트를 실행할까요?' })
  await expect(dialog).toBeVisible()
  await expect(page.getByRole('button', { name: '닫기' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button', { name: '진행중으로 이동' })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page.getByText('요약 결과가 준비되었습니다.')).toBeVisible()
  await expect(page.getByText('완료', { exact: true }).last()).toBeVisible()
})

test('retries a failed prompt through the button alternative', async ({ page }) => {
  await mockApi(page, [prompt({ status: 'failed', errorMessage: '일시적인 실행 오류' })])
  await page.goto('/')

  await page.getByRole('button', { name: '재실행' }).press('Enter')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '진행중으로 이동' }).press('Enter')
  await expect(page.getByText('요약 결과가 준비되었습니다.')).toBeVisible()
})

test('recovers from an initial loading error', async ({ page }) => {
  let attempts = 0
  let shouldSucceed = false
  await page.route('**/api/**', async (route) => {
    attempts += 1
    if (!shouldSucceed) return json(route, { detail: '테스트 연결 오류' }, 503)
    return json(route, board([]))
  })
  await page.goto('/')

  await expect(page.getByRole('alert')).toContainText('테스트 연결 오류')
  shouldSucceed = true
  await page.getByRole('button', { name: '다시 시도' }).click()
  await expect(page.getByRole('alert')).toBeHidden()
  expect(attempts).toBeGreaterThanOrEqual(2)
})

test('uses a readable single-column board at 390px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page, [prompt(), prompt({ id: 'failed-001', status: 'failed' })])
  await page.goto('/')

  await expect(page.locator('.board-grid')).toHaveCSS('grid-template-columns', '362px')
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(hasHorizontalOverflow).toBe(false)
  await expect(page.getByRole('button', { name: '프롬프트 작성' })).toBeVisible()
})
