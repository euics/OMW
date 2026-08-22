from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Matdathon Agent API"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    github_copilot_model: str = "auto"
    github_copilot_timeout: float = 60.0
    github_copilot_log_level: str = "info"
    github_copilot_cli_path: str | None = None
    github_copilot_instructions: str = (
        "You are an assistant for a prompt operations board. "
        "Answer in Korean unless the user requests another language. "
        "Keep responses concise and actionable."
    )

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
