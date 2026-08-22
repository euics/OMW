from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from app.repositories.prompts import PromptStateConflictError

class PromptExecutionCoordinator:
    """Tracks prompt execution tasks within the current API process.

    This registry is intentionally process-local. If the backend runs with multiple
    workers or restarts, only executions started in the active process remain
    cancellable from memory.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def schedule(
        self,
        prompt_id: str,
        runner: Callable[[], Awaitable[None]],
    ) -> None:
        async with self._lock:
            existing = self._tasks.get(prompt_id)
            if existing is not None and not existing.done():
                raise PromptStateConflictError(f"Prompt {prompt_id} is already running.")
            task = asyncio.create_task(self._run_and_cleanup(prompt_id, runner))
            self._tasks[prompt_id] = task

    async def cancel(self, prompt_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(prompt_id)
            if task is None or task.done():
                self._tasks.pop(prompt_id, None)
                return False
            task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task
        return True

    async def close(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()

        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_and_cleanup(
        self,
        prompt_id: str,
        runner: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await runner()
        finally:
            async with self._lock:
                current = self._tasks.get(prompt_id)
                if current is asyncio.current_task():
                    self._tasks.pop(prompt_id, None)
