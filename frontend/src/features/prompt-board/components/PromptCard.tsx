import type { DragEvent } from 'react'

import { OUTPUT_FORMAT_LABELS, type PromptItem } from '../types'
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
  const canManage = prompt.status === 'draft' || prompt.status === 'failed'
  const canRun = prompt.status === 'draft' || prompt.status === 'failed'
  const timeLabel =
    prompt.status === 'draft'
      ? '수정됨'
      : prompt.status === 'running'
        ? '시작됨'
        : prompt.status === 'completed'
          ? '완료됨'
          : '실패함'
  const displayedTime =
    prompt.status === 'running'
      ? (prompt.startedAt ?? prompt.updatedAt)
      : prompt.status === 'completed'
        ? (prompt.completedAt ?? prompt.updatedAt)
        : prompt.updatedAt

  return (
    <article
      className={`prompt-card card-${prompt.status} ${
        isDragging ? 'is-dragging' : ''
      }`}
      draggable={canRun}
      onDragStart={canRun ? onDragStart : undefined}
      onDragEnd={canRun ? onDragEnd : undefined}
    >
      <div className="card-header">
        <div className="card-identity">
          <span className="card-type-icon">
            <Icon name="prompt" size={14} />
          </span>
          <span>PRM-{prompt.id.slice(0, 6).toUpperCase()}</span>
        </div>

        {canManage && (
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
        <span>AI 자동 선택</span>
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
          {timeLabel} {dateFormatter.format(displayedTime)}
        </span>
        {canRun ? (
          <button className="drag-hint" type="button" onClick={onRun}>
            <Icon name="send" size={13} />
            {prompt.status === 'failed' ? '재실행' : '실행'}
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
