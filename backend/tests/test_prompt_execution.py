from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from app.schemas.orchestration import OrchestrationPlan, ReviewerReview, ReviewerVerdict
from app.schemas.prompt import (
    OutputFormat,
    PromptEventStage,
    PromptEventType,
    PromptRead,
    PromptStatus,
    PromptStreamEvent,
)
from app.services.agent import AgentResult, CopilotAgentService
from app.services.execution import PromptExecutionCoordinator
from app.services.orchestration import (
    PromptOrchestrationError,
    PromptOrchestrationService,
)
from app.services.prompt_events import (
    PromptEventBus,
    completed_event,
    get_prompt_event_bus,
    stage_event,
)
from app.services.prompts import PromptService


def _prompt(prompt_id: str = "prompt-1") -> PromptRead:
    return PromptRead.model_validate(
        {
            "id": prompt_id,
            "title": "실행 테스트",
            "prompt": "간단히 답해 줘.",
            "outputFormat": OutputFormat.MARKDOWN,
            "status": PromptStatus.DRAFT,
            "output": None,
            "errorMessage": None,
            "createdAt": 1,
            "updatedAt": 1,
            "startedAt": None,
            "completedAt": None,
        }
    )


class InMemoryPromptRepository:
    def __init__(self, prompt: PromptRead) -> None:
        self._prompt = prompt

    def get(self, prompt_id: str) -> PromptRead:
        assert prompt_id == self._prompt.id
        return self._prompt

    def mark_running(self, prompt_id: str) -> PromptRead:
        assert prompt_id == self._prompt.id
        self._prompt = self._prompt.model_copy(
            update={
                "status": PromptStatus.RUNNING,
                "output": None,
                "error_message": None,
                "started_at": 1,
                "completed_at": None,
            }
        )
        return self._prompt

    def mark_completed(self, prompt_id: str, *, output: str) -> PromptRead:
        assert prompt_id == self._prompt.id
        self._prompt = self._prompt.model_copy(
            update={
                "status": PromptStatus.COMPLETED,
                "output": output,
                "error_message": None,
                "completed_at": 2,
            }
        )
        return self._prompt

    def mark_failed(self, prompt_id: str, error_message: str) -> PromptRead:
        assert prompt_id == self._prompt.id
        self._prompt = self._prompt.model_copy(
            update={
                "status": PromptStatus.FAILED,
                "output": None,
                "error_message": error_message,
                "started_at": None,
                "completed_at": None,
            }
        )
        return self._prompt


@dataclass
class ScriptedReply:
    reply: str
    chunks: list[str] = field(default_factory=list)


class ScriptedAgent:
    def __init__(self, scripted_responses: list[object]) -> None:
        self._scripted_responses = list(scripted_responses)
        self.calls: list[dict[str, object]] = []

    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat | str = OutputFormat.MARKDOWN,
        on_update=None,
    ) -> AgentResult:
        self.calls.append({"message": message, "output_format": output_format})
        if not self._scripted_responses:
            raise AssertionError("No scripted response available")
        response = self._scripted_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, ScriptedReply)
        for chunk in response.chunks:
            if on_update is None:
                continue
            callback_result = on_update(chunk)
            if inspect.isawaitable(callback_result):
                await callback_result
        return AgentResult(reply=response.reply)


class BlockingOrchestrationService:
    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def execute(self, prompt: PromptRead, *, emit_event=None) -> str:
        if emit_event is not None:
            result = emit_event(stage_event(PromptEventStage.EXECUTOR, "작업을 시작합니다."))
            if inspect.isawaitable(result):
                await result
        self.started.set()
        await asyncio.Event().wait()
        return "never reached"

    async def close(self) -> None:
        return None


