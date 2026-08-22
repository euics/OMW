from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from agent_framework.exceptions import AgentException
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    reply: str
    thread_id: str
    provider: str


class CopilotSession(Protocol):
    service_session_id: str | None


class CopilotResponse(Protocol):
    @property
    def text(self) -> str: ...


class CopilotAgent(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def create_session(self) -> CopilotSession: ...

    def get_session(self, *, service_session_id: str) -> CopilotSession: ...

    async def run(
        self,
        message: str,
        *,
        session: CopilotSession,
        options: GitHubCopilotOptions | None = None,
    ) -> CopilotResponse: ...


class AgentServiceError(RuntimeError):
    """Raised when the configured agent provider cannot complete a request."""


class CopilotAgentService:
    """Microsoft Agent Framework service backed by the GitHub Copilot SDK."""

    provider = "microsoft-agent-framework/github-copilot-sdk"

    def __init__(
        self,
        *,
        model: str,
        timeout: float,
        log_level: str,
        instructions: str,
        cli_path: str | None = None,
        agent: CopilotAgent | None = None,
    ) -> None:
        options = GitHubCopilotOptions(
            model=model,
            timeout=timeout,
            log_level=log_level,
        )
        if cli_path:
            options["cli_path"] = cli_path

        self._agent: CopilotAgent = agent or GitHubCopilotAgent(
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
        thread_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")

        await self._ensure_started()
        session = (
            self._agent.get_session(service_session_id=thread_id)
            if thread_id
            else self._agent.create_session()
        )

        try:
            options = GitHubCopilotOptions(model=model) if model else None
            response = await self._agent.run(
                normalized,
                session=session,
                options=options,
            )
        except AgentException as exc:
            logger.exception("GitHub Copilot request failed")
            raise AgentServiceError(
                "GitHub Copilot 요청에 실패했습니다. 인증 상태와 모델 설정을 확인해 주세요."
            ) from exc

        active_thread_id = session.service_session_id
        if not isinstance(active_thread_id, str) or not active_thread_id:
            raise AgentServiceError("GitHub Copilot이 세션 ID를 반환하지 않았습니다.")

        reply = response.text.strip()
        if not reply:
            raise AgentServiceError("GitHub Copilot이 빈 응답을 반환했습니다.")

        return AgentResult(
            reply=reply,
            thread_id=active_thread_id,
            provider=self.provider,
        )

    async def close(self) -> None:
        if not self._started:
            return

        await self._agent.stop()
        self._started = False


@lru_cache
def get_agent_service() -> CopilotAgentService:
    settings = get_settings()
    return CopilotAgentService(
        model=settings.github_copilot_model,
        timeout=settings.github_copilot_timeout,
        log_level=settings.github_copilot_log_level,
        cli_path=settings.github_copilot_cli_path,
        instructions=settings.github_copilot_instructions,
    )


async def close_agent_service() -> None:
    if get_agent_service.cache_info().currsize == 0:
        return

    await get_agent_service().close()
    get_agent_service.cache_clear()
