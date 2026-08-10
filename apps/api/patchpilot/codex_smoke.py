"""Manual, credentialed Codex CLI smoke test. Never targets a production repository."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from patchpilot.agents.codex import CodexCodingAgent
from patchpilot.agents.coding import AgentTaskContext
from patchpilot.core.config import get_settings


async def _run(*argv: str, cwd: Path) -> None:
    process = await asyncio.create_subprocess_exec(*argv, cwd=str(cwd))
    if await process.wait():
        raise RuntimeError(f"Command failed: {argv[0]} {argv[1]}")


async def main() -> None:
    settings = get_settings()
    root = Path(tempfile.mkdtemp(prefix="patchpilot-codex-smoke-"))
    try:
        await _run("git", "init", "-b", "main", cwd=root)
        await _run("git", "config", "user.email", "smoke@patchpilot.local", cwd=root)
        await _run("git", "config", "user.name", "PatchPilot Smoke", cwd=root)
        (root / "value.txt").write_text("one\n", encoding="utf-8")
        (root / "test_value.py").write_text("def test_value():\n    assert open('value.txt').read().strip() == 'two'\n", encoding="utf-8")
        await _run("git", "add", ".", cwd=root)
        await _run("git", "commit", "-m", "smoke fixture", cwd=root)
        context = AgentTaskContext(task_id=uuid.uuid4(), repository="local/smoke", issue_number=1, title="Change value.txt from one to two so the test passes", workspace_path=str(root), test_command="pytest -q")
        result = await CodexCodingAgent(executable=settings.codex_cli_path, model=settings.codex_model, timeout=settings.codex_timeout_seconds).implement(context)
        process = await asyncio.create_subprocess_exec("pytest", "-q", cwd=str(root), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await process.communicate()
        print(json.dumps({"agent": result.model_dump(mode="json"), "validation_exit_code": process.returncode, "validation_summary": output.decode(errors="replace")[-2000:], "workspace": str(root), "retained": settings.agent_workspace_retain}, indent=2))
    finally:
        if not settings.agent_workspace_retain:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
