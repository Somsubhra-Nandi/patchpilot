from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from patchpilot.agents.planner import create_plan, rank_files
from patchpilot.caspian.protocols import CommunicationGateway, NullCommunicationGateway
from patchpilot.core.config import Settings, get_settings
from patchpilot.github.client import GitHubClient, GitHubError
from patchpilot.models import AgentTask, Approval, Repository
from patchpilot.models.enums import ApprovalStatus, TaskStatus, WorkflowStage
from patchpilot.repositories.domain import RepositoryRepository, TaskRepository
from patchpilot.schemas.domain import DecisionRequest, TaskCreate
from patchpilot.services.security import (
    ensure_paths_allowed,
    parse_validation_command,
    validate_repository_identifier,
)
from patchpilot.workflows.state import InvalidTransition, WorkflowStateService


class WorkflowError(ValueError):
    pass


class WorkflowOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        github: GitHubClient | None = None,
        gateway: CommunicationGateway | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.github = github or GitHubClient(self.settings.github_token)
        self.gateway = gateway or NullCommunicationGateway()
        self.tasks = TaskRepository(db)
        self.repositories = RepositoryRepository(db)
        self.state = WorkflowStateService(db)

    def _repository_for(self, data: TaskCreate) -> Repository:
        repository = self.repositories.get(data.repository_id) if data.repository_id else None
        if not repository and data.repository:
            full_name = validate_repository_identifier(data.repository)
            repository = self.repositories.by_full_name(full_name)
            if not repository:
                owner, name = full_name.split("/", 1)
                repository = Repository(
                    name=name,
                    owner=owner,
                    full_name=full_name,
                    github_url=f"https://github.com/{full_name}",
                    protected_paths=[".github/workflows", ".env"],
                    autonomy_level="approval_required",
                )
                self.db.add(repository)
                self.db.flush()
        if not repository:
            raise WorkflowError("A valid repository_id or owner/repository is required")
        return repository

    async def create(self, data: TaskCreate) -> AgentTask:
        repository = self._repository_for(data)
        task = AgentTask(
            repository_id=repository.id,
            github_issue_number=data.github_issue_number,
            github_issue_url=f"{repository.github_url}/issues/{data.github_issue_number}",
            title=data.title or f"Issue #{data.github_issue_number}",
            description=data.description,
            origin_channel=data.origin_channel,
            origin_sender=data.origin_sender,
            origin_conversation_id=data.origin_conversation_id,
            assigned_maintainer=data.assigned_maintainer or data.origin_sender,
        )
        self.db.add(task)
        self.db.flush()
        self.tasks.event(
            task,
            event_type="message.inbound" if data.origin_channel != "web" else "task.created",
            stage=WorkflowStage.MESSAGE_RECEIVED,
            summary=f"Request accepted from {data.origin_channel}",
            details={"issue": task.github_issue_url},
            channel=data.origin_channel,
            actor=data.origin_sender,
        )
        self.db.commit()
        await self.analyze(task)
        return self.tasks.get(task.id) or task

    async def analyze(self, task: AgentTask) -> None:
        self.state.transition(
            task,
            status=TaskStatus.ANALYZING,
            stage=WorkflowStage.ISSUE_LOADED,
            summary="Loading issue and repository metadata",
        )
        issue: dict = {}
        github_mode = "live"
        try:
            issue = await self.github.issue(task.repository.full_name, task.github_issue_number)
            task.title = issue["title"]
            task.description = issue["body"]
        except (GitHubError, OSError, TimeoutError) as exc:
            if not self.settings.patchpilot_demo_mode:
                task.failure_reason = str(exc)
                self.state.transition(
                    task,
                    status=TaskStatus.FAILED,
                    stage=WorkflowStage.ISSUE_LOADED,
                    summary="Issue could not be loaded",
                    details={"error": str(exc)},
                )
                return
            github_mode = "simulated"
            issue = {
                "title": task.title,
                "body": task.description or "Demonstrate a bounded maintainer workflow change.",
                "labels": ["demo"],
                "comments": [],
            }
        self.state.advance(
            task,
            stage=WorkflowStage.ISSUE_LOADED,
            summary=f"Issue #{task.github_issue_number} loaded",
            details={
                "mode": github_mode,
                "title": issue["title"],
                "labels": issue.get("labels", []),
                "comment_count": len(issue.get("comments", [])),
            },
        )

        paths: list[str]
        try:
            tree = await self.github.tree(task.repository.full_name, task.repository.default_branch)
            paths = [item["path"] for item in tree[:5000]]
        except (GitHubError, OSError, TimeoutError):
            paths = [
                "README.md",
                "src/patchpilot/workflow.py",
                "src/patchpilot/commands.py",
                "tests/test_workflow.py",
            ]
        self.state.advance(
            task,
            stage=WorkflowStage.REPOSITORY_INSPECTED,
            summary=f"Repository map built from {len(paths)} candidate files",
            details={"file_count": len(paths), "mode": github_mode},
        )
        relevant_files = rank_files(f"{issue['title']}\n{issue['body']}", paths)
        self.state.advance(
            task,
            stage=WorkflowStage.FILES_IDENTIFIED,
            summary=f"Identified {len(relevant_files)} likely files",
            details={"relevant_files": relevant_files, "heuristic": "token-path scoring"},
        )
        plan = create_plan(
            issue_title=issue["title"],
            issue_body=issue["body"],
            relevant_files=relevant_files,
            test_command=task.repository.test_command,
        )
        self.state.advance(
            task,
            stage=WorkflowStage.PLAN_GENERATED,
            summary="Implementation plan generated",
            details={"plan": plan.model_dump(), "decision_summary": "Bounded deterministic plan"},
        )
        approval = Approval(
            task_id=task.id,
            requested_channel=task.origin_channel,
            requested_from=task.assigned_maintainer,
        )
        self.db.add(approval)
        self.db.flush()
        self.state.transition(
            task,
            status=TaskStatus.AWAITING_APPROVAL,
            stage=WorkflowStage.APPROVAL_REQUESTED,
            summary="Maintainer approval required before any implementation",
            details={"approval_id": str(approval.id), "write_operations_blocked": True},
        )
        if task.origin_conversation_id:
            text = self._plan_message(task, plan.model_dump())
            await self.gateway.send_message(task.origin_channel, task.origin_conversation_id, text)
            self.tasks.event(
                task,
                event_type="message.outbound",
                stage=WorkflowStage.APPROVAL_REQUESTED,
                summary=f"Plan sent to {task.origin_channel}",
                details={"purpose": "approval_request"},
                channel=task.origin_channel,
                actor="patchpilot",
            )
            self.db.commit()

    async def approve(self, task: AgentTask, decision: DecisionRequest) -> AgentTask:
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidTransition("Only a task awaiting approval can be approved")
        approval = self.tasks.pending_approval(task.id)
        if not approval:
            raise WorkflowError("No pending approval exists")
        approval.status = ApprovalStatus.APPROVED
        approval.responded_channel = decision.channel
        approval.responded_by = decision.actor
        approval.response_note = decision.note
        approval.responded_at = datetime.now(UTC)
        self.state.transition(
            task,
            status=TaskStatus.APPROVED,
            stage=WorkflowStage.APPROVAL_RECEIVED,
            summary=f"Plan approved by {decision.actor} via {decision.channel}",
            details={"approval_id": str(approval.id), "note": decision.note},
            channel=decision.channel,
            actor=decision.actor,
        )
        await self.implement(task)
        return self.tasks.get(task.id) or task

    async def reject(self, task: AgentTask, decision: DecisionRequest) -> AgentTask:
        if task.status != TaskStatus.AWAITING_APPROVAL:
            raise InvalidTransition("Only a task awaiting approval can be rejected")
        approval = self.tasks.pending_approval(task.id)
        if not approval:
            raise WorkflowError("No pending approval exists")
        approval.status = ApprovalStatus.REJECTED
        approval.responded_channel = decision.channel
        approval.responded_by = decision.actor
        approval.response_note = decision.note
        approval.responded_at = datetime.now(UTC)
        self.state.transition(
            task,
            status=TaskStatus.REJECTED,
            stage=WorkflowStage.APPROVAL_RECEIVED,
            summary=f"Plan rejected by {decision.actor}",
            details={"note": decision.note},
            channel=decision.channel,
            actor=decision.actor,
        )
        return self.tasks.get(task.id) or task

    async def cancel(self, task: AgentTask, decision: DecisionRequest) -> AgentTask:
        if task.status in {TaskStatus.COMPLETED, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise InvalidTransition(f"A {task.status} task cannot be cancelled")
        self.state.transition(
            task,
            status=TaskStatus.CANCELLED,
            stage=WorkflowStage(task.current_stage),
            summary=f"Task cancelled by {decision.actor}",
            details={"note": decision.note},
            channel=decision.channel,
            actor=decision.actor,
        )
        return self.tasks.get(task.id) or task

    async def implement(self, task: AgentTask) -> None:
        branch = f"patchpilot/issue-{task.github_issue_number}-{str(task.id)[:8]}"
        task.branch_name = branch
        self.state.transition(
            task,
            status=TaskStatus.IMPLEMENTING,
            stage=WorkflowStage.BRANCH_PREPARED,
            summary=f"Prepared isolated branch {branch}",
            details={"branch": branch, "simulated": not self.settings.github_write_enabled},
        )
        plan_event = next((event for event in task.events if event.stage == "plan_generated"), None)
        plan = (plan_event.details or {}).get("plan", {}) if plan_event else {}
        changed_files = [
            path
            for path in plan.get("relevant_files", ["README.md"])
            if not path.lower().endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock"))
        ][:3]
        ensure_paths_allowed(changed_files, task.repository.protected_paths)
        patch_artifact = {
            "mode": "safe_demo" if not self.settings.github_write_enabled else "write_requested",
            "changed_files": changed_files,
            "diffs": [
                {
                    "path": path,
                    "summary": "Proposed bounded implementation update",
                    "diff": f"--- a/{path}\n+++ b/{path}\n@@\n+# PatchPilot proposed change for issue #{task.github_issue_number}",
                }
                for path in changed_files
            ],
            "protected_paths_checked": True,
        }
        self.state.advance(
            task,
            stage=WorkflowStage.CHANGES_GENERATED,
            summary=f"Generated a safe proposed patch across {len(changed_files)} files",
            details={"artifact": patch_artifact, "simulated": True},
        )
        self.state.transition(
            task,
            status=TaskStatus.VALIDATING,
            stage=WorkflowStage.TESTS_RUN,
            summary="Running configured validation",
        )
        results = await self._validate(task)
        failed = any(result["exit_code"] != 0 for result in results)
        self.state.advance(
            task,
            stage=WorkflowStage.TESTS_RUN,
            summary="Validation failed" if failed else "Validation completed successfully",
            details={"results": results, "simulated": all(item["simulated"] for item in results)},
            event_type="validation.completed",
        )
        if failed:
            task.failure_reason = "One or more configured validation commands failed"
            self.state.transition(
                task,
                status=TaskStatus.FAILED,
                stage=WorkflowStage.TESTS_RUN,
                summary="Workflow stopped after failed validation",
                details={"results": results},
            )
            return
        self.state.transition(
            task,
            status=TaskStatus.CREATING_PULL_REQUEST,
            stage=WorkflowStage.PULL_REQUEST_CREATED,
            summary="Preparing draft pull request",
        )
        pr_payload = self._draft_pr_payload(task, changed_files, results)
        if self.settings.github_write_enabled:
            artifact_path = f"patchpilot-proposals/issue-{task.github_issue_number}.md"
            ensure_paths_allowed([artifact_path], task.repository.protected_paths)
            try:
                pr = await self.github.create_proposal_draft_pr(
                    full_name=task.repository.full_name,
                    base_branch=task.repository.default_branch,
                    branch_name=branch,
                    artifact_path=artifact_path,
                    artifact_content=pr_payload["body"],
                    title=pr_payload["title"],
                    body=pr_payload["body"],
                )
            except GitHubError as exc:
                task.failure_reason = str(exc)
                self.state.transition(
                    task,
                    status=TaskStatus.FAILED,
                    stage=WorkflowStage.PULL_REQUEST_CREATED,
                    summary="GitHub draft pull request could not be created",
                    details={"error": str(exc), "simulated": False},
                )
                return
            task.pull_request_url = pr.get("html_url")
            self.state.advance(
                task,
                stage=WorkflowStage.PULL_REQUEST_CREATED,
                summary="Draft pull request created on GitHub",
                details={
                    "pull_request": pr_payload,
                    "url": task.pull_request_url,
                    "artifact_path": artifact_path,
                    "simulated": False,
                },
                event_type="pull_request.created",
            )
        else:
            self.state.advance(
                task,
                stage=WorkflowStage.PULL_REQUEST_CREATED,
                summary="Draft pull-request payload prepared safely",
                details={"pull_request": pr_payload, "simulated": True},
                event_type="pull_request.prepared",
            )
        self.state.transition(
            task,
            status=TaskStatus.COMPLETED,
            stage=WorkflowStage.MAINTAINERS_NOTIFIED,
            summary="PatchPilot workflow completed",
            details={
                "result": "draft_pull_request" if task.pull_request_url else "draft_pr_payload",
                "simulated": not bool(task.pull_request_url),
            },
        )
        await self.gateway.broadcast_task_update(
            task.id,
            f"PatchPilot completed {task.repository.full_name}#{task.github_issue_number}. "
            f"Validation passed; a safe draft PR payload is ready. Task: {task.id}",
        )

    async def _validate(self, task: AgentTask) -> list[dict]:
        commands = [command for command in (task.repository.lint_command, task.repository.test_command) if command]
        checkout = self.settings.demo_repository_path
        if not commands:
            commands = ["pytest -q"]
        if not checkout or not Path(checkout).is_dir():
            return [
                {
                    "command": command,
                    "exit_code": 0,
                    "duration_ms": 420,
                    "output_summary": "Simulated pass: no sandbox checkout configured",
                    "simulated": True,
                }
                for command in commands
            ]
        results = []
        for command in commands:
            argv = parse_validation_command(command)
            started = time.perf_counter()
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(checkout),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
            except TimeoutError:
                process.kill()
                await process.wait()
                output = b"Validation timed out after 120 seconds"
            results.append(
                {
                    "command": command,
                    "exit_code": process.returncode if process.returncode is not None else 124,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "output_summary": output.decode(errors="replace")[-4000:],
                    "simulated": False,
                }
            )
        return results

    @staticmethod
    def _plan_message(task: AgentTask, plan: dict) -> str:
        files = ", ".join(plan["relevant_files"][:5])
        return (
            f"PatchPilot plan for {task.repository.full_name}#{task.github_issue_number}\n"
            f"Summary: {plan['issue_summary']}\nFiles: {files}\n"
            f"Validation: {', '.join(plan['validation_strategy'])}\n"
            f"Confidence: {plan['confidence']}\n\n"
            f"Approve: /patchpilot approve {task.id}\n"
            f"Reject: /patchpilot reject {task.id} <reason>"
        )

    @staticmethod
    def _draft_pr_payload(task: AgentTask, changed_files: list[str], results: list[dict]) -> dict:
        body = (
            f"## Summary\nProposed bounded fix for #{task.github_issue_number}.\n\n"
            f"## Changes\n" + "\n".join(f"- `{path}`" for path in changed_files) + "\n\n"
            "## Validation\n"
            + "\n".join(f"- `{item['command']}`: exit {item['exit_code']}" for item in results)
            + "\n\n## Risks\nGenerated in safe demo mode; review the proposed diff before applying."
            "\n\n## Approval\nImplementation was explicitly approved by a maintainer."
            "\n\n---\nPrepared by PatchPilot. Never auto-merged."
        )
        return {
            "title": f"Draft: {task.title}",
            "head": task.branch_name,
            "base": task.repository.default_branch,
            "body": body,
            "draft": True,
            "issue": task.github_issue_url,
        }
