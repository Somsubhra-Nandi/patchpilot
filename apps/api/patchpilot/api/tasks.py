from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from patchpilot.caspian.runtime import get_gateway
from patchpilot.db.session import SessionLocal, get_db
from patchpilot.models import AgentTask, TaskEvent
from patchpilot.repositories.domain import TaskRepository
from patchpilot.schemas.domain import (
    DecisionRequest,
    TaskCreate,
    TaskEventRead,
    TaskList,
    TaskRead,
)
from patchpilot.workflows.orchestrator import WorkflowError, WorkflowOrchestrator
from patchpilot.workflows.state import InvalidTransition

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def task_or_404(task_id: uuid.UUID, db: Session) -> AgentTask:
    task = TaskRepository(db).get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("", response_model=TaskList)
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    repository_id: uuid.UUID | None = None,
    origin_channel: str | None = None,
    db: Session = Depends(get_db),
) -> TaskList:
    items, total = TaskRepository(db).list(
        page=page,
        page_size=page_size,
        status=status,
        repository_id=repository_id,
        origin_channel=origin_channel,
    )
    return TaskList(items=list(items), total=total, page=page, page_size=page_size)


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(data: TaskCreate, db: Session = Depends(get_db)) -> AgentTask:
    try:
        return await WorkflowOrchestrator(db, gateway=get_gateway()).create(data)
    except WorkflowError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentTask:
    return task_or_404(task_id, db)


async def apply_decision(
    task_id: uuid.UUID, data: DecisionRequest, action: str, db: Session
) -> AgentTask:
    task = task_or_404(task_id, db)
    workflow = WorkflowOrchestrator(db, gateway=get_gateway())
    try:
        return await getattr(workflow, action)(task, data)
    except (InvalidTransition, WorkflowError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{task_id}/approve", response_model=TaskRead)
async def approve_task(
    task_id: uuid.UUID, data: DecisionRequest, db: Session = Depends(get_db)
) -> AgentTask:
    return await apply_decision(task_id, data, "approve", db)


@router.post("/{task_id}/reject", response_model=TaskRead)
async def reject_task(
    task_id: uuid.UUID, data: DecisionRequest, db: Session = Depends(get_db)
) -> AgentTask:
    return await apply_decision(task_id, data, "reject", db)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: uuid.UUID, data: DecisionRequest, db: Session = Depends(get_db)
) -> AgentTask:
    return await apply_decision(task_id, data, "cancel", db)


@router.get("/{task_id}/events", response_model=list[TaskEventRead])
def task_events(task_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TaskEvent]:
    task_or_404(task_id, db)
    return list(
        db.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.created_at, TaskEvent.id)
        ).all()
    )


async def event_stream(task_id: uuid.UUID) -> AsyncIterator[str]:
    seen: set[uuid.UUID] = set()
    idle_ticks = 0
    while True:
        with SessionLocal() as db:
            task = db.get(AgentTask, task_id)
            if not task:
                yield "event: error\ndata: {\"detail\":\"Task not found\"}\n\n"
                return
            events = db.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id, TaskEvent.id.not_in(seen))
                .order_by(TaskEvent.created_at, TaskEvent.id)
            ).all()
            for event in events:
                seen.add(event.id)
                payload = TaskEventRead.model_validate(event).model_dump(mode="json")
                yield f"id: {event.id}\nevent: task-event\ndata: {json.dumps(payload)}\n\n"
            terminal = task.status in {"completed", "failed", "rejected", "cancelled"}
        if events:
            idle_ticks = 0
        else:
            idle_ticks += 1
            if idle_ticks % 15 == 0:
                yield ": keep-alive\n\n"
        if terminal and not events:
            yield "event: end\ndata: {}\n\n"
            return
        await asyncio.sleep(1)


@router.get("/{task_id}/stream")
async def stream_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    task_or_404(task_id, db)
    return StreamingResponse(
        event_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

