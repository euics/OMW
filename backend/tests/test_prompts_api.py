from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient

from app.api import prompts as prompts_api
from app.database import Database
from app.main import app
from app.repositories.prompts import PromptRepository, PromptStateConflictError
from app.schemas.prompt import PromptCreate
from app.services.agent import AgentResult, AgentServiceError
from app.services.prompts import PromptService, get_prompt_service


class StubPromptAgent:
    async def reply(
        self,
        message: str,
        *,
        output_format=None,
    ) -> AgentResult:
        return AgentResult(reply="요청된 프롬프트의 실행 결과입니다.")


class FailingPromptAgent:
    async def reply(
        self,
        message: str,
        *,
        output_format=None,
    ) -> AgentResult:
        raise AgentServiceError("AI 요청에 실패했습니다.")


class InvalidJsonPromptAgent:
    async def reply(self, message: str) -> AgentResult:
        return AgentResult(reply="JSON 형식이 아닌 응답")


def create_test_client(
    database: Database,
    agent: StubPromptAgent | FailingPromptAgent | InvalidJsonPromptAgent | None = None,
) -> tuple[TestClient, PromptService, PromptRepository]:
    repository = PromptRepository(database)
    service = PromptService(
        repository=repository,
        agent_service=agent or StubPromptAgent(),
    )
    app.dependency_overrides[get_prompt_service] = lambda: service
    return TestClient(app), service, repository


def wait_for_prompt_status(
    client: TestClient,
    *,
    prompt_id: str,
    status: str,
    attempts: int = 20,
) -> dict[str, object]:
    for _ in range(attempts):
        response = client.get(f"/api/prompts?status={status}")
        assert response.status_code == 200
        items = response.json()["items"]
        for item in items:
            if item["id"] == prompt_id:
                return item
        time.sleep(0.05)
    raise AssertionError(f"Prompt {prompt_id} never reached status {status}")


