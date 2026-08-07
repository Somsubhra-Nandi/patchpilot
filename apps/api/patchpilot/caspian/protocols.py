from __future__ import annotations

from typing import Protocol
from uuid import UUID


class CommunicationGateway(Protocol):
    async def send_message(self, channel: str, conversation_id: str, text: str) -> None: ...

    async def broadcast_task_update(self, task_id: UUID, text: str) -> None: ...


class NullCommunicationGateway:
    async def send_message(self, channel: str, conversation_id: str, text: str) -> None:
        return None

    async def broadcast_task_update(self, task_id: UUID, text: str) -> None:
        return None

