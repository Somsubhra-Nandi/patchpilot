from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from patchpilot.core.config import Settings, get_settings
from patchpilot.db.session import SessionLocal
from patchpilot.models import AgentTask, ChannelConnection
from patchpilot.repositories.domain import TaskRepository
from patchpilot.schemas.domain import InboundMessage
from patchpilot.services.commands import CommandService

logger = structlog.get_logger(__name__)


def sender_label(sender: dict[str, Any] | None) -> str:
    if not sender:
        return "unknown"
    for key in ("display_name", "name", "username", "address", "id"):
        if value := sender.get(key):
            return str(value)
    return "unknown"


def normalize_caspian_message(message: Any) -> InboundMessage:
    channel = str(message.channel).lower()
    if channel not in {"slack", "telegram"}:
        raise ValueError(f"Unsupported PatchPilot channel: {channel}")
    if not message.text or not str(message.text).strip():
        raise ValueError("Inbound message text is empty")
    return InboundMessage(
        channel=channel,
        sender=sender_label(message.sender),
        conversation_id=str(message.conversation_id),
        message_id=str(message.id),
        connection_id=str(message.connection_id),
        text=str(message.text),
    )


class CaspianGateway:
    """The only module that imports caspian-sdk.

    All business logic consumes internal models and the CommunicationGateway protocol.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client: Any | None = None
        self._listener_thread: threading.Thread | None = None

    def configure(self) -> None:
        if not self.settings.caspian_enabled:
            return
        if not self.settings.caspian_api_key:
            raise RuntimeError("CASPIAN_ENABLED requires CASPIAN_API_KEY")
        from caspian_sdk import CommClient

        self.client = CommClient(
            api_key=self.settings.caspian_api_key,
            base_url=self.settings.caspian_base_url,
        )
        configured = 0
        if self.settings.caspian_telegram_bot_token:
            result = self.client.connect_telegram(
                bot_token=self.settings.caspian_telegram_bot_token
            )
            self._save_connection("telegram", "PatchPilot Telegram", result)
            configured += 1
        result = self._configure_slack()
        if result:
            self._save_connection("slack", self.settings.caspian_slack_display_name, result)
            configured += 1
        if configured < 2:
            logger.warning("caspian_less_than_two_channels", configured=configured)

        @self.client.on_message
        def shared_handler(message: Any) -> None:
            try:
                inbound = normalize_caspian_message(message)
            except ValueError as exc:
                logger.warning("caspian_message_rejected", reason=str(exc))
                return
            with SessionLocal() as db:
                response = asyncio.run(CommandService(db, self).process(inbound))
            if response:
                message.reply(response)

    def _configure_slack(self) -> dict | None:
        if self.settings.caspian_slack_mode == "quick":
            return self.client.install_slack(
                display_name=self.settings.caspian_slack_display_name,
                icon_url=self.settings.caspian_slack_icon_url,
            )
        if self.settings.caspian_slack_bot_token and self.settings.caspian_slack_app_token:
            return self.client.connect_slack(
                bot_token=self.settings.caspian_slack_bot_token,
                app_token=self.settings.caspian_slack_app_token,
            )
        if all(
            (
                self.settings.caspian_slack_client_id,
                self.settings.caspian_slack_client_secret,
                self.settings.caspian_slack_signing_secret,
            )
        ):
            return self.client.connect_slack(
                slack_client_id=self.settings.caspian_slack_client_id,
                slack_client_secret=self.settings.caspian_slack_client_secret,
                slack_signing_secret=self.settings.caspian_slack_signing_secret,
            )
        return None

    def _save_connection(self, channel: str, display_name: str, result: dict) -> None:
        with SessionLocal() as db:
            connection = db.scalar(
                select(ChannelConnection).where(ChannelConnection.channel_type == channel)
            ) or ChannelConnection(channel_type=channel, display_name=display_name)
            connection.display_name = display_name
            connection.status = result.get("status", "configured")
            connection.external_connection_id = result.get("id")
            connection.configuration_summary = {
                "provider": result.get("provider", "caspian_hosted"),
                "address": result.get("address"),
                "authorization_required": bool(result.get("authorize_url")),
                "authorize_url": result.get("authorize_url"),
            }
            db.add(connection)
            db.commit()

    def start(self) -> None:
        self.configure()
        if not self.client or not self.settings.caspian_start_listener:
            return
        self._listener_thread = threading.Thread(
            target=self.client.listen,
            kwargs={"concurrency": "queue"},
            daemon=True,
            name="caspian-listener",
        )
        self._listener_thread.start()

    async def send_message(self, channel: str, conversation_id: str, text: str) -> None:
        if not self.client:
            return
        await asyncio.to_thread(self.client.send_message, conversation_id, text=text)

    async def broadcast_task_update(self, task_id: uuid.UUID, text: str) -> None:
        if not self.client:
            return
        with SessionLocal() as db:
            task = db.get(AgentTask, task_id)
            connections = db.scalars(
                select(ChannelConnection).where(
                    ChannelConnection.channel_type.in_(["slack", "telegram"]),
                    ChannelConnection.default_conversation_id.is_not(None),
                )
            ).all()
            targets = {
                (item.channel_type, item.default_conversation_id) for item in connections
            }
            if task and task.origin_conversation_id:
                targets.add((task.origin_channel, task.origin_conversation_id))
            for channel, conversation_id in targets:
                await asyncio.to_thread(self.client.send_message, conversation_id, text=text)
                if task:
                    TaskRepository(db).event(
                        task,
                        event_type="message.outbound",
                        stage=task.current_stage,
                        summary=f"Final result sent to {channel}",
                        details={"purpose": "final_broadcast"},
                        channel=channel,
                        actor="patchpilot",
                    )
            db.commit()
