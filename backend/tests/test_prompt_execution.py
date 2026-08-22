from __future__ import annotations

import asyncio

from app.schemas.prompt import OutputFormat, PromptRead, PromptStatus
from app.services.agent import AgentResult
from app.services.execution import PromptExecutionCoordinator
from app.services.prompts import PromptService


class FakePromptRepository:
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


class RecordingPromptAgent:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[OutputFormat] = []

    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat = OutputFormat.MARKDOWN,
    ) -> AgentResult:
        self.calls.append(output_format)
        return AgentResult(reply=self.reply_text)


class BlockingPromptAgent:
    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat = OutputFormat.MARKDOWN,
    ) -> AgentResult:
        self.started.set()
        await asyncio.Event().wait()
        return AgentResult(reply="never reached")


def test_prompt_service_passes_output_format_to_agent() -> None:
    async def exercise() -> None:
        prompt = PromptRead.model_validate(
            {
                "id": "prompt-1",
                "title": "JSON 요청",
                "prompt": "구조화된 결과를 반환해 줘.",
                "outputFormat": OutputFormat.JSON,
                "status": PromptStatus.DRAFT,
                "output": None,
                "errorMessage": None,
                "createdAt": 1,
                "updatedAt": 1,
                "startedAt": None,
                "completedAt": None,
            }
        )
        repository = FakePromptRepository(prompt)
        agent = RecordingPromptAgent('{"ok":true}')
        service = PromptService(
            repository=repository,
            agent_service=agent,
            execution_coordinator=PromptExecutionCoordinator(),
        )

        await service.run_execution(prompt.id)
        await service.close()

        assert agent.calls == [OutputFormat.JSON]
        assert repository.get(prompt.id).status == PromptStatus.COMPLETED

    asyncio.run(exercise())


def test_prompt_execution_cancellation_updates_persistent_state() -> None:
    async def exercise() -> None:
        prompt = PromptRead.model_validate(
            {
                "id": "prompt-2",
                "title": "취소 요청",
                "prompt": "오래 걸리는 작업.",
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
        repository = FakePromptRepository(prompt)
        started = asyncio.Event()
        agent = BlockingPromptAgent(started)
        service = PromptService(
            repository=repository,
            agent_service=agent,
            execution_coordinator=PromptExecutionCoordinator(),
        )

        await service.start_execution(prompt.id)
        await asyncio.wait_for(started.wait(), timeout=1)

        cancelled_prompt = await service.cancel_execution(prompt.id)
        await service.close()

        assert cancelled_prompt.status == PromptStatus.FAILED
        assert "취소" in (cancelled_prompt.error_message or "")
        assert repository.get(prompt.id).status == PromptStatus.FAILED

    asyncio.run(exercise())
