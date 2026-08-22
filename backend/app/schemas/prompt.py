from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )


class PromptStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plainText"
    JSON = "json"


class PromptWrite(ApiModel):
    title: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=4000)
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
    output_format: OutputFormat
    id: str
    status: PromptStatus
    output: str | None
    error_message: str | None
    created_at: int
    updated_at: int
    started_at: int | None
    completed_at: int | None


class PromptPage(ApiModel):
    items: list[PromptRead]
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool


class PromptBoard(ApiModel):
    columns: dict[PromptStatus, PromptPage]


class PromptEventType(str, Enum):
    STAGE = "stage"
    CHUNK = "chunk"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PromptEventStage(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class PromptStreamEvent(ApiModel):
    type: PromptEventType
    stage: PromptEventStage | None = None
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized
