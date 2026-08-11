from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field

from patchpilot.agents.coding import ValidationPlan
from patchpilot.services.security import parse_validation_command


class ApprovedValidationPlan(ValidationPlan):
    broadened_by_policy: bool = False
    policy_reasons: list[str] = Field(default_factory=list)


def _normalized(paths: list[str]) -> list[str]:
    return [str(PurePosixPath(path.replace("\\", "/"))).lower() for path in paths]


def _is_docs_only(paths: list[str]) -> bool:
    normalized = _normalized(paths)
    return bool(normalized) and all(
        path.startswith(("docs/", "documentation/"))
        or PurePosixPath(path).name in {"readme.md", "contributing.md", "changelog.md"}
        or PurePosixPath(path).suffix in {".md", ".rst"}
        for path in normalized
    )


def _is_risky(paths: list[str]) -> bool:
    normalized = _normalized(paths)
    return any(
        any(token in path for token in ("security", "auth", "permission", "migration", "alembic/versions"))
        or PurePosixPath(path).name in {"pyproject.toml", "package.json", "requirements.txt", "pnpm-lock.yaml", "package-lock.json"}
        for path in normalized
    )


def _full_commands(configured_commands: list[str]) -> list[str]:
    return list(dict.fromkeys(configured_commands or ["pytest -q"]))


def review_validation_plan(
    proposed: ValidationPlan,
    *,
    changed_files: list[str],
    configured_commands: list[str],
) -> ApprovedValidationPlan:
    """Apply PatchPilot's deterministic safety floor to an agent-proposed plan."""
    for command in proposed.commands_to_run:
        parse_validation_command(command)
    for command in configured_commands:
        parse_validation_command(command)

    commands = list(dict.fromkeys(proposed.commands_to_run))
    reasons: list[str] = []
    broaden = False
    docs_only = _is_docs_only(changed_files)
    risky = _is_risky(changed_files)

    if not commands and not docs_only:
        reasons.append("Executable or unclassified changes cannot skip all validation.")
        commands = _full_commands(configured_commands)
        broaden = True
    elif not commands and not proposed.rationale.strip():
        reasons.append("A no-validation plan requires an explicit rationale.")
        commands = _full_commands(configured_commands)
        broaden = True

    if proposed.validation_scope == "targeted" and changed_files and not proposed.relevant_test_files:
        reasons.append("No targeted test mapping was identified, so full repository validation is required.")
        commands = _full_commands(configured_commands)
        broaden = True

    if risky and proposed.validation_scope != "full":
        reasons.append("Security, migration, or dependency changes require the repository's broader validation set.")
        commands = list(dict.fromkeys([*commands, *_full_commands(configured_commands)]))
        broaden = True

    scope = "full" if broaden else proposed.validation_scope
    return ApprovedValidationPlan(
        commands_to_run=commands,
        checks_skipped=proposed.checks_skipped,
        rationale=proposed.rationale,
        relevant_test_files=proposed.relevant_test_files,
        validation_scope=scope,
        confidence=proposed.confidence,
        broadened_by_policy=broaden,
        policy_reasons=reasons,
    )
