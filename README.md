# OnMyWay Prompt Operations

프롬프트 작성, 실행, 결과 보관 흐름을 한 화면에서 관리하는 웹 애플리케이션입니다.
로그인이나 사용자 구분 없이 하나의 워크스페이스로 동작합니다.

## 구성

```text
matdathon/
├── frontend/   # React + TypeScript + Vite
├── backend/    # FastAPI + MySQL + pytest
├── .env.example
└── package.json
```

개발 환경에서는 Vite가 `/api` 요청을 FastAPI(`http://localhost:8000`)로 프록시합니다.
프롬프트는 MySQL 8에 저장됩니다. 실행 요청은 Microsoft Agent Framework의 공식
GitHub Copilot 커넥터를 통해 GitHub Copilot SDK를 호출하며, FE는 진행중 항목이
있는 동안 API를 폴링해 완료 결과를 반영합니다.

## 시작하기

macOS/Linux 기준입니다. Node.js 20 이상과 Python 3.11 이상, MySQL 8이 필요합니다.
GitHub Copilot CLI에 로그인된 계정 또는 SDK에서 지원하는 인증 환경이 필요합니다.

```bash
cp .env.example .env
# .env의 DATABASE_PASSWORD를 MySQL 사용자 비밀번호로 변경
npm run bootstrap
npm run dev
```

- 웹: http://localhost:5173
- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/api/health

## 배포

`main` 브랜치에 푸시하면 GitHub Actions가 FE/BE 이미지를 각각 Docker Hub에
게시한 뒤 Azure VM에서 이미지를 pull해 두 앱 컨테이너만 배포합니다. GitHub
저장소의 `Settings → Secrets and variables → Actions → Repository secrets`에
다음 시크릿을 등록해야 합니다.

- `AZURE_HOST`: Azure VM 공인 IP
- `AZURE_SSH_USER`: Azure VM SSH 사용자
- `AZURE_SSH_PRIVATE_KEY`: 해당 사용자의 SSH 개인 키
- `DOCKER_USERNAME`: Docker Hub 사용자명
- `DOCKER_TOKEN`: Docker Hub 액세스 토큰
- `DB_PASSWORD`: MySQL `omw` 사용자 비밀번호

Azure VM의 홈 디렉터리에는 `backend`, `frontend` 서비스와 기존 MySQL 연결 설정이
포함된 Compose 파일이 있어야 합니다. CI는 이 파일을 수정하지 않고 두 앱 이미지만
pull한 뒤 재기동합니다.

## 프롬프트 API

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/prompts/board?pageSize=20` | 상태별 첫 페이지 보드 조회 |
| `GET` | `/api/prompts?status=draft&page=1&pageSize=20` | 상태별 페이지 조회 |
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
    "outputFormat": "markdown"
  }'
```

AI 모델은 FE 요청과 분리되어 백엔드의 `GITHUB_COPILOT_MODEL=auto` 설정으로
자동 선택됩니다. 타임아웃은 `GITHUB_COPILOT_TIMEOUT`으로 변경할 수 있습니다.
로그인·사용자 테이블·소유자 필드는 없으며, 파일·셸·URL 도구 권한은 API
서버에서 기본적으로 거부됩니다.

## 확인 명령

```bash
npm run check
```
