from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.schemas.orchestration import OrchestrationPlan, ReviewerReview, ReviewerVerdict
from app.schemas.prompt import OutputFormat, PromptEventStage, PromptRead
from app.services.agent import CopilotAgentService, get_agent_service
from app.services.prompt_events import PromptStreamEvent, chunk_event, stage_event

EventEmitter = Callable[[PromptStreamEvent], Awaitable[None] | None]
ChunkEmitter = Callable[[str], Awaitable[None] | None]

PLANNER_INSTRUCTIONS = (
    "You are the planning agent for a product-runtime orchestration flow. "
    "Return only valid JSON describing a compact execution plan. "
    "Do not reveal internal reasoning."
)

REVIEWER_INSTRUCTIONS = (
    "You are the reviewer agent for a product-runtime orchestration flow. "
    "Return only valid JSON with a verdict and concise feedback. "
    "Do not reveal internal reasoning."
)

EXECUTOR_INSTRUCTIONS = (
    "You are the executor agent for a product-runtime orchestration flow. "
    "Follow the provided plan and user request exactly. "
    "Do not mention the planner or reviewer. "
    "Keep the answer concise and actionable."
)


class AgentResponder(Protocol):
    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat | str = OutputFormat.MARKDOWN,
        on_update: ChunkEmitter | None = None,
    ): ...


class PromptOrchestrationError(RuntimeError):
    pass


