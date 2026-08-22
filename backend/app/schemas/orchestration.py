from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator

from app.schemas.prompt import ApiModel


class OrchestrationPlan(ApiModel):
    objective: str = Field(min_length=1, max_length=500)
    steps: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(
        min_length=1,
        alias="acceptanceCriteria",
    )

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("steps", "acceptance_criteria")
    @classmethod
    def normalize_text_items(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if not item:
                raise ValueError("must not be blank")
            normalized.append(item)
        return normalized


class ReviewerVerdict(str, Enum):
    PASS = "PASS"
    REVISE = "REVISE"


class ReviewerReview(ApiModel):
    verdict: ReviewerVerdict
    feedback: str = Field(min_length=1, max_length=2000)

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized
