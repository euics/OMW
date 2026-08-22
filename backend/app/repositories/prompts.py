from __future__ import annotations

import time
from functools import lru_cache
from typing import Mapping
from uuid import uuid4

from pymysql.cursors import DictCursor

from app.database import Database, get_database
from app.schemas.prompt import (
    PromptCreate,
    PromptBoard,
    PromptPage,
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


def row_to_prompt(row: Mapping[str, object]) -> PromptRead:
    return PromptRead.model_validate(dict(row))


PROMPT_COLUMNS = """
id, title, prompt, output_format, status, output, error_message,
created_at, updated_at, started_at, completed_at
"""


class PromptRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def list_page(
        self,
        prompt_status: PromptStatus,
        page: int,
        page_size: int,
    ) -> PromptPage:
        with self._database.connect() as connection:
            return self._list_page(connection, prompt_status, page, page_size)

    def get_board(self, page_size: int) -> PromptBoard:
        with self._database.connect() as connection:
            columns = {
                prompt_status: self._list_page(
                    connection,
                    prompt_status,
                    page=1,
                    page_size=page_size,
                )
                for prompt_status in PromptStatus
            }
        return PromptBoard(columns=columns)

    def get(self, prompt_id: str) -> PromptRead:
        with self._database.connect() as connection:
            connection.execute(
                f"SELECT {PROMPT_COLUMNS} FROM prompts WHERE id = %s",
                (prompt_id,),
            )
            row = connection.fetchone()
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
                    id, title, prompt, output_format, status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    prompt_id,
                    payload.title,
                    payload.prompt,
                    payload.output_format,
                    PromptStatus.DRAFT.value,
                    now,
                    now,
                ),
            )
        return self.get(prompt_id)

    def update(self, prompt_id: str, payload: PromptUpdate) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE prompts
                SET title = %s, prompt = %s, output_format = %s, status = %s,
                    error_message = NULL, updated_at = %s
                WHERE id = %s AND status IN (%s, %s)
                """,
                (
                    payload.title,
                    payload.prompt,
                    payload.output_format,
                    PromptStatus.DRAFT.value,
                    now,
                    prompt_id,
                    PromptStatus.DRAFT.value,
                    PromptStatus.FAILED.value,
                ),
            )
            if connection.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "미실행 또는 실패 프롬프트만 수정할 수 있습니다.",
                )
        return self.get(prompt_id)

    def delete(self, prompt_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM prompts WHERE id = %s AND status IN (%s, %s)",
                (
                    prompt_id,
                    PromptStatus.DRAFT.value,
                    PromptStatus.FAILED.value,
                ),
            )
            if connection.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "미실행 또는 실패 프롬프트만 삭제할 수 있습니다.",
                )

    def mark_running(self, prompt_id: str) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE prompts
                SET status = %s, error_message = NULL, output = NULL,
                    started_at = %s, completed_at = NULL, updated_at = %s
                WHERE id = %s AND status IN (%s, %s)
                """,
                (
                    PromptStatus.RUNNING.value,
                    now,
                    now,
                    prompt_id,
                    PromptStatus.DRAFT.value,
                    PromptStatus.FAILED.value,
                ),
            )
            if connection.rowcount == 0:
                self._raise_mutation_error(
                    connection,
                    prompt_id,
                    "미실행 또는 실패 프롬프트만 실행할 수 있습니다.",
                )
        return self.get(prompt_id)

    def mark_completed(
        self,
        prompt_id: str,
        *,
        output: str,
    ) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE prompts
                SET status = %s, output = %s, completed_at = %s, updated_at = %s
                WHERE id = %s AND status = %s
                """,
                (
                    PromptStatus.COMPLETED.value,
                    output,
                    now,
                    now,
                    prompt_id,
                    PromptStatus.RUNNING.value,
                ),
            )
            if connection.rowcount == 0:
                raise PromptStateConflictError("진행중인 프롬프트가 아닙니다.")
        return self.get(prompt_id)

    def mark_failed(self, prompt_id: str, error_message: str) -> PromptRead:
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE prompts
                SET status = %s, error_message = %s, started_at = NULL,
                    completed_at = NULL, updated_at = %s
                WHERE id = %s AND status = %s
                """,
                (
                    PromptStatus.FAILED.value,
                    error_message,
                    now,
                    prompt_id,
                    PromptStatus.RUNNING.value,
                ),
            )
            if connection.rowcount == 0:
                raise PromptStateConflictError("진행중인 프롬프트가 아닙니다.")
        return self.get(prompt_id)

    def recover_interrupted(self) -> int:
        now = current_time_ms()
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE prompts
                SET status = %s, error_message = %s, started_at = NULL,
                    completed_at = NULL, updated_at = %s
                WHERE status = %s
                """,
                (
                    PromptStatus.FAILED.value,
                    "서버가 재시작되어 실행이 중단되었습니다. 다시 실행해 주세요.",
                    now,
                    PromptStatus.RUNNING.value,
                ),
            )
            return connection.rowcount

    @staticmethod
    def _list_page(
        connection: DictCursor,
        prompt_status: PromptStatus,
        page: int,
        page_size: int,
    ) -> PromptPage:
        connection.execute(
            "SELECT COUNT(*) AS total FROM prompts WHERE status = %s",
            (prompt_status.value,),
        )
        total = connection.fetchone()["total"]
        connection.execute(
            f"""
            SELECT {PROMPT_COLUMNS}
            FROM prompts
            WHERE status = %s
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (prompt_status.value, page_size, (page - 1) * page_size),
        )
        rows = connection.fetchall()
        total_pages = (total + page_size - 1) // page_size
        return PromptPage(
            items=[row_to_prompt(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
        )

    @staticmethod
    def _raise_mutation_error(
        connection: DictCursor,
        prompt_id: str,
        conflict_message: str,
    ) -> None:
        connection.execute(
            "SELECT 1 FROM prompts WHERE id = %s",
            (prompt_id,),
        )
        exists = connection.fetchone()
        if exists is None:
            raise PromptNotFoundError(prompt_id)
        raise PromptStateConflictError(conflict_message)


@lru_cache
def get_prompt_repository() -> PromptRepository:
    return PromptRepository(get_database())