class PromptOrchestrationService:
    def __init__(
        self,
        *,
        planner_service: AgentResponder | None = None,
        executor_service: AgentResponder | None = None,
        reviewer_service: AgentResponder | None = None,
        enabled: bool | None = None,
    ) -> None:
        if enabled is None:
            if planner_service is not None and executor_service is not None and reviewer_service is not None:
                self._enabled = True
            else:
                settings = get_settings()
                self._enabled = settings.github_copilot_orchestration_enabled
        else:
            self._enabled = enabled
        self._planner_service = planner_service
        self._executor_service = executor_service
        self._reviewer_service = reviewer_service

    @classmethod
    def single_agent(cls, executor_service: AgentResponder) -> "PromptOrchestrationService":
        return cls(executor_service=executor_service, enabled=False)

    async def execute(
        self,
        prompt: PromptRead,
        *,
        emit_event: EventEmitter | None = None,
    ) -> str:
        if not self._enabled:
            await self._emit(emit_event, stage_event(PromptEventStage.EXECUTOR, "단일 실행을 시작합니다."))
            result = await self._reply(
                self._executor(),
                self._single_agent_request(prompt),
                output_format=prompt.output_format,
                on_update=lambda chunk: self._emit_chunk(emit_event, chunk),
            )
            return result.reply

        plan = await self._plan(prompt, emit_event=emit_event)
        first_output = await self._execute(
            prompt,
            plan,
            emit_event=emit_event,
            reviewer_feedback=None,
            message="계획을 실행합니다.",
        )
        review = await self._review(prompt, plan, first_output, emit_event=emit_event, message="초안 검토를 시작합니다.")
        if review.verdict == ReviewerVerdict.PASS:
            return first_output

        revised_output = await self._execute(
            prompt,
            plan,
            emit_event=emit_event,
            reviewer_feedback=review.feedback,
            message="수정 요청을 반영합니다.",
        )
        final_review = await self._review(
            prompt,
            plan,
            revised_output,
            emit_event=emit_event,
            message="최종 검토를 시작합니다.",
        )
        if final_review.verdict != ReviewerVerdict.PASS:
            raise PromptOrchestrationError(final_review.feedback)
        return revised_output

    async def _plan(
        self,
        prompt: PromptRead,
        *,
        emit_event: EventEmitter | None,
    ) -> OrchestrationPlan:
        await self._emit(emit_event, stage_event(PromptEventStage.PLANNER, "계획을 생성합니다."))
        result = await self._reply(
            self._planner(),
            self._planner_request(prompt),
            output_format=OutputFormat.JSON,
        )
        try:
            return OrchestrationPlan.model_validate_json(result.reply)
        except Exception as exc:
            raise PromptOrchestrationError("계획 응답이 유효하지 않습니다.") from exc

    async def _execute(
        self,
        prompt: PromptRead,
        plan: OrchestrationPlan,
        *,
        emit_event: EventEmitter | None,
        reviewer_feedback: str | None,
        message: str,
    ) -> str:
        await self._emit(emit_event, stage_event(PromptEventStage.EXECUTOR, message))
        result = await self._reply(
            self._executor(),
            self._executor_request(prompt, plan, reviewer_feedback=reviewer_feedback),
            output_format=prompt.output_format,
            on_update=lambda chunk: self._emit_chunk(emit_event, chunk),
        )
        return result.reply

    async def _review(
        self,
        prompt: PromptRead,
        plan: OrchestrationPlan,
        output: str,
        *,
        emit_event: EventEmitter | None,
        message: str,
    ) -> ReviewerReview:
        await self._emit(emit_event, stage_event(PromptEventStage.REVIEWER, message))
        result = await self._reply(
            self._reviewer(),
            self._reviewer_request(prompt, plan, output),
            output_format=OutputFormat.JSON,
        )
        try:
            review = ReviewerReview.model_validate_json(result.reply)
        except Exception as exc:
            raise PromptOrchestrationError("리뷰어 응답이 유효하지 않습니다.") from exc
        if review.verdict not in {ReviewerVerdict.PASS, ReviewerVerdict.REVISE}:
            raise PromptOrchestrationError("리뷰어 verdict가 유효하지 않습니다.")
        return review

    def _planner(self) -> AgentResponder:
        if self._planner_service is None:
            self._planner_service = self._build_agent_service(
                name="PromptPlannerAgent",
                description="Builds compact execution plans for prompts.",
                instructions=PLANNER_INSTRUCTIONS,
            )
        return self._planner_service

    def _executor(self) -> AgentResponder:
        if self._executor_service is None:
            self._executor_service = self._build_agent_service(
                name="PromptExecutorAgent",
                description="Executes prompt plans and returns the final answer.",
                instructions=EXECUTOR_INSTRUCTIONS,
            )
        return self._executor_service

    def _reviewer(self) -> AgentResponder:
        if self._reviewer_service is None:
            self._reviewer_service = self._build_agent_service(
                name="PromptReviewerAgent",
                description="Reviews prompt outputs and returns pass or revise.",
                instructions=REVIEWER_INSTRUCTIONS,
            )
        return self._reviewer_service

    def _build_agent_service(
        self,
        *,
        name: str,
        description: str,
        instructions: str,
    ) -> CopilotAgentService:
        settings = get_settings()
        return CopilotAgentService(
            model=settings.github_copilot_model,
            timeout=settings.github_copilot_timeout,
            log_level=settings.github_copilot_log_level,
            cli_path=settings.github_copilot_cli_path,
            token=(
                settings.github_copilot_token.get_secret_value()
                if settings.github_copilot_token
                else None
            ),
            retry_attempts=settings.github_copilot_retry_attempts,
            retry_backoff_seconds=settings.github_copilot_retry_backoff_seconds,
            retry_backoff_multiplier=settings.github_copilot_retry_backoff_multiplier,
            retry_max_backoff_seconds=settings.github_copilot_retry_max_backoff_seconds,
            fallback_model=settings.github_copilot_fallback_model,
            instructions=instructions,
            name=name,
            description=description,
        )

    def _planner_request(self, prompt: PromptRead) -> str:
        return (
            "다음 사용자의 요청을 실행하기 위한 계획을 작성하세요.\n"
            "반드시 objective, steps, acceptanceCriteria만 포함한 JSON을 반환하세요.\n"
            "추론 과정은 절대 노출하지 마세요.\n\n"
            f"작업 제목: {prompt.title}\n"
            f"사용자 요청:\n{prompt.prompt}"
        )

    def _executor_request(
        self,
        prompt: PromptRead,
        plan: OrchestrationPlan,
        *,
        reviewer_feedback: str | None,
    ) -> str:
        plan_json = plan.model_dump_json(by_alias=True, ensure_ascii=False)
        output_format = (
            prompt.output_format.value
            if hasattr(prompt.output_format, "value")
            else prompt.output_format
        )
        feedback_section = (
            f"\n리뷰어 피드백:\n{reviewer_feedback}\n"
            if reviewer_feedback
            else "\n"
        )
        return (
            "다음 계획을 바탕으로 사용자의 요청을 실제로 수행하세요.\n"
            "플래너/리뷰어 내부 추론은 언급하지 마세요.\n"
            f"원하는 출력 형식: {output_format}\n"
            f"계획 JSON:\n{plan_json}\n"
            f"{feedback_section}\n"
            f"사용자 요청:\n{prompt.prompt}"
        )

    def _reviewer_request(
        self,
        prompt: PromptRead,
        plan: OrchestrationPlan,
        output: str,
    ) -> str:
        return (
            "다음 실행 결과를 검토하세요.\n"
            "반드시 verdict(PASS 또는 REVISE)와 feedback만 포함한 JSON을 반환하세요.\n"
            "추론 과정은 노출하지 마세요.\n\n"
            f"계획:\n{plan.model_dump_json(by_alias=True, ensure_ascii=False)}\n\n"
            f"사용자 요청:\n{prompt.prompt}\n\n"
            f"실행 결과:\n{output}"
        )

    def _single_agent_request(self, prompt: PromptRead) -> str:
        output_format = (
            prompt.output_format.value
            if hasattr(prompt.output_format, "value")
            else prompt.output_format
        )
        return (
            f"작업 이름: {prompt.title}\n\n"
            f"출력 형식: {output_format}\n\n"
            f"사용자 프롬프트:\n{prompt.prompt}\n\n"
            "응답은 플래너/리뷰어 단계를 거치지 않고 바로 작성하세요."
        )

    async def _reply(
        self,
        responder: AgentResponder,
        message: str,
        *,
        output_format: OutputFormat | str,
        on_update: ChunkEmitter | None = None,
    ):
        try:
            result = responder.reply(
                message,
                output_format=output_format,
                on_update=on_update,
            )
        except TypeError:
            result = responder.reply(message, output_format=output_format)
        if hasattr(result, "__await__"):
            return await result  # type: ignore[func-returns-value]
        return result

    async def _emit(self, emitter: EventEmitter | None, event: PromptStreamEvent) -> None:
        if emitter is None:
            return
        result = emitter(event)
        if hasattr(result, "__await__"):
            await result  # type: ignore[func-returns-value]

    async def _emit_chunk(self, emitter: EventEmitter | None, chunk: str) -> None:
        if not chunk.strip():
            return
        await self._emit(emitter, chunk_event(chunk))

    async def close(self) -> None:
        for service in (self._planner_service, self._executor_service, self._reviewer_service):
            if service is None:
                continue
            close_method = getattr(service, "close", None)
            if close_method is None:
                continue
            result = close_method()
            if hasattr(result, "__await__"):
                await result  # type: ignore[func-returns-value]


@lru_cache
def get_prompt_orchestration_service() -> PromptOrchestrationService:
    settings = get_settings()
    if not settings.github_copilot_orchestration_enabled:
        return PromptOrchestrationService.single_agent(get_agent_service())
    return PromptOrchestrationService()


async def close_prompt_orchestration_service() -> None:
    if get_prompt_orchestration_service.cache_info().currsize == 0:
        return

    await get_prompt_orchestration_service().close()
    get_prompt_orchestration_service.cache_clear()
