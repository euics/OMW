from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    provider: str


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
