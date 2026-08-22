from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agent_framework import AgentResponse, AgentResponseUpdate, ChatOptions, ResponseStream
from agent_framework.exceptions import AgentException
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot import CopilotClient

from app.core.config import get_settings
from app.schemas.prompt import OutputFormat

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[str], Awaitable[None] | None]


@dataclass(frozen=True)
class AgentResult:
    reply: str


class CopilotSession(Protocol):
    pass


class CopilotResponse(Protocol):
    @property
    def text(self) -> str: ...


class CopilotResponseStream(Protocol):
    def __aiter__(self) -> Any: ...

    async def get_final_response(self) -> CopilotResponse: ...


class CopilotAgent(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def create_session(self) -> CopilotSession: ...

    def run(
        self,
        message: str,
        *,
        stream: bool = False,
        session: CopilotSession | None = None,
        options: ChatOptions[Any] | None = None,
    ) -> (
        ResponseStream[AgentResponseUpdate, AgentResponse[Any]]
        | Awaitable[AgentResponse[Any]]
        | Awaitable[ResponseStream[AgentResponseUpdate, AgentResponse[Any]]]
    ): ...


class AgentServiceError(RuntimeError):
    """Raised when the configured agent provider cannot complete a request."""


class RetryableAgentServiceError(AgentServiceError):
    """Raised for retryable Agent Framework failures."""


class EmptyCopilotResponseError(RetryableAgentServiceError):
    """Raised when the agent returns no usable text."""


class InvalidStructuredResponseError(RetryableAgentServiceError):
    """Raised when a structured response cannot be validated."""


class CopilotAgentService:
    """Microsoft Agent Framework service backed by the GitHub Copilot SDK."""

    def __init__(
        self,
        *,
        model: str,
        timeout: float,
        log_level: str,
        instructions: str,
        name: str = "PromptExecutionAgent",
        description: str = "Executes prompts submitted from the prompt operations board.",
        cli_path: str | None = None,
        token: str | None = None,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        retry_backoff_multiplier: float = 2.0,
        retry_max_backoff_seconds: float = 5.0,
        fallback_model: str | None = None,
        agent: CopilotAgent | None = None,
    ) -> None:
        options = GitHubCopilotOptions(
            model=model,
            timeout=timeout,
            log_level=log_level,
        )
        if cli_path:
            options["cli_path"] = cli_path

        self._client = CopilotClient(github_token=token) if token else None
        self._agent: CopilotAgent = agent or GitHubCopilotAgent(
            client=self._client,
            name=name,
            description=description,
            instructions=instructions,
            default_options=options,
        )
        self._started = False
        self._start_lock = asyncio.Lock()
        self._primary_model = model
        self._fallback_model = fallback_model
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._retry_backoff_multiplier = max(1.0, retry_backoff_multiplier)
        self._retry_max_backoff_seconds = max(
            self._retry_backoff_seconds,
            retry_max_backoff_seconds,
        )

    async def _ensure_started(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            start_method = getattr(self._agent, "start", None)
            if start_method is None:
                self._started = True
                return

            try:
                await self._resolve_awaitable(start_method())
            except AgentException as exc:
                logger.exception("Failed to start the GitHub Copilot agent")
                raise AgentServiceError(
                    "GitHub Copilot을 시작하지 못했습니다. CLI 인증과 설정을 확인해 주세요."
                ) from exc

            self._started = True

    async def reply(
        self,
        message: str,
        *,
        output_format: OutputFormat | str = OutputFormat.MARKDOWN,
        on_update: UpdateCallback | None = None,
    ) -> AgentResult:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")

        await self._ensure_started()
        create_session = getattr(self._agent, "create_session", None)
        session = create_session() if create_session is not None else None

        try:
            reply = await self._run_with_policy(
                normalized,
                session=session,
                output_format=output_format,
                on_update=on_update,
            )
        except RetryableAgentServiceError as exc:
            logger.exception("GitHub Copilot request failed")
            raise AgentServiceError(str(exc)) from exc
        except AgentServiceError:
            raise
        except Exception as exc:
            logger.exception("Unexpected GitHub Copilot failure")
            raise AgentServiceError(
                "GitHub Copilot 요청에 실패했습니다. 인증 상태와 모델 설정을 확인해 주세요."
            ) from exc

        return AgentResult(reply=reply)

    async def _run_with_policy(
        self,
        message: str,
        *,
        session: CopilotSession,
        output_format: OutputFormat | str,
        on_update: UpdateCallback | None,
    ) -> str:
        try:
            return await self._run_with_retries(
                message,
                session=session,
                model=self._primary_model,
                output_format=output_format,
                on_update=on_update,
            )
        except RetryableAgentServiceError as primary_error:
            if self._fallback_model is None:
                raise
            logger.warning(
                "Primary Copilot model failed; retrying with fallback model %s",
                self._fallback_model,
            )
            try:
                return await self._run_once(
                    message,
                    session=session,
                    model=self._fallback_model,
                    output_format=output_format,
                    on_update=on_update,
                )
            except RetryableAgentServiceError as fallback_error:
                raise fallback_error from primary_error

    async def _run_with_retries(
        self,
        message: str,
        *,
        session: CopilotSession,
        model: str,
        output_format: OutputFormat | str,
        on_update: UpdateCallback | None,
    ) -> str:
        last_error: RetryableAgentServiceError | None = None
        for attempt_index in range(self._retry_attempts):
            try:
                return await self._run_once(
                    message,
                    session=session,
                    model=model,
                    output_format=output_format,
                    on_update=on_update,
                )
            except RetryableAgentServiceError as exc:
                last_error = exc
                if attempt_index < self._retry_attempts - 1:
                    await asyncio.sleep(self._backoff_seconds_for_attempt(attempt_index))
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise AgentServiceError("GitHub Copilot 요청에 실패했습니다.")

    async def _run_once(
        self,
        message: str,
        *,
        session: CopilotSession,
        model: str,
        output_format: OutputFormat | str,
        on_update: UpdateCallback | None,
    ) -> str:
        run_options = self._build_run_options(model=model, output_format=output_format)

        try:
            run_result = self._agent.run(
                message,
                stream=True,
                session=session,
                options=run_options,
            )
            stream = await self._resolve_stream(run_result)
            collected_chunks: list[str] = []
            async for update in stream:
                text = getattr(update, "text", "")
                if text:
                    collected_chunks.append(text)
                    if on_update is not None:
                        callback_result = on_update(text)
                        if inspect.isawaitable(callback_result):
                            await callback_result
            final_response = await self._resolve_awaitable(stream.get_final_response())
        except AgentException as exc:
            raise RetryableAgentServiceError(
                "GitHub Copilot 요청에 실패했습니다. 인증 상태와 모델 설정을 확인해 주세요."
            ) from exc
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise RetryableAgentServiceError(
                "GitHub Copilot 요청이 시간 초과되었습니다. 잠시 후 다시 시도해 주세요."
            ) from exc

        reply = final_response.text.strip() or "".join(collected_chunks).strip()
        if not reply:
            raise EmptyCopilotResponseError("GitHub Copilot이 빈 응답을 반환했습니다.")

        if output_format == OutputFormat.JSON:
            reply = self._normalize_json(reply)

        return reply

    def _build_run_options(
        self,
        *,
        model: str,
        output_format: OutputFormat | str,
    ) -> ChatOptions[Any]:
        options: ChatOptions[Any] = {"model": model}
        if output_format == OutputFormat.JSON:
            options["response_format"] = {"type": "json_object"}
        return options

    def _normalize_json(self, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InvalidStructuredResponseError(
                "GitHub Copilot이 유효한 JSON을 반환하지 않았습니다."
            ) from exc
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    def _backoff_seconds_for_attempt(self, attempt_index: int) -> float:
        delay = self._retry_backoff_seconds * (self._retry_backoff_multiplier**attempt_index)
        return min(self._retry_max_backoff_seconds, delay)

    async def _resolve_stream(
        self,
        stream_or_awaitable: (
            ResponseStream[AgentResponseUpdate, AgentResponse[Any]]
            | Awaitable[ResponseStream[AgentResponseUpdate, AgentResponse[Any]]]
        ),
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        stream = await self._resolve_awaitable(stream_or_awaitable)
        return stream

    async def _resolve_awaitable(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def close(self) -> None:
        if not self._started:
            return

        stop_method = getattr(self._agent, "stop", None)
        if stop_method is not None:
            await self._resolve_awaitable(stop_method())
        if self._client:
            await self._resolve_awaitable(self._client.stop())
        self._started = False


def _build_settings_agent_service(
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


@lru_cache
def get_executor_agent_service() -> CopilotAgentService:
    settings = get_settings()
    return _build_settings_agent_service(
        name="PromptExecutorAgent",
        description="Executes prompt plans and returns the final answer.",
        instructions=settings.github_copilot_instructions,
    )


@lru_cache
def get_agent_service() -> CopilotAgentService:
    return get_executor_agent_service()


@lru_cache
def get_planner_agent_service() -> CopilotAgentService:
    settings = get_settings()
    return _build_settings_agent_service(
        name="PromptPlannerAgent",
        description="Builds compact execution plans for prompts.",
        instructions=(
            settings.github_copilot_instructions
            + " Return only JSON with objective, steps, and acceptanceCriteria."
        ),
    )


@lru_cache
def get_reviewer_agent_service() -> CopilotAgentService:
    settings = get_settings()
    return _build_settings_agent_service(
        name="PromptReviewerAgent",
        description="Reviews prompt outputs and returns a pass or revise verdict.",
        instructions=(
            settings.github_copilot_instructions
            + " Return only JSON with verdict and feedback."
        ),
    )


async def close_agent_service() -> None:
    services = [
        get_executor_agent_service,
        get_planner_agent_service,
        get_reviewer_agent_service,
    ]
    for getter in services:
        if getter.cache_info().currsize == 0:
            continue
        await getter().close()
        getter.cache_clear()

    get_agent_service.cache_clear()
