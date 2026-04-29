"""Task decomposition service that turns writing requests into a DAG."""

from __future__ import annotations

from collections import deque
import re

from app.schemas.task import DAGSchema, VALID_DEPTHS, VALID_MODES, ValidationResult
from app.utils.llm_client import BaseLLMClient, LLMUnavailableError
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TaskValidationError(Exception):
    """Raised when task input validation fails."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__(f"Task validation failed: {issues}")


class CyclicDAGError(Exception):
    """Raised when the DAG contains a cycle or an unknown dependency."""


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

_MIN_TITLE_LENGTH = 6
_LONG_FORM_EXPANSION_THRESHOLD = 12000
_QUICK_COMPACT_TARGET_WORDS_MAX = 2000
_DEPTH_CHAPTER_BOUNDS: dict[str, tuple[int, int]] = {
    "quick": (3, 5),
    "standard": (5, 8),
    "deep": (8, 12),
}
_LONGFORM_MIN_CHAPTERS_BY_TARGET: list[tuple[int, dict[str, int]]] = [
    (50000, {"quick": 12, "standard": 14, "deep": 16}),
    (30000, {"quick": 10, "standard": 12, "deep": 14}),
]
_CHAPTER_TITLE_TEMPLATES = [
    "研究背景与问题界定",
    "核心概念与评价框架",
    "现状诊断与关键矛盾",
    "技术路线与实现机制",
    "数据与证据基础",
    "组织机制与流程重构",
    "治理与合规边界",
    "实施路径与阶段计划",
    "风险识别与应对策略",
    "成本收益与资源配置",
    "行业案例与对比分析",
    "综合结论与行动建议",
    "分场景扩展与落地细则",
    "监测评估与持续优化",
    "长期演进与战略展望",
]


def _parse_chapter_index(title: str) -> int | None:
    text = (title or "").strip()
    if not text:
        return None
    match = re.search(r"第\s*(\d+)\s*章", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _is_expansion_title(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return False
    markers = ("扩写", "补写", "整合", "篇幅补足")
    return any(marker in text for marker in markers)


def _normalized_chapter_title(chapter_index: int) -> str:
    idx = max(1, chapter_index) - 1
    if idx < len(_CHAPTER_TITLE_TEMPLATES):
        name = _CHAPTER_TITLE_TEMPLATES[idx]
    else:
        name = f"分主题展开{chapter_index}"
    return f"第{chapter_index}章：{name}"


def _looks_like_low_value_chapter_title(title: str) -> bool:
    text = (title or "").strip()
    if not text:
        return True
    low_value_markers = ("补充专题", "专题补写", "扩写", "篇幅补足", "待补充", "章节草稿")
    return any(marker in text for marker in low_value_markers)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _allocate_node_id(existing_ids: set[str], prefix: str) -> str:
    suffix = 1
    candidate = f"{prefix}_{suffix}"
    while candidate in existing_ids:
        suffix += 1
        candidate = f"{prefix}_{suffix}"
    existing_ids.add(candidate)
    return candidate


def validate_task_input(title: str, mode: str, depth: str) -> ValidationResult:
    """Validate task input before invoking the LLM."""
    issues: list[str] = []
    stripped = title.strip()

    if len(stripped) < _MIN_TITLE_LENGTH:
        issues.append(
            f"Title must be at least {_MIN_TITLE_LENGTH} characters "
            f"(got {len(stripped)})"
        )

    if mode not in VALID_MODES:
        issues.append(
            f"Invalid mode '{mode}', expected one of {sorted(VALID_MODES)}"
        )

    if depth not in VALID_DEPTHS:
        issues.append(
            f"Invalid depth '{depth}', expected one of {sorted(VALID_DEPTHS)}"
        )

    return ValidationResult(ok=len(issues) == 0, issues=issues)


# ---------------------------------------------------------------------------
# DAG Parsing and Validation
# ---------------------------------------------------------------------------

def parse_dag_response(raw: dict) -> DAGSchema:
    """
    Parse and validate the DAG JSON returned by the LLM.

    Raises:
        ValueError: The DAG payload is malformed or violates structural rules.
    """
    try:
        dag = DAGSchema.model_validate(raw)
    except Exception as e:
        raise ValueError(f"DAG schema validation failed: {e}") from e

    # Node IDs must be unique.
    node_ids = [n.id for n in dag.nodes]
    if len(node_ids) != len(set(node_ids)):
        seen: set[str] = set()
        dupes = []
        for nid in node_ids:
            if nid in seen:
                dupes.append(nid)
            seen.add(nid)
        raise ValueError(f"Duplicate node IDs: {dupes}")

    # If role is present, the first node must be the outline step.
    # Capability-only DAGs may omit role intentionally.
    if dag.nodes[0].role is not None and dag.nodes[0].role != "outline":
        raise ValueError(
            f"First node must have role 'outline', got '{dag.nodes[0].role}'"
        )

    return dag


def validate_dag_acyclic(dag: DAGSchema) -> None:
    """
    Validate that the DAG is acyclic using Kahn topological sorting.

    Raises:
        CyclicDAGError: The DAG contains a cycle or references unknown nodes.
    """
    node_ids = {n.id for n in dag.nodes}

    # Every dependency must reference an existing node.
    for node in dag.nodes:
        for dep in node.depends_on:
            if dep not in node_ids:
                raise CyclicDAGError(
                    f"Node '{node.id}' depends on unknown node '{dep}'"
                )

    # Detect cycles with Kahn topological sorting.
    in_degree: dict[str, int] = {n.id: 0 for n in dag.nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in dag.nodes}

    for node in dag.nodes:
        for dep in node.depends_on:
            adjacency[dep].append(node.id)
            in_degree[node.id] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    sorted_count = 0

    while queue:
        current = queue.popleft()
        sorted_count += 1
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count != len(dag.nodes):
        raise CyclicDAGError(
            f"DAG contains a cycle (sorted {sorted_count}/{len(dag.nodes)} nodes)"
        )


def _build_fallback_dag(title: str) -> DAGSchema:
    """Build a minimal safe DAG when the LLM decomposition output is unusable."""
    short_title = title.strip()[:48]
    dag = DAGSchema(
        nodes=[
            {
                "id": "n1",
                "title": f"{short_title} - 大纲",
                "role": "outline",
                "depends_on": [],
            },
            {
                "id": "n2",
                "title": f"{short_title} - 研究计划与证据池",
                "role": "researcher",
                "depends_on": ["n1"],
            },
            {
                "id": "n3",
                "title": f"{short_title} - 初稿",
                "role": "writer",
                "depends_on": ["n2"],
            },
            {
                "id": "n4",
                "title": f"{short_title} - 评审",
                "role": "reviewer",
                "depends_on": ["n3"],
            },
        ]
    )
    validate_dag_acyclic(dag)
    return dag


def _ensure_research_gate(dag: DAGSchema) -> DAGSchema:
    """Enforce a hard research stage before writer nodes.

    Rules:
    - Keep outline as first node.
    - Ensure at least one `researcher` node exists after outline.
    - Every writer node must depend on a researcher node.
    """
    if not dag.nodes:
        return dag

    researcher_ids = [node.id for node in dag.nodes if node.role == "researcher"]
    if not researcher_ids:
        existing_ids = {node.id for node in dag.nodes}
        base_id = "n_research"
        suffix = 1
        candidate = base_id
        while candidate in existing_ids:
            suffix += 1
            candidate = f"{base_id}_{suffix}"

        gate_node = {
            "id": candidate,
            "title": "研究计划与证据池构建",
            "role": "researcher",
            "depends_on": [dag.nodes[0].id],
        }
        raw_nodes = [node.model_dump() for node in dag.nodes]
        raw_nodes.insert(1, gate_node)
        dag = DAGSchema.model_validate({"nodes": raw_nodes})
        researcher_ids = [candidate]

    for node in dag.nodes:
        if node.role != "writer":
            continue
        for research_id in researcher_ids:
            if research_id not in node.depends_on:
                node.depends_on.append(research_id)

    return dag


def _inject_long_form_expansion_nodes(dag: DAGSchema, *, target_words: int) -> DAGSchema:
    """Inject chapter expansion writers for long-form targets.

    This mirrors the "initial draft + expansion rounds" strategy seen in
    mature multi-agent writing pipelines, while keeping schema unchanged.
    """
    if target_words < _LONG_FORM_EXPANSION_THRESHOLD or not dag.nodes:
        return dag

    writer_nodes = [node for node in dag.nodes if node.role == "writer"]
    if not writer_nodes:
        return dag

    # Prefer chapter-like writer nodes as primary writers; fallback to all writers.
    chapter_like = [
        node for node in writer_nodes
        if _parse_chapter_index(node.title) is not None and not _is_expansion_title(node.title)
    ]
    if chapter_like:
        primary_writers = sorted(
            chapter_like,
            key=lambda node: (_parse_chapter_index(node.title) or 0, node.title.lower()),
        )
    else:
        primary_writers = [
            node for node in writer_nodes
            if not _is_expansion_title(node.title)
        ] or writer_nodes
    if len(primary_writers) <= 1:
        return dag

    raw_nodes = [node.model_dump() for node in dag.nodes]
    existing_ids = {str(node["id"]) for node in raw_nodes}
    expansion_by_primary: dict[str, str] = {}
    expansion_ids: list[str] = []

    for writer in primary_writers:
        expansion_id = _allocate_node_id(existing_ids, "n_expand")
        base_title = writer.title.strip() or "章节扩写"
        chapter_idx = _parse_chapter_index(base_title)
        if chapter_idx is not None:
            expansion_title = f"{base_title}（扩写）"
        else:
            expansion_title = f"{base_title} - 扩写补足"
        raw_nodes.append(
            {
                "id": expansion_id,
                "title": expansion_title,
                "role": "writer",
                "depends_on": [writer.id],
            }
        )
        expansion_by_primary[writer.id] = expansion_id
        expansion_ids.append(expansion_id)

    global_expansion_id: str | None = None
    if target_words >= 16000 and len(expansion_ids) >= 2:
        global_expansion_id = _allocate_node_id(existing_ids, "n_expand_global")
        raw_nodes.append(
            {
                "id": global_expansion_id,
                "title": "全稿扩写与篇幅补足",
                "role": "writer",
                "depends_on": expansion_ids,
            }
        )

    for raw in raw_nodes:
        role = str(raw.get("role") or "").strip().lower()
        if role not in {"reviewer", "consistency"}:
            continue
        deps = [str(dep) for dep in raw.get("depends_on", [])]
        rewritten: list[str] = []
        for dep in deps:
            rewritten.append(expansion_by_primary.get(dep, dep))

        if role == "consistency":
            if global_expansion_id is not None:
                rewritten = [dep for dep in rewritten if dep not in expansion_ids]
                rewritten.append(global_expansion_id)
            elif expansion_ids:
                rewritten.extend(expansion_ids)
        raw["depends_on"] = _dedupe_preserve_order(rewritten)

    return DAGSchema.model_validate({"nodes": raw_nodes})


def _required_min_primary_chapters(*, depth: str, target_words: int) -> int | None:
    bounds = _DEPTH_CHAPTER_BOUNDS.get(depth)
    if not bounds:
        return None
    min_chapters = int(bounds[0])
    for threshold, profile in _LONGFORM_MIN_CHAPTERS_BY_TARGET:
        if target_words >= threshold:
            min_chapters = max(min_chapters, int(profile.get(depth, min_chapters)))
            break
    return min_chapters


def _ensure_depth_chapter_count(
    dag: DAGSchema,
    *,
    depth: str,
    target_words: int,
) -> DAGSchema:
    """Enforce minimum primary chapter count by depth.

    Primary chapters are writer nodes that are not expansion/final-merge nodes.
    """
    if not dag.nodes:
        return dag

    min_chapters = _required_min_primary_chapters(depth=depth, target_words=target_words)
    if min_chapters is None:
        return dag
    raw_nodes = [node.model_dump() for node in dag.nodes]
    existing_ids = {str(node["id"]) for node in raw_nodes}

    def _role(node: dict) -> str:
        return str(node.get("role") or "").strip().lower()

    def _is_primary_writer(node: dict) -> bool:
        return _role(node) == "writer" and not _is_expansion_title(str(node.get("title") or ""))

    primary_writers = [node for node in raw_nodes if _is_primary_writer(node)]

    # Normalize low-value writer titles into executable chapter intents.
    for writer in primary_writers:
        title = str(writer.get("title") or "")
        idx = _parse_chapter_index(title)
        if idx is None:
            continue
        if _looks_like_low_value_chapter_title(title):
            writer["title"] = _normalized_chapter_title(idx)

    if len(primary_writers) >= min_chapters:
        return dag

    researcher_ids = [str(node["id"]) for node in raw_nodes if _role(node) == "researcher"]
    outline_id = next((str(node["id"]) for node in raw_nodes if _role(node) == "outline"), "")
    writer_default_deps = researcher_ids or ([outline_id] if outline_id else [])

    max_chapter_index = 0
    for writer in primary_writers:
        idx = _parse_chapter_index(str(writer.get("title") or ""))
        if idx is not None:
            max_chapter_index = max(max_chapter_index, idx)
    if max_chapter_index <= 0:
        max_chapter_index = len(primary_writers)

    missing = min_chapters - len(primary_writers)
    for offset in range(1, missing + 1):
        chapter_index = max_chapter_index + offset
        writer_id = _allocate_node_id(existing_ids, "n_writer_extra")
        reviewer_id = _allocate_node_id(existing_ids, "n_reviewer_extra")
        writer_title = _normalized_chapter_title(chapter_index)
        reviewer_title = f"第{chapter_index}章审查"

        raw_nodes.append(
            {
                "id": writer_id,
                "title": writer_title,
                "role": "writer",
                "depends_on": list(writer_default_deps),
            }
        )
        raw_nodes.append(
            {
                "id": reviewer_id,
                "title": reviewer_title,
                "role": "reviewer",
                "depends_on": [writer_id],
            }
        )

    reviewer_ids = [str(node["id"]) for node in raw_nodes if _role(node) == "reviewer"]
    consistency_nodes = [node for node in raw_nodes if _role(node) == "consistency"]
    if consistency_nodes:
        for node in consistency_nodes:
            deps = [str(dep) for dep in node.get("depends_on", [])]
            node["depends_on"] = _dedupe_preserve_order(deps + reviewer_ids)
    elif reviewer_ids:
        consistency_id = _allocate_node_id(existing_ids, "n_consistency")
        raw_nodes.append(
            {
                "id": consistency_id,
                "title": "一致性检查",
                "role": "consistency",
                "depends_on": reviewer_ids,
            }
        )

    logger.bind(depth=depth, target_words=target_words).info(
        "Applied chapter guard: primary writers {} -> minimum {}",
        len(primary_writers),
        min_chapters,
    )
    return DAGSchema.model_validate({"nodes": raw_nodes})


def _compact_quick_short_dag(
    dag: DAGSchema,
    *,
    depth: str,
    target_words: int,
) -> DAGSchema:
    """Shrink quick low-word tasks to a minimal linear chain.

    This lowers end-to-end latency for smoke/E2E quick runs while preserving the
    role contract: outline -> researcher -> writer -> reviewer -> consistency.
    """
    if depth != "quick" or target_words > _QUICK_COMPACT_TARGET_WORDS_MAX:
        return dag
    if not dag.nodes:
        return dag

    role_nodes: dict[str, list] = {
        "outline": [],
        "researcher": [],
        "writer": [],
        "reviewer": [],
        "consistency": [],
    }
    for node in dag.nodes:
        role = str(node.role or "").strip().lower()
        if role in role_nodes:
            role_nodes[role].append(node)

    outline = role_nodes["outline"][0] if role_nodes["outline"] else None
    researcher = role_nodes["researcher"][0] if role_nodes["researcher"] else None
    writer = role_nodes["writer"][0] if role_nodes["writer"] else None
    reviewer = role_nodes["reviewer"][0] if role_nodes["reviewer"] else None
    consistency = role_nodes["consistency"][0] if role_nodes["consistency"] else None

    if outline is None:
        return dag
    if researcher is None or writer is None or reviewer is None:
        return dag

    outline_raw = outline.model_dump()
    outline_raw["depends_on"] = []
    researcher_raw = researcher.model_dump()
    researcher_raw["depends_on"] = [outline.id]
    writer_raw = writer.model_dump()
    writer_raw["depends_on"] = [researcher.id]
    reviewer_raw = reviewer.model_dump()
    reviewer_raw["depends_on"] = [writer.id]

    compact_nodes = [outline_raw, researcher_raw, writer_raw, reviewer_raw]
    if consistency is not None:
        consistency_raw = consistency.model_dump()
        consistency_raw["depends_on"] = [reviewer.id]
        compact_nodes.append(consistency_raw)

    compact = DAGSchema.model_validate({"nodes": compact_nodes})
    logger.bind(
        original_nodes=len(dag.nodes),
        compact_nodes=len(compact.nodes),
        target_words=target_words,
    ).info("Applied quick compact DAG for short target")
    return compact


# ---------------------------------------------------------------------------
# Main Decomposition
# ---------------------------------------------------------------------------

_prompt_loader = PromptLoader()


async def decompose_task(
    *,
    title: str,
    mode: str,
    depth: str = "standard",
    target_words: int = 10000,
    llm_client: BaseLLMClient,
    model: str | None = None,
    max_retries: int | None = None,
    fallback_models: list[str] | None = None,
) -> DAGSchema:
    """
    Validate input, load the prompt, call the LLM, and verify the DAG.

    Args:
        title: Task title or description.
        mode: Writing mode (report/novel/custom).
        depth: Planning depth (quick/standard/deep).
        target_words: Target word count.
        llm_client: Injected LLM client, including mocks in tests.

    Returns:
        DAGSchema: A validated DAG structure.

    Raises:
        TaskValidationError: Task input is invalid.
        ValueError: The DAG structure is invalid.
        CyclicDAGError: The DAG contains a cycle.
    """
    # Validate inputs before spending tokens.
    validation = validate_task_input(title, mode, depth)
    if not validation.ok:
        raise TaskValidationError(validation.issues)

    # Load and render the decomposition prompt.
    prompt = _prompt_loader.load(
        "orchestrator",
        "decompose",
        title=title,
        mode=mode,
        depth=depth,
        target_words=str(target_words),
    )

    # Ask the LLM for the DAG JSON.
    logger.bind(title=title, mode=mode, depth=depth).info(
        "Decomposing task via LLM"
    )
    try:
        raw = await llm_client.chat_json(
            messages=[{"role": "user", "content": prompt}],
            role="orchestrator",
            model=model,
            max_retries=max_retries,
            fallback_models=fallback_models,
            schema=DAGSchema,
        )
        # chat_json with schema returns model_dump() dict.
        dag = parse_dag_response(raw)
        dag = _ensure_research_gate(dag)
        dag = _ensure_depth_chapter_count(dag, depth=depth, target_words=target_words)
        dag = _inject_long_form_expansion_nodes(dag, target_words=target_words)
        dag = _compact_quick_short_dag(dag, depth=depth, target_words=target_words)
        # Ensure the returned DAG is acyclic.
        validate_dag_acyclic(dag)
        logger.bind(node_count=len(dag.nodes)).info("Task decomposed successfully")
        return dag
    except LLMUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - fallback should never crash task creation.
        logger.bind(title=title, mode=mode, depth=depth).warning(
            "LLM decomposition failed, using fallback DAG: {}", exc
        )
        dag = _build_fallback_dag(title)
        dag = _ensure_research_gate(dag)
        dag = _ensure_depth_chapter_count(dag, depth=depth, target_words=target_words)
        dag = _inject_long_form_expansion_nodes(dag, target_words=target_words)
        dag = _compact_quick_short_dag(dag, depth=depth, target_words=target_words)
        logger.bind(node_count=len(dag.nodes)).info("Fallback DAG generated")
        return dag
