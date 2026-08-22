#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_service() -> object:
    sys.path.insert(0, str(repo_root() / "backend"))
    from app.services.agent import CopilotAgentService

    return CopilotAgentService(
        model=os.getenv("GITHUB_COPILOT_MODEL", "auto"),
        timeout=float(os.getenv("GITHUB_COPILOT_TIMEOUT", "60")),
        log_level=os.getenv("GITHUB_COPILOT_LOG_LEVEL", "info"),
        cli_path=os.getenv("GITHUB_COPILOT_CLI_PATH"),
        token=os.getenv("GITHUB_COPILOT_TOKEN"),
        retry_attempts=int(os.getenv("GITHUB_COPILOT_RETRY_ATTEMPTS", "3")),
        retry_backoff_seconds=float(
            os.getenv("GITHUB_COPILOT_RETRY_BACKOFF_SECONDS", "0.5")
        ),
        retry_backoff_multiplier=float(
            os.getenv("GITHUB_COPILOT_RETRY_BACKOFF_MULTIPLIER", "2.0")
        ),
        retry_max_backoff_seconds=float(
            os.getenv("GITHUB_COPILOT_RETRY_MAX_BACKOFF_SECONDS", "5.0")
        ),
        fallback_model=os.getenv("GITHUB_COPILOT_FALLBACK_MODEL") or None,
        instructions=os.getenv(
            "GITHUB_COPILOT_INSTRUCTIONS",
            "Follow the supplied role instructions exactly.",
        ),
    )


async def run() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: copilot-role-adapter.py <role> <output-path>")

    role, output_path = sys.argv[1], Path(sys.argv[2])
    prompt = sys.stdin.read()
    service = None

    if role == "developer":
        write_json(
            output_path,
            {
                "status": "BLOCKED",
                "summary": (
                    "Safe developer file editing is not exposed through this adapter."
                ),
                "changed_files": [],
                "checks_run": [],
                "risks": [
                    "The adapter intentionally fails closed instead of broadening file-edit permissions.",
                ],
            },
        )
        return 0

    if role not in {"planner", "qa"}:
        write_json(
            output_path,
            {
                "status": "BLOCKED",
                "summary": f"Unsupported role: {role}",
                "risks": ["Role must be planner, developer, or qa."],
            },
        )
        return 0

    service = load_service()
    try:
        from app.schemas.prompt import OutputFormat

        response = await service.reply(prompt, output_format=OutputFormat.JSON)
        write_json(output_path, json.loads(response.reply))
        return 0
    except Exception as exc:  # fail closed, but still emit a valid JSON object
        write_json(
            output_path,
            {
                "status": "BLOCKED",
                "summary": "Copilot adapter could not complete the request.",
                "risks": [str(exc)],
            },
        )
        return 0
    finally:
        close = getattr(service, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
