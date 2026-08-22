from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from app.repositories.prompts import PromptRepository, get_prompt_repository
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

logger = logging.getLogger(__name__)


class AgentResponder(Protocol):
    async def reply(self, message: str) -> AgentResult: ...


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
    ) -> None:
        self._repository = repository
        self._agent_service = agent_service

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

    def start_execution(self, prompt_id: str) -> PromptRead:
        return self._repository.mark_running(prompt_id)

    async def run_execution(self, prompt_id: str) -> None:
        prompt = self._repository.get(prompt_id)
        instruction = OUTPUT_INSTRUCTIONS[prompt.output_format]
        request = (
            f"작업 이름: {prompt.title}\n\n"
            f"사용자 프롬프트:\n{prompt.prompt}\n\n"
            f"응답 지침: {instruction}"
        )
        try:
            result = await self._agent_service.reply(request)
            self._repository.mark_completed(
                prompt.id,
                output=result.reply,
            )
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


@lru_cache
def get_prompt_service() -> PromptService:
    return PromptService(
        repository=get_prompt_repository(),
        agent_service=get_agent_service(),
    )
