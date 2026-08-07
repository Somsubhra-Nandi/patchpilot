from __future__ import annotations

import pytest
from sqlalchemy import select

from patchpilot.core.config import Settings
from patchpilot.models import Approval, ProcessedInboundMessage, Repository
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

    async def create_proposal_draft_pr(self, **kwargs):
        self.writes.append(kwargs)
        return {"html_url": "https://github.com/octo/demo/pull/9"}


class RecordingGateway:
    def __init__(self):
        self.messages = []
        self.broadcasts = []

    async def send_message(self, channel, conversation_id, text):
        self.messages.append((channel, conversation_id, text))

    async def broadcast_task_update(self, task_id, text):
        self.broadcasts.append((task_id, text))


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
async def test_github_write_waits_for_approval_and_creates_only_draft_proposal(db):
    repository = configured_repository(db)
    github = FakeGitHub()
    settings = Settings(github_write_enabled=True, patchpilot_demo_mode=True)
    workflow = WorkflowOrchestrator(db, github=github, settings=settings)
    task = await workflow.create(
        TaskCreate(repository_id=repository.id, github_issue_number=9)
    )
    assert github.writes == []
    task = await workflow.approve(task, DecisionRequest(actor="maya", channel="telegram"))
    assert task.pull_request_url == "https://github.com/octo/demo/pull/9"
    assert len(github.writes) == 1
    write = github.writes[0]
    assert write["artifact_path"] == "patchpilot-proposals/issue-9.md"
    assert write["base_branch"] == "main"
