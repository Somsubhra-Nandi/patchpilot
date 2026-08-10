"""Persist isolated coding-agent workspace metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0003_codex_workspaces"
down_revision = "0002_agent_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("agent_tasks")}
    for name, column in {
        "workspace_path": sa.Column("workspace_path", sa.String(1024)),
        "workspace_status": sa.Column("workspace_status", sa.String(64)),
        "source_commit_sha": sa.Column("source_commit_sha", sa.String(64)),
    }.items():
        if name not in columns:
            op.add_column("agent_tasks", column)
    indexes = {index["name"] for index in inspector.get_indexes("agent_tasks")}
    if "ix_agent_tasks_workspace_status" not in indexes:
        op.create_index("ix_agent_tasks_workspace_status", "agent_tasks", ["workspace_status"])


def downgrade() -> None:
    op.drop_index("ix_agent_tasks_workspace_status", table_name="agent_tasks")
    for column in ("source_commit_sha", "workspace_status", "workspace_path"):
        op.drop_column("agent_tasks", column)
