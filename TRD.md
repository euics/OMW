# Focus Agent 기술 요구사항 정의서 (TRD)

> **문서 상태:** 구현 기준안  
> **대상 버전:** 4시간 MVP  
> **관련 문서:** [PRD](./PRD.md)  
> **기술 스택:** React 19, TypeScript, Vite, FastAPI, Pydantic, Microsoft Agent Framework, GitHub Copilot SDK

---

## 1. 목적과 범위

이 문서는 PRD의 핵심 흐름인 `목표 입력 → 계획 승인 → 단계 실행 → 완료 검토 → Markdown 내보내기`를 현재 저장소에 구현하기 위한 기술 계약을 정의한다.

MVP는 다음 원칙을 따른다.

- 로그인과 서버 데이터베이스를 사용하지 않는다.
- 사용자 세션은 브라우저 `localStorage`에 저장한다.
- 서버는 요청 처리 중 필요한 데이터만 사용하고 영구 저장하지 않는다.
- AI 출력은 서버에서 Pydantic 스키마로 검증한 뒤 반환한다.
- 하나의 목표 세션과 하나의 순차 실행만 지원한다.
- 외부 파일, 셸, URL 및 쓰기 도구는 에이전트에 허용하지 않는다.

---

## 2. 현재 구현과 목표 상태

### 현재 구현

- 프론트엔드는 `frontend/src/App.tsx`에 정적 프롬프트 칸반 보드가 구현되어 있다.
- 백엔드는 `POST /api/agent/chat` 범용 채팅 API를 제공한다.
- 에이전트 서비스는 Microsoft Agent Framework의 `GitHubCopilotAgent`를 사용한다.
- `thread_id`를 전달하면 Copilot 대화를 이어갈 수 있다.
- 상태 저장, 구조화 출력, 계획·실행·검토 API는 아직 없다.

### 목표 상태

| 영역 | 현재 | MVP 목표 |
|---|---|---|
| 프론트엔드 | 정적 칸반 보드 | 단일 목표 워크플로 |
| 상태 | React 메모리 | reducer + `localStorage` |
| AI API | 자유 텍스트 채팅 | 계획·단계 결과·검토 구조화 API |
| 검증 | 채팅 문자열 검증 | 요청과 AI JSON 모두 Pydantic 검증 |
| 복구 | 없음 | 새로고침 후 현재 세션 복원 |
| 내보내기 | 없음 | Markdown 복사 및 다운로드 |
| 테스트 | 채팅·에이전트 단위 테스트 | 워크플로 API와 상태 전이 테스트 |

기존 `POST /api/agent/chat`은 개발 진단용으로 유지할 수 있지만, 제품 UI에서는 사용하지 않는다.

---

## 3. 시스템 구조

```text
Browser
  ├─ React workflow UI
  ├─ useReducer state machine
  ├─ localStorage session snapshot
  └─ Markdown export
          │ HTTPS / JSON
          ▼
FastAPI
  ├─ request validation
  ├─ workflow prompt builder
  ├─ Microsoft Agent Framework
  ├─ GitHub Copilot SDK
  └─ structured response validation
```

### 책임 분리

**프론트엔드**

- 사용자 입력과 길이 제한 검증
- 화면 및 워크플로 상태 전이
- 현재 세션의 로컬 저장과 복원
- API 로딩, 오류, 명시적 재시도 처리
- Markdown 생성, 복사, 다운로드

**백엔드**

- 요청 본문 검증
- 역할별 시스템 지침과 프롬프트 구성
- Copilot 세션 생성 또는 재사용
- AI 응답의 JSON 추출 및 스키마 검증
- 안전한 오류 응답과 최소 로그 기록

**AI 에이전트**

- 계획, 단계 결과물, 완료 검토 생성
- 제공된 입력과 세션 문맥만 사용
- 지정된 JSON 형태 외 텍스트를 반환하지 않음

---

## 4. 사용자 흐름과 상태 머신

### 워크플로 상태

```ts
type WorkflowStatus =
  | 'draft'
  | 'planning'
  | 'awaitingPlanApproval'
  | 'executing'
  | 'reviewing'
  | 'done'
  | 'failed'
```

### 상태 전이

