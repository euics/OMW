from __future__ import annotations

import sqlite3
import time
from functools import lru_cache
from uuid import uuid4

from app.database import Database, get_database
from app.schemas.prompt import (
    ExecutionState,
    PromptCreate,
    PromptRead,
    PromptStatus,
    PromptUpdate,
)


class PromptNotFoundError(LookupError):
    pass


class PromptStateConflictError(RuntimeError):
    pass


def current_time_ms() -> int:
    return time.time_ns() // 1_000_000


def row_to_prompt(row: sqlite3.Row) -> PromptRead:
    return PromptRead.model_validate(dict(row))


class PromptRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def list(self) -> list[PromptRead]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prompts ORDER BY created_at DESC"
            ).fetchall()
        return [row_to_prompt(row) for row in rows]

    def get(self, prompt_id: str) -> PromptRead:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM prompts WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        if row is None:
            raise PromptNotFoundError(prompt_id)
        return row_to_prompt(row)

    def create(self, payload: PromptCreate) -> PromptRead:
        prompt_id = str(uuid4())
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO prompts (
                    id, title, prompt, model, output_format, status,
                    execution_state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_id,
                    payload.title,
                    payload.prompt,
                    payload.model,
                    payload.output_format,
                    PromptStatus.DRAFT.value,
                    ExecutionState.IDLE.value,
                    now,
                    now,
                ),
            )
        return self.get(prompt_id)

    def update(self, prompt_id: str, payload: PromptUpdate) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE prompts
                SET title = ?, prompt = ?, model = ?, output_format = ?,
                    execution_state = ?, error_message = NULL, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    payload.title,
                    payload.prompt,
                    payload.model,
                    payload.output_format,
                    ExecutionState.IDLE.value,
                    now,
                    prompt_id,
                    PromptStatus.DRAFT.value,
                ),
            )
            if result.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "실행 전 프롬프트만 수정할 수 있습니다.",
                )
        return self.get(prompt_id)

    def delete(self, prompt_id: str) -> None:
        with self._database.connect() as connection:
            result = connection.execute(
                "DELETE FROM prompts WHERE id = ? AND status = ?",
                (prompt_id, PromptStatus.DRAFT.value),
            )
            if result.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "실행 전 프롬프트만 삭제할 수 있습니다.",
                )

    def mark_running(self, prompt_id: str) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE prompts
                SET status = ?, execution_state = ?, error_message = NULL,
                    output = NULL, started_at = ?, completed_at = NULL,
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    PromptStatus.RUNNING.value,
                    ExecutionState.REQUESTING.value,
                    now,
                    now,
                    prompt_id,
                    PromptStatus.DRAFT.value,
                ),
            )
            if result.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "이미 실행된 프롬프트입니다.",
                )
        return self.get(prompt_id)

    def mark_completed(
        self,
        prompt_id: str,
        *,
        output: str,
        thread_id: str,
    ) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE prompts
                SET status = ?, execution_state = ?, output = ?,
                    thread_id = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status = ? AND execution_state = ?
                """,
                (
                    PromptStatus.COMPLETED.value,
                    ExecutionState.SUCCEEDED.value,
                    output,
                    thread_id,
                    now,
                    now,
                    prompt_id,
                    PromptStatus.RUNNING.value,
                    ExecutionState.REQUESTING.value,
                ),
            )
            if result.rowcount == 0:
                raise PromptStateConflictError("진행중인 프롬프트가 아닙니다.")
        return self.get(prompt_id)

    def mark_failed(self, prompt_id: str, error_message: str) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE prompts
                SET status = ?, execution_state = ?, error_message = ?,
                    started_at = NULL, updated_at = ?
                WHERE id = ? AND status = ? AND execution_state = ?
                """,
                (
                    PromptStatus.DRAFT.value,
                    ExecutionState.FAILED.value,
                    error_message,
                    now,
                    prompt_id,
                    PromptStatus.RUNNING.value,
                    ExecutionState.REQUESTING.value,
                ),
            )
            if result.rowcount == 0:
                raise PromptStateConflictError("진행중인 프롬프트가 아닙니다.")
        return self.get(prompt_id)

    @staticmethod
    def _raise_mutation_error(
        connection: sqlite3.Connection,
        prompt_id: str,
        conflict_message: str,
    ) -> None:
        exists = connection.execute(
            "SELECT 1 FROM prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        if exists is None:
            raise PromptNotFoundError(prompt_id)
        raise PromptStateConflictError(conflict_message)


@lru_cache
def get_prompt_repository() -> PromptRepository:
    return PromptRepository(get_database())
