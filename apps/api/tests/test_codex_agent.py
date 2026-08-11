import json
import subprocess
import uuid
from pathlib import Path

import pytest

from patchpilot.agents.codex import CodexCodingAgent, strict_output_schema
from patchpilot.agents.coding import (
    AgentAnalysis,
    AgentExecutionResult,
    AgentTaskContext,
    HumanDecision,
)
from patchpilot.agents.factory import create_coding_agent
from patchpilot.agents.workspace import WorkspaceManager
from patchpilot.core.config import Settings


def context(workspace: Path) -> AgentTaskContext:
    return AgentTaskContext(task_id=uuid.uuid4(), repository="octo/demo", issue_number=42, title="Fix parser", workspace_path=str(workspace), protected_paths=[".github/workflows"])


def event_stream(payload: dict, session: str = "thread-123") -> str:
    return "\n".join([json.dumps({"type": "thread.started", "thread_id": session}), json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}})])


def object_schemas(node):
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node or "additionalProperties" in node:
            yield node
        for value in node.values():
            yield from object_schemas(value)
    elif isinstance(node, list):
        for item in node:
            yield from object_schemas(item)


def contains_keyword(node, keyword):
    if isinstance(node, dict):
        return keyword in node or any(contains_keyword(value, keyword) for value in node.values())
    if isinstance(node, list):
        return any(contains_keyword(item, keyword) for item in node)
    return False


@pytest.mark.parametrize("model", [AgentAnalysis, AgentExecutionResult])
def test_codex_schema_is_strict_recursively(model):
    schema = strict_output_schema(model)
    assert schema["additionalProperties"] is False
    objects = list(object_schemas(schema))
    assert len(objects) > 2
    assert not contains_keyword(schema, "default")
    for object_schema in objects:
        assert object_schema["additionalProperties"] is False
        assert set(object_schema["required"]) == set(object_schema.get("properties", {}))


def test_strict_execution_schema_preserves_result_contract():
    schema = strict_output_schema(AgentExecutionResult)
    assert {"status", "session_id", "summary", "checkpoint", "actions", "decision", "error", "changed_files", "validation_plan"} == set(schema["required"])
    assert "$defs" in schema
    assert "AgentDecision" in schema["$defs"]
    assert "AgentCheckpoint" in schema["$defs"]
    assert "ObservableAgentAction" in schema["$defs"]
    assert "ValidationPlan" in schema["$defs"]
    assert "SkippedValidationCheck" in schema["$defs"]


def test_provider_selection():
    assert create_coding_agent(Settings(coding_agent_provider="fake")).provider == "fake"
    assert create_coding_agent(Settings(coding_agent_provider="codex", codex_cli_path="codex-test")).provider == "codex"
    with pytest.raises(ValueError, match="Unsupported"):
        create_coding_agent(Settings(coding_agent_provider="unknown"))


@pytest.mark.asyncio
async def test_codex_analysis_mapping_and_command(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / ".git").mkdir(parents=True)
    calls = []

    async def runner(argv, cwd, timeout):
        calls.append((argv, cwd, timeout))
        return 0, event_stream({"status": "completed", "session_id": "ignored", "summary": "Analysis complete", "issue_summary": "Parser fails on legacy input", "suspected_change": "Compatibility parsing", "relevant_files": ["src/parser.py"], "proposed_modifications": ["Add adapter"], "validation_strategy": ["pytest"], "risks": [], "open_questions": [], "confidence": "high"})

    result = await CodexCodingAgent(executable="codex-test", runner=runner).analyze(context(workspace))
    assert result.session_id == "thread-123"
    assert result.relevant_files == ["src/parser.py"]
    assert calls[0][0][:3] == ["codex-test", "exec", "--json"]
    assert "--output-schema" in calls[0][0]
    assert calls[0][1] == workspace


@pytest.mark.asyncio
async def test_codex_decision_and_same_session_resume(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / ".git").mkdir(parents=True)
    outputs = [
        event_stream({"status": "decision_required", "session_id": "ignored", "summary": "Need strategy", "decision": {"decision_type": "implementation_strategy", "title": "Choose strategy", "risk_level": "medium", "options": [{"id": "B", "label": "Adapter"}], "recommended_option": "B"}}),
        event_stream({"status": "completed", "session_id": "ignored", "summary": "Resumed", "changed_files": ["src/parser.py"]}, "thread-123"),
    ]

    async def runner(argv, cwd, timeout):
        return 0, outputs.pop(0)

    agent = CodexCodingAgent(runner=runner)
    analysis = await agent.analyze(context(workspace))
    assert analysis.status == "decision_required"
    resumed = await agent.continue_task(analysis.session_id, HumanDecision(option="B", actor="maya", channel="telegram"))
    assert resumed.status == "completed"
    assert resumed.session_id == analysis.session_id


@pytest.mark.asyncio
async def test_codex_failed_execution_is_structured(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / ".git").mkdir(parents=True)

    async def runner(argv, cwd, timeout):
        return 1, "authentication failed"

    result = await CodexCodingAgent(runner=runner).implement(context(workspace))
    assert result.status == "failed"
    assert "authentication failed" in (result.error or "")


@pytest.mark.asyncio
async def test_isolated_workspace_creation_and_cleanup(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    (source / "README.md").write_text("demo", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=source, check=True, capture_output=True)
    task_id = uuid.uuid4()
    manager = WorkspaceManager(tmp_path / "workspaces", retain=False)
    info = await manager.prepare(task_id, str(source), "main")
    assert info.path != source and (info.path / ".git").exists()
    assert len(info.source_sha) == 40
    assert manager.cleanup(task_id) is True
    assert not info.path.exists()


@pytest.mark.asyncio
async def test_workspace_publishes_only_task_branch_with_real_diff(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    source = tmp_path / "source-publish"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    (source / "value.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "value.txt"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=source, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=source, check=True, capture_output=True)
    task_id = uuid.uuid4()
    manager = WorkspaceManager(tmp_path / "publish-workspaces", retain=True)
    info = await manager.prepare(task_id, str(remote), "main")
    await manager.create_branch(info.path, "patchpilot/task-1")
    (info.path / "value.txt").write_text("two\n", encoding="utf-8")
    commit = await manager.publish_branch(info.path, branch="patchpilot/task-1", default_branch="main", source_sha=info.source_sha, expected_files=["value.txt"], token="test-token", commit_message="fix: value")
    refs = subprocess.run(["git", "for-each-ref", "--format=%(refname)", "refs/heads"], cwd=remote, check=True, capture_output=True, text=True).stdout
    assert "refs/heads/patchpilot/task-1" in refs
    assert subprocess.run(["git", "rev-parse", "refs/heads/main"], cwd=remote, check=True, capture_output=True, text=True).stdout.strip() == info.source_sha
    assert len(commit) == 40


@pytest.mark.asyncio
async def test_workspace_refuses_default_branch_push(tmp_path):
    manager = WorkspaceManager(tmp_path, retain=True)
    repository = tmp_path / "repo-default"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    (repository / "value.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repository, check=True, capture_output=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    (repository / "value.txt").write_text("two", encoding="utf-8")
    with pytest.raises(Exception, match="default branch"):
        await manager.publish_branch(repository, branch="main", default_branch="main", source_sha=sha, expected_files=["value.txt"], token="token", commit_message="fix")
