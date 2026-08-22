# Matdathon

React와 FastAPI를 한 저장소에서 함께 실행하는 AI 에이전트 웹 스타터입니다.

## 구성

```text
matdathon/
├── frontend/   # React + TypeScript + Vite
├── backend/    # FastAPI + pytest
├── .env.example
└── package.json
```

개발 환경에서는 Vite가 `/api` 요청을 FastAPI(`http://localhost:8000`)로 프록시합니다.
에이전트 API는 Microsoft Agent Framework의 공식 GitHub Copilot 커넥터를 통해
GitHub Copilot SDK를 호출합니다.

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

## Copilot API

`POST /api/agent/chat`은 Microsoft Agent Framework의 `GitHubCopilotAgent`를
사용합니다. 응답의 `thread_id`를 다음 요청에 전달하면 같은 대화를 이어갑니다.

```bash
curl http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"프롬프트 자동화 아이디어를 세 가지 알려줘"}'
```

```json
{
  "reply": "...",
  "thread_id": "...",
  "provider": "microsoft-agent-framework/github-copilot-sdk"
}
```

모델과 타임아웃은 `.env`의 `GITHUB_COPILOT_MODEL`,
`GITHUB_COPILOT_TIMEOUT`으로 변경할 수 있습니다. 파일·셸·URL 도구 권한은
API 서버에서 기본적으로 거부됩니다.

## 확인 명령

```bash
npm run check
```
