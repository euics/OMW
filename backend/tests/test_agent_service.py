import asyncio

import pytest
from agent_framework.exceptions import AgentException

from app.services.agent import (
    AgentFailureCategory,
    AgentServiceError,
    CopilotAgentService,
)


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


class SequencedCopilotAgent(FakeCopilotAgent):
    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        super().__init__()
        self.outcomes = outcomes
        self.run_count = 0

    async def run(
        self,
        message: str,
        *,
        session: FakeSession,
    ) -> FakeResponse:
        outcome = self.outcomes[self.run_count]
        self.run_count += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


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


def test_copilot_service_retries_timeout_once() -> None:
    async def exercise() -> None:
        fake_agent = SequencedCopilotAgent(
            [asyncio.TimeoutError("secret timeout details"), FakeResponse()]
        )
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
            retry_delay=0,
        )

        result = await service.reply("retry me")

        assert result.reply == FakeResponse.text
        assert fake_agent.run_count == 2

    asyncio.run(exercise())


def test_copilot_service_does_not_retry_authentication_failure() -> None:
    async def exercise() -> None:
        fake_agent = SequencedCopilotAgent(
            [AgentException("401 unauthorized: secret-token")]
        )
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
            retry_delay=0,
        )

        with pytest.raises(AgentServiceError) as caught:
            await service.reply("do not retry")

        assert caught.value.category is AgentFailureCategory.AUTHENTICATION
        assert "secret-token" not in str(caught.value)
        assert fake_agent.run_count == 1

    asyncio.run(exercise())
