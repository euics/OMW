from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, cast

from agent_framework.exceptions import AgentException
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot import CopilotClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    reply: str


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
    ) -> None:
        options = cast(
            GitHubCopilotOptions,
            {
                "model": model,
                "timeout": timeout,
                "log_level": log_level,
                "available_tools": [],
            },
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

    async def _ensure_started(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            try:
                await self._agent.start()
            except AgentException as exc:
                logger.exception("Failed to start the GitHub Copilot agent")
                raise AgentServiceError(
                    "GitHub Copilot을 시작하지 못했습니다. CLI 인증과 설정을 확인해 주세요."
                ) from exc

            self._started = True

    async def reply(
        self,
        message: str,
    ) -> AgentResult:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")

        await self._ensure_started()
        session = self._agent.create_session()

        try:
            response = await self._agent.run(
                normalized,
                session=session,
            )
        except AgentException as exc:
            logger.exception("GitHub Copilot request failed")
            raise AgentServiceError(
                "GitHub Copilot 요청에 실패했습니다. 인증 상태와 모델 설정을 확인해 주세요."
            ) from exc

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


@lru_cache
def get_agent_service() -> CopilotAgentService:
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
    )


async def close_agent_service() -> None:
    if get_agent_service.cache_info().currsize == 0:
        return

    await get_agent_service().close()
    get_agent_service.cache_clear()
