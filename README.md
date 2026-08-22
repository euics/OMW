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

프로덕션에서는 Azure ingress에서 TLS를 반드시 종료하고 HTTPS만 외부에 노출해야
합니다. 애플리케이션의 보안 응답 헤더는 TLS를 대신하지 않습니다.

과거 `SHARED_FILES.md`에 커밋된 self-hosted runner 등록 토큰은 이 변경에서 Git
히스토리를 다시 쓰지 않으므로 GitHub에서 반드시 폐기(revoke)하고 새 토큰을
발급해야 합니다. 문서에는 이제 환경 변수 자리표시자만 포함됩니다.

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
동시에 공급자로 전달되는 요청 수는
`GITHUB_COPILOT_MAX_CONCURRENT_EXECUTIONS`(기본값 `4`, 최소 `1`)로 제한되며,
한도를 초과한 실행은 실패하지 않고 실행 슬롯이 빌 때까지 대기합니다.
로그인·사용자 테이블·소유자 필드는 없으며, 파일·셸·URL 도구 권한은 API
서버에서 기본적으로 거부됩니다.

## 확인 명령

```bash
npm run check
npm --prefix frontend run test:e2e
npm run --silent benchmark
```

E2E 테스트는 Playwright가 API 응답을 가로채 UI 계약만 검증하며 실제 Copilot을 호출하지 않습니다.

### 자동화 워크플로 벤치마크

`npm run benchmark`는 기존 Playwright API mock helper로 고정된 5개 작업
(미실행 2, 진행중 1, 완료 1, 실패 1)을 로드합니다. 보드 준비, 상태 요약과 완료 결과
발견, 실패 작업 재시도(클릭 수와 경과 시간), 외부 창 전환 수를 단일 JSON으로
출력합니다. 시간은 로컬 브라우저의 자동화 단계별 wall-clock 측정값입니다. 이는
재현 가능한 **자동화 워크플로 벤치마크**이며 사용자 연구, 사용자 생산성 주장,
실제 Copilot 호출 또는 라이브 Copilot 지연 시간 측정이 아닙니다.
