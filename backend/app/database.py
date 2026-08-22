from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

import pymysql
from pymysql.cursors import DictCursor

from app.core.config import get_settings

CREATE_PROMPTS_TABLE = """
CREATE TABLE IF NOT EXISTS prompts (
    id CHAR(36) PRIMARY KEY,
    title VARCHAR(80) NOT NULL,
    prompt TEXT NOT NULL,
    output_format VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    output LONGTEXT,
    error_message TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    started_at BIGINT,
    completed_at BIGINT,
    INDEX idx_prompts_status_updated_at (status, updated_at DESC),
    CONSTRAINT chk_prompts_output_format
        CHECK (output_format IN ('markdown', 'plainText', 'json')),
    CONSTRAINT chk_prompts_status
        CHECK (status IN ('draft', 'running', 'completed', 'failed'))
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""


class Database:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        name: str,
        user: str,
        password: str,
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.user = user
        self.password = password

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(CREATE_PROMPTS_TABLE)

    @contextmanager
    def connect(self) -> Iterator[DictCursor]:
        connection = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=5,
            autocommit=False,
        )
        try:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


@lru_cache
def get_database() -> Database:
    settings = get_settings()
    return Database(
        host=settings.database_host,
        port=settings.database_port,
        name=settings.database_name,
        user=settings.database_user,
        password=settings.database_password.get_secret_value(),
    )
