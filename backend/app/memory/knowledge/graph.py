"""In-process Knowledge Graph for cross-task knowledge accumulation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class KGEntry(BaseModel):
    """A single knowledge graph entry."""

    key: str
    content: str
    credibility: float = 0.0
    source_task_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeGraph:
    """In-memory knowledge graph with TTL pruning and keyword query.

    Designed as a lightweight, process-local store that can be populated
    from SessionMemory promotion and queried during Outline/Writer task
    setup.  Persistence to cognee KG backend is handled externally.
    """

    def __init__(self, *, ttl_days: int = 90) -> None:
        self._entries: dict[str, KGEntry] = {}
        self._ttl = timedelta(days=ttl_days)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_entry(self, entry: KGEntry) -> None:
        """Add or update an entry. Higher credibility wins on key collision."""
        existing = self._entries.get(entry.key)
        if existing is None or entry.credibility >= existing.credibility:
            self._entries[entry.key] = entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(self, text: str, *, limit: int = 10) -> list[KGEntry]:
        """Return entries matching any token from *text* (case-insensitive).

        Tokenises the query on whitespace/punctuation so that a query like
        'Quantum Computing Report' matches an entry containing 'Quantum'.
        """
        import re as _re
        tokens = [t.lower() for t in _re.split(r'[\s,.:;!?]+', text) if len(t) > 2]
        if not tokens:
            return []
        def _token_matches(tok: str, entry: KGEntry) -> bool:
            content_l = entry.content.lower()
            key_l = entry.key.lower()
            return (
                tok in content_l
                or tok in key_l
                or key_l in tok  # e.g. token "qubits" matches key "qubit"
            )

        matches = [
            e for e in self._entries.values()
            if any(_token_matches(tok, e) for tok in tokens)
        ]
        matches.sort(key=lambda e: e.credibility, reverse=True)
        return matches[:limit]

    def to_context_string(self, *, limit: int = 10) -> str:
        """Return top entries as a plain-text context block."""
        top = sorted(
            self._entries.values(),
            key=lambda e: e.credibility,
            reverse=True,
        )[:limit]
        lines = [f"- [{e.key}] {e.content}" for e in top]
        return "\n".join(lines)

    def size(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune_stale(self) -> int:
        """Remove entries older than TTL. Returns count of removed entries."""
        cutoff = datetime.now(UTC) - self._ttl
        stale_keys = [
            k for k, e in self._entries.items()
            if e.created_at.replace(tzinfo=UTC) < cutoff
        ]
        for k in stale_keys:
            del self._entries[k]
        return len(stale_keys)

    def to_dict(self) -> dict[str, Any]:
        return {k: e.model_dump() for k, e in self._entries.items()}
