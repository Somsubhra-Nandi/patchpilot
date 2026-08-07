import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from patchpilot.models import AgentTask, Approval, Repository, TaskEvent


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, task_id: uuid.UUID) -> AgentTask | None:
        return self.db.scalar(
            select(AgentTask)
            .where(AgentTask.id == task_id)
            .options(
                selectinload(AgentTask.repository),
                selectinload(AgentTask.events),
                selectinload(AgentTask.approvals),
            )
            .execution_options(populate_existing=True)
        )

    def list(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        repository_id: uuid.UUID | None = None,
        origin_channel: str | None = None,
    ) -> tuple[Sequence[AgentTask], int]:
        filters = []
        if status:
            filters.append(AgentTask.status == status)
        if repository_id:
            filters.append(AgentTask.repository_id == repository_id)
        if origin_channel:
            filters.append(AgentTask.origin_channel == origin_channel)
        base = select(AgentTask).where(*filters)
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = self.db.scalars(
            base.options(
                selectinload(AgentTask.repository),
                selectinload(AgentTask.events),
                selectinload(AgentTask.approvals),
            )
            .order_by(AgentTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return items, total

    def event(
        self,
        task: AgentTask,
        *,
        event_type: str,
        stage: str,
        summary: str,
        details: dict | None = None,
        channel: str | None = None,
        actor: str | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task.id,
            event_type=event_type,
            stage=stage,
            summary=summary,
            details=details or {},
            channel=channel,
            actor=actor,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def pending_approval(self, task_id: uuid.UUID) -> Approval | None:
        return self.db.scalar(
            select(Approval)
            .where(Approval.task_id == task_id, Approval.status == "pending")
            .order_by(Approval.created_at.desc())
        )


class RepositoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def by_full_name(self, full_name: str) -> Repository | None:
        return self.db.scalar(select(Repository).where(Repository.full_name == full_name))

    def get(self, repository_id: uuid.UUID) -> Repository | None:
        return self.db.get(Repository, repository_id)