def test_structured_plan_and_verdict_validation() -> None:
    plan = OrchestrationPlan.model_validate_json(
        """
        {
          "objective": "간단한 작업을 수행한다.",
          "steps": ["1단계", "2단계"],
          "acceptanceCriteria": ["결과가 비어 있지 않다."]
        }
        """
    )
    review = ReviewerReview.model_validate_json(
        """
        {
          "verdict": "PASS",
          "feedback": "승인"
        }
        """
    )

    assert plan.objective == "간단한 작업을 수행한다."
    assert plan.acceptance_criteria == ["결과가 비어 있지 않다."]
    assert review.verdict == ReviewerVerdict.PASS

    with pytest.raises(ValidationError):
        OrchestrationPlan.model_validate_json(
            """
            {
              "objective": " ",
              "steps": [],
              "acceptanceCriteria": [""]
            }
            """
        )

    with pytest.raises(ValidationError):
        ReviewerReview.model_validate_json(
            """
            {
              "verdict": "MAYBE",
              "feedback": "보류"
            }
            """
        )


def test_orchestration_retries_executor_once_after_revision() -> None:
    async def exercise() -> None:
        prompt = _prompt()
        planner = ScriptedAgent(
            [
                ScriptedReply(
                    reply=(
                        '{"objective":"요청을 처리한다.","steps":["검토","실행"],'
                        '"acceptanceCriteria":["결과가 반환된다."]}'
                    )
                )
            ]
        )
        executor = ScriptedAgent(
            [
                ScriptedReply(reply="초안"),
                ScriptedReply(reply="최종본"),
            ]
        )
        reviewer = ScriptedAgent(
            [
                ScriptedReply(reply='{"verdict":"REVISE","feedback":"더 간결하게"}'),
                ScriptedReply(reply='{"verdict":"PASS","feedback":"승인"}'),
            ]
        )
        service = PromptOrchestrationService(
            planner_service=planner,
            executor_service=executor,
            reviewer_service=reviewer,
        )

        result = await service.execute(prompt)
        await service.close()

        assert result == "최종본"
        assert len(planner.calls) == 1
        assert len(executor.calls) == 2
        assert len(reviewer.calls) == 2
        assert "더 간결하게" in str(executor.calls[1]["message"])

    asyncio.run(exercise())


def test_orchestration_fails_closed_after_second_revision_request() -> None:
    async def exercise() -> None:
        prompt = _prompt()
        planner = ScriptedAgent(
            [
                ScriptedReply(
                    reply=(
                        '{"objective":"요청을 처리한다.","steps":["검토","실행"],'
                        '"acceptanceCriteria":["결과가 반환된다."]}'
                    )
                )
            ]
        )
        executor = ScriptedAgent(
            [
                ScriptedReply(reply="초안"),
                ScriptedReply(reply="수정본"),
            ]
        )
        reviewer = ScriptedAgent(
            [
                ScriptedReply(reply='{"verdict":"REVISE","feedback":"더 간결하게"}'),
                ScriptedReply(reply='{"verdict":"REVISE","feedback":"아직 길다"}'),
            ]
        )
        service = PromptOrchestrationService(
            planner_service=planner,
            executor_service=executor,
            reviewer_service=reviewer,
        )

        with pytest.raises(PromptOrchestrationError, match="아직 길다"):
            await service.execute(prompt)
        await service.close()

        assert len(executor.calls) == 2
        assert len(reviewer.calls) == 2

    asyncio.run(exercise())


def test_prompt_event_bus_isolates_subscribers_and_terminates() -> None:
    async def exercise() -> None:
        bus = PromptEventBus()
        prompt_one = "prompt-one"
        prompt_two = "prompt-two"
        queue_one = await bus.subscribe(prompt_one)
        queue_two = await bus.subscribe(prompt_two)

        await bus.publish(prompt_one, stage_event(PromptEventStage.PLANNER, "계획 중"))
        await bus.publish(prompt_one, completed_event("완료"))

        first = await asyncio.wait_for(queue_one.get(), timeout=1)
        second = await asyncio.wait_for(queue_one.get(), timeout=1)
        terminal = await asyncio.wait_for(queue_one.get(), timeout=1)

        assert first.type == PromptEventType.STAGE
        assert second.type == PromptEventType.COMPLETED
        assert terminal is None
        assert queue_two.empty()

        await bus.unsubscribe(prompt_one, queue_one)
        await bus.unsubscribe(prompt_two, queue_two)
        await bus.close()

    asyncio.run(exercise())


