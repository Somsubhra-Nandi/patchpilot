from __future__ import annotations

import uuid
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class AgentTaskContext(BaseModel):
    task_id: uuid.UUID
    repository: str
    issue_number: int
    title: str
    description: str | None = None
    relevant_files: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    checkpoint: dict = Field(default_factory=dict)
    workspace_path: str | None = None
    source_commit_sha: str | None = None
    coding_guidelines: str | None = None
    test_command: str | None = None
    lint_command: str | None = None


class HumanDecision(BaseModel):
    option: str
    actor: str
    channel: str
    note: str | None = None


class AgentDecisionContext(BaseModel):
    relevant_files: list[str] = Field(default_factory=list)
    observable_actions: list[str] = Field(default_factory=list)
    summary: str | None = None


class AgentDecisionOption(BaseModel):
    id: str
    label: str
    risk: Literal["low", "medium", "high", "critical"] | None = None


class ObservableAgentAction(BaseModel):
    action: str
    summary: str
    path: str | None = None
    status: Literal["completed", "attempted", "blocked", "failed"] = "completed"


class AgentCheckpoint(BaseModel):
    phase: str | None = None
    scenario: str | None = None
    selected_option: str | None = None
    decision_id: str | None = None
    summary: str | None = None


class AgentDecision(BaseModel):
    decision_type: str
    title: str
    context: AgentDecisionContext = Field(default_factory=AgentDecisionContext)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    options: list[AgentDecisionOption]
    recommended_option: str | None = None


class AgentResult(BaseModel):
    status: Literal["completed", "decision_required", "failed", "blocked"]
    session_id: str
    summary: str
    checkpoint: AgentCheckpoint = Field(default_factory=AgentCheckpoint)
    actions: list[ObservableAgentAction] = Field(default_factory=list)
    decision: AgentDecision | None = None
    error: str | None = None


class SkippedValidationCheck(BaseModel):
    command_or_check: str
    reason: str


class ValidationPlan(BaseModel):
    commands_to_run: list[str] = Field(default_factory=list)
    checks_skipped: list[SkippedValidationCheck] = Field(default_factory=list)
    rationale: str
    relevant_test_files: list[str] = Field(default_factory=list)
    validation_scope: Literal["targeted", "full", "none"]
    confidence: Literal["low", "medium", "high"]


class AgentAnalysis(AgentResult):
    issue_summary: str = "Analysis completed"
    suspected_change: str = "See agent summary"
    relevant_files: list[str] = Field(default_factory=list)
    proposed_modifications: list[str] = Field(default_factory=list)
    validation_strategy: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    validation_plan: ValidationPlan | None = None


class AgentExecutionResult(AgentResult):
    changed_files: list[str] = Field(default_factory=list)
    validation_plan: ValidationPlan | None = None


class AgentReviewResult(AgentResult):
    findings: list[str] = Field(default_factory=list)


class CodingAgent(Protocol):
    provider: str

    async def analyze(self, context: AgentTaskContext) -> AgentAnalysis: ...
    async def implement(self, context: AgentTaskContext) -> AgentExecutionResult: ...
    async def continue_task(self, session_id: str, decision: HumanDecision) -> AgentExecutionResult: ...
    async def review(self, context: AgentTaskContext) -> AgentReviewResult: ...


class FakeCodingAgent:
    """Deterministic adapter used by the demo and tests; it performs no repository writes."""

    provider = "fake"

    async def analyze(self, context: AgentTaskContext) -> AgentAnalysis:
        session = f"fake-{context.task_id}"
        if "strategy" in f"{context.title} {context.description}".lower():
            return AgentAnalysis(
                status="decision_required", session_id=session,
                summary="Implementation strategy requires maintainer judgment",
                relevant_files=context.relevant_files,
                checkpoint={"phase": "analysis", "scenario": "implementation_strategy"},
                decision=AgentDecision(
                    decision_type="implementation_strategy",
                    title="Modify core parser or add compatibility adapter?",
                    context={"relevant_files": context.relevant_files}, risk_level="medium",
                    options=[
                        {"id": "A", "label": "Modify parser core", "risk": "medium"},
                        {"id": "B", "label": "Add compatibility adapter", "risk": "low"},
                    ], recommended_option="B",
                ),
            )
        return AgentAnalysis(status="completed", session_id=session, summary="Analysis completed", relevant_files=context.relevant_files, checkpoint={"phase": "analysis_complete"})

    async def implement(self, context: AgentTaskContext) -> AgentExecutionResult:
        return AgentExecutionResult(status="completed", session_id=f"fake-{context.task_id}", summary="Safe implementation proposal generated", changed_files=context.relevant_files[:3], checkpoint={"phase": "implementation_complete"})

    async def continue_task(self, session_id: str, decision: HumanDecision) -> AgentExecutionResult:
        if decision.option.lower() in {"abort", "reject"}:
            return AgentExecutionResult(status="blocked", session_id=session_id, summary="Maintainer stopped execution", checkpoint={"phase": "stopped"})
        return AgentExecutionResult(status="completed", session_id=session_id, summary=f"Resumed with option {decision.option}", checkpoint={"phase": "resumed", "selected_option": decision.option})

    async def review(self, context: AgentTaskContext) -> AgentReviewResult:
        return AgentReviewResult(status="completed", session_id=f"fake-{context.task_id}", summary="Review completed", findings=[])