```text
draft
  → planning
  → awaitingPlanApproval
      ├─ 계획 승인 → executing
      └─ 수정 요청 → planning
  → executing
      ├─ 단계 완료 → 다음 단계 실행
      ├─ 수정 요청 → 현재 단계 재실행
      ├─ 건너뛰기 → 다음 단계
      └─ 모든 단계 종료 → reviewing
  → reviewing
  → done
```

API 실패 시 직전 안정 상태와 실패 작업을 함께 보존한 `failed`로 전환한다. 사용자가 재시도하면 실패한 작업만 다시 실행한다.

### 횟수 제한

| 작업 | 제한 |
|---|---:|
| 계획 단계 수 | 3~5개 |
| 완료 조건 수 | 1~5개 |
| 계획 수정 | 세션당 1회 |
| 단계 수정 | 단계당 1회 |
| 실패 작업 재시도 | 작업당 1회 |

프론트엔드와 백엔드가 모두 제한을 검증한다.

---

## 5. 프론트엔드 데이터 모델

```ts
type Criterion = {
  id: string
  text: string
}

type StepStatus =
  | 'pending'
  | 'generating'
  | 'awaitingAction'
  | 'completed'
  | 'skipped'
  | 'failed'

type PlanStep = {
  id: string
  title: string
  description: string
  expectedArtifact: string
  criterionIds: string[]
  status: StepStatus
  result: StepResult | null
  revisionCount: number
}

type StepResult = {
  summary: string
  artifact: string
  nextAction: string
}

type ReviewStatus = 'satisfied' | 'unsatisfied' | 'needsConfirmation'

type CriterionReview = {
  criterionId: string
  status: ReviewStatus
  evidence: string
  nextAction: string
}

type SessionMetrics = {
  startedAt: string
  completedAt: string | null
  completedSteps: number
  skippedSteps: number
  revisionCount: number
}

type FocusSession = {
  schemaVersion: 1
  id: string
  goal: string
  criteria: Criterion[]
  context: string
  status: WorkflowStatus
  goalSummary: string
  steps: PlanStep[]
  currentStepId: string | null
  reviews: CriterionReview[]
  mostImportantNextAction: string
  threadId: string | null
  planRevisionCount: number
  metrics: SessionMetrics
  failure: FailureState | null
}

type FailureState = {
  operation: 'plan' | 'executeStep' | 'review'
  stepId: string | null
  message: string
  retryCount: number
}
```

세션과 완료 조건 ID는 클라이언트에서 `crypto.randomUUID()`로 생성한다. 단계 ID는 모델 출력 검증 후 서버가 순서대로 `step-1` 형식으로 부여하며, AI가 임의로 생성한 ID는 신뢰하지 않는다.

---

## 6. 로컬 저장과 복구

### 저장 키

```text
focus-agent.session.v1
```

### 저장 시점

- 계획 생성 성공
- 계획 승인 또는 수정 요청
- 단계 결과 생성 성공
- 단계 완료, 건너뛰기 또는 수정 요청
- 완료 검토 성공
- API 실패와 재시도

입력 중인 초안은 별도로 저장하지 않는다. 첫 계획 생성이 성공한 시점부터 세션을 저장한다.

### 복구 규칙

1. 앱 시작 시 저장 키를 읽는다.
2. JSON 파싱과 `schemaVersion`을 확인한다.
3. 필수 필드와 상태 조합이 유효하면 세션을 복원한다.
4. 유효하지 않으면 저장값을 삭제하지 않고 복구 오류를 표시한다.
5. 사용자가 `새 목표 시작`을 확인하면 저장값을 삭제하고 `draft`로 초기화한다.

세션 상태가 `planning` 또는 `reviewing`이거나 현재 단계 상태가 `generating`일 때 새로고침되면 네트워크 요청을 자동 재개하지 않는다. 대응하는 작업을 `failed`로 바꾸고 사용자의 명시적 재시도를 요구한다.

---

## 7. API 계약

모든 제품 API는 `/api/agent` 아래에 위치한다. 성공 응답은 `request_id`, `thread_id`, 구조화된 `data`를 반환한다.

### 7.1 계획 생성 및 수정

`POST /api/agent/plan`

