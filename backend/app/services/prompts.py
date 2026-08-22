from __future__ import annotations

import json
import logging
from typing import Protocol

from fastapi import Depends
from pydantic import ConfigDict, JsonValue, RootModel, ValidationError

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
    CopilotAgentService,
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

MAX_STORED_OUTPUT_BYTES = 100_000


class StructuredOutput(RootModel[JsonValue]):
    model_config = ConfigDict(allow_inf_nan=False)


class OutputValidationError(ValueError):
    pass


class MalformedStructuredOutputError(OutputValidationError):
    pass


def validate_output(output: str, output_format: OutputFormat | str) -> str:
    normalized = output.strip()
    if not normalized:
        raise OutputValidationError("AI가 비어 있는 응답을 반환했습니다.")
    if len(normalized.encode("utf-8")) > MAX_STORED_OUTPUT_BYTES:
        raise OutputValidationError(
            "AI 응답이 저장 가능한 최대 크기를 초과했습니다."
        )
    if output_format not in (OutputFormat.JSON, OutputFormat.JSON.value):
        return normalized

    try:
        value = StructuredOutput.model_validate_json(normalized).root
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise MalformedStructuredOutputError(
            "AI가 유효한 JSON 응답을 반환하지 않았습니다."
        ) from exc
    if len(canonical.encode("utf-8")) > MAX_STORED_OUTPUT_BYTES:
        raise OutputValidationError(
            "AI 응답이 저장 가능한 최대 크기를 초과했습니다."
        )
    return canonical


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
            try:
                output = validate_output(result.reply, prompt.output_format)
            except MalformedStructuredOutputError:
                correction_request = (
                    f"{request}\n\n"
                    "이전 응답은 유효한 JSON이 아니었습니다. "
                    "아래 응답을 수정하여 설명이나 Markdown 코드 펜스 없이 "
                    "유효한 JSON만 다시 반환하세요.\n\n"
                    f"<invalid-response>\n{result.reply}\n</invalid-response>"
                )
                corrected = await self._agent_service.reply(correction_request)
                output = validate_output(corrected.reply, prompt.output_format)
            self._repository.mark_completed(
                prompt.id,
                output=output,
            )
        except OutputValidationError as exc:
            logger.warning("Prompt output validation failed for %s", prompt.id)
            self._repository.mark_failed(prompt.id, str(exc))
            return
        except AgentServiceError as exc:
            logger.warning(
                "Prompt execution failed for %s (category=%s)",
                prompt.id,
                exc.category.value,
            )
            self._repository.mark_failed(prompt.id, str(exc))
            return
        except Exception:
            logger.exception("Unexpected prompt execution failure for %s", prompt.id)
            self._repository.mark_failed(
                prompt.id,
                "프롬프트 실행 중 예상하지 못한 오류가 발생했습니다.",
            )
            return


def get_prompt_service(
    agent_service: CopilotAgentService = Depends(get_agent_service),
) -> PromptService:
    return PromptService(
        repository=get_prompt_repository(),
        agent_service=agent_service,
    )
