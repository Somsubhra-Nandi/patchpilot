import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from patchpilot.caspian.runtime import get_gateway
from patchpilot.db.session import get_db
from patchpilot.models import DecisionRequest
from patchpilot.repositories.domain import DecisionRepository
from patchpilot.schemas.domain import DecisionRead, DecisionResolve
from patchpilot.workflows.orchestrator import WorkflowError, WorkflowOrchestrator
from patchpilot.workflows.state import InvalidTransition

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("", response_model=list[DecisionRead])
def list_decisions(status: str | None = None, task_id: uuid.UUID | None = None, risk_level: str | None = None, db: Session = Depends(get_db)) -> list[DecisionRequest]:
    return list(DecisionRepository(db).list(status=status, task_id=task_id, risk_level=risk_level))


@router.get("/{decision_id}", response_model=DecisionRead)
def get_decision(decision_id: uuid.UUID, db: Session = Depends(get_db)) -> DecisionRequest:
    decision = DecisionRepository(db).get(decision_id)
    if not decision:
        raise HTTPException(404, "Decision not found")
    return decision


@router.post("/{decision_id}/resolve", response_model=DecisionRead)
async def resolve_decision(decision_id: uuid.UUID, data: DecisionResolve, db: Session = Depends(get_db)) -> DecisionRequest:
    decision = DecisionRepository(db).get(decision_id)
    if not decision:
        raise HTTPException(404, "Decision not found")
    try:
        await WorkflowOrchestrator(db, gateway=get_gateway()).resolve_decision(decision, option=data.option, actor=data.actor, channel=data.channel, note=data.note)
    except (WorkflowError, InvalidTransition) as exc:
        raise HTTPException(409, str(exc)) from exc
    return DecisionRepository(db).get(decision_id) or decision