```json
{
  "goal": "내일 5분 해커톤 발표를 준비하고 싶어.",
  "criteria": [
    {"id": "criterion-1", "text": "5분 분량의 발표 대본이 있다."}
  ],
  "context": "발표 대상은 개발자다.",
  "previous_plan": null,
  "revision_request": null,
  "thread_id": null
}
```

계획 수정 시 `previous_plan`, `revision_request`, 기존 `thread_id`를 전달한다.

```json
{
  "request_id": "req_...",
  "thread_id": "copilot-session-id",
  "data": {
    "goal_summary": "5분 해커톤 발표 자료 완성",
    "steps": [
      {
        "id": "step-1",
        "title": "발표 구조 설계",
        "description": "문제, 해결책, 데모, 효과 순서로 구조를 만든다.",
        "expected_artifact": "발표 개요",
        "criterion_ids": ["criterion-1"]
      }
    ]
  }
}
```

검증 규칙:

- `goal`: 공백 제거 후 1~500자
- `criteria`: 1~5개, 각 항목 1~300자
- `context`: 최대 2,000자
- `steps`: 3~5개
- 모든 `criterion_ids`는 요청에 존재해야 함
- 각 완료 조건은 최소 한 단계와 연결되어야 함

### 7.2 단계 결과 생성 및 수정

`POST /api/agent/steps/generate`

```json
{
  "goal": "내일 5분 해커톤 발표를 준비하고 싶어.",
  "criteria": [
    {"id": "criterion-1", "text": "5분 분량의 발표 대본이 있다."}
  ],
  "context": "발표 대상은 개발자다.",
  "steps": [
    {
      "id": "step-1",
      "title": "발표 구조 설계",
      "description": "문제, 해결책, 데모, 효과 순서로 구조를 만든다.",
      "expected_artifact": "발표 개요",
      "criterion_ids": ["criterion-1"]
    }
  ],
  "current_step_id": "step-1",
  "completed_results": [],
  "previous_result": null,
  "revision_request": null,
  "thread_id": "copilot-session-id"
}
```

```json
{
  "request_id": "req_...",
  "thread_id": "copilot-session-id",
  "data": {
    "summary": "발표 흐름을 네 부분으로 구성했습니다.",
    "artifact": "## 발표 개요\n...",
    "next_action": "발표 대본 초안을 작성합니다."
  }
}
```

서버는 현재 단계가 `steps`에 존재하는지, 완료 결과가 해당 단계보다 앞선 단계에만 연결되는지 검증한다.

### 7.3 완료 검토

`POST /api/agent/review`

```json
{
  "goal": "내일 5분 해커톤 발표를 준비하고 싶어.",
  "criteria": [
    {"id": "criterion-1", "text": "5분 분량의 발표 대본이 있다."}
  ],
  "steps": [
    {
      "id": "step-1",
      "title": "발표 구조 설계",
      "status": "completed",
      "result": {
        "summary": "발표 흐름을 네 부분으로 구성했습니다.",
        "artifact": "## 발표 개요\n...",
        "next_action": "발표 대본 초안을 작성합니다."
      }
    }
  ],
  "thread_id": "copilot-session-id"
}
```

```json
{
  "request_id": "req_...",
  "thread_id": "copilot-session-id",
  "data": {
    "reviews": [
      {
        "criterion_id": "criterion-1",
        "status": "satisfied",
        "evidence": "step-2 결과에 5분 발표 대본이 포함되어 있습니다.",
        "next_action": "실제 발표 시간을 측정합니다."
      }
    ],
    "most_important_next_action": "발표 리허설을 한 번 진행합니다."
  }
}
```

검증 규칙:

- 모든 완료 조건에 정확히 하나의 검토 결과가 있어야 함
- `status`는 `satisfied`, `unsatisfied`, `needsConfirmation` 중 하나
- 근거가 없는 경우 `satisfied`를 사용할 수 없음

### 7.4 오류 응답

```json
{
  "detail": {
    "code": "AGENT_TIMEOUT",
    "message": "응답 시간이 초과되었습니다.",
    "request_id": "req_...",
    "retryable": true
  }
}
```

