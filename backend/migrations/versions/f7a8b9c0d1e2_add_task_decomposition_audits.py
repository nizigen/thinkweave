"""add task decomposition audits

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_decomposition_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("decomposition_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_llm_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized_dag", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("repair_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("decomposer_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt_no", name="uq_task_decomposition_attempt"),
    )
    op.create_index(
        "ix_task_decomposition_audits_task_id",
        "task_decomposition_audits",
        ["task_id"],
        unique=False,
    )
    op.alter_column("task_decomposition_audits", "attempt_no", server_default=None)
    op.alter_column("task_decomposition_audits", "validation_issues", server_default=None)
    op.alter_column("task_decomposition_audits", "repair_actions", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_task_decomposition_audits_task_id", table_name="task_decomposition_audits")
    op.drop_table("task_decomposition_audits")
