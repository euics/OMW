from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

import pytest
from agent_framework.exceptions import AgentException

from app.schemas.prompt import OutputFormat
from app.services.agent import AgentServiceError, CopilotAgentService


class FakeSession:
    pass


@dataclass
class RecordedRun:
    message: str
    stream: bool
    options: dict[str, object] | None
    session: FakeSession


@dataclass
class FakeStreamUpdate:
    text: str


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeResponseStream:
    def __init__(self, updates: list[str], final_text: str) -> None:
        self._updates = updates
        self._final_text = final_text
        self.iterated = False
        self.finalized = False

    def __aiter__(self):
        async def iterator():
            self.iterated = True
            for update in self._updates:
                yield FakeStreamUpdate(text=update)

        return iterator()

    async def get_final_response(self) -> FakeResponse:
        self.finalized = True
        return FakeResponse(self._final_text)


class ProgrammableCopilotAgent:
    def __init__(self, scripted_responses: list[object]) -> None:
        self._scripted_responses = list(scripted_responses)
        self.start_count = 0
        self.stop_count = 0
        self.calls: list[RecordedRun] = []

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1

    def create_session(self) -> FakeSession:
        return FakeSession()

    def run(
        self,
        message: str,
        *,
        stream: bool = False,
        session: FakeSession | None = None,
        options: dict[str, object] | None = None,
    ) -> object:
        if session is None:
            raise AssertionError("session should always be provided")
        self.calls.append(
            RecordedRun(
                message=message,
                stream=stream,
                options=options,
                session=session,
            )
        )
        if not self._scripted_responses:
            raise AssertionError("No scripted response available")
        response = self._scripted_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_copilot_service_reuses_agent_and_creates_sessions() -> None:
    async def exercise() -> None:
        fake_agent = ProgrammableCopilotAgent(
            [
                FakeResponseStream([], "간단한 Copilot 응답"),
                FakeResponseStream([], "간단한 Copilot 응답"),
            ]
        )
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


def test_copilot_service_streams_and_collects_final_response() -> None:
    async def exercise() -> None:
        stream = FakeResponseStream(["중간", "응답"], "최종 응답")
        fake_agent = ProgrammableCopilotAgent([stream])
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
        )
        chunks: list[str] = []

        result = await service.reply("스트리밍 요청", on_update=chunks.append)
        await service.close()

        assert result.reply == "최종 응답"
        assert stream.iterated is True
        assert stream.finalized is True
        assert fake_agent.calls[0].stream is True
        assert fake_agent.calls[0].options == {"model": "auto"}
        assert chunks == ["중간", "응답"]

    asyncio.run(exercise())


def test_copilot_service_retries_empty_response_before_succeeding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        delays: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            delays.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        fake_agent = ProgrammableCopilotAgent(
            [
                FakeResponseStream([], " "),
                FakeResponseStream([], "복구된 응답"),
            ]
        )
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            retry_attempts=2,
            retry_backoff_seconds=0.01,
            retry_backoff_multiplier=2.0,
            retry_max_backoff_seconds=0.05,
            agent=fake_agent,
        )

        result = await service.reply("빈 응답 재시도")
        await service.close()

        assert result.reply == "복구된 응답"
        assert delays == [0.01]
        assert len(fake_agent.calls) == 2

    asyncio.run(exercise())


def test_copilot_service_uses_fallback_model_after_primary_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        delays: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            delays.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        fake_agent = ProgrammableCopilotAgent(
            [
                AgentException("primary failure"),
                TimeoutError(),
                FakeResponseStream([], "대체 모델 응답"),
            ]
        )
        service = CopilotAgentService(
            model="primary-model",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            retry_attempts=2,
            retry_backoff_seconds=0.02,
            retry_backoff_multiplier=2.0,
            retry_max_backoff_seconds=0.05,
            fallback_model="fallback-model",
            agent=fake_agent,
        )

        result = await service.reply("대체 모델 시도")
        await service.close()

        assert result.reply == "대체 모델 응답"
        assert delays == [0.02]
        assert [call.options["model"] for call in fake_agent.calls] == [
            "primary-model",
            "primary-model",
            "fallback-model",
        ]

    asyncio.run(exercise())


def test_copilot_service_validates_and_normalizes_json_output() -> None:
    async def exercise() -> None:
        fake_agent = ProgrammableCopilotAgent(
            [FakeResponseStream([], '{ "b": 2, "a": 1 }')]
        )
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
        )

        result = await service.reply("JSON 응답", output_format=OutputFormat.JSON)
        await service.close()

        assert result.reply == '{"b":2,"a":1}'
        assert json.loads(result.reply) == {"b": 2, "a": 1}

    asyncio.run(exercise())


def test_copilot_service_rejects_invalid_json_output() -> None:
    async def exercise() -> None:
        fake_agent = ProgrammableCopilotAgent(
            [
                FakeResponseStream([], "not-json"),
                FakeResponseStream([], "still-not-json"),
                FakeResponseStream([], "invalid-json"),
            ]
        )
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=fake_agent,
        )

        with pytest.raises(AgentServiceError, match="유효한 JSON"):
            await service.reply(
                "JSON 응답",
                output_format=OutputFormat.JSON,
            )
        assert len(fake_agent.calls) == 3
        await service.close()

    asyncio.run(exercise())


def test_real_copilot_service_smoke() -> None:
    token = os.getenv("GITHUB_COPILOT_INTEGRATION_TOKEN")
    if not token:
        pytest.skip("GITHUB_COPILOT_INTEGRATION_TOKEN is not set")

    async def exercise() -> None:
        service = CopilotAgentService(
            model=os.getenv("GITHUB_COPILOT_INTEGRATION_MODEL", "auto"),
            timeout=float(os.getenv("GITHUB_COPILOT_INTEGRATION_TIMEOUT", "60")),
            log_level=os.getenv("GITHUB_COPILOT_INTEGRATION_LOG_LEVEL", "info"),
            instructions="Keep the response concise.",
            token=token,
        )
        response = await service.reply("짧은 한국어 한 문장으로만 답해 주세요.")
        await service.close()

        assert response.reply.strip()

    asyncio.run(exercise())
