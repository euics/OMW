# TRD — OnMyWay Agent Operations Harness

> **문서 상태:** 2026-08-22 최신 `main` 구현 기준
> **관련 문서:** [PRD](./PRD.md)
> **기술 스택:** React 19, TypeScript, Vite, FastAPI, MySQL, Microsoft Agent Framework, GitHub Copilot SDK

## 1. 기술 목표

OnMyWay는 여러 AI 작업을 독립적인 실행 단위로 저장하고, Microsoft Agent Framework
기반 하네스에서 실행한 뒤 상태와 결과를 일관되게 관리한다.

기술적으로 다음을 보장한다.

- 클라이언트는 AI 공급자 자격 증명이나 모델을 직접 제어하지 않는다.
- 같은 작업에 대한 중복 실행 요청은 데이터베이스 상태 전이로 차단한다.
- 완료 결과와 실패 원인을 영속적으로 보관한다.
- 서버 재시작으로 중단된 실행을 사용자가 다시 시도할 수 있는 상태로 복구한다.
- 프론트엔드는 여러 작업의 상태를 주기적으로 갱신한다.

## 2. 시스템 구조

```text
Browser
  └─ React prompt operations board
       ├─ prompt create/update/delete
       ├─ execution confirmation
       ├─ status polling
       └─ result/error display
              │ HTTP / JSON
              ▼
FastAPI
  ├─ request validation
  ├─ prompt lifecycle service
  ├─ Microsoft Agent Framework
  │    └─ GitHubCopilotAgent
  ├─ GitHub Copilot SDK
  └─ MySQL repository
              │
              ▼
          MySQL 8
```

### 책임 분리

**프론트엔드**

- 프롬프트 입력과 실행 전 확인
- 상태별 작업과 개수 표시
- 진행중 작업 자동 갱신
- 완료 결과, 실패 원인과 재시도 동작 제공
- 데스크톱 4열, 태블릿 2열, 모바일 1열의 반응형 보드 제공
- 터치 환경에서 카드 관리 동작을 항상 노출하고 작은 화면에서 작성 서랍과 실행
  대화상자를 뷰포트 안에 배치

**백엔드 API**

- 요청 스키마와 페이지 범위 검증
- 허용된 상태 전이만 처리
- 실행 요청을 백그라운드 작업으로 전달
- 도메인 오류를 HTTP 상태 코드로 변환

**에이전트 하네스**

- Planner, Executor, Reviewer 역할별 `GitHubCopilotAgent` 생명주기 관리
- 서버 설정으로 모델, 타임아웃, 로그 수준 구성
- 각 프롬프트 실행을 독립된 Copilot 세션에서 처리
- `run(..., stream=True)`로 응답 스트림을 수집하고 최종 응답을 저장
- 단계 이벤트와 Executor 응답 조각을 SSE로 전달
- SDK 시작·실행 오류, 시간 초과와 빈 응답을 재시도한 뒤 실패로 변환
- JSON 출력은 파싱 후 정규화하고, 잘못된 JSON은 실패로 처리
- 실행 취소는 프로세스 로컬 코디네이터가 추적하고, 서버 재시작 시 안전하게 정리

**저장소**

- 프롬프트, 실행 상태, 결과와 오류 저장
- 원자적 조건부 업데이트로 중복 실행 방지
- 상태별 페이지 조회
- 서버 시작 시 중단 실행 복구

## 3. 에이전트 하네스

### 필수 기술 연결

하네스는 Microsoft Agent Framework의 `GitHubCopilotAgent`를 사용하며, 필요하면
GitHub 토큰으로 생성한 Copilot SDK `CopilotClient`를 주입한다.

```text
PromptService
  → PromptOrchestrator
      ├─ PlannerAgent
      ├─ ExecutorAgent
      └─ ReviewerAgent
           → CopilotAgentService
               → GitHubCopilotAgent
                   → CopilotClient
```

### 실행 생명주기

1. Planner가 요청을 구조화된 계획으로 변환한다.
2. Executor가 독립 세션에서 계획을 실행하며 응답 조각을 스트리밍한다.
3. Reviewer가 구조화된 판정으로 결과와 수용 기준을 검증한다.
4. `REVISE` 판정이면 피드백을 반영해 Executor를 최대 한 번 재실행한다.
5. 최종 결과와 단계 상태를 저장하고 SSE 구독자에게 종료 이벤트를 전달한다.
6. 각 Agent Framework 호출은 재시도와 백오프로 일시적 실패를 처리한다.
7. 종료 시 에이전트와 직접 생성한 SDK 클라이언트를 정리한다.

### 현재 의도

각 작업은 Planner, Executor, Reviewer의 제한된 순차 오케스트레이션을 사용한다.
Reviewer 피드백 루프는 최대 한 번으로 제한하며, 서로 다른 작업은 독립 세션과
이벤트 채널을 사용해 병렬 실행한다.

### 확장 방향

- 작업별 Copilot 세션 ID 저장 및 후속 요청
- 작업 의존성 기반 순차·병렬 오케스트레이션
- 허용 목록 기반 읽기 전용 도구 호출
- 취소, 타임아웃과 재시도 정책의 세분화

