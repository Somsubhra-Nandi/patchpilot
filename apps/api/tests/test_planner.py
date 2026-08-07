import pytest
from pydantic import ValidationError

from patchpilot.agents.planner import create_plan, rank_files
from patchpilot.schemas.domain import PlanModel


def test_file_ranking_is_deterministic():
    paths = ["src/auth/token.py", "tests/test_token.py", "README.md", "src/billing/invoice.py"]
    result = rank_files("Token authentication fails", paths)
    assert result[:2] == ["src/auth/token.py", "tests/test_token.py"]


def test_generated_plan_validates():
    plan = create_plan(
        issue_title="Fix token refresh",
        issue_body="Refresh should retain scopes",
        relevant_files=["src/token.py"],
        test_command="pytest -q",
    )
    assert plan.confidence == "medium"


def test_plan_requires_relevant_files():
    with pytest.raises(ValidationError):
        PlanModel(
            issue_summary="Valid summary",
            suspected_change="Valid proposed root cause",
            relevant_files=[],
            proposed_modifications=["change"],
            validation_strategy=["test"],
            risks=[],
            open_questions=[],
            confidence="high",
        )

