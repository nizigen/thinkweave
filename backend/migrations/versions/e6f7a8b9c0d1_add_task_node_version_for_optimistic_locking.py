"""add task_nodes.version for optimistic locking

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_nodes",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("task_nodes", "version", server_default=None)


def downgrade() -> None:
    op.drop_column("task_nodes", "version")
