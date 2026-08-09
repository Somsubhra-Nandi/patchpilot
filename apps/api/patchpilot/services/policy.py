from pydantic import BaseModel, Field

from patchpilot.models.enums import PolicyDecision


class PolicyInput(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    diff_lines: int = 0
    validation_failures: int = 0


class PolicyResult(BaseModel):
    decision: PolicyDecision
    reason: str
    decision_type: str | None = None
    risk_level: str = "low"


def evaluate_policy(data: PolicyInput) -> PolicyResult:
    normalized = [path.replace("\\", "/").lower() for path in data.changed_files]
    protected = [path.replace("\\", "/").lower().rstrip("/") for path in data.protected_paths]
    if any(path == prefix or path.startswith(prefix + "/") for path in normalized for prefix in protected):
        return PolicyResult(decision=PolicyDecision.BLOCK, reason="A protected repository path would be changed", decision_type="protected_path_change", risk_level="critical")
    if any(any(token in path for token in ("auth", "security", "permission", "secret")) for path in normalized):
        return PolicyResult(decision=PolicyDecision.REQUIRE_HUMAN, reason="Security-sensitive files are in scope", decision_type="security_sensitive_change", risk_level="high")
    if any("migration" in path or "alembic/versions" in path for path in normalized):
        return PolicyResult(decision=PolicyDecision.REQUIRE_HUMAN, reason="A database migration is in scope", decision_type="database_migration", risk_level="high")
    if any(path.endswith(("requirements.txt", "pyproject.toml", "package.json", "pnpm-lock.yaml")) for path in normalized):
        return PolicyResult(decision=PolicyDecision.REQUIRE_HUMAN, reason="A dependency manifest would change", decision_type="dependency_upgrade", risk_level="medium")
    if data.diff_lines > 500:
        return PolicyResult(decision=PolicyDecision.REQUIRE_HUMAN, reason="The proposed diff exceeds 500 lines", decision_type="scope_expansion", risk_level="medium")
    if data.validation_failures >= 3:
        return PolicyResult(decision=PolicyDecision.REQUIRE_HUMAN, reason="Validation retry limit was exhausted", decision_type="retry_exhausted", risk_level="medium")
    return PolicyResult(decision=PolicyDecision.CONTINUE, reason="Change is within normal source, test, or documentation bounds")
