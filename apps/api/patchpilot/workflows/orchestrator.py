from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from patchpilot.agents.coding import (
    AgentExecutionResult,
    AgentTaskContext,
    CodingAgent,
    HumanDecision,
    ValidationPlan,
)
from patchpilot.agents.factory import create_coding_agent
from patchpilot.agents.planner import create_plan, rank_files
from patchpilot.agents.workspace import WorkspaceError, WorkspaceManager
from patchpilot.caspian.protocols import CommunicationGateway, NullCommunicationGateway
from patchpilot.core.config import Settings, get_settings
from patchpilot.github.client import GitHubClient, GitHubError
from patchpilot.models import AgentTask, Approval, Repository
from patchpilot.models import DecisionRequest as DecisionModel
from patchpilot.models.enums import ApprovalStatus, TaskStatus, WorkflowStage
from patchpilot.repositories.domain import RepositoryRepository, TaskRepository
from patchpilot.schemas.domain import HumanActionRequest, TaskCreate
from patchpilot.services.policy import PolicyInput, evaluate_policy
from patchpilot.services.security import (
    ensure_paths_allowed,
    parse_validation_command,
    validate_repository_identifier,
)
from patchpilot.services.validation import (
    ApprovedValidationPlan,
    classify_validation_failure,
    review_validation_plan,
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
        coding_agent: CodingAgent | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.github = github or GitHubClient(self.settings.github_token)
        self.gateway = gateway or NullCommunicationGateway()
        self.coding_agent = coding_agent or create_coding_agent(self.settings)
        self.workspaces = WorkspaceManager(self.settings.agent_workspace_root, retain=self.settings.agent_workspace_retain)
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
        if self.coding_agent.provider == "codex":
            task.workspace_status = "preparing"
            try:
                workspace = await self.workspaces.prepare(task.id, f"{task.repository.github_url}.git", task.repository.default_branch)
            except WorkspaceError as exc:
                task.workspace_status = "failed"
                task.failure_reason = str(exc)
                self.state.transition(task, status=TaskStatus.FAILED, stage=WorkflowStage.REPOSITORY_INSPECTED, summary="Isolated repository workspace could not be prepared", details={"error": str(exc)})
                return
            task.workspace_path = str(workspace.path)
            task.source_commit_sha = workspace.source_sha
            task.workspace_status = "ready"
        context = self._agent_context(task, relevant_files)
        task.coding_agent_provider = self.coding_agent.provider
        task.agent_execution_status = "running"
        task.last_execution_at = datetime.now(UTC)
        self.tasks.event(task, event_type="agent.started", stage=WorkflowStage.AGENT_STARTED, summary=f"{self.coding_agent.provider.title()} coding agent started", details={"provider": self.coding_agent.provider}, actor=self.coding_agent.provider)
        result = await self.coding_agent.analyze(context)
        task.external_session_id = result.session_id
        task.agent_execution_status = result.status
        task.last_checkpoint = result.checkpoint.model_dump(exclude_none=True)
        task.last_execution_at = datetime.now(UTC)
        if self.coding_agent.provider == "codex":
            plan = {
                "issue_summary": result.issue_summary,
                "suspected_change": result.suspected_change,
                "relevant_files": result.relevant_files,
                "proposed_modifications": result.proposed_modifications,
                "validation_strategy": result.validation_strategy,
                "risks": result.risks,
                "open_questions": result.open_questions,
                "confidence": result.confidence,
                "validation_plan": result.validation_plan.model_dump() if result.validation_plan else None,
            }
            self.state.advance(task, stage=WorkflowStage.PLAN_GENERATED, summary="Codex analysis completed", details={"plan": plan, "decision_summary": result.summary}, event_type="agent.analysis_completed", actor="codex")
        if result.status == "decision_required" and result.decision:
            await self._request_decision(task, result.decision.model_dump())
            return
        if result.status in {"failed", "blocked"}:
            task.failure_reason = result.error or result.summary
            task.workspace_status = "failed" if task.workspace_path else task.workspace_status
            self.state.transition(task, status=TaskStatus.FAILED, stage=WorkflowStage.AGENT_STARTED, summary=result.summary, details={"error": result.error}, actor=self.coding_agent.provider)
            return
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

    async def _request_decision(self, task: AgentTask, data: dict) -> DecisionModel:
        decision = DecisionModel(task_id=task.id, requested_by_agent=self.coding_agent.provider, **data)
        self.db.add(decision)
        self.db.flush()
        task.last_checkpoint = {**(task.last_checkpoint or {}), "decision_id": str(decision.id)}
        self.state.transition(task, status=TaskStatus.WAITING_FOR_HUMAN, stage=WorkflowStage.DECISION_REQUESTED, summary=f"Agent paused: {decision.title}", details={"decision_id": str(decision.id), "risk": decision.risk_level, "options": decision.options, "recommendation": decision.recommended_option}, event_type="decision.requested", actor=self.coding_agent.provider)
        await self.gateway.broadcast_task_update(task.id, f"Human decision required\n{str(decision.id)[:8]} — {decision.title}\nRisk: {decision.risk_level.upper()}\nRecommendation: {decision.recommended_option}\nChoose: patchpilot choose {str(decision.id)[:8]} <option>")
        return decision

    async def resolve_decision(self, decision: DecisionModel, *, option: str, actor: str, channel: str, note: str | None = None) -> AgentTask:
        if decision.status != "pending":
            raise WorkflowError("Decision is no longer pending")
        valid = {str(item.get("id")) for item in decision.options}
        if option not in valid:
            raise WorkflowError(f"Invalid option {option}; choose one of {', '.join(sorted(valid))}")
        task = self.tasks.get(decision.task_id)
        if not task:
            raise WorkflowError("Decision task no longer exists")
        decision.status = "resolved"
        decision.resolution = option
        decision.resolution_note = note
        decision.resolved_by = actor
        decision.resolved_channel = channel
        decision.resolved_at = datetime.now(UTC)
        self.tasks.event(task, event_type="decision.resolved", stage=WorkflowStage.DECISION_RESOLVED, summary=f"Decision resolved from {channel} with option {option}", details={"decision_id": str(decision.id), "option": option}, channel=channel, actor=actor)
        self.state.transition(task, status=TaskStatus.AGENT_RUNNING, stage=WorkflowStage.AGENT_RESUMED, summary=f"Agent resumed after decision by {actor}", details={"session_id": task.external_session_id, "option": option}, event_type="agent.resumed", channel=channel, actor=actor)
        if self.coding_agent.provider == "codex" and task.external_session_id and task.workspace_path:
            if not task.branch_name:
                task.branch_name = f"patchpilot/issue-{task.github_issue_number}-{str(task.id)[:8]}"
                await self.workspaces.create_branch(Path(task.workspace_path), task.branch_name)
            restore = getattr(self.coding_agent, "restore_session", None)
            if restore:
                restore(task.external_session_id, task.workspace_path)
        result = await self.coding_agent.continue_task(task.external_session_id or f"fake-{task.id}", HumanDecision(option=option, actor=actor, channel=channel, note=note))
        task.agent_execution_status = result.status
        task.last_checkpoint = {**result.checkpoint.model_dump(exclude_none=True), "approved_decision_type": decision.decision_type}
        task.last_execution_at = datetime.now(UTC)
        if result.status == "blocked":
            task.failure_reason = result.summary
            self.state.transition(task, status=TaskStatus.FAILED, stage=WorkflowStage.AGENT_RESUMED, summary=result.summary)
        else:
            await self.implement(task, execution_result=result)
        return self.tasks.get(task.id) or task

    async def pause(self, task: AgentTask, decision: HumanActionRequest) -> AgentTask:
        if task.status in {TaskStatus.COMPLETED, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.WAITING_FOR_HUMAN}:
            raise InvalidTransition(f"A {task.status} task cannot be paused")
        self.state.transition(task, status=TaskStatus.AGENT_PAUSED, stage=WorkflowStage(task.current_stage), summary=f"Task paused by {decision.actor}", details={"note": decision.note}, channel=decision.channel, actor=decision.actor)
        return self.tasks.get(task.id) or task

    async def resume(self, task: AgentTask, decision: HumanActionRequest) -> AgentTask:
        if task.status != TaskStatus.AGENT_PAUSED:
            raise InvalidTransition("Only a manually paused task can be resumed")
        self.state.transition(task, status=TaskStatus.AGENT_RUNNING, stage=WorkflowStage.AGENT_RESUMED, summary=f"Task resumed by {decision.actor}", details={"note": decision.note}, channel=decision.channel, actor=decision.actor)
        if self.coding_agent.provider == "codex" and task.external_session_id and task.workspace_path:
            restore = getattr(self.coding_agent, "restore_session", None)
            if restore:
                restore(task.external_session_id, task.workspace_path)
            result = await self.coding_agent.continue_task(task.external_session_id, HumanDecision(option="resume", actor=decision.actor, channel=decision.channel, note=decision.note))
            await self.implement(task, execution_result=result)
        else:
            await self.implement(task)
        return self.tasks.get(task.id) or task

    async def approve(self, task: AgentTask, decision: HumanActionRequest) -> AgentTask:
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
        if self.coding_agent.provider == "codex" and task.external_session_id and task.workspace_path:
            task.branch_name = f"patchpilot/issue-{task.github_issue_number}-{str(task.id)[:8]}"
            await self.workspaces.create_branch(Path(task.workspace_path), task.branch_name)
            restore = getattr(self.coding_agent, "restore_session", None)
            if restore:
                restore(task.external_session_id, task.workspace_path)
            result = await self.coding_agent.continue_task(task.external_session_id, HumanDecision(option="approve", actor=decision.actor, channel=decision.channel, note=decision.note))
            await self.implement(task, execution_result=result)
        else:
            await self.implement(task)
        return self.tasks.get(task.id) or task

    async def reject(self, task: AgentTask, decision: HumanActionRequest) -> AgentTask:
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

    async def cancel(self, task: AgentTask, decision: HumanActionRequest) -> AgentTask:
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

    async def implement(self, task: AgentTask, execution_result: AgentExecutionResult | None = None) -> None:
        branch = f"patchpilot/issue-{task.github_issue_number}-{str(task.id)[:8]}"
        task.branch_name = branch
        self.state.transition(
            task,
            status=TaskStatus.IMPLEMENTING,
            stage=WorkflowStage.BRANCH_PREPARED,
            summary=f"Prepared isolated branch {branch}",
            details={"branch": branch, "simulated": not self.settings.github_write_enabled},
        )
        if self.coding_agent.provider == "codex":
            if not task.workspace_path:
                raise WorkflowError("Codex task has no isolated workspace")
            workspace_path = Path(task.workspace_path)
            if not execution_result:
                await self.workspaces.create_branch(workspace_path, branch)
                task.workspace_status = "agent_running"
                execution_result = await self.coding_agent.implement(self._agent_context(task))
            task.external_session_id = execution_result.session_id
            task.agent_execution_status = execution_result.status
            task.last_checkpoint = execution_result.checkpoint.model_dump(exclude_none=True)
            task.last_execution_at = datetime.now(UTC)
            if execution_result.status == "decision_required" and execution_result.decision:
                task.workspace_status = "paused"
                await self._request_decision(task, execution_result.decision.model_dump())
                return
            if execution_result.status in {"failed", "blocked"}:
                task.workspace_status = "failed"
                task.failure_reason = execution_result.error or execution_result.summary
                self.state.transition(task, status=TaskStatus.FAILED, stage=WorkflowStage.CHANGES_GENERATED, summary=execution_result.summary, details={"error": execution_result.error})
                return
        plan_event = next((event for event in reversed(task.events) if event.stage == "plan_generated"), None)
        plan = (plan_event.details or {}).get("plan", {}) if plan_event else {}
        if self.coding_agent.provider == "codex":
            changed_files = await self.workspaces.changed_files(Path(task.workspace_path or ""))
            diff_lines, diff_summary = await self.workspaces.diff_summary(Path(task.workspace_path or ""))
        else:
            changed_files = [path for path in plan.get("relevant_files", ["README.md"]) if not path.lower().endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock"))][:3]
            diff_lines, diff_summary = 0, "Deterministic demo proposal"
        policy = evaluate_policy(PolicyInput(changed_files=changed_files, protected_paths=task.repository.protected_paths, diff_lines=diff_lines))
        self.tasks.event(task, event_type="policy.evaluated", stage=WorkflowStage.POLICY_EVALUATED, summary=policy.reason, details=policy.model_dump(mode="json"), actor="policy")
        if policy.decision.value in {"require_human", "block"} and (task.last_checkpoint or {}).get("approved_decision_type") != policy.decision_type:
            await self._request_decision(task, {"decision_type": policy.decision_type or "protected_path_change", "title": policy.reason, "context": {"relevant_files": changed_files}, "risk_level": policy.risk_level, "options": [{"id": "approve", "label": "Proceed with explicit approval"}, {"id": "abort", "label": "Abort change"}], "recommended_option": "abort" if policy.decision.value == "block" else "approve"})
            return
        if (task.last_checkpoint or {}).get("approved_decision_type") != "protected_path_change":
            ensure_paths_allowed(changed_files, task.repository.protected_paths)
        patch_artifact = {
            "mode": "isolated_workspace" if self.coding_agent.provider == "codex" else ("safe_demo" if not self.settings.github_write_enabled else "write_requested"),
            "changed_files": changed_files,
            "diff_summary": diff_summary,
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
            details={"artifact": patch_artifact, "simulated": self.coding_agent.provider != "codex"},
        )
        proposed_validation = self._proposed_validation_plan(task, execution_result)
        self.tasks.event(
            task,
            event_type="validation.plan_proposed",
            stage=WorkflowStage.TESTS_RUN,
            summary=f"Validation plan proposed by {self.coding_agent.provider.title()}",
            details={"proposed_validation_plan": proposed_validation.model_dump()},
            actor=self.coding_agent.provider,
        )
        try:
            validation_workspace = Path(task.workspace_path) if task.workspace_path else None
            configured_validation = [
                command
                for command in (task.repository.lint_command, task.repository.test_command)
                if command
            ]
            approved_validation = review_validation_plan(
                proposed_validation,
                changed_files=changed_files,
                configured_commands=configured_validation,
                workspace=validation_workspace,
            )
        except ValueError as exc:
            task.failure_reason = str(exc)
            self.state.transition(
                task,
                status=TaskStatus.FAILED,
                stage=WorkflowStage.TESTS_RUN,
                summary="Unsafe validation plan rejected by PatchPilot",
                details={"error": str(exc), "proposed_validation_plan": proposed_validation.model_dump()},
                event_type="validation.plan_rejected",
                actor="policy",
            )
            return
        self.tasks.event(
            task,
            event_type="validation.plan_approved",
            stage=WorkflowStage.TESTS_RUN,
            summary="PatchPilot broadened the validation plan" if approved_validation.broadened_by_policy else "PatchPilot approved the validation plan",
            details={"approved_validation_plan": approved_validation.model_dump()},
            actor="policy",
        )
        self.state.transition(
            task,
            status=TaskStatus.VALIDATING,
            stage=WorkflowStage.TESTS_RUN,
            summary="Running configured validation",
        )
        results = await self._validate(
            task,
            approved_validation,
            validation_workspace,
            changed_files=changed_files,
            configured_commands=configured_validation,
        )
        final_by_command = {result["command"]: result for result in results}
        failed = any(
            result["exit_code"] != 0 and not result.get("superseded_by_replan")
            for result in final_by_command.values()
        )
        skipped = not approved_validation.commands_to_run and not results
        self.state.advance(
            task,
            stage=WorkflowStage.TESTS_RUN,
            summary=(
                "Validation failed"
                if failed
                else "Automated validation skipped with repository evidence"
                if skipped
                else "Validation completed successfully"
            ),
            details={
                "proposed_validation_plan": proposed_validation.model_dump(),
                "approved_validation_plan": approved_validation.model_dump(),
                "commands_executed": [item["command"] for item in results],
                "checks_skipped": [item.model_dump() for item in approved_validation.checks_skipped],
                "rationale": approved_validation.rationale,
                "results": results,
                "retry_count": sum(1 for item in results if item.get("retried")),
                "final_validation_result": "failed" if failed else "skipped" if skipped else "passed",
                "simulated": bool(results) and all(item["simulated"] for item in results),
            },
            event_type="validation.completed",
        )
        if failed:
            if self.coding_agent.provider == "codex":
                task.workspace_status = "paused"
                await self._request_decision(task, {"decision_type": "retry_exhausted", "title": "Validation retry limit was exhausted", "context": {"results": results, "relevant_files": changed_files}, "risk_level": "medium", "options": [{"id": "retry", "label": "Let Codex retry"}, {"id": "continue", "label": "Continue with known failure"}, {"id": "abort", "label": "Abort task"}], "recommended_option": "retry"})
            else:
                task.failure_reason = "One or more configured validation commands failed"
                self.state.transition(task, status=TaskStatus.FAILED, stage=WorkflowStage.TESTS_RUN, summary="Workflow stopped after failed validation", details={"results": results})
            return
        if self.coding_agent.provider == "codex":
            review = await self.coding_agent.review(self._agent_context(task, changed_files))
            self.tasks.event(task, event_type="agent.review_completed", stage=WorkflowStage.TESTS_RUN, summary=review.summary, details={"findings": review.findings, "status": review.status}, actor="codex")
        self.state.transition(
            task,
            status=TaskStatus.CREATING_PULL_REQUEST,
            stage=WorkflowStage.PULL_REQUEST_CREATED,
            summary="Preparing draft pull request",
        )
        pr_payload = self._draft_pr_payload(task, changed_files, results, proposed_validation, approved_validation)
        if self.settings.github_write_enabled:
            task.publishing_status = "publishing"
            try:
                if self.coding_agent.provider != "codex" or not task.workspace_path:
                    raise WorkspaceError("Real publishing requires the isolated Codex task workspace")
                if not task.approvals or any(approval.status != ApprovalStatus.APPROVED for approval in task.approvals):
                    raise WorkspaceError("All required approvals must be completed before publishing")
                if any(decision.status == "pending" for decision in task.decisions):
                    raise WorkspaceError("All required decisions must be resolved before publishing")
                if not task.source_commit_sha:
                    raise WorkspaceError("A known source commit is required before publishing")
                validate_repository_identifier(task.repository.full_name)
                ensure_paths_allowed(changed_files, task.repository.protected_paths)
                self.tasks.event(task, event_type="git.branch_created", stage=WorkflowStage.PULL_REQUEST_CREATED, summary=f"Task branch created: {branch}", details={"branch": branch}, actor="patchpilot")
                commit_sha = await self.workspaces.publish_branch(
                    Path(task.workspace_path), branch=branch,
                    default_branch=task.repository.default_branch,
                    source_sha=task.source_commit_sha, expected_files=changed_files,
                    token=self.settings.github_token or "",
                    commit_message=f"fix: {task.title}",
                )
                task.published_commit_sha = commit_sha
                self.tasks.event(task, event_type="git.commit_created", stage=WorkflowStage.PULL_REQUEST_CREATED, summary=f"Commit created: {commit_sha[:12]}", details={"branch": branch, "commit_sha": commit_sha, "changed_files": changed_files}, actor="patchpilot")
                self.tasks.event(task, event_type="git.push_succeeded", stage=WorkflowStage.PULL_REQUEST_CREATED, summary=f"Task branch pushed: {branch}", details={"branch": branch, "commit_sha": commit_sha, "force": False}, actor="patchpilot")
                pr = await self.github.create_draft_pr(
                    full_name=task.repository.full_name,
                    base_branch=task.repository.default_branch,
                    branch_name=branch,
                    title=pr_payload["title"],
                    body=pr_payload["body"],
                )
            except (GitHubError, WorkspaceError, ValueError) as exc:
                task.publishing_status = "failed"
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
            task.pull_request_number = pr.get("number")
            task.published_at = datetime.now(UTC)
            task.publishing_status = "published"
            self.state.advance(
                task,
                stage=WorkflowStage.PULL_REQUEST_CREATED,
                summary="Draft pull request created on GitHub",
                details={
                    "pull_request": pr_payload,
                    "url": task.pull_request_url,
                    "number": task.pull_request_number,
                    "commit_sha": task.published_commit_sha,
                    "simulated": False,
                },
                event_type="pull_request.created",
            )
        else:
            task.publishing_status = "safe_mode"
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
        final_message = (
            f"Draft PR created: {task.pull_request_url}"
            if task.pull_request_url
            else f"PatchPilot completed {task.repository.full_name}#{task.github_issue_number}. Validation passed; PR information is ready locally (write mode is disabled). Task: {task.id}"
        )
        await self.gateway.broadcast_task_update(task.id, final_message)
        task.workspace_status = "retained" if self.settings.agent_workspace_retain else "cleaned"
        self.workspaces.cleanup(task.id)
        self.db.commit()

    async def _validate(
        self,
        task: AgentTask,
        plan: ApprovedValidationPlan,
        workspace: Path | None = None,
        *,
        changed_files: list[str] | None = None,
        configured_commands: list[str] | None = None,
    ) -> list[dict]:
        commands = plan.commands_to_run
        checkout = workspace or self.settings.demo_repository_path
        if not commands:
            return []
        if not checkout or str(checkout).strip() in {"", "."} or not Path(checkout).is_dir():
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
        results: list[dict] = []
        command_queue = list(commands)
        nonretryable_commands: set[str] = set()
        changed_files = changed_files or []
        configured_commands = configured_commands or []
        max_replans = max(1, self.settings.agent_validation_max_attempts)
        replans = 0
        command_index = 0
        while command_index < len(command_queue):
            command = command_queue[command_index]
            command_index += 1
            argv = parse_validation_command(command)
            attempts = self.settings.agent_validation_max_attempts if workspace else 1
            for attempt in range(1, attempts + 1):
                started = time.perf_counter()
                exit_code, output_summary, executable_missing = await self._run_validation_command(
                    argv, Path(checkout)
                )
                classification = (
                    None
                    if exit_code == 0
                    else classify_validation_failure(
                        exit_code=exit_code,
                        output=output_summary,
                        executable_missing=executable_missing,
                    )
                )
                result = {
                    "command": command,
                    "exit_code": exit_code,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "output_summary": output_summary[-4000:],
                    "simulated": False,
                    "attempt": attempt,
                    "retried": attempt > 1,
                    "failure_classification": classification,
                }
                results.append(result)
                if exit_code == 0:
                    break
                if classification == "infrastructure_error" and attempt < attempts:
                    continue

                repair = await self._repair_validation_failure(
                    task,
                    command=command,
                    classification=classification or "unknown",
                    output_summary=output_summary,
                    workspace=workspace,
                    changed_files=changed_files,
                )
                if classification == "test_failure" and repair and attempt < attempts:
                    continue

                if classification in {
                    "command_not_found",
                    "invalid_test_target",
                    "missing_dependency",
                    "configuration_error",
                }:
                    nonretryable_commands.add(command)
                    if repair and repair.validation_plan and replans < max_replans:
                        corrected = review_validation_plan(
                            repair.validation_plan,
                            changed_files=changed_files,
                            configured_commands=configured_commands,
                            workspace=workspace,
                        )
                        result["replacement_validation_plan"] = corrected.model_dump()
                        replacements_added = False
                        for replacement in corrected.commands_to_run:
                            if (
                                replacement not in nonretryable_commands
                                and replacement not in command_queue
                            ):
                                command_queue.append(replacement)
                                replacements_added = True
                        if replacements_added:
                            result["superseded_by_replan"] = True
                        replans += 1
                break
        return results

    async def _run_validation_command(
        self, argv: list[str], checkout: Path
    ) -> tuple[int, str, bool]:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(checkout),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            return 127, f"Validation executable is unavailable: {argv[0]}", True
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
        except TimeoutError:
            process.kill()
            await process.wait()
            return 124, "Validation timed out after 120 seconds", False
        return (
            process.returncode if process.returncode is not None else 124,
            output.decode(errors="replace"),
            False,
        )

    async def _repair_validation_failure(
        self,
        task: AgentTask,
        *,
        command: str,
        classification: str,
        output_summary: str,
        workspace: Path | None,
        changed_files: list[str],
    ) -> AgentExecutionResult | None:
        repair = getattr(self.coding_agent, "repair_validation", None)
        if self.coding_agent.provider != "codex" or not repair or not task.external_session_id:
            return None
        try:
            result = await repair(
                task.external_session_id,
                command=command,
                failure_classification=classification,
                output_summary=output_summary,
            )
        except Exception as exc:
            self.tasks.event(
                task,
                event_type="validation.repair_failed",
                stage=WorkflowStage.TESTS_RUN,
                summary="Codex could not propose a validation repair",
                details={"command": command, "classification": classification, "error": str(exc)},
                actor="codex",
            )
            return None
        if result.status != "completed":
            return None
        if workspace:
            actual_files = await self.workspaces.changed_files(workspace)
            ensure_paths_allowed(actual_files, task.repository.protected_paths)
            if not set(actual_files).issubset(changed_files):
                self.tasks.event(
                    task,
                    event_type="validation.repair_rejected",
                    stage=WorkflowStage.TESTS_RUN,
                    summary="Validation repair changed files outside the approved scope",
                    details={"unexpected_files": sorted(set(actual_files) - set(changed_files))},
                    actor="policy",
                )
                return None
        self.tasks.event(
            task,
            event_type="validation.repair_proposed",
            stage=WorkflowStage.TESTS_RUN,
            summary="Codex responded to classified validation evidence",
            details={
                "command": command,
                "classification": classification,
                "replacement_validation_plan": (
                    result.validation_plan.model_dump() if result.validation_plan else None
                ),
            },
            actor="codex",
        )
        return result

    def _proposed_validation_plan(
        self, task: AgentTask, execution_result: AgentExecutionResult | None
    ) -> ValidationPlan:
        if execution_result and execution_result.validation_plan:
            return execution_result.validation_plan
        commands = [
            command
            for command in (task.repository.lint_command, task.repository.test_command)
            if command
        ]
        return ValidationPlan(
            commands_to_run=commands,
            checks_skipped=(
                []
                if commands
                else [
                    {
                        "command_or_check": "automated validation",
                        "reason": "The agent supplied no plan and the repository has no configured validation command.",
                    }
                ]
            ),
            rationale=(
                "Preserved configured repository validation for agents without validation-plan support."
                if commands
                else "No automated command was manufactured without repository evidence."
            ),
            relevant_test_files=[],
            validation_scope="full" if commands else "none",
            confidence="medium",
        )

    def _agent_context(self, task: AgentTask, relevant_files: list[str] | None = None) -> AgentTaskContext:
        return AgentTaskContext(task_id=task.id, repository=task.repository.full_name, issue_number=task.github_issue_number, title=task.title, description=task.description, relevant_files=relevant_files or [], protected_paths=task.repository.protected_paths, checkpoint=task.last_checkpoint or {}, workspace_path=task.workspace_path, source_commit_sha=task.source_commit_sha, coding_guidelines=task.repository.coding_guidelines, test_command=task.repository.test_command, lint_command=task.repository.lint_command)

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
    def _draft_pr_payload(task: AgentTask, changed_files: list[str], results: list[dict], proposed_validation, approved_validation) -> dict:
        approvals = [f"- {approval.approval_type}: {approval.status} by {approval.responded_by or 'pending'} via {approval.responded_channel or approval.requested_channel}" for approval in task.approvals]
        decisions = [f"- {decision.decision_type}: {decision.resolution or decision.status} by {decision.resolved_by or 'pending'}" for decision in task.decisions]
        risks: list[str] = []
        for event in reversed(task.events):
            candidate = (event.details or {}).get("plan")
            if candidate:
                risks = candidate.get("risks", [])
                break
        body = (
            f"## Related issue\n{task.github_issue_url}\n\n"
            f"## Implementation summary\n{task.title}\n\n"
            f"## Changes\n" + "\n".join(f"- `{path}`" for path in changed_files) + "\n\n"
            "## Validation plan\n"
            + f"Proposed ({proposed_validation.validation_scope}): {proposed_validation.rationale}\n"
            + "\n".join(f"- `{command}`" for command in approved_validation.commands_to_run)
            + "\n\n## Commands actually run\n"
            + "\n".join(f"- `{item['command']}`" for item in results)
            + "\n\n## Validation results\n"
            + "\n".join(f"- `{item['command']}`: exit {item['exit_code']}" for item in results)
            + "\n\n## Human approvals and decisions\n" + "\n".join([*approvals, *decisions] or ["- No additional decisions required."])
            + "\n\n## Risks\n" + "\n".join(f"- {risk}" for risk in risks or ["No specific risks identified by Codex; maintainer review is still required."])
            + "\n\n---\nPrepared by PatchPilot. Never auto-merged."
        )
        return {
            "title": f"Draft: {task.title}",
            "head": task.branch_name,
            "base": task.repository.default_branch,
            "body": body,
            "draft": True,
            "issue": task.github_issue_url,
        }
