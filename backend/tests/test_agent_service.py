import asyncio

from app.services.agent import CopilotAgentService


class FakeSession:
    pass


class FakeResponse:
    text = "간단한 Copilot 응답"


class FakeCopilotAgent:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    def create_session(self) -> FakeSession:
        return FakeSession()

    async def run(
        self,
        message: str,
        *,
        session: FakeSession,
    ) -> FakeResponse:
        return FakeResponse()


def test_copilot_service_reuses_agent_and_creates_sessions() -> None:
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
        second = await service.reply("두 번째 요청")
        await service.close()

        assert first.reply == "간단한 Copilot 응답"
        assert second.reply == "간단한 Copilot 응답"
        assert fake_agent.start_count == 1
        assert fake_agent.stop_count == 1

    asyncio.run(exercise())
