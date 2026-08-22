import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_framework.exceptions import AgentException

from app.services.agent import (
    AgentFailureCategory,
    AgentServiceError,
    AgentServiceProvider,
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


class BlockingCopilotAgent(FakeCopilotAgent):
    def __init__(self, expected_concurrency: int) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0
        self.capacity_reached = asyncio.Event()
        self.release = asyncio.Event()
        self.expected_concurrency = expected_concurrency

    async def run(
        self,
        message: str,
        *,
        session: FakeSession,
    ) -> FakeResponse:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active == self.expected_concurrency:
            self.capacity_reached.set()
        await self.release.wait()
        self.active -= 1
        return FakeResponse()


def test_agent_service_provider_constructs_one_instance_concurrently() -> None:
    callers = 8
    ready = threading.Barrier(callers)
    construction_count = 0
    construction_lock = threading.Lock()

    def factory() -> CopilotAgentService:
        nonlocal construction_count
        with construction_lock:
            construction_count += 1
        return CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=FakeCopilotAgent(),
        )

    provider = AgentServiceProvider(factory=factory)

    def get_service() -> CopilotAgentService:
        ready.wait()
        return provider.get()

    with ThreadPoolExecutor(max_workers=callers) as executor:
        instances = list(executor.map(lambda _: get_service(), range(callers)))

    assert construction_count == 1
    assert all(instance is instances[0] for instance in instances)


def test_agent_service_provider_rejects_get_during_close() -> None:
    class PausingLock:
        def __init__(self) -> None:
            self._lock = threading.Lock()
            self.close_has_lock = threading.Event()
            self.get_attempted_lock = threading.Event()
            self.allow_close = threading.Event()

        def __enter__(self) -> None:
            if threading.current_thread().name == "provider-close":
                self._lock.acquire()
                self.close_has_lock.set()
                self.allow_close.wait()
            else:
                self.get_attempted_lock.set()
                self._lock.acquire()

        def __exit__(self, *args: object) -> None:
            self._lock.release()

    service = CopilotAgentService(
        model="auto",
        timeout=30,
        log_level="info",
        instructions="Be concise.",
        agent=FakeCopilotAgent(),
    )
    provider = AgentServiceProvider(factory=lambda: service)
    assert provider.get() is service

    lock = PausingLock()
    provider._lock = lock
    close_thread = threading.Thread(
        target=lambda: asyncio.run(provider.close()),
        name="provider-close",
    )
    close_thread.start()
    assert lock.close_has_lock.wait(timeout=1)

    with ThreadPoolExecutor(max_workers=1) as executor:
        get_result = executor.submit(provider.get)
        attempted_lock = lock.get_attempted_lock.wait(timeout=1)
        lock.allow_close.set()
        close_thread.join(timeout=1)

        assert attempted_lock
        assert not close_thread.is_alive()
        with pytest.raises(RuntimeError, match="provider is closed"):
            get_result.result(timeout=1)


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


def test_copilot_service_queues_work_above_concurrency_cap() -> None:
    async def exercise() -> None:
        fake_agent = BlockingCopilotAgent(expected_concurrency=2)
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
            max_concurrent_executions=2,
        )

        requests = [
            asyncio.create_task(service.reply(f"request {index}"))
            for index in range(3)
        ]
        await asyncio.wait_for(fake_agent.capacity_reached.wait(), timeout=1)
        await asyncio.sleep(0)

        assert fake_agent.active == 2
        assert sum(request.done() for request in requests) == 0

        fake_agent.release.set()
        results = await asyncio.gather(*requests)

        assert fake_agent.max_active == 2
        assert [result.reply for result in results] == [FakeResponse.text] * 3

    asyncio.run(exercise())
