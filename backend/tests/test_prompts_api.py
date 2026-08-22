from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Database
from app.main import app
from app.repositories.prompts import PromptRepository, PromptStateConflictError
from app.schemas.prompt import PromptCreate
from app.services.agent import AgentResult
from app.services.prompts import PromptService, get_prompt_service


class StubPromptAgent:
    async def reply(
        self,
        message: str,
        thread_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            reply="요청된 프롬프트의 실행 결과입니다.",
            thread_id="prompt-thread",
            provider="test",
        )


def create_test_client(
    database_path: Path,
) -> tuple[TestClient, PromptService, PromptRepository]:
    database = Database(database_path)
    database.initialize()
    repository = PromptRepository(database)
    service = PromptService(
        repository=repository,
        agent_service=StubPromptAgent(),
    )
    app.dependency_overrides[get_prompt_service] = lambda: service
    return TestClient(app), service, repository


def test_prompt_crud_without_user_data(tmp_path: Path) -> None:
    client, _, _ = create_test_client(tmp_path / "prompts.db")
    create_response = client.post(
        "/api/prompts",
        json={
            "title": "고객 피드백 요약",
            "prompt": "피드백의 핵심 이슈를 세 줄로 요약해 줘.",
            "model": "auto",
            "outputFormat": "markdown",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "draft"
    assert "userId" not in created

    list_response = client.get("/api/prompts")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    update_response = client.patch(
        f"/api/prompts/{created['id']}",
        json={
            "title": "수정된 요약",
            "prompt": "핵심 이슈를 다섯 줄로 요약해 줘.",
            "model": "gpt-5.6-sol",
            "outputFormat": "plainText",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "수정된 요약"

    delete_response = client.delete(f"/api/prompts/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/prompts").json() == []


def test_execute_prompt_persists_completed_response(tmp_path: Path) -> None:
    client, _, _ = create_test_client(tmp_path / "execute.db")
    created = client.post(
        "/api/prompts",
        json={
            "title": "실행 테스트",
            "prompt": "간단히 답해 줘.",
            "model": "auto",
            "outputFormat": "markdown",
        },
    ).json()

    execute_response = client.post(f"/api/prompts/{created['id']}/execute")

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "running"
    assert execute_response.json()["executionState"] == "requesting"

    stored = client.get("/api/prompts").json()[0]
    assert stored["status"] == "completed"
    assert stored["executionState"] == "succeeded"
    assert stored["output"] == "요청된 프롬프트의 실행 결과입니다."

    conflict_response = client.patch(
        f"/api/prompts/{created['id']}",
        json={
            "title": "수정 불가",
            "prompt": "완료 후에는 수정할 수 없어야 한다.",
            "model": "auto",
            "outputFormat": "markdown",
        },
    )
    assert conflict_response.status_code == 409


def test_only_one_concurrent_execution_request_wins(tmp_path: Path) -> None:
    _, _, repository = create_test_client(tmp_path / "concurrent.db")
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