def test_prompt_event_bus_replays_events_to_late_subscriber() -> None:
    async def exercise() -> None:
        bus = PromptEventBus()
        prompt_id = "late-subscriber"

        await bus.publish(
            prompt_id,
            stage_event(PromptEventStage.PLANNER, "계획 중"),
        )
        queue = await bus.subscribe(prompt_id)

        event = await asyncio.wait_for(queue.get(), timeout=1)

        assert event is not None
        assert event.type == PromptEventType.STAGE
        assert event.stage == PromptEventStage.PLANNER
        await bus.unsubscribe(prompt_id, queue)
        await bus.close()

    asyncio.run(exercise())


def test_executor_chunks_are_forwarded_to_callback() -> None:
    async def exercise() -> None:
        class FakeSession:
            pass

        class FakeStreamUpdate:
            def __init__(self, text: str) -> None:
                self.text = text

        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

        class FakeResponseStream:
            def __init__(self, updates: list[str], final_text: str) -> None:
                self._updates = updates
                self._final_text = final_text

            def __aiter__(self):
                async def iterator():
                    for update in self._updates:
                        yield FakeStreamUpdate(update)

                return iterator()

            async def get_final_response(self) -> FakeResponse:
                return FakeResponse(self._final_text)

        class ProgrammableAgent:
            def __init__(self, scripted_responses: list[object]) -> None:
                self._scripted_responses = list(scripted_responses)
                self.start_count = 0
                self.stop_count = 0
                self.calls: list[dict[str, object]] = []

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
                assert stream is True
                assert session is not None
                self.calls.append(
                    {
                        "message": message,
                        "stream": stream,
                        "session": session,
                        "options": options,
                    }
                )
                response = self._scripted_responses.pop(0)
                assert isinstance(response, FakeResponseStream)
                return response

        stream = ProgrammableAgent([FakeResponseStream(["중간", "응답"], "최종 응답")])
        service = CopilotAgentService(
            model="auto",
            timeout=30,
            log_level="info",
            instructions="Be concise.",
            agent=stream,
        )
        chunks: list[str] = []

        result = await service.reply(
            "스트리밍 요청",
            on_update=chunks.append,
        )
        await service.close()

        assert result.reply == "최종 응답"
        assert chunks == ["중간", "응답"]

    asyncio.run(exercise())


def test_prompt_cancellation_emits_cancelled_event() -> None:
    async def exercise() -> None:
        prompt = _prompt("prompt-cancel")
        repository = InMemoryPromptRepository(prompt)
        started = asyncio.Event()
        service = PromptService(
            repository=repository,
            orchestration_service=BlockingOrchestrationService(started),
            execution_coordinator=PromptExecutionCoordinator(),
        )
        bus = get_prompt_event_bus()
        queue = await bus.subscribe(prompt.id)

        await service.start_execution(prompt.id)
        await asyncio.wait_for(started.wait(), timeout=1)

        cancelled_prompt = await service.cancel_execution(prompt.id)

        events: list[PromptStreamEvent | None] = []
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=1)
            events.append(event)
            if event is None or event.type == PromptEventType.CANCELLED:
                break

        assert any(event and event.type == PromptEventType.CANCELLED for event in events)
        assert cancelled_prompt.status == PromptStatus.FAILED
        assert "취소" in (cancelled_prompt.error_message or "")

        await bus.unsubscribe(prompt.id, queue)
        await service.close()

    asyncio.run(exercise())
