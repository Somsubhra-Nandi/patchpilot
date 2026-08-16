from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from patchpilot.agents.coding import AgentExecutionResult, FakeCodingAgent
from patchpilot.core.config import Settings
from patchpilot.services.validation import ApprovedValidationPlan
from patchpilot.workflows.orchestrator import WorkflowOrchestrator


def approved(command: str) -> ApprovedValidationPlan:
    return ApprovedValidationPlan(
        commands_to_run=[command],
        checks_skipped=[],
        rationale="Repository evidence supports this command.",
        relevant_test_files=[],
        validation_scope="full",
        confidence="high",
    )


@pytest.mark.asyncio
async def test_invalid_unittest_target_is_executed_once_not_three_times(db, tmp_path):
    workflow = WorkflowOrchestrator(
        db,
        settings=Settings(agent_validation_max_attempts=3),
        coding_agent=FakeCodingAgent(),
    )

    results = await workflow._validate(
        SimpleNamespace(),
        approved("python -m unittest discover -s tests -v"),
        tmp_path,
    )

    assert len(results) == 1
    assert results[0]["attempt"] == 1
    assert results[0]["failure_classification"] == "invalid_test_target"


@pytest.mark.asyncio
async def test_genuine_assertion_failure_can_trigger_agent_repair_and_retry(db, tmp_path):
    agent = SimpleNamespace(provider="codex")
    workflow = WorkflowOrchestrator(
        db,
        settings=Settings(agent_validation_max_attempts=3),
        coding_agent=agent,
    )
    workflow._run_validation_command = AsyncMock(
        side_effect=[
            (1, "AssertionError: expected 2, got 1", False),
            (0, "1 passed", False),
        ]
    )
    workflow._repair_validation_failure = AsyncMock(
        return_value=AgentExecutionResult(
            status="completed",
            session_id="session-1",
            summary="Corrected the implementation.",
        )
    )

    results = await workflow._validate(
        SimpleNamespace(),
        approved("pytest tests/test_filter.py -q"),
        tmp_path,
    )

    assert len(results) == 2
    assert results[0]["failure_classification"] == "test_failure"
    assert results[1]["exit_code"] == 0
    workflow._repair_validation_failure.assert_awaited_once()
