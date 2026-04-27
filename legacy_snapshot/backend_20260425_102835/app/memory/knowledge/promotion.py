"""Session → Knowledge Graph promotion logic."""

from __future__ import annotations

from typing import Any

from app.memory.knowledge.graph import KGEntry, KnowledgeGraph
from app.utils.logger import logger


async def promote_session(
    entries: list[dict[str, Any]],
    kg: KnowledgeGraph,
    *,
    credibility_threshold: float = 0.7,
) -> int:
    """Promote session memory entries to the knowledge graph.

    Only entries with ``credibility >= credibility_threshold`` are promoted.
    Returns the count of entries actually added to *kg*.

    Args:
        entries: List of dicts with keys ``key``, ``content``, ``credibility``
                 (and optionally ``source_task_id``).
        kg: Target KnowledgeGraph instance.
        credibility_threshold: Minimum credibility to promote (default 0.7).
    """
    promoted = 0
    for raw in entries:
        credibility = float(raw.get("credibility", 0.0))
        if credibility < credibility_threshold:
            continue
        key = str(raw.get("key") or "").strip()
        content = str(raw.get("content") or "").strip()
        if not key or not content:
            continue
        entry = KGEntry(
            key=key,
            content=content,
            credibility=credibility,
            source_task_id=str(raw.get("source_task_id") or ""),
        )
        kg.add_entry(entry)
        promoted += 1

    logger.info("KG promotion: {} of {} entries promoted", promoted, len(entries))
    return promoted
