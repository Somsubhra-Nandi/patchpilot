from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from patchpilot.agents.coding import AgentExecutionResult, AgentReviewResult, ValidationPlan
from patchpilot.core.config import Settings
from patchpilot.github.client import GitHubError
from patchpilot.models import (
    AgentTask,
    Approval,
    ProcessedInboundMessage,
    Repository,
)
from patchpilot.models import DecisionRequest as DecisionModel
from patchpilot.models.enums import ApprovalStatus, TaskStatus, WorkflowStage
from patchpilot.schemas.domain import DecisionRequest, InboundMessage, TaskCreate
from patchpilot.services.commands import CommandService
from patchpilot.workflows.orchestrator import WorkflowOrchestrator
from patchpilot.workflows.state import InvalidTransition


class FakeGitHub:
    def __init__(self):
        self.writes = []

    async def issue(self, full_name: str, number: int):
        return {
            "title": "Fix retry state",
            "body": "Retryable deliveries should include clear operator guidance.",
            "labels": ["bug"],
            "comments": ["Please add a regression test."],
        }

    async def tree(self, full_name: str, branch: str):
        return [
            {"path": "src/webhooks/retry.py"},
            {"path": "tests/test_retry.py"},
            {"path": "README.md"},
        ]

    async def create_draft_pr(self, **kwargs):
        self.writes.append(kwargs)
        return {"html_url": "https://github.com/octo/demo/pull/9", "number": 9}


class RecordingGateway:
    def __init__(self):
        self.messages = []
        self.broadcasts = []

    async def send_message(self, channel, conversation_id, text):
        self.messages.append((channel, conversation_id, text))

    async def broadcast_task_update(self, task_id, text):
        self.broadcasts.append((task_id, text))


