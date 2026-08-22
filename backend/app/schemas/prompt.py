from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
    )


class PromptStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"


class ExecutionState(str, Enum):
    IDLE = "idle"
    REQUESTING = "requesting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PromptModel(str, Enum):
    AUTO = "auto"
    GPT_5_6_SOL = "gpt-5.6-sol"
    CLAUDE_SONNET_5 = "claude-sonnet-5"


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plainText"
    JSON = "json"


class PromptWrite(ApiModel):
    title: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=4000)
    model: PromptModel = PromptModel.AUTO
    output_format: OutputFormat = OutputFormat.MARKDOWN

    @field_validator("title", "prompt")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class PromptCreate(PromptWrite):
    pass


class PromptUpdate(PromptWrite):
    pass


class PromptRead(PromptWrite):
    id: str
    status: PromptStatus
    execution_state: ExecutionState
    output: Optional[str] = None
    error_message: Optional[str] = None
    created_at: int
    updated_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
