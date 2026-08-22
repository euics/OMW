import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { promptApi } from './api'
import {
  PROMPT_STATUSES,
  type OrchestrationStage,
  type PromptExecutionState,
  type PromptFormValues,
  type PromptPage,
  type PromptStatus,
  type PromptStreamEvent,
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

function emptyExecutionState(): PromptExecutionState {
  return {
    stage: null,
    stageMessage: '',
    streamedText: '',
    isCancelling: false,
    cancelError: null,
  }
}

function isOrchestrationStage(
  stage: string | null | undefined,
): stage is OrchestrationStage {
  return stage === 'planner' || stage === 'executor' || stage === 'reviewer'
}

function isPromptEvent(
  payload: unknown,
): payload is PromptStreamEvent {
  return (
    payload !== null &&
    typeof payload === 'object' &&
    'type' in payload &&
    'message' in payload
  )
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
  const [pendingExecutionIds, setPendingExecutionIds] = useState<string[]>([])
  const [executionStates, setExecutionStates] = useState<
    Record<string, PromptExecutionState>
  >({})
  const eventSourcesRef = useRef<Map<string, EventSource>>(new Map())
  const terminalExecutionIdsRef = useRef<Set<string>>(new Set())

  const runningPromptIds = useMemo(
    () => columns.running.items.map((prompt) => prompt.id),
    [columns.running.items],
  )
  const trackedExecutionIds = useMemo(
    () => Array.from(new Set([...runningPromptIds, ...pendingExecutionIds])),
    [pendingExecutionIds, runningPromptIds],
  )

  const updateExecutionState = useCallback(
    (id: string, updater: (current: PromptExecutionState) => PromptExecutionState) => {
      setExecutionStates((current) => {
        const nextState = updater(current[id] ?? emptyExecutionState())
        return {
          ...current,
          [id]: nextState,
        }
      })
    },
    [],
  )

  const patchExecutionState = useCallback(
    (id: string, patch: Partial<PromptExecutionState>) => {
      updateExecutionState(id, (current) => ({
        ...current,
        ...patch,
      }))
    },
    [updateExecutionState],
  )

  const clearExecutionState = useCallback((id: string) => {
    setExecutionStates((current) => {
      if (!(id in current)) return current
      const next = { ...current }
      delete next[id]
      return next
    })
  }, [])

  const closeExecutionStream = useCallback(
    (id: string) => {
      const source = eventSourcesRef.current.get(id)
      if (!source) return

      source.close()
      eventSourcesRef.current.delete(id)
    },
    [],
  )

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

  const openExecutionStream = useCallback(
    (id: string) => {
      if (
        eventSourcesRef.current.has(id) ||
        terminalExecutionIdsRef.current.has(id)
      ) {
        return
      }

      const source = new EventSource(promptApi.events(id))
      eventSourcesRef.current.set(id, source)
      patchExecutionState(id, {
        cancelError: null,
        isCancelling: false,
      })

      source.onmessage = (event) => {
        let payload: unknown
        try {
          payload = JSON.parse(event.data)
        } catch {
          return
        }

        if (!isPromptEvent(payload)) return

        const stage = isOrchestrationStage(payload.stage)
          ? payload.stage
          : null
        const message = payload.message ?? ''

        switch (payload.type) {
          case 'stage':
            patchExecutionState(id, {
              stage,
              stageMessage: message,
            })
            break
          case 'chunk':
            updateExecutionState(id, (current) => ({
              ...current,
              stage: stage ?? current.stage,
              stageMessage: message || current.stageMessage,
              streamedText: `${current.streamedText}${message}`,
            }))
            break
          case 'completed':
          case 'failed':
          case 'cancelled':
            terminalExecutionIdsRef.current.add(id)
            patchExecutionState(id, {
              stage,
              stageMessage: message,
            })
            closeExecutionStream(id)
            setPendingExecutionIds((current) =>
              current.filter((pendingId) => pendingId !== id),
            )
            setAwaitingExecutionRefresh(false)
            void refreshPrompts().catch(() => undefined)
            break
        }
      }

      source.onerror = () => {
        closeExecutionStream(id)
        patchExecutionState(id, {
          cancelError: null,
        })
      }
    },
    [closeExecutionStream, patchExecutionState, refreshPrompts, updateExecutionState],
  )

  useEffect(() => {
    void refreshPrompts(true).catch(() => undefined)
  }, [refreshPrompts])

  useEffect(() => {
    if (runningPromptIds.length === 0) return

    setPendingExecutionIds((current) => {
      const runningSet = new Set(runningPromptIds)
      const next = current.filter((id) => !runningSet.has(id))
      return next.length === current.length ? current : next
    })
  }, [runningPromptIds])

  useEffect(() => {
    const activeIds = new Set(trackedExecutionIds)

    for (const id of terminalExecutionIdsRef.current) {
      if (!activeIds.has(id)) {
        terminalExecutionIdsRef.current.delete(id)
        clearExecutionState(id)
      }
    }

    for (const [id, source] of eventSourcesRef.current.entries()) {
      if (!activeIds.has(id)) {
        source.close()
        eventSourcesRef.current.delete(id)
        clearExecutionState(id)
      }
    }

    for (const id of trackedExecutionIds) {
      if (!eventSourcesRef.current.has(id)) {
        openExecutionStream(id)
      }
    }
  }, [
    clearExecutionState,
    openExecutionStream,
    trackedExecutionIds,
  ])

  useEffect(
    () => () => {
      for (const source of eventSourcesRef.current.values()) {
        source.close()
      }
      eventSourcesRef.current.clear()
      terminalExecutionIdsRef.current.clear()
    },
    [],
  )

  useEffect(() => {
    if (
      !runningPromptIds.length &&
      !isAwaitingExecutionRefresh &&
      !pendingExecutionIds.length
    ) {
      return
    }

    const timer = window.setInterval(() => {
      void refreshPrompts().catch(() => undefined)
    }, POLLING_INTERVAL_MS)

    return () => window.clearInterval(timer)
  }, [
    isAwaitingExecutionRefresh,
    refreshPrompts,
    pendingExecutionIds.length,
    runningPromptIds.length,
  ])

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

  const createPrompt = useCallback(
    async (values: PromptFormValues) => {
      try {
        await promptApi.create(values)
        setErrorMessage(null)
        refreshAfterMutation()
      } catch (error) {
        setErrorMessage(getErrorMessage(error))
        throw error
      }
    },
    [refreshAfterMutation],
  )

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

  const deletePrompt = useCallback(
    async (id: string) => {
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
    },
    [refreshAfterMutation],
  )

  const startPrompt = useCallback(
    async (id: string) => {
      try {
        await promptApi.execute(id)
        terminalExecutionIdsRef.current.delete(id)
        setPendingExecutionIds((current) =>
          current.includes(id) ? current : [...current, id],
        )
        setAwaitingExecutionRefresh(true)
        setErrorMessage(null)
        openExecutionStream(id)
        refreshAfterMutation()
      } catch (error) {
        setErrorMessage(getErrorMessage(error))
        throw error
      }
    },
    [openExecutionStream, refreshAfterMutation],
  )

  const cancelPrompt = useCallback(
    async (id: string) => {
      patchExecutionState(id, {
        isCancelling: true,
        cancelError: null,
      })

      try {
        await promptApi.cancel(id)
        patchExecutionState(id, {
          isCancelling: false,
        })
        setErrorMessage(null)
        refreshAfterMutation()
      } catch (error) {
        patchExecutionState(id, {
          isCancelling: false,
          cancelError: getErrorMessage(error),
        })
        setErrorMessage(getErrorMessage(error))
        throw error
      }
    },
    [patchExecutionState, refreshAfterMutation],
  )

  return {
    prompts: PROMPT_STATUSES.flatMap((status) => columns[status].items),
    columns,
    isLoading,
    errorMessage,
    loadingMoreStatus,
    executionStates,
    clearError: () => setErrorMessage(null),
    refreshPrompts,
    loadMore,
    createPrompt,
    updatePrompt,
    deletePrompt,
    startPrompt,
    cancelPrompt,
  }
}
