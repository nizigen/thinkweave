"""Memory data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TopicClaim(BaseModel):
    """Topic ownership claim used for chapter-level dedup guidance."""

    chapter_id: str
    owns: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)


class ContentSummary(BaseModel):
    """Compact summary generated after a chapter is written."""

    chapter_id: str
    summary: str
    keywords: list[str] = Field(default_factory=list)


class EntityRelation(BaseModel):
    """Extracted entity-relation triple."""

    source: str
    relation: str
    target: str
    confidence: float = 0.0