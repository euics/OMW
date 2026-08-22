import type { DragEvent } from 'react'

import {
  MODEL_LABELS,
  OUTPUT_FORMAT_LABELS,
  type PromptItem,
} from '../types'
import { Icon } from './Icon'

type PromptCardProps = {
  prompt: PromptItem
  isDragging: boolean
  onEdit: () => void
  onDelete: () => void
  onRun: () => void
  onDragStart: (event: DragEvent<HTMLElement>) => void
  onDragEnd: () => void
}

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function PromptCard({
  prompt,
  isDragging,
  onEdit,
  onDelete,
  onRun,
  onDragStart,
  onDragEnd,
}: PromptCardProps) {
  const isDraft = prompt.status === 'draft'

  return (
    <article
      className={`prompt-card card-${prompt.status} ${
        isDragging ? 'is-dragging' : ''
      }`}
      draggable={isDraft}
      onDragStart={isDraft ? onDragStart : undefined}
      onDragEnd={isDraft ? onDragEnd : undefined}
    >
      <div className="card-header">
        <div className="card-identity">
          <span className="card-type-icon">
            <Icon name="prompt" size={14} />
          </span>
          <span>PRM-{prompt.id.slice(0, 6).toUpperCase()}</span>
        </div>

        {isDraft && (
          <div className="card-actions">
            <button type="button" aria-label="수정" onClick={onEdit}>
              <Icon name="edit" size={15} />
            </button>
            <button
              className="delete-action"
              type="button"
              aria-label="삭제"
              onClick={onDelete}
            >
              <Icon name="trash" size={15} />
            </button>
          </div>
        )}
      </div>

      <h4>{prompt.title}</h4>
      <p className="prompt-preview">{prompt.prompt}</p>

      <div className="prompt-options">
        <span>{MODEL_LABELS[prompt.model]}</span>
        <i />
        <span>{OUTPUT_FORMAT_LABELS[prompt.outputFormat]}</span>
      </div>

      {prompt.status === 'running' && (
        <div className="execution-state">
          <span className="execution-spinner" />
          <div>
            <strong>API 응답 대기</strong>
            <small>Copilot이 프롬프트를 처리하고 있습니다.</small>
          </div>
        </div>
      )}

      {prompt.status === 'completed' && prompt.output && (
        <div className="result-preview">
          <span>응답 결과</span>
          <p>{prompt.output}</p>
        </div>
      )}

      {prompt.errorMessage && (
        <div className="card-error">{prompt.errorMessage}</div>
      )}

      <footer className="card-footer">
        <span>
          {prompt.status === 'draft' ? '수정됨' : '시작됨'}{' '}
          {dateFormatter.format(
            prompt.status === 'draft'
              ? prompt.updatedAt
              : (prompt.startedAt ?? prompt.updatedAt),
          )}
        </span>
        {isDraft ? (
          <button className="drag-hint" type="button" onClick={onRun}>
            <Icon name="send" size={13} />
            실행
          </button>
        ) : (
          <span className={`card-status ${prompt.status}`}>
            <i />
            {prompt.status === 'running' ? '진행중' : '완료'}
          </span>
        )}
      </footer>
    </article>
  )
}
