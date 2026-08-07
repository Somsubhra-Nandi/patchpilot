from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from patchpilot.db.session import SessionLocal
from patchpilot.models import AgentTask, Approval, ChannelConnection, Repository, TaskEvent

DEMO_REPOSITORY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
COMPLETED_TASK_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
APPROVAL_TASK_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
FAILED_TASK_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


def event(
    task_id: uuid.UUID,
    event_type: str,
    stage: str,
    summary: str,
    minutes_ago: int,
    details: dict | None = None,
    channel: str | None = None,
    actor: str = "patchpilot",
) -> TaskEvent:
    return TaskEvent(
        task_id=task_id,
        event_type=event_type,
        stage=stage,
        summary=summary,
        details=details or {},
        channel=channel,
        actor=actor,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


def seed_database() -> None:
    with SessionLocal() as db:
        if (db.scalar(select(func.count()).select_from(Repository)) or 0) > 0:
            return
        repository = Repository(
            id=DEMO_REPOSITORY_ID,
            name="patchpilot-demo",
            owner="caspian-labs",
            full_name="caspian-labs/patchpilot-demo",
            github_url="https://github.com/caspian-labs/patchpilot-demo",
            default_branch="main",
            test_command="pytest -q",
            lint_command="ruff check .",
            protected_paths=[".github/workflows", ".env", "infra/production"],
            coding_guidelines="Small diffs, regression tests, and no secrets in logs.",
            autonomy_level="approval_required",
        )
        db.add(repository)
        db.add_all(
            [
                ChannelConnection(
                    channel_type="slack",
                    display_name="PatchPilot · Slack",
                    status="connected",
                    configuration_summary={
                        "provider": "caspian_hosted",
                        "mode": "demo",
                        "secrets_present": False,
                    },
                    last_event_at=datetime.now(UTC) - timedelta(minutes=3),
                ),
                ChannelConnection(
                    channel_type="telegram",
                    display_name="@PatchPilotDemoBot",
                    status="connected",
                    configuration_summary={
                        "provider": "caspian_hosted",
                        "mode": "demo",
                        "secrets_present": False,
                    },
                    last_event_at=datetime.now(UTC) - timedelta(minutes=1),
                ),
            ]
        )
        completed = AgentTask(
            id=COMPLETED_TASK_ID,
            repository_id=repository.id,
            github_issue_number=143,
            github_issue_url=f"{repository.github_url}/issues/143",
            title="Preserve labels when synchronizing issue metadata",
            description="Avoid dropping existing labels during a partial issue update.",
            status="completed",
            current_stage="maintainers_notified",
            origin_channel="slack",
            origin_sender="maya@maintainers",
            assigned_maintainer="Maya Chen",
            branch_name="patchpilot/issue-143-22222222",
            pull_request_url="https://github.com/caspian-labs/patchpilot-demo/pull/57",
            completed_at=datetime.now(UTC) - timedelta(minutes=16),
        )
        awaiting = AgentTask(
            id=APPROVAL_TASK_ID,
            repository_id=repository.id,
            github_issue_number=151,
            github_issue_url=f"{repository.github_url}/issues/151",
            title="Add retry guidance to failed webhook deliveries",
            description="Surface a recovery hint when the provider returns a transient error.",
            status="awaiting_approval",
            current_stage="approval_requested",
            origin_channel="telegram",
            origin_sender="@arjunmaintains",
            assigned_maintainer="Arjun Rao",
        )
        failed = AgentTask(
            id=FAILED_TASK_ID,
            repository_id=repository.id,
            github_issue_number=138,
            github_issue_url=f"{repository.github_url}/issues/138",
            title="Tighten repository identifier validation",
            description="Reject malformed repository identifiers before GitHub API calls.",
            status="failed",
            current_stage="tests_run",
            origin_channel="slack",
            origin_sender="nina@maintainers",
            assigned_maintainer="Nina Patel",
            branch_name="patchpilot/issue-138-44444444",
            failure_reason="Integration test test_repository_identifier_unicode failed",
            completed_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db.add_all([completed, awaiting, failed])
        db.flush()
        db.add_all(
            [
                event(COMPLETED_TASK_ID, "message.inbound", "message_received", "Issue assigned from Slack", 28, {"command": "/patchpilot start caspian-labs/patchpilot-demo#143"}, "slack", "maya@maintainers"),
                event(COMPLETED_TASK_ID, "github.issue_loaded", "issue_loaded", "Loaded issue #143 with 3 comments", 27, {"mode": "live"}),
                event(COMPLETED_TASK_ID, "analysis.completed", "repository_inspected", "Mapped repository conventions and dependency surfaces", 25, {"file_count": 184}),
                event(COMPLETED_TASK_ID, "analysis.files", "files_identified", "Identified issue_service.py and regression tests", 24, {"relevant_files": ["src/issues/issue_service.py", "tests/test_issue_service.py"]}),
                event(COMPLETED_TASK_ID, "plan.generated", "plan_generated", "Generated a focused two-file implementation plan", 22, {"plan": {"issue_summary": "Preserve labels during partial issue updates", "suspected_change": "Merge existing labels before PATCH", "relevant_files": ["src/issues/issue_service.py", "tests/test_issue_service.py"], "proposed_modifications": ["Merge labels without mutation", "Add regression coverage"], "validation_strategy": ["pytest -q", "ruff check ."], "risks": ["API response ordering"], "open_questions": [], "confidence": "high"}}),
                event(COMPLETED_TASK_ID, "approval.requested", "approval_requested", "Approval requested in Slack", 21, {"write_operations_blocked": True}, "slack"),
                event(COMPLETED_TASK_ID, "approval.received", "approval_received", "Approved from Telegram by Maya Chen", 19, {"cross_channel": True}, "telegram", "Maya Chen"),
                event(COMPLETED_TASK_ID, "patch.generated", "changes_generated", "Generated bounded changes across 2 files", 17, {"simulated": False, "artifact": {"changed_files": ["src/issues/issue_service.py", "tests/test_issue_service.py"]}}),
                event(COMPLETED_TASK_ID, "validation.completed", "tests_run", "34 tests passed; lint clean", 16, {"simulated": False, "results": [{"command": "pytest -q", "exit_code": 0, "duration_ms": 1840, "output_summary": "34 passed", "simulated": False}, {"command": "ruff check .", "exit_code": 0, "duration_ms": 210, "output_summary": "All checks passed", "simulated": False}]}),
                event(COMPLETED_TASK_ID, "pull_request.created", "pull_request_created", "Created draft pull request #57", 15, {"url": completed.pull_request_url, "draft": True}),
                event(COMPLETED_TASK_ID, "message.outbound", "maintainers_notified", "Final result broadcast to Slack and Telegram", 14, {"channels": ["slack", "telegram"]}),
                event(APPROVAL_TASK_ID, "message.inbound", "message_received", "Issue assigned from Telegram", 9, channel="telegram", actor="@arjunmaintains"),
                event(APPROVAL_TASK_ID, "github.issue_loaded", "issue_loaded", "Loaded issue #151", 8, {"mode": "demo"}),
                event(APPROVAL_TASK_ID, "analysis.completed", "repository_inspected", "Repository analysis completed", 7, {"file_count": 184}),
                event(APPROVAL_TASK_ID, "analysis.files", "files_identified", "Identified delivery and retry modules", 6, {"relevant_files": ["src/webhooks/delivery.py", "tests/test_delivery.py"]}),
                event(APPROVAL_TASK_ID, "plan.generated", "plan_generated", "Plan ready for maintainer review", 5, {"plan": {"issue_summary": "Add retry guidance after transient webhook failures", "suspected_change": "Map retryable provider errors to operator guidance", "relevant_files": ["src/webhooks/delivery.py", "tests/test_delivery.py"], "proposed_modifications": ["Classify transient failures", "Return a bounded retry hint"], "validation_strategy": ["pytest -q"], "risks": ["Avoid retrying permanent errors"], "open_questions": ["Should hints include provider request IDs?"], "confidence": "medium"}}),
                event(APPROVAL_TASK_ID, "approval.requested", "approval_requested", "Waiting for approval from Slack or Telegram", 4, {"write_operations_blocked": True}, "telegram"),
                event(FAILED_TASK_ID, "message.inbound", "message_received", "Issue assigned from Slack", 135, channel="slack", actor="nina@maintainers"),
                event(FAILED_TASK_ID, "approval.received", "approval_received", "Implementation plan approved", 128, channel="slack", actor="Nina Patel"),
                event(FAILED_TASK_ID, "patch.generated", "changes_generated", "Generated identifier validation patch", 123, {"artifact": {"changed_files": ["src/github/identifiers.py", "tests/test_identifiers.py"]}}),
                event(FAILED_TASK_ID, "validation.completed", "tests_run", "Validation failed: 1 failed, 41 passed", 120, {"simulated": False, "results": [{"command": "pytest -q", "exit_code": 1, "duration_ms": 2310, "output_summary": "1 failed, 41 passed", "simulated": False}]}),
            ]
        )
        db.add_all(
            [
                Approval(
                    task_id=COMPLETED_TASK_ID,
                    status="approved",
                    requested_channel="slack",
                    requested_from="Maya Chen",
                    responded_channel="telegram",
                    responded_by="Maya Chen",
                    responded_at=datetime.now(UTC) - timedelta(minutes=19),
                ),
                Approval(
                    task_id=APPROVAL_TASK_ID,
                    status="pending",
                    requested_channel="telegram",
                    requested_from="Arjun Rao",
                ),
                Approval(
                    task_id=FAILED_TASK_ID,
                    status="approved",
                    requested_channel="slack",
                    requested_from="Nina Patel",
                    responded_channel="slack",
                    responded_by="Nina Patel",
                    responded_at=datetime.now(UTC) - timedelta(minutes=128),
                ),
            ]
        )
        db.commit()

