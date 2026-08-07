from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from patchpilot.db.session import get_db
from patchpilot.models import ChannelConnection
from patchpilot.schemas.domain import ChannelRead

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("", response_model=list[ChannelRead])
def list_channels(db: Session = Depends(get_db)) -> list[ChannelConnection]:
    return list(
        db.scalars(select(ChannelConnection).order_by(ChannelConnection.channel_type)).all()
    )

