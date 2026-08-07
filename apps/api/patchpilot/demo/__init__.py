from __future__ import annotations

import asyncio

from sqlalchemy import select

from patchpilot.db.session import SessionLocal
from patchpilot.models import Repository
from patchpilot.schemas.domain import DecisionRequest, TaskCreate
from patchpilot.workflows.orchestrator import WorkflowOrchestrator


async def run_demo() -> None:
    with SessionLocal() as db:
        repository = db.scalar(select(Repository).order_by(Repository.created_at))
        if not repository:
            raise RuntimeError("Seed the database before running the demo")
        workflow = WorkflowOrchestrator(db)
        task = await workflow.create(
            TaskCreate(
                repository_id=repository.id,
                github_issue_number=202,
                title="Demonstrate the live PatchPilot mission timeline",
                description="Create a safe end-to-end workflow for the judging demo.",
                origin_channel="slack",
                origin_sender="demo-maintainer",
                assigned_maintainer="Demo Maintainer",
            )
        )
        print(f"Created task {task.id}; approval will arrive from Telegram in 4 seconds.", flush=True)
        await asyncio.sleep(4)
        task = await workflow.approve(
            task,
            DecisionRequest(actor="demo-maintainer", channel="telegram", note="Demo approval"),
        )
        print(f"Demo task completed: {task.id} ({task.status})", flush=True)


if __name__ == "__main__":
    asyncio.run(run_demo())

