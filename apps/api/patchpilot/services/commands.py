from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from patchpilot.caspian.protocols import CommunicationGateway
from patchpilot.models import AgentTask, ChannelConnection, ProcessedInboundMessage
from patchpilot.schemas.domain import DecisionRequest, InboundMessage, TaskCreate
from patchpilot.workflows.orchestrator import WorkflowOrchestrator


class CommandError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    argument: str | None = None
    reason: str | None = None


START_RE = re.compile(r"^(?:/patchpilot\s+start\s+|analy[sz]e\s+issue\s+)([\w.-]+/[\w.-]+)#?(\d+)(?:\s+in\s+([\w.-]+/[\w.-]+))?$", re.I)
NL_START_RE = re.compile(r"^analy[sz]e\s+issue\s+(\d+)\s+in\s+([\w.-]+/[\w.-]+)$", re.I)
ACTION_RE = re.compile(
    r"^(?:/patchpilot\s+)?(status|approve|reject|cancel)\s+([0-9a-f-]{6,36})(?:\s+(.+))?$",
    re.I,
)
NL_STATUS_RE = re.compile(r"^what is the status of task\s+([0-9a-f-]{6,36})\??$", re.I)


def parse_command(text: str) -> Command:
    cleaned = " ".join(text.strip().split())
    if cleaned.lower() in {"/patchpilot", "/patchpilot help", "help", "patchpilot help"}:
        return Command("help")
    match = START_RE.fullmatch(cleaned)
    if match:
        if match.group(3):
            repository, issue = match.group(3), match.group(2)
        else:
            repository, issue = match.group(1), match.group(2)
        return Command("start", f"{repository}#{issue}")
    match = NL_START_RE.fullmatch(cleaned)
    if match:
        return Command("start", f"{match.group(2)}#{match.group(1)}")
    match = ACTION_RE.fullmatch(cleaned)
    if match:
        return Command(match.group(1).lower(), match.group(2), match.group(3))
    match = NL_STATUS_RE.fullmatch(cleaned)
    if match:
        return Command("status", match.group(1))
    if cleaned.lower().startswith("approve task "):
        return Command("approve", cleaned.split()[-1])
    raise CommandError("Unsupported command. Send /patchpilot help for deterministic examples.")


HELP_TEXT = """PatchPilot commands
/patchpilot start owner/repository#143
/patchpilot status <task-id>
/patchpilot approve <task-id>
/patchpilot reject <task-id> <reason>
/patchpilot cancel <task-id>
/patchpilot help

Writes never begin before explicit approval. Safe demo mode is the default."""


class CommandService:
    def __init__(self, db: Session, gateway: CommunicationGateway):
        self.db = db
        self.gateway = gateway
        self.workflow = WorkflowOrchestrator(db, gateway=gateway)

    def _resolve_task(self, prefix: str) -> AgentTask:
        normalized = prefix.lower()
        tasks = self.db.scalars(select(AgentTask)).all()
        matches = [task for task in tasks if str(task.id).startswith(normalized)]
        if not matches:
            raise CommandError(f"No task matches {prefix}")
        if len(matches) > 1:
            raise CommandError(f"Task prefix {prefix} is ambiguous; use the full task ID")
        return matches[0]

    async def process(self, message: InboundMessage) -> str | None:
        receipt = ProcessedInboundMessage(channel=message.channel, message_id=message.message_id)
        self.db.add(receipt)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None
        connection = self.db.scalar(
            select(ChannelConnection).where(ChannelConnection.channel_type == message.channel)
        )
        if connection:
            connection.default_conversation_id = message.conversation_id
            connection.last_event_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
            self.db.commit()
        try:
            command = parse_command(message.text)
            if command.name == "help":
                response = HELP_TEXT
            elif command.name == "start":
                repository, issue = (command.argument or "").rsplit("#", 1)
                task = await self.workflow.create(
                    TaskCreate(
                        repository=repository,
                        github_issue_number=int(issue),
                        origin_channel=message.channel,
                        origin_sender=message.sender,
                        origin_conversation_id=message.conversation_id,
                        assigned_maintainer=message.sender,
                    )
                )
                receipt.task_id = task.id
                response = (
                    f"Task {task.id} is {task.status}. I analyzed {repository}#{issue} and "
                    "sent the approval-ready plan in this conversation."
                )
            else:
                task = self._resolve_task(command.argument or "")
                receipt.task_id = task.id
                if command.name == "status":
                    response = (
                        f"Task {task.id}\nRepository: {task.repository.full_name}"
                        f"\nStatus: {task.status}\nStage: {task.current_stage}"
                    )
                elif command.name == "approve":
                    task = await self.workflow.approve(
                        task,
                        DecisionRequest(actor=message.sender, channel=message.channel),
                    )
                    response = f"Approved. Task {task.id} finished with status {task.status}."
                elif command.name == "reject":
                    task = await self.workflow.reject(
                        task,
                        DecisionRequest(
                            actor=message.sender, channel=message.channel, note=command.reason
                        ),
                    )
                    response = f"Rejected. Task {task.id} is closed with an audit record."
                elif command.name == "cancel":
                    task = await self.workflow.cancel(
                        task,
                        DecisionRequest(
                            actor=message.sender, channel=message.channel, note=command.reason
                        ),
                    )
                    response = f"Cancelled task {task.id}."
                else:
                    raise CommandError("Unsupported command")
            self.db.commit()
            return response
        except (CommandError, ValueError) as exc:
            self.db.rollback()
            return f"PatchPilot could not process that request: {exc}"
