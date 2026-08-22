export type PromptStatus = 'draft' | 'running' | 'completed'
export type PromptModel = 'auto' | 'gpt-5.6-sol' | 'claude-sonnet-5'
export type OutputFormat = 'markdown' | 'plainText' | 'json'
export type ExecutionState =
  | 'idle'
  | 'requesting'
  | 'succeeded'
  | 'failed'

export type PromptFormValues = {
  title: string
  prompt: string
  model: PromptModel
  outputFormat: OutputFormat
}

export type PromptItem = PromptFormValues & {
  id: string
  status: PromptStatus
  executionState: ExecutionState
  createdAt: number
  updatedAt: number
  startedAt?: number
  completedAt?: number
  output?: string
  errorMessage?: string
}

export const MODEL_LABELS: Record<PromptModel, string> = {
  auto: '자동 선택',
  'gpt-5.6-sol': 'GPT-5.6 Sol',
  'claude-sonnet-5': 'Claude Sonnet 5',
}

export const OUTPUT_FORMAT_LABELS: Record<OutputFormat, string> = {
  markdown: 'Markdown',
  plainText: '일반 텍스트',
  json: 'JSON',
}

export const EMPTY_PROMPT_FORM: PromptFormValues = {
  title: '',
  prompt: '',
  model: 'auto',
  outputFormat: 'markdown',
}
