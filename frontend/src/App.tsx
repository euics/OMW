import { useMemo, useState } from 'react'
import type { DragEvent } from 'react'

import {
  Icon,
  type IconName,
} from './features/prompt-board/components/Icon'
import { PromptCard } from './features/prompt-board/components/PromptCard'
import { PromptComposer } from './features/prompt-board/components/PromptComposer'
import {
  OUTPUT_FORMAT_LABELS,
  type PromptItem,
  type PromptStatus,
} from './features/prompt-board/types'
import { usePromptBoard } from './features/prompt-board/usePromptBoard'

const columns: Array<{
  id: PromptStatus
  eyebrow: string
  title: string
  description: string
  icon: IconName
  emptyIcon: IconName
  emptyTitle: string
  emptyDescription: string
}> = [
  {
    id: 'draft',
    eyebrow: 'READY',
    title: '미실행 프롬프트',
    description: '실행 전까지 내용을 자유롭게 편집할 수 있어요.',
    icon: 'edit',
    emptyIcon: 'prompt',
    emptyTitle: '첫 프롬프트를 작성해 보세요',
    emptyDescription: '저장한 프롬프트는 이곳에서 실행 전까지 관리됩니다.',
  },
  {
    id: 'running',
    eyebrow: 'PROCESSING',
    title: '진행중',
    description: 'API로 전달된 프롬프트의 응답을 기다립니다.',
    icon: 'loader',
    emptyIcon: 'send',
    emptyTitle: '실행 중인 프롬프트가 없습니다',
    emptyDescription: '미실행 카드를 이곳으로 드래그해 실행을 시작합니다.',
  },
  {
    id: 'completed',
    eyebrow: 'ARCHIVE',
    title: '완료',
    description: '응답이 도착하면 결과와 함께 자동 저장됩니다.',
    icon: 'check',
    emptyIcon: 'archive',
    emptyTitle: '완료된 응답이 없습니다',
    emptyDescription: '백엔드 응답이 완료되면 결과가 자동으로 표시됩니다.',
  },
  {
    id: 'failed',
    eyebrow: 'FAILED',
    title: '실패',
    description: '실패 원인을 확인하고 수정하거나 다시 실행할 수 있어요.',
    icon: 'info',
    emptyIcon: 'info',
    emptyTitle: '실패한 프롬프트가 없습니다',
    emptyDescription: '실행 오류가 발생하면 원인과 함께 이곳에 표시됩니다.',
  },
]

