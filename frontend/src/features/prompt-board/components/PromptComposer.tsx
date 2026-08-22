import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import {
  EMPTY_PROMPT_FORM,
  OUTPUT_FORMAT_LABELS,
  type OutputFormat,
  type PromptFormValues,
  type PromptItem,
} from '../types'
import { Icon } from './Icon'

type PromptComposerProps = {
  open: boolean
  prompt: PromptItem | null
  onClose: () => void
  onSubmit: (values: PromptFormValues) => Promise<void>
}

export function PromptComposer({
  open,
  prompt,
  onClose,
  onSubmit,
}: PromptComposerProps) {
  const [values, setValues] =
    useState<PromptFormValues>(EMPTY_PROMPT_FORM)
  const [submitted, setSubmitted] = useState(false)
  const [isSaving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return

    setValues(
      prompt
        ? {
            title: prompt.title,
            prompt: prompt.prompt,
            outputFormat: prompt.outputFormat,
          }
        : EMPTY_PROMPT_FORM,
    )
    setSubmitted(false)
    setSaving(false)
    setSubmitError(null)

    const focusTimer = window.setTimeout(
      () => titleInputRef.current?.focus(),
      120,
    )
    return () => window.clearTimeout(focusTimer)
  }, [open, prompt])

  useEffect(() => {
    if (!open) return

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [onClose, open])

  if (!open) return null

  const titleIsInvalid = !values.title.trim()
  const promptIsInvalid = !values.prompt.trim()

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitted(true)
    if (titleIsInvalid || promptIsInvalid) return

    setSaving(true)
    setSubmitError(null)
    try {
      await onSubmit({
        ...values,
        title: values.title.trim(),
        prompt: values.prompt.trim(),
      })
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : '프롬프트를 저장하지 못했습니다.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <aside
        className="prompt-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="composer-title"
      >
        <header className="drawer-header">
          <div>
            <span>{prompt ? 'EDIT PROMPT' : 'NEW PROMPT'}</span>
            <h2 id="composer-title">
              {prompt ? '프롬프트 수정' : '새 프롬프트 작성'}
            </h2>
          </div>
          <button type="button" aria-label="닫기" onClick={onClose}>
            <Icon name="close" size={19} />
          </button>
        </header>

        <div className="drawer-guide">
          <span><Icon name="info" size={16} /></span>
          <p>
            저장한 프롬프트는 <strong>미실행 프롬프트</strong>에 추가됩니다.
            실행 전까지 언제든 수정할 수 있어요.
          </p>
        </div>

        <form className="prompt-form" onSubmit={handleSubmit}>
          <div className="form-section">
            <div className="form-section-title">
              <span>01</span>
              <div>
                <strong>기본 정보</strong>
                <small>보드에서 구분할 이름을 입력하세요.</small>
              </div>
            </div>

            <label className="form-field">
              <span>
                프롬프트 이름 <em>필수</em>
              </span>
              <input
                ref={titleInputRef}
                className={submitted && titleIsInvalid ? 'invalid' : ''}
                value={values.title}
                maxLength={80}
                placeholder="예: 주간 고객 피드백 요약"
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
              <small className="field-meta">
                <span>
                  {submitted && titleIsInvalid
                    ? '프롬프트 이름을 입력해 주세요.'
                    : '실행 목적을 알아보기 쉽게 작성해 주세요.'}
                </span>
                <span>{values.title.length}/80</span>
              </small>
            </label>
          </div>

          <div className="form-section">
            <div className="form-section-title">
              <span>02</span>
              <div>
                <strong>프롬프트</strong>
                <small>백엔드로 전달할 요청 내용을 작성하세요.</small>
              </div>
            </div>

            <label className="form-field">
              <span>
                요청 내용 <em>필수</em>
              </span>
              <div
                className={`prompt-textarea ${
                  submitted && promptIsInvalid ? 'invalid' : ''
                }`}
              >
                <textarea
                  value={values.prompt}
                  maxLength={4000}
                  rows={11}
                  placeholder={
                    '역할, 필요한 입력, 원하는 결과 형식을 구체적으로 작성해 주세요.\n\n예: 아래 고객 피드백을 긍정/부정으로 분류하고 핵심 이슈를 세 줄로 요약해 줘.'
                  }
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      prompt: event.target.value,
                    }))
                  }
                />
                <div className="textarea-toolbar">
                  <span><Icon name="command" size={13} /> 실행 전 검토 가능</span>
                  <span>{values.prompt.length}/4,000</span>
                </div>
              </div>
              {submitted && promptIsInvalid && (
                <small className="field-error">
                  요청 내용을 입력해 주세요.
                </small>
              )}
            </label>
          </div>

          <div className="form-section">
            <div className="form-section-title">
              <span>03</span>
              <div>
                <strong>실행 옵션</strong>
                <small>AI 모델은 백엔드가 자동으로 선택합니다.</small>
              </div>
            </div>

            <label className="form-field">
              <span>응답 형식</span>
              <div className="select-control">
                <select
                  value={values.outputFormat}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      outputFormat: event.target.value as OutputFormat,
                    }))
                  }
                >
                  {Object.entries(OUTPUT_FORMAT_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <Icon name="chevronDown" size={15} />
              </div>
            </label>
          </div>

          <footer className="drawer-actions">
            <div>
              <Icon name="archive" size={15} />
              초안으로 저장됩니다
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
              disabled={isSaving}
            >
              취소
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={isSaving}
            >
              <Icon name={prompt ? 'check' : 'plus'} size={16} />
              {isSaving
                ? '저장 중...'
                : prompt
                  ? '변경사항 저장'
                  : '프롬프트 저장'}
            </button>
          </footer>
          {submitError && (
            <div className="drawer-submit-error" role="alert">
              {submitError}
            </div>
          )}
        </form>
      </aside>
    </div>
  )
}
