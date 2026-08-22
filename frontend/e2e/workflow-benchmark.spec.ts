import { expect, test } from '@playwright/test'

import { mockApi, prompt } from './helpers/mockPromptApi'

const fixture = [
  prompt({ id: 'draft-001', title: '초안 A' }),
  prompt({ id: 'draft-002', title: '초안 B' }),
  prompt({ id: 'running-001', title: '실행 중', status: 'running' }),
  prompt({
    id: 'completed-001',
    title: '완료 결과',
    status: 'completed',
    output: '고정된 완료 결과입니다.',
  }),
  prompt({
    id: 'failed-001',
    title: '재시도 대상',
    status: 'failed',
    errorMessage: '고정된 실행 오류',
  }),
]

test('automated five-task workflow benchmark', async ({ page, context }, testInfo) => {
  await mockApi(page, fixture)

  let externalWindowSwitches = 0
  context.on('page', (openedPage) => {
    if (openedPage !== page) externalWindowSwitches += 1
  })

  const boardStartedAt = performance.now()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '실행 보드' })).toBeVisible()
  await expect(page.locator('.prompt-card')).toHaveCount(5)
  const boardReadinessMs = performance.now() - boardStartedAt

  const overviewStartedAt = performance.now()
  const statusSummary = page.locator('.status-summary')
  await expect(statusSummary).toContainText('미실행 2')
  await expect(statusSummary).toContainText('진행중 1')
  await expect(statusSummary).toContainText('완료 1')
  await expect(statusSummary).toContainText('실패 1')
  const statusOverviewDiscoveryMs = performance.now() - overviewStartedAt

  const completedStartedAt = performance.now()
  await expect(page.getByText('고정된 완료 결과입니다.')).toBeVisible()
  const completedResultDiscoveryMs = performance.now() - completedStartedAt

  let retryUserActions = 0
  const retryStartedAt = performance.now()
  retryUserActions += 1
  await page.getByRole('button', { name: '재실행' }).click()
  await expect(page.getByRole('dialog', { name: '이 프롬프트를 실행할까요?' })).toBeVisible()
  retryUserActions += 1
  await page.getByRole('button', { name: '진행중으로 이동' }).click()
  await expect(page.getByText('요약 결과가 준비되었습니다.')).toBeVisible()
  const failedTaskRetryMs = performance.now() - retryStartedAt

  const result = {
    benchmark: 'automated-workflow-benchmark',
    description: 'Deterministic Playwright UI workflow; not a user study or live Copilot latency measurement.',
    fixture: {
      taskCount: 5,
      initialStatusCounts: { draft: 2, running: 1, completed: 1, failed: 1 },
    },
    metrics: {
      boardReadiness: { ready: true, milliseconds: Math.round(boardReadinessMs) },
      statusOverviewDiscovery: {
        discovered: true,
        milliseconds: Math.round(statusOverviewDiscoveryMs),
        discoveredCounts: { draft: 2, running: 1, completed: 1, failed: 1 },
      },
      completedResultDiscovery: {
        discovered: true,
        milliseconds: Math.round(completedResultDiscoveryMs),
      },
      failedTaskRetry: {
        completed: true,
        userActions: retryUserActions,
        milliseconds: Math.round(failedTaskRetryMs),
      },
      externalWindowSwitches,
    },
  }

  await testInfo.attach('benchmark-result', {
    body: JSON.stringify(result),
    contentType: 'application/json',
  })
})
