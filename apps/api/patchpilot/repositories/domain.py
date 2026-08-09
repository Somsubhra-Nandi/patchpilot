import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from patchpilot.models import AgentTask, Approval, DecisionRequest, Repository, TaskEvent


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
                selectinload(AgentTask.decisions),
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
                selectinload(AgentTask.decisions),
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


class DecisionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, decision_id: uuid.UUID) -> DecisionRequest | None:
        return self.db.scalar(select(DecisionRequest).where(DecisionRequest.id == decision_id).options(selectinload(DecisionRequest.task).selectinload(AgentTask.repository)))

    def resolve_prefix(self, prefix: str) -> DecisionRequest | None:
        matches = [item for item in self.db.scalars(select(DecisionRequest)).all() if str(item.id).startswith(prefix.lower())]
        if len(matches) > 1:
            raise ValueError(f"Decision prefix {prefix} is ambiguous")
        return matches[0] if matches else None

    def list(self, *, status: str | None = None, task_id: uuid.UUID | None = None, risk_level: str | None = None) -> Sequence[DecisionRequest]:
        filters = []
        if status:
            filters.append(DecisionRequest.status == status)
        if task_id:
            filters.append(DecisionRequest.task_id == task_id)
        if risk_level:
            filters.append(DecisionRequest.risk_level == risk_level)
        return self.db.scalars(select(DecisionRequest).where(*filters).order_by(DecisionRequest.created_at.desc())).all()


class RepositoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def by_full_name(self, full_name: str) -> Repository | None:
        return self.db.scalar(select(Repository).where(Repository.full_name == full_name))

    def get(self, repository_id: uuid.UUID) -> Repository | None:
        return self.db.get(Repository, repository_id)
