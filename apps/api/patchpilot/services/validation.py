from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from patchpilot.agents.coding import SkippedValidationCheck, ValidationPlan
from patchpilot.services.security import parse_validation_command

ValidationFailureType = Literal[
    "test_failure",
    "command_not_found",
    "invalid_test_target",
    "missing_dependency",
    "configuration_error",
    "infrastructure_error",
    "unknown",
]


class ApprovedValidationPlan(ValidationPlan):
    broadened_by_policy: bool = False
    policy_reasons: list[str] = Field(default_factory=list)
    repository_evidence: list[str] = Field(default_factory=list)
    rejected_commands: list[SkippedValidationCheck] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RepositoryEvidence:
    root: Path | None
    inspected_files: tuple[str, ...]
    frameworks: frozenset[str]
    known_commands: tuple[str, ...]
    test_files: tuple[str, ...]
    npm_scripts: frozenset[str]
    make_targets: frozenset[str]


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
        any(
            token in path
            for token in ("security", "auth", "permission", "migration", "alembic/versions")
        )
        or PurePosixPath(path).name
        in {
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "pnpm-lock.yaml",
            "package-lock.json",
        }
        for path in normalized
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def _repository_file(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def collect_repository_evidence(
    workspace: Path | None, configured_commands: list[str]
) -> RepositoryEvidence:
    known_commands = list(dict.fromkeys(configured_commands))
    if not workspace or not workspace.is_dir():
        inspected = ("repository-configured validation commands",) if configured_commands else ()
        return RepositoryEvidence(
            root=None,
            inspected_files=inspected,
            frameworks=frozenset(),
            known_commands=tuple(known_commands),
            test_files=(),
            npm_scripts=frozenset(),
            make_targets=frozenset(),
        )

    root = workspace.resolve()
    candidates: list[Path] = []
    for name in (
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "package.json",
        "Makefile",
        "makefile",
        "README.md",
        "README.rst",
        "CONTRIBUTING.md",
    ):
        path = root / name
        if path.is_file():
            candidates.append(path)
    candidates.extend(sorted(root.glob("requirements*.txt")))
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        candidates.extend(sorted(workflows.glob("*.y*ml")))

    inspected: list[str] = []
    texts: dict[str, str] = {}
    for path in dict.fromkeys(candidates):
        relative = _repository_file(root, path)
        inspected.append(relative)
        texts[relative] = _read_text(path)

    ignored_parts = {".git", ".venv", "venv", "node_modules", ".next"}
    test_paths: list[Path] = []
    for pattern in ("test_*.py", "*_test.py", "*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts"):
        for path in root.rglob(pattern):
            if not ignored_parts.intersection(path.relative_to(root).parts):
                test_paths.append(path)
            if len(test_paths) >= 500:
                break
        if len(test_paths) >= 500:
            break
    test_files = tuple(
        sorted({_repository_file(root, path) for path in test_paths if path.is_file()})
    )
    inspected.extend(path for path in test_files[:50] if path not in inspected)

    all_text = "\n".join(texts.values()).lower()
    test_text = "\n".join(_read_text(root / path) for path in test_files[:50]).lower()
    frameworks: set[str] = set()
    if (
        (root / "pytest.ini").is_file()
        or "[tool.pytest" in all_text
        or re.search(r"(^|[\s\"'=<>])pytest([\s\"'=<>]|$)", all_text)
        or "import pytest" in test_text
    ):
        frameworks.add("pytest")
        known_commands.append("pytest -q")
    if "unittest" in all_text or "import unittest" in test_text:
        frameworks.add("unittest")
    if "[tool.ruff" in all_text or re.search(r"(^|[\s\"'=<>])ruff([\s\"'=<>]|$)", all_text):
        frameworks.add("ruff")

    npm_scripts: set[str] = set()
    package_path = root / "package.json"
    if package_path.is_file():
        try:
            package = json.loads(_read_text(package_path))
            npm_scripts = set((package.get("scripts") or {}).keys())
        except (json.JSONDecodeError, AttributeError):
            npm_scripts = set()
        if "test" in npm_scripts:
            known_commands.append("npm test")

    make_targets: set[str] = set()
    for make_name in ("Makefile", "makefile"):
        make_text = texts.get(make_name, "")
        make_targets.update(
            match.group(1)
            for match in re.finditer(r"(?m)^([A-Za-z0-9_.-]+)\s*:(?!=)", make_text)
        )
    if "test" in make_targets:
        known_commands.append("make test")

    return RepositoryEvidence(
        root=root,
        inspected_files=tuple(dict.fromkeys(inspected)),
        frameworks=frozenset(frameworks),
        known_commands=tuple(dict.fromkeys(known_commands)),
        test_files=test_files,
        npm_scripts=frozenset(npm_scripts),
        make_targets=frozenset(make_targets),
    )


def _target_reason(argv: list[str], evidence: RepositoryEvidence) -> str | None:
    if not evidence.root:
        return None
    root = evidence.root
    if (
        len(argv) >= 3
        and argv[:3] in (["python", "-m", "unittest"], ["python3", "-m", "unittest"])
        and "-s" in argv
    ):
        index = argv.index("-s") + 1
        if index >= len(argv):
            return "unittest discovery has no start directory after -s"
        target = argv[index]
        if not (root / target).is_dir():
            return f"unittest discovery start directory does not exist: {target}"

    is_pytest = argv[0] == "pytest" or (
        len(argv) >= 3 and argv[0] in {"python", "python3"} and argv[1:3] == ["-m", "pytest"]
    )
    if is_pytest:
        for target in evidence.test_files:
            if target and not (root / target).exists():
                return f"proposed relevant test file does not exist: {target}"
    return None


def command_evidence(
    command: str,
    evidence: RepositoryEvidence,
    configured_commands: list[str],
    relevant_test_files: list[str] | None = None,
) -> tuple[bool, str]:
    argv = parse_validation_command(command)
    if evidence.root and relevant_test_files:
        for target in relevant_test_files:
            if not (evidence.root / target).exists():
                return False, f"relevant test target does not exist: {target}"
    if target_reason := _target_reason(argv, evidence):
        return False, target_reason
    if command in configured_commands:
        return True, "repository-configured validation command"

    is_pytest = argv[0] == "pytest" or (
        len(argv) >= 3 and argv[0] in {"python", "python3"} and argv[1:3] == ["-m", "pytest"]
    )
    if is_pytest:
        return (
            (True, "pytest configuration, dependency, CI, or test imports were found")
            if "pytest" in evidence.frameworks
            else (False, "no repository evidence supports pytest")
        )

    is_unittest = (
        len(argv) >= 3
        and argv[0] in {"python", "python3"}
        and argv[1:3] == ["-m", "unittest"]
    )
    if is_unittest:
        return (
            (True, "unittest usage or imports were found")
            if "unittest" in evidence.frameworks
            else (False, "no repository evidence supports unittest discovery")
        )

    if argv[0] == "ruff":
        return (
            (True, "ruff configuration or dependency evidence was found")
            if "ruff" in evidence.frameworks
            else (False, "no repository evidence supports ruff")
        )
    if argv[0] in {"npm", "pnpm", "yarn"}:
        script = "test" if argv[1:2] == ["test"] else argv[2] if argv[1:2] == ["run"] and len(argv) > 2 else None
        return (
            (True, f"package.json defines the {script} script")
            if script and script in evidence.npm_scripts
            else (False, "package.json does not define the requested script")
        )
    if argv[0] == "make":
        target = argv[1] if len(argv) > 1 else None
        return (
            (True, f"Makefile defines the {target} target")
            if target and target in evidence.make_targets
            else (False, "Makefile does not define the requested target")
        )
    if argv[0] == "cargo":
        return (
            (True, "Cargo.toml exists")
            if evidence.root and (evidence.root / "Cargo.toml").is_file()
            else (False, "Cargo.toml was not found")
        )
    if argv[0] == "go":
        return (
            (True, "go.mod exists")
            if evidence.root and (evidence.root / "go.mod").is_file()
            else (False, "go.mod was not found")
        )
    if argv[0] == "git":
        return True, "git diff check is scoped to explicit repository paths"
    return False, "the command is safe but has no supporting repository evidence"


def _supported_commands(
    commands: list[str], evidence: RepositoryEvidence, configured_commands: list[str]
) -> list[str]:
    return [
        command
        for command in commands
        if command_evidence(command, evidence, configured_commands)[0]
    ]


def review_validation_plan(
    proposed: ValidationPlan,
    *,
    changed_files: list[str],
    configured_commands: list[str],
    workspace: Path | None = None,
) -> ApprovedValidationPlan:
    """Approve only safe validation supported by observable repository evidence."""
    for command in [*proposed.commands_to_run, *configured_commands]:
        parse_validation_command(command)

    evidence = collect_repository_evidence(workspace, configured_commands)
    commands: list[str] = []
    rejected: list[SkippedValidationCheck] = []
    for command in dict.fromkeys(proposed.commands_to_run):
        supported, reason = command_evidence(
            command, evidence, configured_commands, proposed.relevant_test_files
        )
        if supported:
            commands.append(command)
        else:
            rejected.append(SkippedValidationCheck(command_or_check=command, reason=reason))

    fallback = _supported_commands(
        list(evidence.known_commands), evidence, configured_commands
    )
    reasons: list[str] = []
    broaden = False
    docs_only = _is_docs_only(changed_files)
    risky = _is_risky(changed_files)

    if rejected:
        reasons.append("Unsupported proposed validation commands were rejected using repository evidence.")

    if not commands and not docs_only and fallback:
        commands = fallback
        reasons.append("Used the repository's known validation command because no proposal was supportable.")
        broaden = True
    elif not commands and not docs_only:
        reasons.append("No repository-backed automated validation command was found; automated tests are skipped.")

    if proposed.validation_scope == "targeted" and commands and not proposed.relevant_test_files:
        if fallback:
            reasons.append(
                "No targeted test mapping was identified, so repository-wide validation is required."
            )
            commands = fallback
        else:
            reasons.append(
                "No targeted mapping or repository-wide command was found; automated tests are skipped."
            )
            commands = []
        broaden = True

    if risky and proposed.validation_scope != "full":
        reasons.append(
            "Security, migration, or dependency changes require the repository's broader validation set."
        )
        commands = list(dict.fromkeys([*commands, *fallback]))
        broaden = True
        if not commands:
            reasons.append(
                "No broader automated command is supported; maintainers must review the recorded risk."
            )

    skipped = [*proposed.checks_skipped, *rejected]
    if not commands and not any(
        check.command_or_check == "automated validation" for check in skipped
    ):
        skipped.append(
            SkippedValidationCheck(
                command_or_check="automated validation",
                reason=(
                    "Documentation-only change; no executable-code validation is required."
                    if docs_only
                    else "No applicable automated command was supported by inspected repository evidence."
                ),
            )
        )

    scope = "full" if broaden and commands else "none" if not commands else proposed.validation_scope
    return ApprovedValidationPlan(
        commands_to_run=list(dict.fromkeys(commands)),
        checks_skipped=skipped,
        rationale=proposed.rationale,
        relevant_test_files=proposed.relevant_test_files,
        validation_scope=scope,
        confidence=proposed.confidence,
        broadened_by_policy=broaden,
        policy_reasons=reasons,
        repository_evidence=list(evidence.inspected_files),
        rejected_commands=rejected,
    )


def classify_validation_failure(
    *, exit_code: int, output: str, executable_missing: bool = False
) -> ValidationFailureType:
    normalized = output.lower()
    if executable_missing or exit_code == 127:
        return "command_not_found"
    if exit_code == 124 or any(
        text in normalized
        for text in ("timed out", "temporary failure", "connection reset", "resource unavailable")
    ):
        return "infrastructure_error"
    if any(
        text in normalized
        for text in (
            "start directory is not importable",
            "file or directory not found",
            "not found: tests/",
            "no tests found for given includes",
            "cannot find test target",
        )
    ):
        return "invalid_test_target"
    if any(
        text in normalized
        for text in (
            "modulenotfounderror",
            "no module named",
            "cannot find module",
            "could not resolve dependency",
        )
    ):
        return "missing_dependency"
    if any(
        text in normalized
        for text in (
            "error parsing",
            "failed to parse",
            "configuration error",
            "invalid configuration",
            "error: usage:",
        )
    ):
        return "configuration_error"
    if any(
        text in normalized
        for text in ("assertionerror", "failed (failures=", " failed ", "failures", "tests failed")
    ):
        return "test_failure"
    return "unknown"
