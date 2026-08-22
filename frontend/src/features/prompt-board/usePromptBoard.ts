import { useCallback, useEffect, useState } from 'react'

import { promptApi } from './api'
import {
  PROMPT_STATUSES,
  type PromptFormValues,
  type PromptPage,
  type PromptStatus,
} from './types'

const POLLING_INTERVAL_MS = 2_000
const PAGE_SIZE = 20

function emptyPage(): PromptPage {
  return {
    items: [],
    page: 1,
    pageSize: PAGE_SIZE,
    total: 0,
    totalPages: 0,
    hasNext: false,
  }
}

function emptyColumns(): Record<PromptStatus, PromptPage> {
  return {
    draft: emptyPage(),
    running: emptyPage(),
    completed: emptyPage(),
    failed: emptyPage(),
  }
}

function mergeColumns(
  current: Record<PromptStatus, PromptPage>,
  incoming: Record<PromptStatus, PromptPage>,
): Record<PromptStatus, PromptPage> {
  const incomingIds = new Set(
    PROMPT_STATUSES.flatMap((status) =>
      incoming[status].items.map((prompt) => prompt.id),
    ),
  )

  return Object.fromEntries(
    PROMPT_STATUSES.map((status) => {
      const freshPage = incoming[status]
      const retainedItems = current[status].items.filter(
        (prompt) => !incomingIds.has(prompt.id),
      )
      const items = [...freshPage.items, ...retainedItems].slice(
        0,
        freshPage.total,
      )

      return [
        status,
        {
          ...freshPage,
          items,
          page: Math.max(1, Math.ceil(items.length / PAGE_SIZE)),
          pageSize: PAGE_SIZE,
          totalPages: Math.ceil(freshPage.total / PAGE_SIZE),
          hasNext: items.length < freshPage.total,
        },
      ]
    }),
  ) as Record<PromptStatus, PromptPage>
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : '프롬프트 데이터를 처리하지 못했습니다.'
}

export function usePromptBoard() {
  const [columns, setColumns] =
    useState<Record<PromptStatus, PromptPage>>(emptyColumns)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [loadingMoreStatus, setLoadingMoreStatus] =
    useState<PromptStatus | null>(null)
  const [isAwaitingExecutionRefresh, setAwaitingExecutionRefresh] =
    useState(false)
  const prompts = PROMPT_STATUSES.flatMap((status) => columns[status].items)
  const hasRunningPrompt = columns.running.total > 0

  const refreshPrompts = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true)
    try {
      const board = await promptApi.board(PAGE_SIZE)
      setColumns((current) =>
        showLoading ? board.columns : mergeColumns(current, board.columns),
      )
      setAwaitingExecutionRefresh(false)
      setErrorMessage(null)
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    } finally {
      if (showLoading) setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshPrompts(true).catch(() => undefined)
  }, [refreshPrompts])

  useEffect(() => {
    if (!hasRunningPrompt && !isAwaitingExecutionRefresh) return

    const timer = window.setInterval(() => {
      void refreshPrompts().catch(() => undefined)
    }, POLLING_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [hasRunningPrompt, isAwaitingExecutionRefresh, refreshPrompts])

  const loadMore = useCallback(
    async (status: PromptStatus) => {
      const currentPage = columns[status]
      if (!currentPage.hasNext || loadingMoreStatus) return

      setLoadingMoreStatus(status)
      try {
        const nextPage = await promptApi.list(
          status,
          currentPage.page + 1,
          PAGE_SIZE,
        )
        setColumns((current) => ({
          ...current,
          [status]: {
            ...nextPage,
            items: [...current[status].items, ...nextPage.items],
          },
        }))
        setErrorMessage(null)
      } catch (error) {
        setErrorMessage(getErrorMessage(error))
        throw error
      } finally {
        setLoadingMoreStatus(null)
      }
    },
    [columns, loadingMoreStatus],
  )

  const refreshAfterMutation = useCallback(() => {
    void refreshPrompts().catch(() => undefined)
  }, [refreshPrompts])

  const createPrompt = useCallback(async (values: PromptFormValues) => {
    try {
      await promptApi.create(values)
      setErrorMessage(null)
      refreshAfterMutation()
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [refreshAfterMutation])

  const updatePrompt = useCallback(
    async (id: string, values: PromptFormValues) => {
      try {
        await promptApi.update(id, values)
        setErrorMessage(null)
        refreshAfterMutation()
      } catch (error) {
        setErrorMessage(getErrorMessage(error))
        throw error
      }
    },
    [refreshAfterMutation],
  )

  const deletePrompt = useCallback(async (id: string) => {
    try {
      await promptApi.delete(id)
      setColumns((current) =>
        Object.fromEntries(
          PROMPT_STATUSES.map((status) => {
            const page = current[status]
            const items = page.items.filter((prompt) => prompt.id !== id)
            if (items.length === page.items.length) return [status, page]

            const total = Math.max(0, page.total - 1)
            return [
              status,
              {
                ...page,
                items,
                page: Math.max(1, Math.ceil(items.length / PAGE_SIZE)),
                total,
                totalPages: Math.ceil(total / PAGE_SIZE),
                hasNext: items.length < total,
              },
            ]
          }),
        ) as Record<PromptStatus, PromptPage>,
      )
      setErrorMessage(null)
      refreshAfterMutation()
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [refreshAfterMutation])

  const startPrompt = useCallback(async (id: string) => {
    try {
      await promptApi.execute(id)
      setAwaitingExecutionRefresh(true)
      setErrorMessage(null)
      refreshAfterMutation()
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [refreshAfterMutation])

  return {
    prompts,
    columns,
    isLoading,
    errorMessage,
    loadingMoreStatus,
    clearError: () => setErrorMessage(null),
    refreshPrompts,
    loadMore,
    createPrompt,
    updatePrompt,
    deletePrompt,
    startPrompt,
  }
}
