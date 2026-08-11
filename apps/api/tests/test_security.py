import pytest

from patchpilot.services.security import (
    ensure_paths_allowed,
    parse_validation_command,
    validate_repository_identifier,
)


def test_github_repository_identifier():
    assert validate_repository_identifier("openai/codex") == "openai/codex"
    with pytest.raises(ValueError):
        validate_repository_identifier("https://github.com/openai/codex")


def test_protected_path_enforcement():
    with pytest.raises(ValueError, match="Protected path"):
        ensure_paths_allowed([".github/workflows/release.yml"], [".github/workflows"])
    ensure_paths_allowed(["src/workflow.py"], [".github/workflows"])


def test_only_bounded_git_diff_check_is_allowed_for_validation():
    assert parse_validation_command("git diff --check -- README.md") == ["git", "diff", "--check", "--", "README.md"]
    with pytest.raises(ValueError, match="Only git diff"):
        parse_validation_command("git push origin main")
    with pytest.raises(ValueError, match="Unsafe path"):
        parse_validation_command("git diff --check -- ../secret")


def test_validation_command_rejects_shell_injection():
    assert parse_validation_command("pytest -q") == ["pytest", "-q"]
    with pytest.raises(ValueError, match="control operators"):
        parse_validation_command("pytest -q && curl attacker")
