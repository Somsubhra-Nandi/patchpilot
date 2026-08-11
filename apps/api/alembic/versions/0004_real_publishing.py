"""Persist real task-workspace publication results."""

import sqlalchemy as sa

from alembic import op

revision = "0004_real_publishing"
down_revision = "0003_codex_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("agent_tasks")}
    for name, column in {
        "pull_request_number": sa.Column("pull_request_number", sa.Integer()),
        "published_commit_sha": sa.Column("published_commit_sha", sa.String(64)),
        "published_at": sa.Column("published_at", sa.DateTime(timezone=True)),
        "publishing_status": sa.Column("publishing_status", sa.String(64)),
    }.items():
        if name not in columns:
            op.add_column("agent_tasks", column)
    indexes = {index["name"] for index in inspector.get_indexes("agent_tasks")}
    if "ix_agent_tasks_publishing_status" not in indexes:
        op.create_index("ix_agent_tasks_publishing_status", "agent_tasks", ["publishing_status"])


def downgrade() -> None:
    op.drop_index("ix_agent_tasks_publishing_status", table_name="agent_tasks")
    for column in ("publishing_status", "published_at", "published_commit_sha", "pull_request_number"):
        op.drop_column("agent_tasks", column)
