from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from patchpilot.models import AgentTask
from patchpilot.models.enums import TaskStatus, WorkflowStage
from patchpilot.repositories.domain import TaskRepository


class InvalidTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.CREATED: {TaskStatus.ANALYZING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.ANALYZING: {TaskStatus.AGENT_RUNNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.AGENT_RUNNING: {TaskStatus.IMPLEMENTING, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.AGENT_PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.AGENT_PAUSED: {TaskStatus.AGENT_RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.WAITING_FOR_HUMAN: {TaskStatus.AGENT_RUNNING, TaskStatus.REJECTED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.AWAITING_APPROVAL: {
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.APPROVED: {TaskStatus.IMPLEMENTING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.IMPLEMENTING: {TaskStatus.VALIDATING, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.AGENT_PAUSED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.VALIDATING: {
        TaskStatus.CREATING_PULL_REQUEST,
        TaskStatus.WAITING_FOR_HUMAN,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.CREATING_PULL_REQUEST: {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.REJECTED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


class WorkflowStateService:
    def __init__(self, db: Session):
        self.db = db
        self.tasks = TaskRepository(db)

    def transition(
        self,
        task: AgentTask,
        *,
        status: TaskStatus,
        stage: WorkflowStage,
        summary: str,
        details: dict | None = None,
        event_type: str = "workflow.transition",
        actor: str = "patchpilot",
        channel: str | None = None,
    ) -> None:
        if status == task.status:
            raise InvalidTransition(f"Task is already {status}")
        if status not in ALLOWED_TRANSITIONS.get(task.status, set()):
            raise InvalidTransition(f"Cannot transition task from {task.status} to {status}")
        task.status = status
        task.current_stage = stage
        if status in {
            TaskStatus.COMPLETED,
            TaskStatus.REJECTED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            task.completed_at = datetime.now(UTC)
        self.tasks.event(
            task,
            event_type=event_type,
            stage=stage,
            summary=summary,
            details=details,
            actor=actor,
            channel=channel,
        )
        self.db.commit()

    def advance(
        self,
        task: AgentTask,
        *,
        stage: WorkflowStage,
        summary: str,
        details: dict | None = None,
        event_type: str = "workflow.stage",
        actor: str = "patchpilot",
        channel: str | None = None,
    ) -> None:
        task.current_stage = stage
        self.tasks.event(
            task,
            event_type=event_type,
            stage=stage,
            summary=summary,
            details=details,
            actor=actor,
            channel=channel,
        )
        self.db.commit()
