from __future__ import annotations

import asyncio
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceInfo:
    path: Path
    source_sha: str


class WorkspaceManager:
    def __init__(self, root: Path, *, retain: bool = True) -> None:
        self.root = root.resolve()
        self.retain = retain

    def path_for(self, task_id: uuid.UUID) -> Path:
        path = (self.root / str(task_id)).resolve()
        if path.parent != self.root:
            raise WorkspaceError("Workspace escaped the configured root")
        return path

    async def prepare(self, task_id: uuid.UUID, clone_url: str, branch: str) -> WorkspaceInfo:
        path = self.path_for(task_id)
        if path.exists():
            raise WorkspaceError(f"Workspace already exists for task {task_id}")
        self.root.mkdir(parents=True, exist_ok=True)
        await self._run("git", "clone", "--no-tags", "--single-branch", "--branch", branch, "--", clone_url, str(path), cwd=self.root)
        sha = (await self._run("git", "rev-parse", "HEAD", cwd=path)).strip()
        return WorkspaceInfo(path=path, source_sha=sha)

    async def create_branch(self, path: Path, branch: str) -> None:
        await self._run("git", "switch", "-c", branch, cwd=self._inside(path))

    async def changed_files(self, path: Path) -> list[str]:
        output = await self._run("git", "status", "--porcelain=v1", "-z", cwd=self._inside(path))
        return sorted({entry[3:] for entry in output.split("\0") if len(entry) > 3})

    async def diff_summary(self, path: Path) -> tuple[int, str]:
        workspace = self._inside(path)
        numstat = await self._run("git", "diff", "--numstat", "HEAD", cwd=workspace)
        lines = sum(int(value) for row in numstat.splitlines() for value in row.split("\t")[:2] if value.isdigit())
        stat = await self._run("git", "diff", "--stat", "HEAD", cwd=workspace)
        return lines, stat[-4000:]

    def cleanup(self, task_id: uuid.UUID) -> bool:
        path = self.path_for(task_id)
        if self.retain or not path.exists():
            return False
        shutil.rmtree(path)
        return True

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceError("Command path is outside the workspace root")
        return resolved

    @staticmethod
    async def _run(*argv: str, cwd: Path) -> str:
        process = await asyncio.create_subprocess_exec(*argv, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await process.communicate()
        text = output.decode(errors="replace")
        if process.returncode:
            raise WorkspaceError(f"Workspace command failed ({argv[0]} {argv[1]}): {text[-1000:]}")
        return text