def test_prompt_crud_without_user_data(database: Database) -> None:
    client, _, _ = create_test_client(database)
    create_response = client.post(
        "/api/prompts",
        json={
            "title": "고객 피드백 요약",
            "prompt": "피드백의 핵심 이슈를 세 줄로 요약해 줘.",
            "outputFormat": "markdown",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "draft"
    assert "userId" not in created

    list_response = client.get("/api/prompts?status=draft")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [created["id"]]

    update_response = client.patch(
        f"/api/prompts/{created['id']}",
        json={
            "title": "수정된 요약",
            "prompt": "핵심 이슈를 다섯 줄로 요약해 줘.",
            "outputFormat": "plainText",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "수정된 요약"

    delete_response = client.delete(f"/api/prompts/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/prompts?status=draft").json()["items"] == []


def test_client_cannot_select_ai_model(database: Database) -> None:
    client, _, _ = create_test_client(database)

    response = client.post(
        "/api/prompts",
        json={
            "title": "모델 선택 시도",
            "prompt": "모델은 백엔드가 선택해야 한다.",
            "model": "gpt-5.6-sol",
            "outputFormat": "markdown",
        },
    )

    assert response.status_code == 422


def test_execute_prompt_persists_completed_response(database: Database) -> None:
    client, _, _ = create_test_client(database)
    created = client.post(
        "/api/prompts",
        json={
            "title": "실행 테스트",
            "prompt": "간단히 답해 줘.",
            "outputFormat": "markdown",
        },
    ).json()

    execute_response = client.post(f"/api/prompts/{created['id']}/execute")

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "running"

    stored = wait_for_prompt_status(
        client,
        prompt_id=created["id"],
        status="completed",
    )
    assert stored["status"] == "completed"
    assert stored["output"] == "요청된 프롬프트의 실행 결과입니다."

    conflict_response = client.patch(
        f"/api/prompts/{created['id']}",
        json={
            "title": "수정 불가",
            "prompt": "완료 후에는 수정할 수 없어야 한다.",
            "outputFormat": "markdown",
        },
    )
    assert conflict_response.status_code == 409


def test_failed_execution_moves_prompt_to_failed(database: Database) -> None:
    client, _, _ = create_test_client(
        database,
        agent=FailingPromptAgent(),
    )
    created = client.post(
        "/api/prompts",
        json={
            "title": "실패 테스트",
            "prompt": "실패 상태를 저장해 줘.",
            "outputFormat": "markdown",
        },
    ).json()

    response = client.post(f"/api/prompts/{created['id']}/execute")

    assert response.status_code == 202
    stored = wait_for_prompt_status(
        client,
        prompt_id=created["id"],
        status="failed",
    )
    assert stored["status"] == "failed"
    assert stored["errorMessage"] == "AI 요청에 실패했습니다."

    retry_response = client.post(f"/api/prompts/{created['id']}/execute")
    assert retry_response.status_code == 202


def test_invalid_json_execution_moves_prompt_to_failed(database: Database) -> None:
    client, _, _ = create_test_client(
        database,
        agent=InvalidJsonPromptAgent(),
    )
    created = client.post(
        "/api/prompts",
        json={
            "title": "JSON 검증",
            "prompt": "JSON으로 답해 줘.",
            "outputFormat": "json",
        },
    ).json()

    response = client.post(f"/api/prompts/{created['id']}/execute")

    assert response.status_code == 202
    stored = client.get("/api/prompts?status=failed").json()["items"][0]
    assert stored["status"] == "failed"
    assert "유효한 JSON" in stored["errorMessage"]


def test_execute_prompt_is_rate_limited(database: Database) -> None:
    client, _, _ = create_test_client(database)
    prompts_api.execution_rate_limiter.reset()
    try:
        for _ in range(prompts_api.execution_rate_limiter.limit):
            response = client.post("/api/prompts/missing/execute")
            assert response.status_code == 404

        response = client.post("/api/prompts/missing/execute")

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
    finally:
        prompts_api.execution_rate_limiter.reset()


def test_only_one_concurrent_execution_request_wins(database: Database) -> None:
    _, _, repository = create_test_client(database)
    prompt = repository.create(
        PromptCreate(
            title="동시 실행",
            prompt="한 번만 실행되어야 한다.",
        )
    )

    def queue() -> str:
        try:
            repository.mark_running(prompt.id)
            return "running"
        except PromptStateConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: queue(), range(2)))

    assert sorted(results) == ["conflict", "running"]


def test_interrupted_execution_is_recovered_on_startup(database: Database) -> None:
    _, _, repository = create_test_client(database)
    prompt = repository.create(
        PromptCreate(
            title="중단 복구",
            prompt="서버 재시작 후 다시 실행할 수 있어야 한다.",
        )
    )
    repository.mark_running(prompt.id)

    recovered_count = repository.recover_interrupted()
    recovered = repository.get(prompt.id)

    assert recovered_count == 1
    assert recovered.status == "failed"
    assert recovered.started_at is None
    assert recovered.error_message


def test_board_and_status_list_are_paginated(database: Database) -> None:
    client, _, _ = create_test_client(database)
    for index in range(5):
        client.post(
            "/api/prompts",
            json={
                "title": f"페이지 테스트 {index}",
                "prompt": "페이지 단위로 조회되어야 한다.",
                "outputFormat": "markdown",
            },
        )

    first_page = client.get(
        "/api/prompts?status=draft&page=1&pageSize=2"
    ).json()
    second_page = client.get(
        "/api/prompts?status=draft&page=2&pageSize=2"
    ).json()
    board = client.get("/api/prompts/board?pageSize=2").json()

    assert len(first_page["items"]) == 2
    assert first_page["total"] == 5
    assert first_page["totalPages"] == 3
    assert first_page["hasNext"] is True
    assert len(second_page["items"]) == 2
    assert board["columns"]["draft"]["total"] == 5
    assert set(board["columns"]) == {"draft", "running", "completed", "failed"}
