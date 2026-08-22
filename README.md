# OnMyWay Prompt Operations

프롬프트 작성, 실행, 결과 보관 흐름을 한 화면에서 관리하는 웹 애플리케이션입니다.
로그인이나 사용자 구분 없이 하나의 워크스페이스로 동작합니다.

## 구성

```text
matdathon/
├── frontend/   # React + TypeScript + Vite
├── backend/    # FastAPI + SQLite + pytest
├── .env.example
└── package.json
```

개발 환경에서는 Vite가 `/api` 요청을 FastAPI(`http://localhost:8000`)로 프록시합니다.
프롬프트는 SQLite에 저장됩니다. 실행 요청은 Microsoft Agent Framework의 공식
GitHub Copilot 커넥터를 통해 GitHub Copilot SDK를 호출하며, FE는 진행중 항목이
있는 동안 API를 폴링해 완료 결과를 반영합니다.

## 시작하기

macOS/Linux 기준입니다. Node.js 20 이상과 Python 3.11 이상이 필요합니다.
GitHub Copilot CLI에 로그인된 계정 또는 SDK에서 지원하는 인증 환경이 필요합니다.

```bash
cp .env.example .env
npm run bootstrap
npm run dev
```

- 웹: http://localhost:5173
- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/api/health

## 프롬프트 API

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/prompts` | 전체 프롬프트 조회 |
| `POST` | `/api/prompts` | 미실행 프롬프트 생성 |
| `PATCH` | `/api/prompts/{id}` | 미실행 프롬프트 수정 |
| `DELETE` | `/api/prompts/{id}` | 미실행 프롬프트 삭제 |
| `POST` | `/api/prompts/{id}/execute` | 실행 요청 후 `202` 반환 |

```bash
curl http://localhost:8000/api/prompts \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "주간 피드백 요약",
    "prompt": "고객 피드백의 핵심 이슈를 세 줄로 요약해 줘.",
    "model": "auto",
    "outputFormat": "markdown"
  }'
```

모델과 타임아웃은 `.env`의 `GITHUB_COPILOT_MODEL`,
`GITHUB_COPILOT_TIMEOUT`으로 변경할 수 있습니다. 로그인·사용자 테이블·소유자
필드는 없으며, 파일·셸·URL 도구 권한은 API 서버에서 기본적으로 거부됩니다.

## 확인 명령

```bash
npm run check
```
