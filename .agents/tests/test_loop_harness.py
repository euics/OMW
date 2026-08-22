from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "orchestrator" / "loop_harness.py"
)
SPEC = importlib.util.spec_from_file_location("loop_harness", MODULE_PATH)
assert SPEC and SPEC.loader
loop_harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop_harness
SPEC.loader.exec_module(loop_harness)


class LoopHarnessUnitTests(unittest.TestCase):
    def test_rejects_broad_and_escaping_scopes(self) -> None:
        for value in (".", "", "../outside"):
            with self.subTest(value=value):
                with self.assertRaises(loop_harness.HarnessError):
                    loop_harness.normalize_scope(value)

    def test_path_allowed_uses_path_boundaries(self) -> None:
        self.assertTrue(
            loop_harness.path_allowed("frontend/src/App.tsx", ["frontend/src"])
        )
        self.assertFalse(
            loop_harness.path_allowed("frontend/source.ts", ["frontend/src"])
        )

    def test_extracts_fenced_json_and_validates_status(self) -> None:
        output = loop_harness.extract_json(
            '```json\n{"status":"PASS","findings":[]}\n```',
            "qa",
        )
        loop_harness.validate_role_output("qa", output)
        self.assertEqual("PASS", output["status"])

    def test_redacts_common_secret_assignments(self) -> None:
        redacted = loop_harness.redact("TOKEN=super-secret-value")
        self.assertNotIn("super-secret-value", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_security_scan_uses_unredacted_diff(self) -> None:
        raw_diff = "token=ghp_abcdefghijklmnopqrstuvwxyz123456"
        findings = loop_harness.security_findings(Path("."), [], raw_diff)
        self.assertTrue(findings)

    def test_rejects_oversized_markdown_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "docs").mkdir()
            (repo / "docs" / "large.md").write_text(
                "\n".join(f"line {index}" for index in range(4)),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=repo, check=True)

            with self.assertRaises(loop_harness.HarnessError):
                loop_harness.build_context_bundle(
                    repo,
                    ["docs"],
                    always_include=[],
                    max_files=5,
                    max_bytes=10000,
                    max_markdown_lines=3,
                    max_markdown_bytes=10000,
                )

    def test_context_records_deleted_tracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "src").mkdir()
            tracked = repo / "src" / "deleted.txt"
            tracked.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            tracked.unlink()

            bundle, manifest = loop_harness.build_context_bundle(
                repo,
                ["src"],
                always_include=[],
                max_files=5,
                max_bytes=10000,
            )

            self.assertIn("deleted in current working tree", bundle)
            self.assertEqual(
                [{"path": "src/deleted.txt", "deleted": True}],
                manifest,
            )

    def test_rejects_ignored_change_before_repository_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            workspace = Path(temp_dir) / "workspace"
            repo.mkdir()
            workspace.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / ".gitignore").write_text("generated/\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
            (workspace / "generated").mkdir()
            (workspace / "generated" / "tool").write_text(
                "malicious",
                encoding="utf-8",
            )

            with self.assertRaises(loop_harness.HarnessError):
                loop_harness.apply_developer_workspace(
                    repo,
                    workspace,
                    ["generated"],
                    {},
                    ["generated/tool"],
                )

            self.assertFalse((repo / "generated" / "tool").exists())

    def test_rejects_unplanned_change_before_any_repository_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            workspace = Path(temp_dir) / "workspace"
            repo.mkdir()
            workspace.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (workspace / "src").mkdir()
            (workspace / "src" / "approved.txt").write_text(
                "approved",
                encoding="utf-8",
            )
            (workspace / "src" / "unplanned.txt").write_text(
                "unplanned",
                encoding="utf-8",
            )

            with self.assertRaises(loop_harness.HarnessError):
                loop_harness.apply_developer_workspace(
                    repo,
                    workspace,
                    ["src"],
                    {},
                    ["src/approved.txt"],
                )

            self.assertFalse((repo / "src" / "approved.txt").exists())
            self.assertFalse((repo / "src" / "unplanned.txt").exists())

    def test_rejects_secret_before_repository_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            workspace = Path(temp_dir) / "workspace"
            repo.mkdir()
            workspace.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (workspace / "src").mkdir()
            (workspace / "src" / "secret.txt").write_text(
                "ghp_abcdefghijklmnopqrstuvwxyz123456",
                encoding="utf-8",
            )

            with self.assertRaises(loop_harness.HarnessError):
                loop_harness.apply_developer_workspace(
                    repo,
                    workspace,
                    ["src"],
                    {},
                    ["src/secret.txt"],
                )

            self.assertFalse((repo / "src" / "secret.txt").exists())


class LoopHarnessIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Harness Test"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / ".gitignore").write_text(".agents/runs/\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.txt").write_text("initial\n", encoding="utf-8")
        roles = self.repo / ".agents" / "roles"
        roles.mkdir(parents=True)
        for role in ("planner", "developer", "qa"):
            (roles / f"{role}.md").write_text(f"# {role}\n", encoding="utf-8")
        fake_agent = self.repo / ".agents" / "fake_agent.py"
        fake_agent.write_text(
            """
import json
import os
import pathlib
import sys

role, output = sys.argv[1], pathlib.Path(sys.argv[2])
loop = int(output.name.split(".")[1])
if role == "planner":
    value = {
        "status": "READY",
        "summary": "plan",
        "files": ["src/app.txt"],
        "steps": ["implement"],
        "acceptance_criteria": ["works"],
        "risks": [],
    }
elif role == "developer":
    pathlib.Path(os.environ["HOME"]).joinpath(".codexrc").write_text(
        "scratch",
        encoding="utf-8",
    )
    pathlib.Path("src/app.txt").write_text(
        f"implemented loop {loop}\\n",
        encoding="utf-8",
    )
    value = {
        "status": "DONE",
        "summary": "implemented",
        "changed_files": ["src/app.txt"],
        "checks_run": [],
        "risks": [],
    }
else:
    value = {
        "status": "FAIL" if loop == 1 else "PASS",
        "summary": "retry" if loop == 1 else "ok",
        "findings": ([{
            "severity": "blocking",
            "file": "src/app.txt",
            "reason": "first pass",
            "fix": "retry",
        }] if loop == 1 else []),
    }
output.write_text(json.dumps(value), encoding="utf-8")
""".strip()
            + "\n",
            encoding="utf-8",
        )
        config = {
            "max_loops": 5,
            "agent_timeout_seconds": 30,
            "context": {
                "max_files": 5,
                "max_bytes": 10000,
                "always_include": [],
            },
            "agent_command": [
                sys.executable,
                "-c",
                fake_agent.read_text(encoding="utf-8"),
                "{role}",
                "{output}",
            ],
            "qa_commands": [
                [
                    sys.executable,
                    "-c",
                    (
                        "import pathlib,sys; "
                        "ok='loop 2' in pathlib.Path('src/app.txt').read_text(); "
                        "print('deterministic QA passed' if ok else 'need loop 2'); "
                        "sys.exit(0 if ok else 1)"
                    ),
                ]
            ],
        }
        (self.repo / ".agents" / "config.json").write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "initial"],
            cwd=self.repo,
            check=True,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_qa_failure_returns_to_planning_and_passes_on_second_loop(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "test requirement",
                "--repo",
                str(self.repo),
                "--scope",
                "src",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        run_dir = Path(result.stdout.strip())
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual("passed", meta["status"])
        self.assertEqual(2, len(meta["loops"]))
        self.assertEqual("FAIL", meta["loops"][0]["qa"]["status"])
        self.assertEqual("PASS", meta["loops"][1]["qa"]["status"])
        for role in ("planner", "developer"):
            prompt = (run_dir / f"{role}.2.prompt.md").read_text(encoding="utf-8")
            self.assertIn("first pass", prompt)
            self.assertIn("need loop 2", prompt)

    def test_max_loop_limit_is_enforced(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "test requirement",
                "--repo",
                str(self.repo),
                "--scope",
                "src",
                "--max-loops",
                "1",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        run_dir = Path(result.stdout.strip())
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", meta["status"])
        self.assertEqual(1, len(meta["loops"]))


if __name__ == "__main__":
    unittest.main()
