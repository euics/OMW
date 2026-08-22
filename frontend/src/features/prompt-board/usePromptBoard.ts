import { useCallback, useEffect, useState } from 'react'

import { promptApi } from './api'
import type { PromptFormValues, PromptItem } from './types'

const POLLING_INTERVAL_MS = 2_000

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : '프롬프트 데이터를 처리하지 못했습니다.'
}

export function usePromptBoard() {
  const [prompts, setPrompts] = useState<PromptItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const refreshPrompts = useCallback(async (showLoading = false) => {
    if (showLoading) setIsLoading(true)
    try {
      const items = await promptApi.list()
      setPrompts(items)
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
    if (!prompts.some((prompt) => prompt.status === 'running')) return

    const timer = window.setInterval(() => {
      void refreshPrompts().catch(() => undefined)
    }, POLLING_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [prompts, refreshPrompts])

  const createPrompt = useCallback(async (values: PromptFormValues) => {
    try {
      const prompt = await promptApi.create(values)
      setPrompts((current) => [prompt, ...current])
      setErrorMessage(null)
      return prompt
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [])

  const updatePrompt = useCallback(
    async (id: string, values: PromptFormValues) => {
      try {
        const updated = await promptApi.update(id, values)
        setPrompts((current) =>
          current.map((prompt) =>
            prompt.id === updated.id ? updated : prompt,
          ),
        )
        setErrorMessage(null)
        return updated
      } catch (error) {
        setErrorMessage(getErrorMessage(error))
        throw error
      }
    },
    [],
  )

  const deletePrompt = useCallback(async (id: string) => {
    try {
      await promptApi.delete(id)
      setPrompts((current) =>
        current.filter((prompt) => prompt.id !== id),
      )
      setErrorMessage(null)
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [])

  const startPrompt = useCallback(async (id: string) => {
    try {
      const running = await promptApi.execute(id)
      setPrompts((current) =>
        current.map((prompt) =>
          prompt.id === running.id ? running : prompt,
        ),
      )
      setErrorMessage(null)
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
      throw error
    }
  }, [])

  return {
    prompts,
    isLoading,
    errorMessage,
    clearError: () => setErrorMessage(null),
    refreshPrompts,
    createPrompt,
    updatePrompt,
    deletePrompt,
    startPrompt,
  }
}
