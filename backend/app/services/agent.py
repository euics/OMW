from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from agent_framework.exceptions import AgentException
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot import CopilotClient
from fastapi import Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    reply: str


class AgentFailureCategory(str, Enum):
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


class CopilotSession(Protocol):
    pass


class CopilotResponse(Protocol):
    @property
    def text(self) -> str: ...


class CopilotAgent(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def create_session(self) -> CopilotSession: ...

    async def run(
        self,
        message: str,
        *,
        session: CopilotSession,
    ) -> CopilotResponse: ...


class AgentServiceError(RuntimeError):
    """Raised when the configured agent provider cannot complete a request."""

    def __init__(
        self,
        message: str,
        *,
        category: AgentFailureCategory = AgentFailureCategory.UNKNOWN,
    ) -> None:
        super().__init__(message)
        self.category = category

    @property
    def retryable(self) -> bool:
        return self.category in {
            AgentFailureCategory.TIMEOUT,
            AgentFailureCategory.TRANSIENT,
        }


_FAILURE_MESSAGES = {
    AgentFailureCategory.AUTHENTICATION: (
        "GitHub Copilot 인증에 실패했습니다. 서버 인증 설정을 확인해 주세요."
    ),
    AgentFailureCategory.CONFIGURATION: (
        "GitHub Copilot 설정이 올바르지 않습니다. 서버 설정을 확인해 주세요."
    ),
    AgentFailureCategory.TIMEOUT: (
        "GitHub Copilot 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    ),
    AgentFailureCategory.TRANSIENT: (
        "GitHub Copilot 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
    ),
    AgentFailureCategory.UNKNOWN: "GitHub Copilot 요청을 완료하지 못했습니다.",
}


def classify_provider_failure(error: BaseException) -> AgentFailureCategory:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return AgentFailureCategory.TIMEOUT

    details = f"{type(error).__name__} {error}".lower()
    if any(
        marker in details
        for marker in (
            "unauthorized",
            "forbidden",
            "authentication",
            "credential",
            "not logged in",
            "invalid token",
            "401",
            "403",
        )
    ):
        return AgentFailureCategory.AUTHENTICATION
    if any(
        marker in details
        for marker in (
            "configuration",
            "invalid config",
            "invalid model",
            "model not found",
            "cli not found",
            "executable not found",
            "enoent",
        )
    ):
        return AgentFailureCategory.CONFIGURATION
    if any(marker in details for marker in ("timeout", "timed out", "deadline")):
        return AgentFailureCategory.TIMEOUT
    if any(
        marker in details
        for marker in (
            "rate limit",
            "too many requests",
            "temporar",
            "unavailable",
            "overloaded",
            "connection",
            "network",
            "reset",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
    ):
        return AgentFailureCategory.TRANSIENT
    return AgentFailureCategory.UNKNOWN


def _safe_provider_error(error: BaseException) -> AgentServiceError:
    category = classify_provider_failure(error)
    return AgentServiceError(_FAILURE_MESSAGES[category], category=category)


class CopilotAgentService:
    """Microsoft Agent Framework service backed by the GitHub Copilot SDK."""

    def __init__(
        self,
        *,
        model: str,
        timeout: float,
        log_level: str,
        instructions: str,
        cli_path: str | None = None,
        token: str | None = None,
        agent: CopilotAgent | None = None,
        max_concurrent_executions: int = 4,
        max_provider_attempts: int = 2,
        retry_delay: float = 0.05,
    ) -> None:
        if max_concurrent_executions < 1:
            raise ValueError("max_concurrent_executions must be at least 1")
        if not 1 <= max_provider_attempts <= 3:
            raise ValueError("max_provider_attempts must be between 1 and 3")
        if retry_delay < 0:
            raise ValueError("retry_delay must not be negative")

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
            name="PromptExecutionAgent",
            description="Executes prompts submitted from the prompt operations board.",
            instructions=instructions,
            default_options=options,
        )
        self._started = False
        self._start_lock = asyncio.Lock()
        self._execution_slots = asyncio.Semaphore(max_concurrent_executions)
        self._max_provider_attempts = max_provider_attempts
        self._retry_delay = retry_delay

    async def _ensure_started(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            for attempt in range(1, self._max_provider_attempts + 1):
                try:
                    await self._agent.start()
                    break
                except (AgentException, asyncio.TimeoutError) as exc:
                    error = _safe_provider_error(exc)
                    logger.warning(
                        "GitHub Copilot agent start failed (category=%s, attempt=%d)",
                        error.category.value,
                        attempt,
                    )
                    if not error.retryable or attempt == self._max_provider_attempts:
                        raise error from exc
                    await asyncio.sleep(self._retry_delay)

            self._started = True

    async def reply(
        self,
        message: str,
    ) -> AgentResult:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")

        async with self._execution_slots:
            await self._ensure_started()
            for attempt in range(1, self._max_provider_attempts + 1):
                try:
                    session = self._agent.create_session()
                    response = await self._agent.run(
                        normalized,
                        session=session,
                    )
                    break
                except (AgentException, asyncio.TimeoutError) as exc:
                    error = _safe_provider_error(exc)
                    logger.warning(
                        "GitHub Copilot request failed (category=%s, attempt=%d)",
                        error.category.value,
                        attempt,
                    )
                    if not error.retryable or attempt == self._max_provider_attempts:
                        raise error from exc
                    await asyncio.sleep(self._retry_delay)

        reply = response.text.strip()
        if not reply:
            raise AgentServiceError("GitHub Copilot이 빈 응답을 반환했습니다.")

        return AgentResult(reply=reply)

    async def close(self) -> None:
        if not self._started:
            return

        await self._agent.stop()
        if self._client:
            await self._client.stop()
        self._started = False


def create_agent_service() -> CopilotAgentService:
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
        instructions=settings.github_copilot_instructions,
        max_concurrent_executions=(
            settings.github_copilot_max_concurrent_executions
        ),
    )


class AgentServiceProvider:
    """Owns one service and rejects access once shutdown has begun."""

    def __init__(
        self,
        factory: Callable[[], CopilotAgentService] = create_agent_service,
    ) -> None:
        self._factory = factory
        self._service: CopilotAgentService | None = None
        self._closed = False
        self._lock = threading.Lock()

    def get(self) -> CopilotAgentService:
        """Return the live service, or raise after close has claimed the lifecycle."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Agent service provider is closed")
            if self._service is None:
                self._service = self._factory()
            return self._service

    async def close(self) -> None:
        with self._lock:
            self._closed = True
            service = self._service
            self._service = None

        if service is not None:
            await service.close()


def get_agent_service(request: Request) -> CopilotAgentService:
    provider: AgentServiceProvider = request.app.state.agent_service_provider
    return provider.get()