function App() {
  const {
    prompts,
    columns: promptColumns,
    isLoading,
    errorMessage,
    loadingMoreStatus,
    executionStates,
    clearError,
    refreshPrompts,
    loadMore,
    createPrompt,
    updatePrompt,
    deletePrompt,
    startPrompt,
    cancelPrompt,
  } = usePromptBoard()
  const [isComposerOpen, setComposerOpen] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState<PromptItem | null>(null)
  const [pendingRun, setPendingRun] = useState<PromptItem | null>(null)
  const [draggedPromptId, setDraggedPromptId] = useState<string | null>(null)
  const [isRunningDropActive, setRunningDropActive] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  const counts = useMemo(
    () => ({
      draft: promptColumns.draft.total,
      running: promptColumns.running.total,
      completed: promptColumns.completed.total,
      failed: promptColumns.failed.total,
    }),
    [promptColumns],
  )
  const totalCount = Object.values(promptColumns).reduce(
    (total, page) => total + page.total,
    0,
  )

  const openNewPrompt = () => {
    setEditingPrompt(null)
    setComposerOpen(true)
  }

  const openPromptEditor = (prompt: PromptItem) => {
    setEditingPrompt(prompt)
    setComposerOpen(true)
  }

  const closeComposer = () => {
    setComposerOpen(false)
    setEditingPrompt(null)
  }

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    const promptId =
      event.dataTransfer.getData('text/plain') || draggedPromptId
    const prompt = prompts.find(
      (item) =>
        item.id === promptId &&
        (item.status === 'draft' || item.status === 'failed'),
    )

    setRunningDropActive(false)
    setDraggedPromptId(null)

    if (prompt) {
      setPendingRun(prompt)
    }
  }

  const confirmRun = () => {
    if (!pendingRun) return

    const prompt = pendingRun
    setPendingRun(null)
    void startPrompt(prompt.id)
      .then(() => {
        setAnnouncement(`${prompt.title} 프롬프트의 실행을 요청했습니다.`)
      })
      .catch(() => undefined)
  }

  return (
    <div className="app-shell">
      <main id="main">
        <section className="page-intro">
          <div className="intro-copy">
            <div className="section-label">
              <span />
              PROMPT PIPELINE
            </div>
            <h1>
              작성부터 응답까지,
              <br />
              흐름이 보이도록.
            </h1>
            <p>
              프롬프트를 준비하고 실행 상태로 이동하세요. API가 연결되면
              실행과 동시에 백엔드로 전달되고, 응답 완료 후 결과가 보관됩니다.
            </p>
          </div>

          <div className="pipeline-overview" aria-label="프롬프트 실행 흐름">
            <div className="pipeline-step">
              <span className="step-number">01</span>
              <div>
                <strong>작성</strong>
                <small>내용과 실행 옵션 설정</small>
              </div>
            </div>
            <Icon name="chevronRight" size={17} />
            <div className="pipeline-step">
              <span className="step-number">02</span>
              <div>
                <strong>실행 요청</strong>
                <small>백엔드 API로 전달</small>
              </div>
            </div>
            <Icon name="chevronRight" size={17} />
            <div className="pipeline-step">
              <span className="step-number">03</span>
              <div>
                <strong>응답 보관</strong>
                <small>완료 결과 확인</small>
              </div>
            </div>
          </div>
        </section>

        <section className="board-section" id="board">
          <div className="board-heading">
            <div>
              <div className="board-title-row">
                <h2>실행 보드</h2>
                <span className="total-count">{totalCount}</span>
              </div>
              <p>카드를 진행중 열로 드래그하면 실행 흐름이 시작됩니다.</p>
            </div>

            <div className="board-actions">
              <button className="primary-button" onClick={openNewPrompt}>
                <Icon name="plus" size={17} />
                프롬프트 작성
              </button>
            </div>
          </div>

          <div className="status-summary">
            <div>
              <span className="summary-dot draft" />
              미실행 <strong>{counts.draft}</strong>
            </div>
            <div>
              <span className="summary-dot running" />
              진행중 <strong>{counts.running}</strong>
            </div>
            <div>
              <span className="summary-dot completed" />
              완료 <strong>{counts.completed}</strong>
            </div>
            <div>
              <span className="summary-dot failed" />
              실패 <strong>{counts.failed}</strong>
            </div>
            <span className="summary-divider" />
            <div className="api-readiness">
              <Icon name="plug" size={14} />
              MySQL 저장
            </div>
          </div>

          {errorMessage && (
            <div className="board-error" role="alert">
              <span><Icon name="info" size={17} /></span>
              <div>
                <strong>데이터를 불러오지 못했습니다.</strong>
                <p>{errorMessage}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  clearError()
                  void refreshPrompts(true).catch(() => undefined)
                }}
              >
                다시 시도
              </button>
            </div>
          )}

          <div className="board-grid">
            {columns.map((column) => {
              const page = promptColumns[column.id]
              const columnPrompts = page.items
              const acceptsDrop = column.id === 'running' && Boolean(draggedPromptId)

              return (
                <section
                  className={`prompt-column column-${column.id} ${
                    acceptsDrop ? 'can-drop' : ''
                  } ${
                    column.id === 'running' && isRunningDropActive
                      ? 'is-over'
                      : ''
                  }`}
                  key={column.id}
                  onDragEnter={(event) => {
                    if (column.id !== 'running' || !draggedPromptId) return
                    event.preventDefault()
                    setRunningDropActive(true)
                  }}
                  onDragOver={(event) => {
                    if (column.id !== 'running' || !draggedPromptId) return
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                  }}
                  onDragLeave={(event) => {
                    if (
                      column.id === 'running' &&
                      !event.currentTarget.contains(
                        event.relatedTarget as Node | null,
                      )
                    ) {
                      setRunningDropActive(false)
                    }
                  }}
                  onDrop={
                    column.id === 'running' ? handleDrop : undefined
                  }
                >
                  <header className="column-heading">
                    <div className="column-title">
                      <span className="column-icon">
                        <Icon name={column.icon} size={16} />
                      </span>
                      <div>
                        <span>{column.eyebrow}</span>
                        <h3>{column.title}</h3>
                      </div>
                    </div>
                    <span className="column-count">{page.total}</span>
                  </header>
                  <p className="column-description">{column.description}</p>

                  <div className="card-list">
                    {columnPrompts.map((prompt) => (
                      <PromptCard
                        key={prompt.id}
                        prompt={prompt}
                        isDragging={draggedPromptId === prompt.id}
                        executionState={executionStates[prompt.id]}
                        onEdit={() => openPromptEditor(prompt)}
                        onRun={() => setPendingRun(prompt)}
                        onCancel={() => {
                          void cancelPrompt(prompt.id)
                            .then(() => {
                              setAnnouncement(
                                `${prompt.title} 프롬프트의 취소를 요청했습니다.`,
                              )
                            })
                            .catch(() => undefined)
                        }}
                        onDelete={() => {
                          void deletePrompt(prompt.id)
                            .then(() => {
                              setAnnouncement(
                                `${prompt.title} 프롬프트를 삭제했습니다.`,
                              )
                            })
                            .catch(() => undefined)
                        }}
                        onDragStart={(event) => {
                          event.dataTransfer.effectAllowed = 'move'
                          event.dataTransfer.setData('text/plain', prompt.id)
                          setDraggedPromptId(prompt.id)
                        }}
                        onDragEnd={() => {
                          setDraggedPromptId(null)
                          setRunningDropActive(false)
                        }}
                      />
                    ))}

                    {columnPrompts.length === 0 && (
                      <div className="column-empty">
                        <span className="empty-illustration">
                          <Icon name={column.emptyIcon} size={25} />
                        </span>
                        <strong>
                          {isLoading
                            ? '프롬프트를 불러오는 중입니다'
                            : column.emptyTitle}
                        </strong>
                        <p>
                          {isLoading
                            ? '저장된 데이터를 확인하고 있어요.'
                            : column.emptyDescription}
                        </p>
                        {!isLoading && column.id === 'draft' && (
                          <button
                            className="empty-action"
                            type="button"
                            onClick={openNewPrompt}
                          >
                            <Icon name="plus" size={15} />
                            프롬프트 만들기
                          </button>
                        )}

                      </div>
                    )}

                    {page.hasNext && (
                      <button
                        className="column-load-more"
                        type="button"
                        disabled={loadingMoreStatus !== null}
                        onClick={() => {
                          void loadMore(column.id).catch(() => undefined)
                        }}
                      >
                        {loadingMoreStatus === column.id
                          ? '불러오는 중...'
                          : `더 보기 (${columnPrompts.length}/${page.total})`}
                      </button>
                    )}
                  </div>

                  {acceptsDrop && (
                    <div className="drop-zone">
                      <span><Icon name="send" size={17} /></span>
                      <strong>여기에 놓아 실행 준비</strong>
                      <small>확인 후 진행중 상태로 이동합니다.</small>
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        </section>
      </main>

      <footer className="app-footer">
        <span className="footer-mark"><Icon name="command" size={14} /></span>
        <p>
          사용자 계정 없이 하나의 로컬 워크스페이스로 동작하며, 모든
          프롬프트와 실행 결과는 서버 데이터베이스에 저장됩니다.
        </p>
      </footer>

      <PromptComposer
        open={isComposerOpen}
        prompt={editingPrompt}
        onClose={closeComposer}
        onSubmit={async (values) => {
          if (editingPrompt) {
            await updatePrompt(editingPrompt.id, values)
            setAnnouncement(`${values.title} 프롬프트를 수정했습니다.`)
          } else {
            await createPrompt(values)
            setAnnouncement(`${values.title} 프롬프트를 만들었습니다.`)
          }
          closeComposer()
        }}
      />

      {pendingRun && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPendingRun(null)
          }}
        >
          <section
            className="run-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="run-dialog-title"
          >
            <button
              className="dialog-close"
              type="button"
              aria-label="닫기"
              onClick={() => setPendingRun(null)}
            >
              <Icon name="close" size={18} />
            </button>
            <span className="dialog-icon"><Icon name="send" size={22} /></span>
            <span className="dialog-eyebrow">START EXECUTION</span>
            <h2 id="run-dialog-title">이 프롬프트를 실행할까요?</h2>
            <p>
              진행중으로 이동한 뒤에는 백엔드 응답이 도착할 때까지 내용을
              수정할 수 없습니다.
            </p>

            <div className="run-preview">
              <div>
                <span>프롬프트</span>
                <strong>{pendingRun.title}</strong>
              </div>
              <p>{pendingRun.prompt}</p>
              <dl>
                <div>
                  <dt>모델</dt>
                  <dd>백엔드 자동 선택</dd>
                </div>
                <div>
                  <dt>응답 형식</dt>
                  <dd>{OUTPUT_FORMAT_LABELS[pendingRun.outputFormat]}</dd>
                </div>
              </dl>
            </div>

            <div className="prototype-notice">
              <Icon name="info" size={17} />
              <p>
                실행 요청은 즉시 저장되고 백그라운드에서 처리됩니다. 화면은
                완료될 때까지 상태를 자동으로 확인합니다.
              </p>
            </div>

            <div className="dialog-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setPendingRun(null)}
              >
                취소
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={confirmRun}
              >
                <Icon name="send" size={16} />
                진행중으로 이동
              </button>
            </div>
          </section>
        </div>
      )}

      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>
    </div>
  )
}

export default App
