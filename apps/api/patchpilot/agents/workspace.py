from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,253}$")


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

    async def publish_branch(
        self,
        path: Path,
        *,
        branch: str,
        default_branch: str,
        source_sha: str,
        expected_files: list[str],
        token: str,
        commit_message: str,
    ) -> str:
        workspace = self._inside(path)
        if not token:
            raise WorkspaceError("GitHub publishing requires a token")
        if (
            not BRANCH_RE.fullmatch(branch)
            or not BRANCH_RE.fullmatch(default_branch)
            or branch.startswith("-")
            or default_branch.startswith("-")
            or ".." in branch
            or ".." in default_branch
        ):
            raise WorkspaceError("Invalid task branch name")
        if branch == default_branch:
            raise WorkspaceError("Publishing to the default branch is forbidden")
        current_branch = (await self._run("git", "branch", "--show-current", cwd=workspace)).strip()
        if current_branch != branch:
            raise WorkspaceError("Workspace is not on the expected task branch")
        head = (await self._run("git", "rev-parse", "HEAD", cwd=workspace)).strip()
        if not source_sha or head != source_sha:
            raise WorkspaceError("Workspace HEAD no longer matches the known source commit")
        actual_files = await self.changed_files(workspace)
        if actual_files != sorted(set(expected_files)):
            raise WorkspaceError("Workspace files changed after policy inspection")
        if not actual_files:
            raise WorkspaceError("There is no task diff to publish")
        await self._run("git", "add", "--", *actual_files, cwd=workspace)
        await self._run(
            "git", "-c", "user.name=PatchPilot", "-c", "user.email=patchpilot@users.noreply.github.com",
            "commit", "-m", commit_message, cwd=workspace,
        )
        commit_sha = (await self._run("git", "rev-parse", "HEAD", cwd=workspace)).strip()
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        git_env = os.environ.copy()
        git_env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        })
        await self._run(
            "git", "push", "--porcelain", "origin", f"refs/heads/{branch}:refs/heads/{branch}",
            cwd=workspace, env=git_env,
        )
        return commit_sha

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
    async def _run(*argv: str, cwd: Path, env: dict[str, str] | None = None) -> str:
        process = await asyncio.create_subprocess_exec(*argv, cwd=str(cwd), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await process.communicate()
        text = output.decode(errors="replace")
        if process.returncode:
            raise WorkspaceError(f"Workspace command failed ({argv[0]} {argv[1]}): {text[-1000:]}")
        return text
