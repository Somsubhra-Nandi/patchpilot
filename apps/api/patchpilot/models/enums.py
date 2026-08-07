from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
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

