export type PromptStatus = 'draft' | 'running' | 'completed' | 'failed'
export type OutputFormat = 'markdown' | 'plainText' | 'json'

export type PromptFormValues = {
  title: string
  prompt: string
  outputFormat: OutputFormat
}

export type PromptItem = PromptFormValues & {
  id: string
  status: PromptStatus
  createdAt: number
  updatedAt: number
  startedAt?: number
  completedAt?: number
  output?: string
  errorMessage?: string
}

export type PromptPage = {
  items: PromptItem[]
  page: number
  pageSize: number
  total: number
  totalPages: number
  hasNext: boolean
}

export type PromptBoard = {
  columns: Record<PromptStatus, PromptPage>
}

export const PROMPT_STATUSES: PromptStatus[] = [
  'draft',
  'running',
  'completed',
  'failed',
]

export const OUTPUT_FORMAT_LABELS: Record<OutputFormat, string> = {
  markdown: 'Markdown',
  plainText: '일반 텍스트',
  json: 'JSON',
}

export const EMPTY_PROMPT_FORM: PromptFormValues = {
  title: '',
  prompt: '',
  outputFormat: 'markdown',
}
