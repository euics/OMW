from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Protocol

from app.repositories.prompts import (
    PromptRepository,
    PromptStateConflictError,
    get_prompt_repository,
)
from app.schemas.prompt import (
    OutputFormat,
    PromptBoard,
    PromptCreate,
    PromptPage,
    PromptRead,
    PromptStatus,
    PromptStreamEvent,
    PromptUpdate,
)
from app.services.agent import AgentResult, AgentServiceError
from app.services.execution import PromptExecutionCoordinator
from app.services.orchestration import (
    PromptOrchestrationError,
    PromptOrchestrationService,
    get_prompt_orchestration_service,
)
from app.services.prompt_events import (
    cancelled_event,
    close_prompt_event_bus,
    completed_event,
    failed_event,
    get_prompt_event_bus,
    is_terminal_event_type,
    snapshot_event,
)

logger = logging.getLogger(__name__)


class AgentResponder(Protocol):
    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat | str = OutputFormat.MARKDOWN,
    ) -> AgentResult: ...


class PromptService:
    def __init__(
        self,
        repository: PromptRepository,
        agent_service: AgentResponder | None = None,
        execution_coordinator: PromptExecutionCoordinator | None = None,
        orchestration_service: PromptOrchestrationService | None = None,
    ) -> None:
        self._repository = repository
        self._execution_coordinator = execution_coordinator or PromptExecutionCoordinator()
        if orchestration_service is not None:
            self._orchestration_service = orchestration_service
        elif agent_service is not None:
            self._orchestration_service = PromptOrchestrationService.single_agent(agent_service)  # type: ignore[arg-type]
        else:
            self._orchestration_service = get_prompt_orchestration_service()

    def list_prompts(
        self,
        prompt_status: PromptStatus,
        page: int,
        page_size: int,
    ) -> PromptPage:
        return self._repository.list_page(prompt_status, page, page_size)

    def get_board(self, page_size: int) -> PromptBoard:
        return self._repository.get_board(page_size)

    def get_prompt(self, prompt_id: str) -> PromptRead:
        return self._repository.get(prompt_id)

    def create_prompt(self, payload: PromptCreate) -> PromptRead:
        return self._repository.create(payload)

    def update_prompt(
        self,
        prompt_id: str,
        payload: PromptUpdate,
    ) -> PromptRead:
        return self._repository.update(prompt_id, payload)

    def delete_prompt(self, prompt_id: str) -> None:
        self._repository.delete(prompt_id)

    async def start_execution(self, prompt_id: str) -> PromptRead:
        prompt = self._repository.mark_running(prompt_id)
        try:
            await self._execution_coordinator.schedule(
                prompt.id,
                lambda: self.run_execution(prompt.id),
            )
        except PromptStateConflictError:
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행을 시작하지 못했습니다.",
            )
            raise
        except RuntimeError:
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행을 시작하지 못했습니다.",
            )
            raise
        return prompt

    async def cancel_execution(self, prompt_id: str) -> PromptRead:
        prompt = self._repository.get(prompt_id)
        if prompt.status != PromptStatus.RUNNING:
            raise PromptStateConflictError("진행중인 프롬프트만 취소할 수 있습니다.")

        cancelled = await self._execution_coordinator.cancel(prompt_id)
        if cancelled:
            return self._repository.get(prompt_id)

        return self._repository.mark_failed(
            prompt_id,
            "프롬프트 실행이 취소되었습니다.",
        )

    async def run_execution(self, prompt_id: str) -> None:
        prompt = self._repository.get(prompt_id)
        bus = get_prompt_event_bus()

        async def emit(event: PromptStreamEvent) -> None:
            await bus.publish(prompt.id, event)

        try:
            output = await self._orchestration_service.execute(
                prompt,
                emit_event=emit,
            )
            self._repository.mark_completed(
                prompt.id,
                output=output,
            )
            await emit(completed_event("프롬프트 실행이 완료되었습니다."))
        except asyncio.CancelledError:
            logger.info("Prompt execution cancelled for %s", prompt.id)
            await emit(cancelled_event("프롬프트 실행이 취소되었습니다."))
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행이 취소되었습니다.",
            )
            raise
        except AgentServiceError as exc:
            logger.warning("Prompt execution failed for %s: %s", prompt.id, exc)
            await emit(failed_event(str(exc)))
            self._repository.mark_failed(prompt.id, str(exc))
            return
        except PromptOrchestrationError as exc:
            logger.warning("Prompt orchestration failed for %s: %s", prompt.id, exc)
            await emit(failed_event(str(exc)))
            self._repository.mark_failed(prompt.id, str(exc))
            return
        except Exception:
            logger.exception("Unexpected prompt execution failure for %s", prompt.id)
            await emit(failed_event("프롬프트 실행 중 예상하지 못한 오류가 발생했습니다."))
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행 중 예상하지 못한 오류가 발생했습니다.",
            )
            return

    async def stream_prompt_events(self, prompt_id: str):
        bus = get_prompt_event_bus()
        queue = await bus.subscribe(prompt_id)
        try:
            prompt = self._repository.get(prompt_id)
            snapshot = snapshot_event(prompt)
            yield snapshot
            if is_terminal_event_type(snapshot.type):
                return

            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
                if is_terminal_event_type(event.type):
                    return
        finally:
            await bus.unsubscribe(prompt_id, queue)

    async def close(self) -> None:
        await self._execution_coordinator.close()
        close_method = getattr(self._orchestration_service, "close", None)
        if close_method is not None:
            result = close_method()
            if hasattr(result, "__await__"):
                await result  # type: ignore[func-returns-value]
        await close_prompt_event_bus()


@lru_cache
def get_prompt_service() -> PromptService:
    return PromptService(
        repository=get_prompt_repository(),
        orchestration_service=get_prompt_orchestration_service(),
    )


async def close_prompt_service() -> None:
    if get_prompt_service.cache_info().currsize == 0:
        return

    await get_prompt_service().close()
    get_prompt_service.cache_clear()
    get_prompt_orchestration_service.cache_clear()
