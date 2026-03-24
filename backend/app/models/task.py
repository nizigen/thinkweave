"""Task ORM models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, Text, Integer, SmallInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    fsm_state: Mapped[str] = mapped_column(String(50), default="init")
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[str] = mapped_column(String(20), default="standard")
    target_words: Mapped[int] = mapped_column(Integer, default=10000)
    checkpoint_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class Outline(Base):
    __tablename__ = "outlines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    confirmed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )


class ChapterReview(Base):
    __tablename__ = "chapter_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_nodes.id"),
        nullable=False,
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    accuracy_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    coherence_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    style_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