| HTTP | 코드 | 의미 | 재시도 |
|---:|---|---|---|
| 422 | `VALIDATION_ERROR` | 요청 형식 또는 제한 위반 | 아니요 |
| 502 | `INVALID_AGENT_OUTPUT` | AI 출력 스키마 검증 실패 | 예 |
| 503 | `AGENT_UNAVAILABLE` | 인증, 모델 또는 SDK 오류 | 예 |
| 504 | `AGENT_TIMEOUT` | 30초 제한 초과 | 예 |

클라이언트에는 내부 예외, 프롬프트, 자격 증명 또는 원본 SDK 응답을 노출하지 않는다.

---

## 8. 에이전트와 구조화 출력

### 역할별 지침

- `Planner`: 목표를 실행 가능한 3~5단계로 분해하고 완료 조건을 연결한다.
- `Coach`: 현재 단계에 필요한 결과물만 생성하고 다음 행동을 한 가지 제시한다.
- `Reviewer`: 생성된 결과만 근거로 완료 조건을 판정한다.

MVP에서는 역할별 에이전트 인스턴스를 병렬 실행하지 않는다. 동일한 `GitHubCopilotAgent` 서비스에 역할별 지침과 요청 데이터를 전달하는 순차 호출로 구현한다.

### 출력 처리

1. 모델에 JSON 전용 출력을 지시한다.
2. 응답에서 Markdown 코드 펜스를 허용하지 않는다.
3. 전체 응답을 JSON으로 파싱한다.
4. 역할별 Pydantic 모델로 검증한다.
5. 검증 실패 시 원본 응답과 오류 위치를 포함해 형식 교정을 한 번 요청한다.
6. 교정 결과도 실패하면 `INVALID_AGENT_OUTPUT`을 반환한다.
7. 사용자가 명시적으로 한 번 재시도할 수 있다.

형식 교정은 동일 작업의 내부 처리이며 사용자 재시도 횟수에는 포함하지 않는다.

---

## 9. 프론트엔드 구성

```text
frontend/src/
  App.tsx
  components/
    GoalForm.tsx
    PlanReview.tsx
    StepRunner.tsx
    CompletionReview.tsx
    ProgressHeader.tsx
    ErrorPanel.tsx
  hooks/
    useFocusSession.ts
  lib/
    api.ts
    exportMarkdown.ts
    storage.ts
  state/
    sessionReducer.ts
    types.ts
  styles.css
```

### 화면 매핑

| 상태 | 기본 화면 |
|---|---|
| `draft` | `GoalForm` |
| `planning` | 목표 화면 + 로딩 상태 |
| `awaitingPlanApproval` | `PlanReview` |
| `executing` | `ProgressHeader` + `StepRunner` |
| `reviewing` | 실행 화면 + 검토 로딩 상태 |
| `done` | `CompletionReview` |
| `failed` | 직전 화면 + `ErrorPanel` |

### 접근성

- 모든 입력에 표시 라벨을 연결한다.
- 상태 변경은 `aria-live="polite"` 영역에 알린다.
- 진행률은 텍스트와 `<progress>`를 함께 제공한다.
- 드래그 조작을 요구하지 않는다.
- 로딩 중인 요청 버튼은 비활성화하고 상태 문구를 표시한다.
- 오류 발생 시 포커스를 오류 제목으로 이동한다.

---

## 10. Markdown 내보내기

내보내기는 서버 호출 없이 브라우저에서 생성한다.

```text
# 목표
## 완료 조건
## 실행 계획
## 단계별 결과
## 완료 검토
## 다음 행동
## 세션 요약
```

- 복사: `navigator.clipboard.writeText`
- 다운로드: `Blob`과 임시 object URL 사용
- 파일명: `focus-agent-{YYYY-MM-DD}.md`
- 사용자 입력과 AI 결과를 HTML로 변환하거나 실행하지 않는다.

---

## 11. 보안, 개인정보 및 로그

- 목표, 참고 내용, 결과물 원문을 애플리케이션 로그에 기록하지 않는다.
- 로그 필드는 `request_id`, 작업 종류, 상태 코드, 지연 시간, 모델명으로 제한한다.
- 프론트엔드는 AI 결과를 일반 텍스트 또는 안전한 Markdown으로 렌더링한다.
- `dangerouslySetInnerHTML`을 사용하지 않는다.
- CORS는 `FRONTEND_ORIGIN` 한 개로 제한한다.
- Copilot CLI 경로와 인증 정보는 서버 환경 변수로만 설정한다.
- 에이전트 도구 권한은 기본 거부 상태를 유지한다.

