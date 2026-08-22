from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from app.core.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    model TEXT NOT NULL CHECK (model IN ('auto', 'gpt-5.6-sol', 'claude-sonnet-5')),
    output_format TEXT NOT NULL CHECK (output_format IN ('markdown', 'plainText', 'json')),
    status TEXT NOT NULL CHECK (status IN ('draft', 'running', 'completed')),
    execution_state TEXT NOT NULL CHECK (
        execution_state IN ('idle', 'requesting', 'succeeded', 'failed')
    ),
    output TEXT,
    error_message TEXT,
    thread_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_prompts_status_updated_at
ON prompts (status, updated_at DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_path)
