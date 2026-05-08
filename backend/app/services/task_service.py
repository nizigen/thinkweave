"""Task service layer for creating, reading, and listing tasks."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.agent import Agent
from app.models.message import Message
from app.models.task import Task
from app.models.task_decomposition_audit import TaskDecompositionAudit
from app.models.task_node import TaskNode
from app.schemas.task import DAGSchema, DecompositionAuditRead, TaskCreate, TaskDetailRead, TaskNodeRead, TaskRead
from app.services.checkpoint_control import normalize_checkpoint_data
from app.services.dag_scheduler import start_scheduler
from app.services.entry_stage import build_entry_metadata
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.stage_contracts import get_stage_contract, resolve_stage_code
from app.services.writer_output import parse_writer_payload
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


_TERMINAL_TASK_STATUSES = {
    "done",
    "completed",
    "failed",
    "cancelled",
    "canceled",
}


def _allocate_hierarchy_node_id(existing_ids: set[str], base: str) -> str:
    if base not in existing_ids:
        existing_ids.add(base)
        return base
    suffix = 1
    while True:
        candidate = f"{base}_{suffix}"
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate
        suffix += 1


def _inject_hierarchy_entry_nodes(dag: DAGSchema) -> bool:
    """Inject L0/L1 lightweight entry nodes without changing downstream business DAG."""
    if not getattr(dag, "nodes", None):
        return False

    existing_ids = {str(getattr(node, "id", "")).strip() for node in dag.nodes}
    existing_ids = {v for v in existing_ids if v}
    orchestrator_id = _allocate_hierarchy_node_id(existing_ids, "l0_orchestrator_entry")
    manager_id = _allocate_hierarchy_node_id(existing_ids, "l1_manager_dispatch")

    original_nodes = list(dag.nodes)
    root_nodes = [
        node
        for node in original_nodes
        if not list(getattr(node, "depends_on", []) or [])
    ]
    if not root_nodes:
        return False

    for node in root_nodes:
        deps = list(getattr(node, "depends_on", []) or [])
        if manager_id not in deps:
            deps.append(manager_id)
        setattr(node, "depends_on", deps)

    orchestrator_node = SimpleNamespace(
        id=orchestrator_id,
        title="L0 编排入口：任务统筹与流程启动",
        role="orchestrator",
        depends_on=[],
        required_capabilities=[],
        preferred_agents=[],
        routing_mode="auto",
    )
    manager_node = SimpleNamespace(
        id=manager_id,
        title="L1 管理入口：资源协调与执行放行",
        role="manager",
        depends_on=[orchestrator_id],
        required_capabilities=[],
        preferred_agents=[],
        routing_mode="auto",
    )
    dag.nodes = [orchestrator_node, manager_node, *original_nodes]
    return True


async def _has_idle_hierarchy_agents(session: AsyncSession) -> bool:
    """Return whether both L0/L1 roles are immediately dispatchable (idle)."""
    if not hasattr(session, "execute"):
        return False
    try:
        result = await session.execute(
            select(Agent.role).where(Agent.status == "idle")
        )
    except Exception:
        logger.opt(exception=True).warning("failed to probe idle hierarchy agents; keep legacy flow")
        return False
    roles = {
        str(row[0] or "").strip().lower()
        for row in result.all()
        if str(row[0] or "").strip()
    }
    return "orchestrator" in roles and "manager" in roles


def _build_decomposition_audit_summary(
    trace: dict[str, Any] | None,
    *,
    attempt_no: int,
) -> dict[str, Any]:
    payload = dict(trace) if isinstance(trace, dict) else {}
    normalized = payload.get("normalized_dag")
    node_count = 0
    if isinstance(normalized, dict):
        nodes = normalized.get("nodes")
        if isinstance(nodes, list):
            node_count = len(nodes)
    repair_actions = payload.get("repair_actions")
    validation_issues = payload.get("validation_issues")
    return {
        "attempt_no": int(attempt_no),
        "decomposer_version": str(payload.get("decomposer_version") or ""),
        "node_count": node_count,
        "repair_actions_count": len(repair_actions) if isinstance(repair_actions, list) else 0,
        "validation_issues_count": len(validation_issues) if isinstance(validation_issues, list) else 0,
    }


async def _persist_decomposition_audit(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    trace: dict[str, Any] | None,
) -> int:
    payload = dict(trace) if isinstance(trace, dict) else {}
    result = await session.execute(
        select(TaskDecompositionAudit.attempt_no)
        .where(TaskDecompositionAudit.task_id == task_id)
        .order_by(TaskDecompositionAudit.attempt_no.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    attempt_no = int(latest or 0) + 1
    audit = TaskDecompositionAudit(
        task_id=task_id,
        attempt_no=attempt_no,
        decomposition_input=(
            payload.get("decomposition_input")
            if isinstance(payload.get("decomposition_input"), dict)
            else {}
        ),
        raw_llm_output=(
            payload.get("raw_llm_output")
            if isinstance(payload.get("raw_llm_output"), dict)
            else None
        ),
        normalized_dag=(
            payload.get("normalized_dag")
            if isinstance(payload.get("normalized_dag"), dict)
            else {}
        ),
        validation_issues=(
            payload.get("validation_issues")
            if isinstance(payload.get("validation_issues"), list)
            else []
        ),
        repair_actions=(
            payload.get("repair_actions")
            if isinstance(payload.get("repair_actions"), list)
            else []
        ),
        decomposer_version=str(payload.get("decomposer_version") or "unknown"),
    )
    session.add(audit)
    await session.flush()
    return attempt_no


def _build_blocking_reason(task: Task, nodes: list[TaskNodeRead]) -> str | None:
    status = str(task.status or "").strip().lower()
    if status in _TERMINAL_TASK_STATUSES:
        return None

    if task.error_message:
        return f"task error: {task.error_message}"

    running = [n for n in nodes if n.status == "running"]
    if running:
        labels = ", ".join(n.title for n in running[:3])
        suffix = "..." if len(running) > 3 else ""
        return f"running nodes ({len(running)}): {labels}{suffix}"

    ready = [n for n in nodes if n.status == "ready"]
    if ready:
        labels = ", ".join(n.title for n in ready[:3])
        suffix = "..." if len(ready) > 3 else ""
        return f"ready nodes waiting for assignment ({len(ready)}): {labels}{suffix}"

    node_by_id = {str(n.id): n for n in nodes}
    pending = [n for n in nodes if n.status == "pending"]
    if pending:
        blocked_titles: list[str] = []
        for node in pending:
            deps = [str(dep) for dep in (node.depends_on or [])]
            if not deps:
                blocked_titles.append(node.title)
                continue
            unresolved = [
                dep_id for dep_id in deps
                if node_by_id.get(dep_id) and node_by_id[dep_id].status not in {"done", "skipped"}
            ]
            if unresolved:
                blocked_titles.append(node.title)
        if blocked_titles:
            labels = ", ".join(blocked_titles[:3])
            suffix = "..." if len(blocked_titles) > 3 else ""
            return f"pending on unresolved dependencies ({len(blocked_titles)}): {labels}{suffix}"
        return f"pending nodes awaiting promotion ({len(pending)})"

    return f"task status={task.status or 'unknown'} with no active nodes"


def _build_node_status_summary(nodes: list[TaskNodeRead]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for node in nodes:
        status = str(node.status or "unknown").strip().lower() or "unknown"
        summary[status] = summary.get(status, 0) + 1
    return summary


def _build_stage_progress(nodes: list[TaskNodeRead]) -> dict[str, int]:
    progress: dict[str, int] = {}
    for node in nodes:
        stage = str(node.stage_code or "QA").strip().upper() or "QA"
        progress[stage] = progress.get(stage, 0) + 1
    return progress


def _parse_json_object(raw: Any) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_evidence_and_citation_summary(nodes: list[TaskNode]) -> tuple[dict[str, int], dict[str, int]]:
    evidence_total = 0
    evidence_with_url = 0
    evidence_unbound_claims = 0

    citations_total = 0
    citations_with_evidence = 0
    citations_uncertain = 0

    for node in nodes:
        role = str(getattr(node, "agent_role", "") or "").strip().lower()
        result = getattr(node, "result", None)
        if not result:
            continue

        if role == "researcher":
            parsed = _parse_json_object(result)
            if not parsed:
                continue
            ledger = parsed.get("evidence_ledger", [])
            if not isinstance(ledger, list):
                continue
            for item in ledger:
                if not isinstance(item, dict):
                    continue
                evidence_total += 1
                source_url = str(item.get("source_url") or "").strip()
                claim_target = str(item.get("claim_target") or "").strip()
                if source_url:
                    evidence_with_url += 1
                if not claim_target:
                    evidence_unbound_claims += 1

        if role == "writer":
            payload = parse_writer_payload(str(result))
            if not isinstance(payload, dict):
                continue
            citation_ledger = payload.get("citation_ledger", [])
            if not isinstance(citation_ledger, list):
                continue
            for row in citation_ledger:
                if not isinstance(row, dict):
                    continue
                citations_total += 1
                support = str(row.get("support") or "").strip().lower()
                if support and "uncertainty" not in support:
                    citations_with_evidence += 1
                else:
                    citations_uncertain += 1

    evidence_summary = {
        "total": evidence_total,
        "with_source_url": evidence_with_url,
        "unbound_claims": evidence_unbound_claims,
    }
    citation_summary = {
        "total": citations_total,
        "bound_to_evidence": citations_with_evidence,
        "uncertain_or_missing": citations_uncertain,
    }
    return evidence_summary, citation_summary


def _parse_capability_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace("\n", ",").replace(";", ",").replace("|", ",")
    tokens = [
        token.strip().lower()
        for token in normalized.split(",")
        if token.strip()
    ]
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _extract_routing_nodes_from_checkpoint(
    checkpoint_data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(checkpoint_data, dict):
        return {}
    raw = checkpoint_data.get("routing_nodes")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for node_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        out[str(node_id)] = {
            "required_capabilities": [
                str(v).strip().lower()
                for v in entry.get("required_capabilities", [])
                if str(v).strip()
            ],
            "preferred_agents": [
                str(v).strip()
                for v in entry.get("preferred_agents", [])
                if str(v).strip()
            ],
            "routing_mode": str(entry.get("routing_mode") or "auto"),
        }
    return out


def _extract_routing_results_from_checkpoint(
    checkpoint_data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(checkpoint_data, dict):
        return {}
    raw = checkpoint_data.get("routing_results")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for node_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        out[str(node_id)] = {
            "routing_reason": str(entry.get("routing_reason") or "").strip() or None,
            "routing_status": str(entry.get("routing_status") or "").strip() or None,
        }
    return out


def _apply_monitor_recovery_event(
    task: Task,
    *,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    checkpoint = normalize_checkpoint_data(
        task.checkpoint_data,
        ensure_control_maps=True,
    )
    control = checkpoint["control"]
    if event_type == "chapter_preview":
        preview_cache = dict(control["preview_cache"])
        preview_cache[node_id] = dict(payload)
        control["preview_cache"] = preview_cache
    elif event_type == "review_score":
        review_scores = dict(control["review_scores"])
        review_scores[node_id] = dict(payload)
        control["review_scores"] = review_scores
    elif event_type == "memory_write":
        memory_writes = dict(control.get("memory_writes") or {})
        node_rows_raw = memory_writes.get(node_id, [])
        node_rows = list(node_rows_raw) if isinstance(node_rows_raw, list) else []
        entry = {
            "at": str(payload.get("at") or ""),
            "role": str(payload.get("role") or ""),
            "title": str(payload.get("title") or ""),
            "summary": str(payload.get("summary") or "")[:500],
            "chars": int(payload.get("chars") or 0),
            "depth": str(payload.get("depth") or ""),
        }
        if payload.get("chapter_index") is not None:
            entry["chapter_index"] = payload.get("chapter_index")
        if payload.get("chapter_title"):
            entry["chapter_title"] = str(payload.get("chapter_title") or "")[:200]
        node_rows.append(entry)
        memory_writes[node_id] = node_rows[-10:]
        control["memory_writes"] = memory_writes
    else:
        return
    checkpoint["control"] = control
    task.checkpoint_data = checkpoint


async def _build_routing_snapshot(
    session: AsyncSession,
    *,
    dag: DAGSchema,
) -> dict[str, Any] | None:
    """Capture required/available roles for diagnostics and operator visibility."""
    required_roles = sorted(
        {
            str(node.role).strip()
            for node in dag.nodes
            if str(node.role).strip()
        }
    )
    if not required_roles:
        return None

    # Unit-test fakes may not implement execute(); keep create_task lightweight there.
    if not hasattr(session, "execute"):
        required_capabilities = sorted(
            {
                cap
                for node in dag.nodes
                for cap in getattr(node, "required_capabilities", [])
                if str(cap).strip()
            }
        )
        return {
            "required_roles": required_roles,
            "available_roles": [],
            "missing_roles": required_roles,
            "required_capabilities": required_capabilities,
            "available_capabilities": [],
            "missing_capabilities": required_capabilities,
            "strict_bind_failures": [],
        }

    required_capabilities = sorted(
        {
            cap
            for node in dag.nodes
            for cap in getattr(node, "required_capabilities", [])
            if str(cap).strip()
        }
    )

    try:
        result = await session.execute(
            select(Agent.id, Agent.name, Agent.role, Agent.capabilities)
            .where(Agent.status.in_(("idle", "busy")))
        )
        rows = result.all()
        available_roles = sorted({
            str(row[2]).strip()
            for row in rows
            if str(row[2]).strip()
        })
        available_capabilities = sorted(
            {
                cap
                for _, _, _, capabilities in rows
                for cap in _parse_capability_tokens(capabilities)
            }
        )
        available_agent_refs = {
            str(agent_id).strip().lower()
            for agent_id, _, _, _ in rows
            if str(agent_id).strip()
        } | {
            str(name).strip().lower()
            for _, name, _, _ in rows
            if str(name).strip()
        }
    except Exception:
        logger.opt(exception=True).warning("failed to build routing snapshot")
        return {
            "required_roles": required_roles,
            "available_roles": [],
            "missing_roles": required_roles,
            "required_capabilities": required_capabilities,
            "available_capabilities": [],
            "missing_capabilities": required_capabilities,
            "strict_bind_failures": [],
        }

    available_set = set(available_roles)
    missing_roles = sorted(role for role in required_roles if role not in available_set)
    available_cap_set = set(available_capabilities)
    missing_capabilities = sorted(
        cap for cap in required_capabilities if cap not in available_cap_set
    )
    strict_bind_failures: list[dict[str, Any]] = []
    for node in dag.nodes:
        routing_mode = str(getattr(node, "routing_mode", "auto") or "auto")
        preferred_agents = [
            str(agent).strip().lower()
            for agent in getattr(node, "preferred_agents", [])
            if str(agent).strip()
        ]
        if routing_mode != "strict_bind" or not preferred_agents:
            continue
        if any(agent in available_agent_refs for agent in preferred_agents):
            continue
        strict_bind_failures.append(
            {
                "node_id": str(getattr(node, "id", "")),
                "preferred_agents": preferred_agents,
            }
        )
    return {
        "required_roles": required_roles,
        "available_roles": available_roles,
        "missing_roles": missing_roles,
        "required_capabilities": required_capabilities,
        "available_capabilities": available_capabilities,
        "missing_capabilities": missing_capabilities,
        "strict_bind_failures": strict_bind_failures,
    }


async def create_task(
    session: AsyncSession,
    task_in: TaskCreate,
    llm_client: BaseLLMClient,
    *,
    owner_id: str = "",
) -> TaskDetailRead:
    """
    Create a task, trigger LLM decomposition, persist DAG nodes.

    Flow: create the task row, decompose it via the LLM, persist DAG nodes,
    then return the task detail payload.
    """
    # Persist the task row first so downstream records can reference it.
    entry_meta = build_entry_metadata(
        draft_text=task_in.draft_text,
        review_comments=task_in.review_comments,
    )
    task = Task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
        owner_id=owner_id or None,
        status="decomposing",
        fsm_state=entry_meta["entry_stage"],
        checkpoint_data=entry_meta,
    )
    session.add(task)
    await session.flush()

    logger.bind(task_id=str(task.id), mode=task.mode).info(
        "Task created, starting decomposition"
    )

    # Phase-1 reset: route planning through stage-oriented orchestrator skeleton.
    orchestrator = PipelineOrchestrator(llm_client)
    dag, pipeline_meta = await orchestrator.plan_task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
    )
    hierarchy_injected = False
    hierarchy_enabled = await _has_idle_hierarchy_agents(session)
    if hierarchy_enabled:
        hierarchy_injected = _inject_hierarchy_entry_nodes(dag)
        if hierarchy_injected:
            logger.bind(task_id=str(task.id)).info(
                "hierarchy entry nodes injected into runtime DAG (L0 -> L1 -> L2)"
            )
    checkpoint = (
        dict(task.checkpoint_data)
        if isinstance(task.checkpoint_data, dict)
        else {}
    )
    checkpoint.update(pipeline_meta)
    pipeline = checkpoint.get("pipeline") if isinstance(checkpoint.get("pipeline"), dict) else {}
    pipeline = dict(pipeline)
    pipeline["hierarchy_entry"] = {
        "enabled": bool(hierarchy_enabled),
        "injected": bool(hierarchy_injected),
    }
    checkpoint["pipeline"] = pipeline
    task.checkpoint_data = checkpoint
    decomposition_trace = (
        pipeline_meta.get("decomposition_trace")
        if isinstance(pipeline_meta, dict)
        else None
    )
    audit_persisted = True
    try:
        async with session.begin_nested():
            attempt_no = await _persist_decomposition_audit(
                session,
                task_id=task.id,
                trace=decomposition_trace if isinstance(decomposition_trace, dict) else None,
            )
    except Exception:
        logger.bind(task_id=str(task.id)).opt(exception=True).warning(
            "failed to persist decomposition audit detail"
        )
        attempt_no = 1
        audit_persisted = False
    checkpoint = (
        dict(task.checkpoint_data)
        if isinstance(task.checkpoint_data, dict)
        else {}
    )
    summary = _build_decomposition_audit_summary(
        decomposition_trace if isinstance(decomposition_trace, dict) else None,
        attempt_no=attempt_no,
    )
    summary["detail_persisted"] = audit_persisted
    checkpoint["decomposition_audit_summary"] = summary
    task.checkpoint_data = checkpoint
    routing_snapshot = await _build_routing_snapshot(session, dag=dag)
    if routing_snapshot is not None:
        checkpoint = (
            dict(task.checkpoint_data)
            if isinstance(task.checkpoint_data, dict)
            else {}
        )
        checkpoint["routing_snapshot"] = routing_snapshot
        task.checkpoint_data = checkpoint
        if routing_snapshot.get("missing_roles"):
            logger.bind(task_id=str(task.id)).warning(
                "task created with missing agent roles: {}",
                routing_snapshot["missing_roles"],
            )

    # Map DAG string IDs to database UUID primary keys.
    id_map: dict[str, uuid.UUID] = {}
    nodes: list[TaskNode] = []

    for dag_node in dag.nodes:
        node_uuid = uuid.uuid4()
        id_map[dag_node.id] = node_uuid

    for dag_node in dag.nodes:
        depends_uuids = [id_map[dep] for dep in dag_node.depends_on]
        node = TaskNode(
            id=id_map[dag_node.id],
            task_id=task.id,
            title=dag_node.title,
            agent_role=dag_node.role,
            status="pending",
            depends_on=depends_uuids if depends_uuids else None,
        )
        nodes.append(node)
        session.add(node)

    routing_nodes: dict[str, dict[str, Any]] = {}
    for dag_node in dag.nodes:
        node_uuid = id_map[dag_node.id]
        required_caps = [
            str(cap).strip().lower()
            for cap in getattr(dag_node, "required_capabilities", [])
            if str(cap).strip()
        ]
        preferred_agents = [
            str(agent).strip()
            for agent in getattr(dag_node, "preferred_agents", [])
            if str(agent).strip()
        ]
        routing_mode = str(getattr(dag_node, "routing_mode", "auto") or "auto")
        if required_caps or preferred_agents or routing_mode != "auto":
            routing_nodes[str(node_uuid)] = {
                "required_capabilities": sorted(set(required_caps)),
                "preferred_agents": preferred_agents,
                "routing_mode": routing_mode,
            }

    if routing_nodes:
        checkpoint = (
            dict(task.checkpoint_data)
            if isinstance(task.checkpoint_data, dict)
            else {}
        )
        checkpoint["routing_nodes"] = routing_nodes
        task.checkpoint_data = checkpoint

    # Mark the task as ready once all nodes are persisted.
    task.status = "pending"
    await session.flush()
    await session.commit()

    logger.bind(task_id=str(task.id), node_count=len(nodes)).info(
        "DAG nodes persisted"
    )

    try:
        await start_scheduler(task.id)
    except Exception:  # noqa: BLE001 - response should not fail after persistence.
        logger.bind(task_id=str(task.id)).opt(exception=True).warning(
            "failed to start DAG scheduler after task creation"
        )

    # Build the response from the persisted task and node state.
    routing_node_meta = _extract_routing_nodes_from_checkpoint(task.checkpoint_data)
    routing_results = _extract_routing_results_from_checkpoint(task.checkpoint_data)
    node_reads = []
    for n in nodes:
        node_meta = routing_node_meta.get(str(n.id), {})
        result_meta = routing_results.get(str(n.id), {})
        stage_code = resolve_stage_code(role=n.agent_role, title=n.title)
        stage_contract = get_stage_contract(stage_code)
        node_reads.append(
            TaskNodeRead(
                id=n.id,
                task_id=n.task_id,
                title=n.title,
                agent_role=n.agent_role,
                assigned_agent=n.assigned_agent,
                status=n.status,
                depends_on=n.depends_on or [],
                retry_count=n.retry_count,
                version=int(getattr(n, "version", 0) or 0),
                started_at=n.started_at,
                finished_at=n.finished_at,
                required_capabilities=list(node_meta.get("required_capabilities", [])),
                preferred_agents=list(node_meta.get("preferred_agents", [])),
                routing_mode=str(node_meta.get("routing_mode") or "auto"),
                routing_reason=result_meta.get("routing_reason"),
                routing_status=result_meta.get("routing_status"),
                stage_code=stage_code,
                stage_name=str(stage_contract.get("name") or "") or None,
            )
        )
    blocking_reason = _build_blocking_reason(task, node_reads)
    evidence_summary, citation_summary = _build_evidence_and_citation_summary(nodes)
    return TaskDetailRead(
        id=task.id,
        title=task.title,
        mode=task.mode,
        status=task.status,
        fsm_state=task.fsm_state,
        word_count=task.word_count,
        depth=task.depth,
        target_words=task.target_words,
        created_at=task.created_at,
        finished_at=task.finished_at,
        checkpoint_data=normalize_checkpoint_data(
            task.checkpoint_data,
            ensure_control_maps=True,
        ),
        nodes=node_reads,
        blocking_reason=blocking_reason,
        node_status_summary=_build_node_status_summary(node_reads),
        stage_progress=_build_stage_progress(node_reads),
        evidence_summary=evidence_summary,
        citation_summary=citation_summary,
        decomposition_audit_summary=dict(
            (
                normalize_checkpoint_data(
                    task.checkpoint_data,
                    ensure_control_maps=True,
                ).get("decomposition_audit_summary")
            )
            or {}
        ),
    )


async def get_task_detail(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str = "",
    is_admin: bool = False,
) -> TaskDetailRead | None:
    """Get a task with its DAG nodes. Returns None if not found."""
    task = await session.get(Task, task_id)
    if task is None:
        return None
    if not task_visible_to_user(task, user_id=user_id, is_admin=is_admin):
        return None

    result = await session.execute(
        select(TaskNode)
        .where(TaskNode.task_id == task_id)
        .order_by(TaskNode.id)
    )
    nodes = list(result.scalars().all())

    routing_node_meta = _extract_routing_nodes_from_checkpoint(task.checkpoint_data)
    routing_results = _extract_routing_results_from_checkpoint(task.checkpoint_data)
    node_reads: list[TaskNodeRead] = []
    for n in nodes:
        node_meta = routing_node_meta.get(str(n.id), {})
        result_meta = routing_results.get(str(n.id), {})
        stage_code = resolve_stage_code(role=n.agent_role, title=n.title)
        stage_contract = get_stage_contract(stage_code)
        read = TaskNodeRead(
            id=n.id,
            task_id=n.task_id,
            title=n.title,
            agent_role=n.agent_role,
            assigned_agent=n.assigned_agent,
            status=n.status,
            depends_on=n.depends_on or [],
            retry_count=n.retry_count,
            version=int(getattr(n, "version", 0) or 0),
            started_at=n.started_at,
            finished_at=n.finished_at,
            required_capabilities=list(node_meta.get("required_capabilities", [])),
            preferred_agents=list(node_meta.get("preferred_agents", [])),
            routing_mode=str(node_meta.get("routing_mode") or "auto"),
            routing_reason=result_meta.get("routing_reason"),
            routing_status=result_meta.get("routing_status"),
            stage_code=stage_code,
            stage_name=str(stage_contract.get("name") or "") or None,
        )
        node_reads.append(read)
    task_read = TaskDetailRead.model_validate(task)
    task_read.checkpoint_data = normalize_checkpoint_data(
        task.checkpoint_data,
        ensure_control_maps=True,
    )
    task_read.nodes = node_reads
    task_read.blocking_reason = _build_blocking_reason(task, node_reads)
    task_read.node_status_summary = _build_node_status_summary(node_reads)
    task_read.stage_progress = _build_stage_progress(node_reads)
    evidence_summary, citation_summary = _build_evidence_and_citation_summary(nodes)
    task_read.evidence_summary = evidence_summary
    task_read.citation_summary = citation_summary
    task_read.decomposition_audit_summary = dict(
        normalize_checkpoint_data(
            task.checkpoint_data,
            ensure_control_maps=True,
        ).get("decomposition_audit_summary")
        or {}
    )
    return task_read


async def get_task_decomposition_audit(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str = "",
    is_admin: bool = False,
) -> DecompositionAuditRead | None:
    task = await session.get(Task, task_id)
    if task is None:
        return None
    if not task_visible_to_user(task, user_id=user_id, is_admin=is_admin):
        return None

    try:
        result = await session.execute(
            select(TaskDecompositionAudit)
            .where(TaskDecompositionAudit.task_id == task_id)
            .order_by(TaskDecompositionAudit.attempt_no.desc())
            .limit(1)
        )
        audit = result.scalar_one_or_none()
    except Exception:
        audit = None

    if audit is not None:
        raw_output = audit.raw_llm_output if is_admin else None
        return DecompositionAuditRead(
            task_id=task_id,
            attempt_no=int(audit.attempt_no),
            decomposition_input=dict(audit.decomposition_input or {}),
            raw_llm_output=dict(raw_output or {}) if isinstance(raw_output, dict) else None,
            normalized_dag=dict(audit.normalized_dag or {}),
            validation_issues=[str(item) for item in (audit.validation_issues or [])],
            repair_actions=[
                dict(item) for item in (audit.repair_actions or [])
                if isinstance(item, dict)
            ],
            decomposer_version=str(audit.decomposer_version or ""),
            created_at=audit.created_at,
        )

    checkpoint = normalize_checkpoint_data(task.checkpoint_data, ensure_control_maps=True)
    pipeline = checkpoint.get("pipeline")
    trace = pipeline.get("decomposition_trace") if isinstance(pipeline, dict) else None
    if not isinstance(trace, dict):
        return None
    summary = checkpoint.get("decomposition_audit_summary")
    attempt_no = int((summary or {}).get("attempt_no", 1)) if isinstance(summary, dict) else 1
    raw_output = trace.get("raw_llm_output") if is_admin else None
    return DecompositionAuditRead(
        task_id=task_id,
        attempt_no=attempt_no,
        decomposition_input=dict(trace.get("decomposition_input") or {}),
        raw_llm_output=dict(raw_output or {}) if isinstance(raw_output, dict) else None,
        normalized_dag=dict(trace.get("normalized_dag") or {}),
        validation_issues=[str(item) for item in (trace.get("validation_issues") or [])],
        repair_actions=[
            dict(item) for item in (trace.get("repair_actions") or [])
            if isinstance(item, dict)
        ],
        decomposer_version=str(trace.get("decomposer_version") or ""),
        created_at=None,
    )


async def persist_monitor_recovery_event(
    *,
    task_id: str | uuid.UUID,
    node_id: str | uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    session: AsyncSession | None = None,
) -> None:
    node_key = str(node_id)
    if event_type not in {"chapter_preview", "review_score", "memory_write"}:
        return

    try:
        task_uuid = uuid.UUID(str(task_id))
    except (TypeError, ValueError, AttributeError):
        return

    if session is not None:
        task = await session.get(Task, task_uuid)
        if task is None:
            return
        _apply_monitor_recovery_event(
            task,
            node_id=node_key,
            event_type=event_type,
            payload=payload,
        )
        return

    async with async_session_factory() as inner_session:
        task = await inner_session.get(Task, task_uuid)
        if task is None:
            return
        _apply_monitor_recovery_event(
            task,
            node_id=node_key,
            event_type=event_type,
            payload=payload,
        )
        await inner_session.commit()


def task_visible_to_user(
    task: Task | Any,
    *,
    user_id: str,
    is_admin: bool,
) -> bool:
    if is_admin:
        return True
    owner_id = str(task.owner_id or "").strip()
    requested_user_id = user_id.strip()
    if not owner_id or not requested_user_id:
        return False
    return owner_id == requested_user_id


async def list_tasks(
    session: AsyncSession,
    *,
    user_id: str = "",
    offset: int = 0,
    limit: int = 50,
    status: str | None = None,
    mode: str | None = None,
    search: str | None = None,
) -> tuple[list[TaskRead], int]:
    """Return tasks ordered by creation time (newest first), with filters and total count."""
    from sqlalchemy import func, select as sa_select
    stmt = sa_select(Task).order_by(Task.created_at.desc())
    if user_id:
        stmt = stmt.where(Task.owner_id == user_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if mode:
        stmt = stmt.where(Task.mode == mode)
    if search:
        stmt = stmt.where(Task.title.ilike(f"%{search}%"))
    count_stmt = sa_select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()
    result = await session.execute(stmt.offset(offset).limit(limit))
    tasks = result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks], total


async def batch_delete_tasks(
    session: AsyncSession,
    *,
    user_id: str,
    ids: list[uuid.UUID],
) -> int:
    """Delete tasks by id list scoped to user. Returns deleted count."""
    from sqlalchemy import delete
    if not ids:
        return 0
    if not user_id:
        raise ValueError("user_id is required for batch_delete_tasks")
    owned_task_rows = await session.execute(
        select(Task.id).where(Task.id.in_(ids)).where(Task.owner_id == user_id)
    )
    owned_task_ids = [row[0] for row in owned_task_rows.all()]
    if not owned_task_ids:
        return 0

    # `messages.task_id` has no DB-level cascade, so remove dependent rows first.
    await session.execute(
        delete(Message).where(Message.task_id.in_(owned_task_ids))
    )
    result = await session.execute(
        delete(Task).where(Task.id.in_(owned_task_ids))
    )
    await session.commit()
    return int(result.rowcount or 0)
