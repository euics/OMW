import asyncio
from collections.abc import Iterable

import pytest

from app.schemas.prompt import OutputFormat, PromptRead, PromptStatus
from app.services.agent import AgentResult
from app.services.prompts import (
    MAX_STORED_OUTPUT_BYTES,
    OutputValidationError,
    PromptService,
    validate_output,
)


class MemoryRepository:
    def __init__(self, output_format: OutputFormat) -> None:
        self.prompt = PromptRead(
            id="prompt-1",
            title="test",
            prompt="return a result",
            output_format=output_format,
            status=PromptStatus.RUNNING,
            created_at=1,
            updated_at=1,
        )
        self.completed_output: str | None = None
        self.failed_message: str | None = None

    def get(self, prompt_id: str) -> PromptRead:
        assert prompt_id == self.prompt.id
        return self.prompt

    def mark_completed(self, prompt_id: str, *, output: str) -> None:
        assert prompt_id == self.prompt.id
        self.completed_output = output

    def mark_failed(self, prompt_id: str, error_message: str) -> None:
        assert prompt_id == self.prompt.id
        self.failed_message = error_message


class SequencedAgent:
    def __init__(self, replies: Iterable[str]) -> None:
        self.replies = iter(replies)
        self.messages: list[str] = []

    async def reply(self, message: str) -> AgentResult:
        self.messages.append(message)
        return AgentResult(reply=next(self.replies))


def run_json_execution(*replies: str) -> tuple[MemoryRepository, SequencedAgent]:
    repository = MemoryRepository(OutputFormat.JSON)
    agent = SequencedAgent(replies)
    service = PromptService(repository, agent)  # type: ignore[arg-type]
    asyncio.run(service.run_execution(repository.prompt.id))
    return repository, agent


def test_valid_json_is_pydantic_validated_and_canonicalized() -> None:
    output = validate_output(' { "z": 1, "a": [true, null] } ', OutputFormat.JSON)

    assert output == '{"a":[true,null],"z":1}'


def test_json_is_rejected_when_canonical_output_exceeds_size_limit() -> None:
    compact = f"[{','.join(['1e99'] * 19_999)}]"
    canonical = f"[{','.join(['1e+99'] * 19_999)}]"

    assert len(compact.encode("utf-8")) <= MAX_STORED_OUTPUT_BYTES
    assert len(canonical.encode("utf-8")) > MAX_STORED_OUTPUT_BYTES
    with pytest.raises(
        OutputValidationError,
        match="AI 응답이 저장 가능한 최대 크기를 초과했습니다.",
    ):
        validate_output(compact, OutputFormat.JSON)


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(OutputValidationError):
        validate_output('{"missing": }', OutputFormat.JSON)


def test_invalid_json_gets_one_successful_correction_attempt() -> None:
    repository, agent = run_json_execution(
        "```json\n{\"value\": 1}\n```",
        '{"value": 1}',
    )

    assert repository.completed_output == '{"value":1}'
    assert repository.failed_message is None
    assert len(agent.messages) == 2
    assert "유효한 JSON만 다시 반환하세요" in agent.messages[1]


def test_invalid_json_correction_failure_marks_execution_failed() -> None:
    repository, agent = run_json_execution("not json", "still not json")

    assert repository.completed_output is None
    assert repository.failed_message == "AI가 유효한 JSON 응답을 반환하지 않았습니다."
    assert len(agent.messages) == 2


def test_text_output_must_be_nonblank_and_bounded() -> None:
    with pytest.raises(OutputValidationError):
        validate_output(" \n ", OutputFormat.MARKDOWN)
    with pytest.raises(OutputValidationError):
        validate_output("a" * (MAX_STORED_OUTPUT_BYTES + 1), OutputFormat.PLAIN_TEXT)
