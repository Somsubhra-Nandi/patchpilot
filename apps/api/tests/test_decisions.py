import uuid

import pytest

from patchpilot.agents.coding import AgentTaskContext, FakeCodingAgent, HumanDecision
from patchpilot.models import Repository
from patchpilot.models.enums import PolicyDecision
from patchpilot.schemas.domain import InboundMessage, TaskCreate
from patchpilot.services.commands import CommandService, parse_command
from patchpilot.services.policy import PolicyInput, evaluate_policy
from patchpilot.workflows.orchestrator import WorkflowError, WorkflowOrchestrator


class StrategyGitHub:
    async def issue(self, full_name: str, number: int):
        return {"title": "Choose parser strategy", "body": "Decide the compatibility strategy", "labels": [], "comments": []}

    async def tree(self, full_name: str, branch: str):
        return [{"path": "src/parser.py"}, {"path": "tests/test_parser.py"}]


class RecordingGateway:
    def __init__(self):
        self.broadcasts = []

    async def send_message(self, channel, conversation_id, text):
        return None

    async def broadcast_task_update(self, task_id, text):
        self.broadcasts.append((task_id, text))


def repository(db):
    item = Repository(name="demo", owner="octo", full_name="octo/demo", github_url="https://github.com/octo/demo", protected_paths=[".github/workflows"])
    db.add(item)
    db.commit()
    return item


@pytest.mark.asyncio
async def test_fake_agent_contract_and_resume():
    agent = FakeCodingAgent()
    context = AgentTaskContext(task_id=uuid.uuid4(), repository="octo/demo", issue_number=42, title="Parser strategy", relevant_files=["src/parser.py"])
    analysis = await agent.analyze(context)
    assert analysis.status == "decision_required"
    assert analysis.decision and analysis.decision.recommended_option == "B"
    resumed = await agent.continue_task(analysis.session_id, HumanDecision(option="B", actor="maya", channel="telegram"))
    assert resumed.status == "completed"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PolicyInput(changed_files=["src/app.py"]), PolicyDecision.CONTINUE),
        (PolicyInput(changed_files=["src/auth/session.py"]), PolicyDecision.REQUIRE_HUMAN),
        (PolicyInput(changed_files=[".github/workflows/release.yml"], protected_paths=[".github/workflows"]), PolicyDecision.BLOCK),
    ],
)
def test_policy_outcomes(data, expected):
    assert evaluate_policy(data).decision == expected


@pytest.mark.asyncio
async def test_slack_task_resolved_from_telegram_with_audit(db, monkeypatch):
    monkeypatch.setenv("DEMO_REPOSITORY_PATH", "/nonexistent")
    repo = repository(db)
    gateway = RecordingGateway()
    workflow = WorkflowOrchestrator(db, github=StrategyGitHub(), gateway=gateway)
    task = await workflow.create(TaskCreate(repository_id=repo.id, github_issue_number=42, origin_channel="slack", origin_sender="maya", origin_conversation_id="C1"))
    assert task.status == "waiting_for_human"
    decision = task.decisions[0]
    task = await workflow.resolve_decision(decision, option="B", actor="maya-telegram", channel="telegram")
    assert task.status == "completed"
    assert decision.resolved_channel == "telegram"
    assert decision.resolved_by == "maya-telegram"
    assert any(event.event_type == "decision.resolved" and event.channel == "telegram" for event in task.events)
    with pytest.raises(WorkflowError, match="no longer pending"):
        await workflow.resolve_decision(decision, option="B", actor="maya", channel="slack")


@pytest.mark.asyncio
async def test_invalid_option_is_rejected(db):
    repo = repository(db)
    workflow = WorkflowOrchestrator(db, github=StrategyGitHub())
    task = await workflow.create(TaskCreate(repository_id=repo.id, github_issue_number=42))
    with pytest.raises(WorkflowError, match="Invalid option"):
        await workflow.resolve_decision(task.decisions[0], option="Z", actor="maya", channel="web")


@pytest.mark.parametrize("text,name", [("patchpilot decisions", "decisions"), ("patchpilot choose abcdef12 B", "choose"), ("patchpilot explain abcdef12", "explain"), ("patchpilot pause abcdef12", "pause"), ("patchpilot resume abcdef12", "resume")])
def test_decision_command_parsing(text, name):
    assert parse_command(text).name == name


@pytest.mark.asyncio
async def test_command_cross_channel_resolution(db, monkeypatch):
    monkeypatch.setenv("DEMO_REPOSITORY_PATH", "/nonexistent")
    repo = repository(db)
    gateway = RecordingGateway()
    workflow = WorkflowOrchestrator(db, github=StrategyGitHub(), gateway=gateway)
    task = await workflow.create(TaskCreate(repository_id=repo.id, github_issue_number=42, origin_channel="slack", origin_sender="maya"))
    service = CommandService(db, gateway)
    service.workflow = workflow
    decision = task.decisions[0]
    response = await service.process(InboundMessage(channel="telegram", sender="maya", conversation_id="T1", message_id="M1", connection_id="X", text=f"patchpilot choose {str(decision.id)[:8]} B"))
    assert response and "resolved via telegram" in response
