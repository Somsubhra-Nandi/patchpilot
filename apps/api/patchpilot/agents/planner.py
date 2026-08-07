from __future__ import annotations

import re
from pathlib import PurePosixPath

from patchpilot.schemas.domain import PlanModel

KEY_FILES = {
    "README.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
}


def rank_files(issue_text: str, paths: list[str], limit: int = 8) -> list[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", issue_text)
        if token.lower() not in {"the", "and", "with", "from", "this", "that", "issue"}
    }
    scored: list[tuple[int, str]] = []
    for path in paths:
        lowered = path.lower()
        name_tokens = set(re.findall(r"[a-z0-9]+", lowered))
        score = len(tokens & name_tokens) * 5
        if PurePosixPath(path).name in KEY_FILES:
            score += 2
        if lowered.startswith(("src/", "app/", "apps/", "lib/")):
            score += 1
        if any(part in lowered for part in ("node_modules", "vendor/", "dist/", "lock")):
            score -= 10
        scored.append((score, path))
    ranked = [path for score, path in sorted(scored, key=lambda item: (-item[0], item[1])) if score >= 0]
    return ranked[:limit] or ["README.md"]


def create_plan(
    *, issue_title: str, issue_body: str, relevant_files: list[str], test_command: str | None
) -> PlanModel:
    requested = issue_body.strip().splitlines()[0][:240] if issue_body.strip() else issue_title
    validation = [test_command] if test_command else ["Run repository test suite (simulated in demo mode)"]
    return PlanModel(
        issue_summary=f"#{issue_title}: {requested}"[:500],
        suspected_change=(
            "The requested behavior likely spans the highest-ranked source file and its nearest "
            "test surface; confirm assumptions before expanding scope."
        ),
        relevant_files=relevant_files,
        proposed_modifications=[
            f"Implement the bounded behavior in {relevant_files[0]}",
            "Add or update regression coverage for the reported behavior",
            "Update operator-facing documentation only if configuration or behavior changes",
        ],
        validation_strategy=validation,
        risks=[
            "Repository analysis is heuristic until a maintainer confirms the plan",
            "Generated changes must not touch configured protected paths",
        ],
        open_questions=["Does the proposed scope match the maintainer's expected acceptance criteria?"],
        confidence="medium",
    )
