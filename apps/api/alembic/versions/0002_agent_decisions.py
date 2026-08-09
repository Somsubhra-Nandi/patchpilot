"""Add coding-agent checkpoints and first-class decisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_agent_decisions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("agent_tasks")}
    additions = {
        "coding_agent_provider": sa.Column("coding_agent_provider", sa.String(64)),
        "external_session_id": sa.Column("external_session_id", sa.String(512)),
        "agent_execution_status": sa.Column("agent_execution_status", sa.String(64)),
        "last_checkpoint": sa.Column("last_checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        "last_execution_at": sa.Column("last_execution_at", sa.DateTime(timezone=True)),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("agent_tasks", column)
    indexes = {index["name"] for index in inspector.get_indexes("agent_tasks")}
    if "ix_agent_tasks_external_session_id" not in indexes:
        op.create_index("ix_agent_tasks_external_session_id", "agent_tasks", ["external_session_id"])
    if "ix_agent_tasks_agent_execution_status" not in indexes:
        op.create_index("ix_agent_tasks_agent_execution_status", "agent_tasks", ["agent_execution_status"])
    if "decision_requests" in inspector.get_table_names():
        return
    op.create_table(
        "decision_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_option", sa.String(128)),
        sa.Column("requested_by_agent", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(512)),
        sa.Column("resolved_channel", sa.String(64)),
        sa.Column("resolution", sa.String(128)),
        sa.Column("resolution_note", sa.Text()),
    )
    op.create_index("ix_decision_requests_task_id", "decision_requests", ["task_id"])
    op.create_index("ix_decision_requests_decision_type", "decision_requests", ["decision_type"])
    op.create_index("ix_decision_requests_risk_level", "decision_requests", ["risk_level"])
    op.create_index("ix_decision_requests_status", "decision_requests", ["status"])
    op.create_index("ix_decision_requests_status_created", "decision_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("decision_requests")
    op.drop_index("ix_agent_tasks_agent_execution_status", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_external_session_id", table_name="agent_tasks")
    for column in ("last_execution_at", "last_checkpoint", "agent_execution_status", "external_session_id", "coding_agent_provider"):
        op.drop_column("agent_tasks", column)
