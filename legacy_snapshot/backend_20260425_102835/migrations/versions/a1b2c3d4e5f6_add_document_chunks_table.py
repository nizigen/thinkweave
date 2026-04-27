"""add document_chunks table for RAG

Revision ID: a1b2c3d4e5f6
Revises: fe2c455b6ef4
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = "fe2c455b6ef4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("chapter_index", sa.SmallInteger, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
    )

    # embedding column (vector type) — requires pgvector extension
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)"
    )

    # tsvector column for full-text search
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )

    # Indexes
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX idx_chunks_tsv ON document_chunks USING gin(tsv)"
    )
    op.create_index("idx_chunks_task", "document_chunks", ["task_id"])


def downgrade() -> None:
    op.drop_table("document_chunks")
