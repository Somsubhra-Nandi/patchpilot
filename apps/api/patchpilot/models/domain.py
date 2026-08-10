import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from patchpilot.db.base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    owner: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(511), unique=True, index=True)
    github_url: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    test_command: Mapped[str | None] = mapped_column(String(1024))
    lint_command: Mapped[str | None] = mapped_column(String(1024))
    protected_paths: Mapped[list[str]] = mapped_column(JSONType, default=list)
    coding_guidelines: Mapped[str | None] = mapped_column(Text)
    autonomy_level: Mapped[str] = mapped_column(String(32), default="approval_required")

    tasks: Mapped[list["AgentTask"]] = relationship(back_populates="repository")


class AgentTask(Base, TimestampMixin):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    github_issue_number: Mapped[int]
    github_issue_url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="created", index=True)
    current_stage: Mapped[str] = mapped_column(String(64), default="message_received")
    origin_channel: Mapped[str] = mapped_column(String(64), default="web")
    origin_sender: Mapped[str] = mapped_column(String(512), default="maintainer")
    origin_conversation_id: Mapped[str | None] = mapped_column(String(512))
    assigned_maintainer: Mapped[str | None] = mapped_column(String(512))
    branch_name: Mapped[str | None] = mapped_column(String(255))
    pull_request_url: Mapped[str | None] = mapped_column(String(1024))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    coding_agent_provider: Mapped[str | None] = mapped_column(String(64))
    external_session_id: Mapped[str | None] = mapped_column(String(512), index=True)
    agent_execution_status: Mapped[str | None] = mapped_column(String(64), index=True)
    last_checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    last_execution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workspace_path: Mapped[str | None] = mapped_column(String(1024))
    workspace_status: Mapped[str | None] = mapped_column(String(64), index=True)
    source_commit_sha: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped[Repository] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.created_at"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["DecisionRequest"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="DecisionRequest.created_at"
    )


class DecisionRequest(Base):
    __tablename__ = "decision_requests"
    __table_args__ = (Index("ix_decision_requests_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    decision_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    recommended_option: Mapped[str | None] = mapped_column(String(128))
    requested_by_agent: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(512))
    resolved_channel: Mapped[str | None] = mapped_column(String(64))
    resolution: Mapped[str | None] = mapped_column(String(128))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    task: Mapped[AgentTask] = relationship(back_populates="decisions")


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(1024))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    channel: Mapped[str | None] = mapped_column(String(64))
    actor: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[AgentTask] = relationship(back_populates="events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tasks.id"), index=True)
    approval_type: Mapped[str] = mapped_column(String(64), default="implementation_plan")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    requested_channel: Mapped[str] = mapped_column(String(64))
    requested_from: Mapped[str | None] = mapped_column(String(512))
    responded_channel: Mapped[str | None] = mapped_column(String(64))
    responded_by: Mapped[str | None] = mapped_column(String(512))
    response_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[AgentTask] = relationship(back_populates="approvals")


class ChannelConnection(Base, TimestampMixin):
    __tablename__ = "channel_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="not_configured")
    configuration_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    external_connection_id: Mapped[str | None] = mapped_column(String(512))
    default_conversation_id: Mapped[str | None] = mapped_column(String(512))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessedInboundMessage(Base):
    __tablename__ = "processed_inbound_messages"
    __table_args__ = (UniqueConstraint("channel", "message_id", name="uq_inbound_channel_message"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(String(512))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_tasks.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