class PublishingAgent:
    provider = "codex"

    async def implement(self, context):
        workspace = __import__("pathlib").Path(context.workspace_path)
        (workspace / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
        return AgentExecutionResult(status="completed", session_id="thread-publish", summary="Updated value", changed_files=["value.py"], validation_plan=ValidationPlan(commands_to_run=["ruff check value.py"], checks_skipped=[], rationale="Lint the changed Python module.", relevant_test_files=[], validation_scope="full", confidence="high"))

    async def review(self, context):
        return AgentReviewResult(status="completed", session_id="thread-publish", summary="Review complete")


class NoOpPublishingAgent(PublishingAgent):
    async def implement(self, context):
        return AgentExecutionResult(
            status="completed",
            session_id="thread-no-op",
            summary="Completed without changes",
        )


class FailingDraftGitHub(FakeGitHub):
    async def create_draft_pr(self, **kwargs):
        raise GitHubError("draft PR API unavailable")


def configured_repository(db):
    repository = Repository(
        name="demo",
        owner="octo",
        full_name="octo/demo",
        github_url="https://github.com/octo/demo",
        test_command="pytest -q",
        protected_paths=[".github/workflows"],
    )
    db.add(repository)
    db.commit()
    return repository


@pytest.mark.asyncio
async def test_approval_from_different_channel_completes_demo_workflow(db):
    repository = configured_repository(db)
    gateway = RecordingGateway()
    workflow = WorkflowOrchestrator(db, github=FakeGitHub(), gateway=gateway)
    task = await workflow.create(
        TaskCreate(
            repository_id=repository.id,
            github_issue_number=42,
            origin_channel="slack",
            origin_sender="maya",
            origin_conversation_id="slack-thread",
        )
    )
    assert task.status == "awaiting_approval"
    assert gateway.messages and gateway.messages[0][0] == "slack"
    task = await workflow.approve(
        task, DecisionRequest(actor="maya", channel="telegram", note="Looks focused")
    )
    assert task.status == "completed"
    approval = db.scalar(select(Approval).where(Approval.task_id == task.id))
    assert approval.responded_channel == "telegram"
    assert gateway.broadcasts
    assert any(event.event_type == "pull_request.prepared" for event in task.events)
    assert task.publishing_status == "safe_mode"


@pytest.mark.asyncio
async def test_duplicate_approval_is_rejected(db):
    repository = configured_repository(db)
    workflow = WorkflowOrchestrator(db, github=FakeGitHub())
    task = await workflow.create(
        TaskCreate(repository_id=repository.id, github_issue_number=4)
    )
    task = await workflow.approve(task, DecisionRequest())
    with pytest.raises(InvalidTransition):
        await workflow.approve(task, DecisionRequest())


@pytest.mark.asyncio
async def test_duplicate_message_is_idempotent(db):
    configured_repository(db)
    gateway = RecordingGateway()
    service = CommandService(db, gateway)
    inbound = InboundMessage(
        channel="slack",
        sender="maya",
        conversation_id="C1",
        message_id="M1",
        connection_id="X1",
        text="/patchpilot help",
    )
    assert await service.process(inbound)
    assert await service.process(inbound) is None
    count = len(db.scalars(select(ProcessedInboundMessage)).all())
    assert count == 1


@pytest.mark.asyncio
async def test_github_write_rejects_non_isolated_fake_agent_publishing(db):
    repository = configured_repository(db)
    github = FakeGitHub()
    settings = Settings(github_write_enabled=True, patchpilot_demo_mode=True)
    workflow = WorkflowOrchestrator(db, github=github, settings=settings)
    task = await workflow.create(
        TaskCreate(repository_id=repository.id, github_issue_number=9)
    )
    assert github.writes == []
    task = await workflow.approve(task, DecisionRequest(actor="maya", channel="telegram"))
    assert task.status == "failed"
    assert task.publishing_status == "failed"
    assert task.pull_request_url is None
    assert github.writes == []


def publishing_task(db, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=seed, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=seed, check=True)
    (seed / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=seed, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=seed, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True, capture_output=True)
    repository = Repository(name="demo", owner="octo", full_name="octo/demo", github_url=str(remote), default_branch="main", test_command="ruff check value.py", protected_paths=[".github/workflows"])
    db.add(repository)
    db.flush()
    task = AgentTask(repository_id=repository.id, github_issue_number=11, github_issue_url="https://github.com/octo/demo/issues/11", title="Update value", status=TaskStatus.APPROVED, current_stage=WorkflowStage.APPROVAL_RECEIVED, origin_channel="slack", origin_sender="maya", origin_conversation_id="thread-1", assigned_maintainer="maya", workspace_status="ready")
    db.add(task)
    db.flush()
    approval = Approval(task_id=task.id, status=ApprovalStatus.APPROVED, requested_channel="slack", requested_from="maya", responded_channel="telegram", responded_by="maya")
    db.add(approval)
    db.commit()
    workspace_root = tmp_path / "workspaces"
    settings = Settings(github_write_enabled=True, github_token="test-token", patchpilot_demo_mode=True, agent_workspace_root=workspace_root, agent_workspace_retain=True)
    return task, remote, settings


@pytest.mark.asyncio
async def test_write_mode_publishes_real_diff_and_persists_draft_pr(db, tmp_path):
    task, remote, settings = publishing_task(db, tmp_path)
    github = FakeGitHub()
    gateway = RecordingGateway()
    workflow = WorkflowOrchestrator(db, github=github, gateway=gateway, settings=settings, coding_agent=PublishingAgent())
    info = await workflow.workspaces.prepare(task.id, str(remote), "main")
    task.workspace_path = str(info.path)
    task.source_commit_sha = info.source_sha
    db.commit()
    await workflow.implement(task)
    assert task.status == "completed"
    assert task.pull_request_url == "https://github.com/octo/demo/pull/9"
    assert task.pull_request_number == 9
    assert task.published_commit_sha and task.published_at
    assert task.publishing_status == "published"
    assert github.writes[0]["branch_name"] == task.branch_name
    assert github.writes[0]["base_branch"] == "main"
    assert "Validation plan" in github.writes[0]["body"]
    assert any("Draft PR created: https://github.com/octo/demo/pull/9" in text for _, text in gateway.broadcasts)
    db.expire(task, ["events"])
    event_types = {event.event_type for event in task.events}
    assert {"git.branch_created", "git.commit_created", "git.push_succeeded", "pull_request.created"} <= event_types


@pytest.mark.asyncio
async def test_resolved_product_decision_authorizes_draft_pr_without_separate_approval(
    db, tmp_path
):
    task, remote, settings = publishing_task(db, tmp_path)
    db.delete(task.approvals[0])
    db.add(
        DecisionModel(
            task_id=task.id,
            decision_type="product_behavior",
            title="Choose overflow behavior",
            context={},
            risk_level="medium",
            options=[{"id": "first_n", "label": "Keep first N"}],
            recommended_option="first_n",
            requested_by_agent="codex",
            status="resolved",
            resolved_at=datetime.now(UTC),
            resolved_by="maya",
            resolved_channel="web",
            resolution="first_n",
        )
    )
    db.commit()
    github = FakeGitHub()
    workflow = WorkflowOrchestrator(
        db,
        github=github,
        settings=settings,
        coding_agent=PublishingAgent(),
    )
    info = await workflow.workspaces.prepare(task.id, str(remote), "main")
    task.workspace_path = str(info.path)
    task.source_commit_sha = info.source_sha
    db.commit()

    await workflow.implement(task)

    assert task.status == "completed"
    assert task.publishing_status == "published"
    assert task.pull_request_url == "https://github.com/octo/demo/pull/9"
    assert github.writes


@pytest.mark.asyncio
async def test_completed_codex_run_without_diff_stops_before_publication(db, tmp_path):
    task, remote, settings = publishing_task(db, tmp_path)
    github = FakeGitHub()
    workflow = WorkflowOrchestrator(
        db,
        github=github,
        settings=settings,
        coding_agent=NoOpPublishingAgent(),
    )
    info = await workflow.workspaces.prepare(task.id, str(remote), "main")
    task.workspace_path = str(info.path)
    task.source_commit_sha = info.source_sha
    db.commit()

    await workflow.implement(task)

    assert task.status == "failed"
    assert task.failure_reason == "Codex completed without creating a repository diff"
    assert github.writes == []


@pytest.mark.asyncio
async def test_github_api_failure_preserves_commit_and_marks_publish_failed(db, tmp_path):
    task, remote, settings = publishing_task(db, tmp_path)
    workflow = WorkflowOrchestrator(db, github=FailingDraftGitHub(), settings=settings, coding_agent=PublishingAgent())
    info = await workflow.workspaces.prepare(task.id, str(remote), "main")
    task.workspace_path = str(info.path)
    task.source_commit_sha = info.source_sha
    db.commit()
    await workflow.implement(task)
    assert task.status == "failed"
    assert task.publishing_status == "failed"
    assert task.published_commit_sha
    assert task.pull_request_url is None
