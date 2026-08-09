from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
    AGENT_RUNNING = "agent_running"
    AGENT_PAUSED = "agent_paused"
    WAITING_FOR_HUMAN = "waiting_for_human"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    IMPLEMENTING = "implementing"
    VALIDATING = "validating"
    CREATING_PULL_REQUEST = "creating_pull_request"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStage(StrEnum):
    MESSAGE_RECEIVED = "message_received"
    ISSUE_LOADED = "issue_loaded"
    REPOSITORY_INSPECTED = "repository_inspected"
    FILES_IDENTIFIED = "files_identified"
    PLAN_GENERATED = "plan_generated"
    AGENT_STARTED = "agent_started"
    POLICY_EVALUATED = "policy_evaluated"
    DECISION_REQUESTED = "decision_requested"
    DECISION_RESOLVED = "decision_resolved"
    AGENT_RESUMED = "agent_resumed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    BRANCH_PREPARED = "branch_prepared"
    CHANGES_GENERATED = "changes_generated"
    TESTS_RUN = "tests_run"
    PULL_REQUEST_CREATED = "pull_request_created"
    MAINTAINERS_NOTIFIED = "maintainers_notified"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentExecutionStatus(StrEnum):
    COMPLETED = "completed"
    DECISION_REQUIRED = "decision_required"
    FAILED = "failed"
    BLOCKED = "blocked"


class PolicyDecision(StrEnum):
    CONTINUE = "continue"
    REQUIRE_HUMAN = "require_human"
    BLOCK = "block"


class DecisionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
