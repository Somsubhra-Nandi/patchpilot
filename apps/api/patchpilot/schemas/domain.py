import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RepositoryCreate(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    github_url: HttpUrl | None = None
    default_branch: str = "main"
    test_command: str | None = None
    lint_command: str | None = None
    protected_paths: list[str] = Field(default_factory=lambda: [".github/workflows", ".env"])
    coding_guidelines: str | None = None
    autonomy_level: Literal["read_only", "approval_required", "bounded_write"] = (
        "approval_required"
    )

    @field_validator("protected_paths")
    @classmethod
    def safe_paths(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().replace("\\", "/").lstrip("/") for item in value if item.strip()})


class RepositoryUpdate(BaseModel):
    default_branch: str | None = None
    test_command: str | None = None
    lint_command: str | None = None
    protected_paths: list[str] | None = None
    coding_guidelines: str | None = None
    autonomy_level: Literal["read_only", "approval_required", "bounded_write"] | None = None


class RepositoryRead(ORMModel):
    id: uuid.UUID
    name: str
    owner: str
    full_name: str
    github_url: str
    default_branch: str
    test_command: str | None
    lint_command: str | None
    protected_paths: list[str]
    coding_guidelines: str | None
    autonomy_level: str
    created_at: datetime
    updated_at: datetime


class PlanModel(BaseModel):
    issue_summary: str = Field(min_length=5)
    suspected_change: str = Field(min_length=5)
    relevant_files: list[str] = Field(min_length=1)
    proposed_modifications: list[str] = Field(min_length=1)
    validation_strategy: list[str] = Field(min_length=1)
    risks: list[str]
    open_questions: list[str]
    confidence: Literal["low", "medium", "high"]


class TaskCreate(BaseModel):
    repository_id: uuid.UUID | None = None
    repository: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    github_issue_number: int = Field(gt=0)
    title: str | None = None
    description: str | None = None
    origin_channel: str = "web"
    origin_sender: str = "maintainer"
    origin_conversation_id: str | None = None
    assigned_maintainer: str | None = None


class TaskEventRead(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    event_type: str
    stage: str
    summary: str
    details: dict[str, Any]
    channel: str | None
    actor: str | None
    created_at: datetime


class ApprovalRead(ORMModel):
    id: uuid.UUID
    approval_type: str
    status: str
    requested_channel: str
    requested_from: str | None
    responded_channel: str | None
    responded_by: str | None
    response_note: str | None
    created_at: datetime
    responded_at: datetime | None


class TaskRead(ORMModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    github_issue_number: int
    github_issue_url: str
    title: str
    description: str | None
    status: str
    current_stage: str
    origin_channel: str
    origin_sender: str
    origin_conversation_id: str | None
    assigned_maintainer: str | None
    branch_name: str | None
    pull_request_url: str | None
    failure_reason: str | None
    coding_agent_provider: str | None
    external_session_id: str | None
    agent_execution_status: str | None
    last_checkpoint: dict[str, Any]
    last_execution_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    repository: RepositoryRead
    events: list[TaskEventRead] = Field(default_factory=list)
    approvals: list[ApprovalRead] = Field(default_factory=list)
    decisions: list["DecisionRead"] = Field(default_factory=list)


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int
    page: int
    page_size: int


class HumanActionRequest(BaseModel):
    actor: str = "maintainer"
    channel: str = "web"
    note: str | None = None


# Backwards-compatible name for the original approval/cancel request payload.
DecisionRequest = HumanActionRequest


class DecisionRead(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    decision_type: str
    title: str
    context: dict[str, Any]
    risk_level: str
    options: list[dict[str, Any]]
    recommended_option: str | None
    requested_by_agent: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    resolved_channel: str | None
    resolution: str | None
    resolution_note: str | None


class DecisionResolve(BaseModel):
    option: str
    actor: str = "maintainer"
    channel: str = "web"
    note: str | None = None


class ChannelRead(ORMModel):
    id: uuid.UUID
    channel_type: str
    display_name: str
    status: str
    configuration_summary: dict[str, Any]
    last_event_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InboundMessage(BaseModel):
    channel: Literal["slack", "telegram"]
    sender: str
    conversation_id: str
    message_id: str
    connection_id: str
    text: str = Field(min_length=1)
