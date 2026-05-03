"""Task decomposition audit trail model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskDecompositionAudit(Base):
    __tablename__ = "task_decomposition_audits"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_no", name="uq_task_decomposition_attempt"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    decomposition_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    normalized_dag: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    repair_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decomposer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