---

## 12. 설정

```dotenv
APP_NAME=Focus Agent API
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173
GITHUB_COPILOT_MODEL=auto
GITHUB_COPILOT_TIMEOUT=30
GITHUB_COPILOT_LOG_LEVEL=info
```

운영 환경에서는 Azure Container Apps의 secret 또는 Key Vault 참조를 사용한다. `.env` 파일은 배포 산출물과 Git에 포함하지 않는다.

---

## 13. 구현 순서

1. 백엔드에 워크플로 요청·응답 Pydantic 모델을 추가한다.
2. 역할별 프롬프트 구성과 JSON 검증 서비스를 추가한다.
3. 계획, 단계 생성, 완료 검토 API와 오류 매핑을 구현한다.
4. 프론트엔드 상태 타입, reducer, 로컬 저장을 구현한다.
5. 목표 입력과 계획 승인 화면을 구현한다.
6. 단계 실행, 수정, 완료, 건너뛰기 흐름을 구현한다.
7. 완료 검토와 Markdown 내보내기를 구현한다.
8. 오류, 재시도, 새로고침 복구, 모바일 UI를 확인한다.

현재 칸반 샘플 UI와 `Ticket` 데이터 모델은 Focus Agent 워크플로로 교체한다.

---

## 14. 테스트 전략

### 백엔드

- 입력 길이와 완료 조건 개수 검증
- 계획 단계 수와 완료 조건 연결 검증
- 단계 결과와 완료 검토 스키마 검증
- 새 Copilot 세션 생성과 기존 `thread_id` 재사용
- SDK 오류, 타임아웃, 빈 응답, 잘못된 JSON 오류 매핑
- 로그에 사용자 원문이 포함되지 않는지 확인

### 프론트엔드

- reducer의 허용 상태 전이
- 잘못된 상태 전이 거부
- 저장, 복원, 버전 불일치 처리
- 계획 및 단계 수정 횟수 제한
- API 실패 후 해당 작업만 재시도
- Markdown 결과의 모든 섹션 포함

### 핵심 통합 시나리오

1. 목표와 완료 조건을 입력한다.
2. 3~5단계 계획을 생성하고 승인한다.
3. 각 단계 결과를 생성해 완료 처리한다.
4. 한 단계에서 수정 요청을 한 번 수행한다.
5. 완료 조건 검토를 생성한다.
6. Markdown을 복사하고 다운로드한다.
7. 각 주요 상태에서 새로고침해 복구 결과를 확인한다.

---

## 15. PRD 완료 조건 추적

| PRD P0 | 기술 구현 | 검증 |
|---|---|---|
| 목표 입력 | `GoalForm`, 요청 스키마 | 경계값 테스트 |
| AI 계획 생성 | `/api/agent/plan` | 3~5단계 및 조건 연결 |
| 계획 승인 | reducer 상태 전이 | 승인·수정 시나리오 |
| 단계별 실행 | `/api/agent/steps/generate` | 순차 결과 생성 |
| 진행 관리 | `StepRunner`, `PlanStep.status` | 완료·수정·건너뛰기 |
| 완료 검토 | `/api/agent/review` | 조건별 단일 판정 |
| 로컬 복구 | `storage.ts`, 스키마 버전 | 새로고침 복구 |
| 결과 내보내기 | `exportMarkdown.ts` | 복사·다운로드 |
| 반응형 UI | 단일 열 모바일 레이아웃 | 360px 확인 |
| 오류 처리 | 표준 오류 응답, `FailureState` | 실패·재시도 |

---

## 16. 완료 정의

- `npm run check`가 성공한다.
- 계획, 실행, 검토 응답이 모두 서버 스키마 검증을 통과한다.
- 새로고침 후 현재 목표, 계획, 결과, 진행 상태가 복구된다.
- API 실패 후 실패한 작업만 한 번 재시도할 수 있다.
- 360px 너비에서 가로 스크롤 없이 핵심 흐름을 완료할 수 있다.
- 전체 결과를 Markdown으로 복사하거나 내려받을 수 있다.
- 브라우저와 서버 로그에 사용자 목표 및 결과물 원문이 남지 않는다.