확장 기능은 실제 구현 전까지 현재 기능으로 간주하지 않는다.

## 4. 작업 상태 머신

```text
draft ──execute──> running ──success──> completed
  ▲                    │
  │                    └──failure/interruption──> failed
  │                                                │
  └────────────── edit/retry preparation ──────────┘
```

| 현재 상태 | 허용 작업 |
|---|---|
| `draft` | 수정, 삭제, 실행 |
| `running` | 상태 조회 |
| `completed` | 결과 조회 |
| `failed` | 수정, 삭제, 재실행 |

`draft` 또는 `failed` 상태인 행만 조건부로 `running`으로 변경한다. 동시에 같은
작업을 실행하려는 요청 중 하나만 성공하고 나머지는 `409 Conflict`를 받는다.

서버 시작 시 남아 있는 `running` 작업은 자동 실행하지 않고 `failed`로 변경한다.
사용자는 중단 안내를 확인한 뒤 명시적으로 재실행한다.

## 5. 데이터 모델

```text
prompts
  id             CHAR(36) PK
  title          VARCHAR(80)
  prompt         TEXT
  output_format  VARCHAR(20)
  status         VARCHAR(20)
  output         LONGTEXT NULL
  error_message  TEXT NULL
  created_at     BIGINT
  updated_at     BIGINT
  started_at     BIGINT NULL
  completed_at   BIGINT NULL
```

`(status, updated_at DESC)` 인덱스로 상태별 최신 작업 조회를 지원한다.

데이터베이스 열은 `snake_case`를 사용하고 API JSON은 Pydantic alias generator를 통해
`camelCase`로 직렬화한다.

## 6. API 계약

| Method | Path | 동작 |
|---|---|---|
| `GET` | `/api/health` | 애플리케이션 상태 확인 |
| `GET` | `/api/prompts/board?pageSize=20` | 상태별 첫 페이지 조회 |
| `GET` | `/api/prompts?status=...&page=1&pageSize=20` | 상태별 페이지 조회 |
| `POST` | `/api/prompts` | 미실행 프롬프트 생성 |
| `PATCH` | `/api/prompts/{id}` | 미실행·실패 프롬프트 수정 |
| `DELETE` | `/api/prompts/{id}` | 미실행·실패 프롬프트 삭제 |
| `POST` | `/api/prompts/{id}/execute` | 실행을 예약하고 `202` 반환 |
| `POST` | `/api/prompts/{id}/cancel` | 진행중 실행을 취소하고 상태를 갱신 |
| `GET` | `/api/prompts/{id}/events` | 에이전트 단계와 Executor 응답을 SSE로 전달 |

### 입력 제약

- 제목: 공백 제거 후 1~80자
- 프롬프트: 공백 제거 후 1~4,000자
- 출력 형식 `outputFormat`: `markdown`, `plainText`, `json`이며 생략 시 `markdown`
- 알 수 없는 필드: 거부
- 페이지 크기: 1~100

클라이언트는 모델명을 전달할 수 없다. 모델은 서버의
`GITHUB_COPILOT_MODEL` 설정으로만 선택한다.

### JSON 응답 계약

- 모든 복합 필드는 `outputFormat`, `errorMessage`, `createdAt`, `updatedAt`,
  `startedAt`, `completedAt`, `pageSize`, `totalPages`, `hasNext`처럼
  `camelCase`로 반환한다.
- `output`, `errorMessage`, `startedAt`, `completedAt`은 응답 객체에 항상 존재하며
  값이 없으면 `null`이다.
- 유효성 검증 실패의 `detail` 배열과 도메인 오류의 문자열 `detail`을 프론트엔드가
  모두 사용자 메시지로 변환한다.

## 7. 동시 실행과 일관성

- 프롬프트 상태 변경은 `WHERE id = ? AND status IN (...)` 조건으로 수행한다.
- 영향받은 행이 없으면 존재 여부를 확인해 `404`와 `409`를 구분한다.
- 각 데이터베이스 작업은 성공 시 커밋하고 예외 시 롤백한다.
- 프론트엔드는 작업별 SSE를 구독하고, 연결 실패 시 2초 간격 보드 조회를 복구
  경로로 유지한다.
- 상태별 추가 페이지를 불러올 때 기존 항목과 새 항목을 병합한다.

## 8. 오류 처리

| 상황 | 처리 |
|---|---|
| 존재하지 않는 작업 | `404 Not Found` |
| 허용되지 않은 상태 변경 | `409 Conflict` |
| 잘못된 입력 | `422 Unprocessable Entity` |
| Agent Framework 시작·실행 실패 | 재시도 후 작업을 `failed`로 저장 |
| 타임아웃 | 재시도 후 작업을 `failed`로 저장 |
| 빈 Copilot 응답 | 재시도 후 작업을 `failed`로 저장 |
| 잘못된 JSON 응답 | 작업을 `failed`로 저장 |
| 실행 취소 | 작업을 `failed`로 저장하고 취소 사유를 남김 |
| 예상하지 못한 실행 오류 | 내부 로그 기록 후 일반화된 오류 저장 |
| 서버 재시작 중 실행 중단 | 시작 시 `failed`로 복구 |

