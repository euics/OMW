import asyncio

from app.services.agent import CopilotAgentService


class FakeSession:
    def __init__(self, service_session_id: str | None = None) -> None:
        self.service_session_id = service_session_id


class FakeResponse:
    text = "간단한 Copilot 응답"


class FakeCopilotAgent:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0
        self.resumed_session_id: str | None = None

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    def create_session(self) -> FakeSession:
        return FakeSession()

    def get_session(self, *, service_session_id: str) -> FakeSession:
        self.resumed_session_id = service_session_id
        return FakeSession(service_session_id)

    async def run(
        self,
        message: str,
        *,
        session: FakeSession,
        options: object | None = None,
    ) -> FakeResponse:
        if session.service_session_id is None:
            session.service_session_id = "generated-session"
        return FakeResponse()


def test_copilot_service_creates_and_resumes_sessions() -> None:
    async def exercise() -> None:
        fake_agent = FakeCopilotAgent()
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
        )

        first = await service.reply("첫 번째 요청")
        second = await service.reply("이어서 요청", "existing-session")
        await service.close()

        assert first.thread_id == "generated-session"
        assert second.thread_id == "existing-session"
        assert second.reply == "간단한 Copilot 응답"
        assert fake_agent.resumed_session_id == "existing-session"
        assert fake_agent.start_count == 1
        assert fake_agent.stop_count == 1

    asyncio.run(exercise())
