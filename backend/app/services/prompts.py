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
    PromptUpdate,
)
from app.services.agent import (
    AgentResult,
    AgentServiceError,
    get_agent_service,
)
from app.services.execution import PromptExecutionCoordinator

logger = logging.getLogger(__name__)


class AgentResponder(Protocol):
    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat | str = OutputFormat.MARKDOWN,
    ) -> AgentResult: ...


OUTPUT_INSTRUCTIONS = {
    OutputFormat.MARKDOWN.value: "응답은 읽기 쉬운 Markdown으로 작성하세요.",
    OutputFormat.PLAIN_TEXT.value: "응답은 서식 없는 일반 텍스트로 작성하세요.",
    OutputFormat.JSON.value: "응답은 유효한 JSON만 반환하세요.",
}


class PromptService:
    def __init__(
        self,
        repository: PromptRepository,
        agent_service: AgentResponder,
        execution_coordinator: PromptExecutionCoordinator | None = None,
    ) -> None:
        self._repository = repository
        self._agent_service = agent_service
        self._execution_coordinator = execution_coordinator or PromptExecutionCoordinator()

    def list_prompts(
        self,
        prompt_status: PromptStatus,
        page: int,
        page_size: int,
    ) -> PromptPage:
        return self._repository.list_page(prompt_status, page, page_size)

    def get_board(self, page_size: int) -> PromptBoard:
        return self._repository.get_board(page_size)

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
        output_format = (
            prompt.output_format.value
            if hasattr(prompt.output_format, "value")
            else prompt.output_format
        )
        instruction = OUTPUT_INSTRUCTIONS[output_format]
        request = (
            f"작업 이름: {prompt.title}\n\n"
            f"출력 형식: {output_format}\n\n"
            f"사용자 프롬프트:\n{prompt.prompt}\n\n"
            f"응답 지침: {instruction}"
        )
        try:
            result = await self._agent_service.reply(
                request,
                output_format=output_format,
            )
            self._repository.mark_completed(
                prompt.id,
                output=result.reply,
            )
        except asyncio.CancelledError:
            logger.info("Prompt execution cancelled for %s", prompt.id)
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행이 취소되었습니다.",
            )
            raise
        except AgentServiceError as exc:
            logger.warning("Prompt execution failed for %s: %s", prompt.id, exc)
            self._repository.mark_failed(prompt.id, str(exc))
            return
        except Exception:
            logger.exception("Unexpected prompt execution failure for %s", prompt.id)
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행 중 예상하지 못한 오류가 발생했습니다.",
            )
            return

    async def close(self) -> None:
        await self._execution_coordinator.close()


@lru_cache
def get_prompt_service() -> PromptService:
    return PromptService(
        repository=get_prompt_repository(),
        agent_service=get_agent_service(),
    )


async def close_prompt_service() -> None:
    if get_prompt_service.cache_info().currsize == 0:
        return

    await get_prompt_service().close()
    get_prompt_service.cache_clear()