프론트엔드는 보드 조회 오류와 폼 저장 오류를 사용자에게 표시하고 다시 시도할 수
있게 한다.

## 9. 보안과 책임 있는 AI

- GitHub 토큰과 데이터베이스 비밀번호는 `SecretStr` 환경 변수로 읽는다.
- `.env`와 가상환경은 Git에서 제외한다.
- 모델 선택은 서버 설정으로 제한한다.
- CORS 허용 출처는 설정된 프론트엔드 한 곳으로 제한한다.
- 실행 전 확인 화면에서 프롬프트와 출력 형식을 다시 보여준다.
- 완료 화면에서 결과가 Copilot 응답임을 표시한다.
- 현재 하네스는 파일, 셸, URL 도구를 등록하지 않는다.
- 데이터베이스에는 프롬프트와 AI 결과가 저장되므로 운영 환경에서 접근 제어,
  보존 기간과 삭제 정책을 별도로 설정해야 한다.

## 10. Azure 배포

```text
GitHub Actions
  ├─ frontend/backend Docker image build
  ├─ Docker Hub에 commit SHA 및 latest 태그 push
  └─ Azure VM SSH deployment
       ├─ 전용 Docker network 생성 및 MySQL 연결
       ├─ backend/frontend 컨테이너 교체
       ├─ backend에 DB·Copilot 환경 변수 주입
       └─ /api/health verification
```

필요한 GitHub Actions 저장소 시크릿:

- `AZURE_HOST`
- `AZURE_SSH_USER`
- `AZURE_SSH_PRIVATE_KEY`
- `DOCKER_USERNAME`
- `DOCKER_TOKEN`
- `DB_PASSWORD`
- `COPILOT_TOKEN`

워크플로는 `COPILOT_TOKEN`을 백엔드 컨테이너의 `GITHUB_COPILOT_TOKEN`으로
전달한다. 프론트엔드는 Vite preview 서버의 `/api` 프록시를 통해 Docker network의
`backend:8000`으로 요청한다. 배포 성공의 완료 조건은 새 컨테이너가 기동되고 Azure
VM 내부의 `http://127.0.0.1/api/health` 요청이 성공하는 것이다.

## 11. 테스트 전략

### 현재 자동 검증

- 프론트엔드 TypeScript 컴파일과 Vite 프로덕션 빌드
- 상태 확인 API
- MySQL 스키마 초기화의 멱등성
- 프롬프트 생성, 조회, 수정, 삭제
- 클라이언트 모델 선택 거부
- 성공·실패 실행 결과 저장
- 스트리밍 응답 수집, 재시도와 fallback 모델 선택
- JSON 출력 검증
- 실행 취소
- 동시 실행 충돌
- 서버 재시작 후 중단 작업 복구
- 상태별 페이지 조회
- 에이전트 인스턴스 재사용과 세션 생성

### 추가가 필요한 검증

- 실제 Copilot SDK를 사용한 배포 환경 통합 테스트
- 프론트엔드 상태 및 사용자 흐름 테스트
- 모바일 뷰포트와 키보드 접근성 테스트
- 프롬프트 인젝션과 민감정보 노출 테스트
- Azure 배포 후 외부 엔드투엔드 점검

## 12. PRD 요구사항 추적

| PRD 요구사항 | 구현 위치 | 검증 |
|---|---|---|
| 프롬프트 등록·관리 | `schemas/prompt.py`, `api/prompts.py` | CRUD API 테스트 |
| 실행 전 확인 | `App.tsx` | 프론트엔드 테스트 추가 필요 |
| Agent Framework 실행 | `services/agent.py` | 에이전트 서비스 테스트 |
| 상태 추적 | `repositories/prompts.py`, `usePromptBoard.ts` | API 테스트 |
| camelCase API 계약 | `schemas/prompt.py`, `api.ts`, `types.ts` | CRUD·페이지 API 테스트 |
| 결과와 실패 보관 | `services/prompts.py` | 성공·실패 테스트 |
| 중복 실행 방지 | `repositories/prompts.py` | 동시 실행 테스트 |
| 중단 복구 | `main.py`, `repositories/prompts.py` | 복구 테스트 |
| 페이지 조회 | `repositories/prompts.py`, `usePromptBoard.ts` | 페이지 테스트 |
| 반응형 UI | `styles.css`, `App.tsx` | 뷰포트·접근성 테스트 추가 필요 |
| Azure 배포 | `.github/workflows/deploy.yml`, `frontend/vite.config.ts` | 배포 성공 기록 필요 |

## 13. 완료 정의

- `npm run check`가 필요한 환경 변수를 포함한 문서화된 환경에서 성공한다.
- 실제 Copilot 요청이 완료되어 결과가 보드에 저장된다.
- 여러 작업의 상태가 보드에서 정확히 갱신된다.
- 동일 작업 중복 실행이 차단된다.
- 실패와 서버 중단 후 사용자가 작업을 재실행할 수 있다.
- 모바일에서 작성, 실행, 결과 확인이 가능하다.
- GitHub Actions의 Azure 배포와 상태 확인이 성공한다.
