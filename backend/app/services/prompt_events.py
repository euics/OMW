from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import lru_cache

from app.schemas.prompt import (
    PromptEventStage,
    PromptEventType,
    PromptRead,
    PromptStreamEvent,
    PromptStatus,
)

TERMINAL_EVENT_TYPES = {
    PromptEventType.COMPLETED.value,
    PromptEventType.FAILED.value,
    PromptEventType.CANCELLED.value,
}


@dataclass(slots=True)
class PromptEventChannel:
    subscribers: set[asyncio.Queue[PromptStreamEvent | None]] = field(default_factory=set)
    history: list[PromptStreamEvent] = field(default_factory=list)
    terminal_event: PromptStreamEvent | None = None


class PromptEventBus:
    def __init__(self) -> None:
        self._channels: dict[str, PromptEventChannel] = {}
        self._lock = asyncio.Lock()

    async def publish(self, prompt_id: str, event: PromptStreamEvent) -> None:
        async with self._lock:
            channel = self._channels.setdefault(prompt_id, PromptEventChannel())
            channel.history.append(event)
            if len(channel.history) > 200:
                channel.history = channel.history[-200:]
            if is_terminal_event_type(event.type):
                channel.terminal_event = event
            subscribers = list(channel.subscribers)

        for queue in subscribers:
            queue.put_nowait(event)
            if is_terminal_event_type(event.type):
                queue.put_nowait(None)

        if is_terminal_event_type(event.type):
            async with self._lock:
                channel = self._channels.get(prompt_id)
                if channel is not None and not channel.subscribers:
                    self._channels.pop(prompt_id, None)

    async def subscribe(
        self,
        prompt_id: str,
    ) -> asyncio.Queue[PromptStreamEvent | None]:
        queue: asyncio.Queue[PromptStreamEvent | None] = asyncio.Queue()
        async with self._lock:
            channel = self._channels.setdefault(prompt_id, PromptEventChannel())
            for event in channel.history:
                queue.put_nowait(event)
            if channel.terminal_event is not None:
                queue.put_nowait(None)
            else:
                channel.subscribers.add(queue)
        return queue

    async def unsubscribe(
        self,
        prompt_id: str,
        queue: asyncio.Queue[PromptStreamEvent | None],
    ) -> None:
        async with self._lock:
            channel = self._channels.get(prompt_id)
            if channel is None:
                return
            channel.subscribers.discard(queue)
            if not channel.subscribers and channel.terminal_event is not None:
                self._channels.pop(prompt_id, None)

    async def close(self) -> None:
        async with self._lock:
            channels = list(self._channels.values())
            self._channels.clear()

        for channel in channels:
            for queue in channel.subscribers:
                queue.put_nowait(None)

    async def get_terminal_event(self, prompt_id: str) -> PromptStreamEvent | None:
        async with self._lock:
            channel = self._channels.get(prompt_id)
            if channel is None:
                return None
            return channel.terminal_event


def snapshot_event(prompt: PromptRead) -> PromptStreamEvent:
    if prompt.status == PromptStatus.COMPLETED:
        return PromptStreamEvent(
            type=PromptEventType.COMPLETED,
            stage=None,
            message="프롬프트 실행이 완료되었습니다.",
        )
    if prompt.status == PromptStatus.FAILED:
        if prompt.error_message and "취소" in prompt.error_message:
            return PromptStreamEvent(
                type=PromptEventType.CANCELLED,
                stage=None,
                message=prompt.error_message,
            )
        return PromptStreamEvent(
            type=PromptEventType.FAILED,
            stage=None,
            message=prompt.error_message or "프롬프트 실행에 실패했습니다.",
        )
    return PromptStreamEvent(
        type=PromptEventType.STAGE,
        stage=None,
        message="프롬프트 이벤트를 기다리는 중입니다.",
    )


def stage_event(stage: PromptEventStage, message: str) -> PromptStreamEvent:
    return PromptStreamEvent(type=PromptEventType.STAGE, stage=stage, message=message)


def chunk_event(message: str) -> PromptStreamEvent:
    return PromptStreamEvent(
        type=PromptEventType.CHUNK,
        stage=PromptEventStage.EXECUTOR,
        message=message,
    )


def completed_event(message: str) -> PromptStreamEvent:
    return PromptStreamEvent(
        type=PromptEventType.COMPLETED,
        stage=None,
        message=message,
    )


def failed_event(message: str) -> PromptStreamEvent:
    return PromptStreamEvent(
        type=PromptEventType.FAILED,
        stage=None,
        message=message,
    )


def is_terminal_event_type(value: PromptEventType | str) -> bool:
    return value in TERMINAL_EVENT_TYPES


def cancelled_event(message: str) -> PromptStreamEvent:
    return PromptStreamEvent(
        type=PromptEventType.CANCELLED,
        stage=None,
        message=message,
    )


@lru_cache
def get_prompt_event_bus() -> PromptEventBus:
    return PromptEventBus()


async def close_prompt_event_bus() -> None:
    if get_prompt_event_bus.cache_info().currsize == 0:
        return

    await get_prompt_event_bus().close()
    get_prompt_event_bus.cache_clear()
