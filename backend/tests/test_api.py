from fastapi.testclient import TestClient

from app.main import app
from app.services.agent import AgentResult, get_agent_service


class StubAgentService:
    async def reply(
        self,
        message: str,
        thread_id: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            reply=f"Copilot response for: {message}",
            thread_id=thread_id or "new-copilot-thread",
            provider="microsoft-agent-framework/github-copilot-sdk",
        )


app.dependency_overrides[get_agent_service] = lambda: StubAgentService()
client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_creates_thread() -> None:
    response = client.post(
        "/api/agent/chat",
        json={"message": "프로젝트 계획을 세워줘"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"]
    assert body["provider"] == "microsoft-agent-framework/github-copilot-sdk"
    assert "프로젝트 계획" in body["reply"]


def test_chat_reuses_thread() -> None:
    response = client.post(
        "/api/agent/chat",
        json={"message": "계속해줘", "thread_id": "existing-thread"},
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == "existing-thread"
