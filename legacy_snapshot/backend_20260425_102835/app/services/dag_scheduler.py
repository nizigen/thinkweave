"""DAG 调度引擎 — 就绪节点检测 / Agent匹配 / 并发控制 / 任务分配 / 失败重试

核心循环（每秒一轮）：
  1. 收集已完成节点的结果
  2. 检查超时节点
  3. 计算新的就绪节点（前置依赖全部完成）
  4. 匹配空闲Agent并分配（受并发上限约束）
  5. 失败节点重试（最多3次）或标记 failed
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent
from app.models.task import Task
from app.models.task_node import TaskNode
from app.services.checkpoint_control import normalize_checkpoint_data
from app.services.writer_output import extract_writer_markdown, is_valid_writer_output_text
from app.services.stage_contracts import (
    SCHEMA_VERSION,
    get_stage_contract,
    resolve_stage_code,
)
from app.services import communicator
from app.services.heartbeat import HEARTBEAT_TIMEOUT_SECONDS, get_all_agent_states
from app.services.redis_streams import (
    MessageEnvelope,
    add_timeout_watch,
    get_dag_state,
    get_timed_out_nodes,
    parse_timeout_watch_member,
    push_ready_node,
    remove_timeout_watch,
    set_dag_node_status,
    task_events_key,
    timeout_watch_member,
    xread_latest,
)
from app.utils.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
MIN_TARGET_WORD_RATIO = 0.9
AUTO_EXPANSION_MAX_WAVES = 3
MAX_CONSISTENCY_REPAIR_WAVES = 2

# 节点状态常量
STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# 协作式控制状态
CONTROL_ACTIVE = "active"
CONTROL_PAUSE_REQUESTED = "pause_requested"
CONTROL_PAUSED = "paused"
CONTROL_BLOCKING_STATUSES = frozenset({CONTROL_PAUSE_REQUESTED, CONTROL_PAUSED})
SATISFIED_DEPENDENCY_STATUSES = frozenset({STATUS_DONE, STATUS_SKIPPED})
TERMINAL_NODE_STATUSES = frozenset({STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED})
SUCCESS_NODE_STATUSES = frozenset({STATUS_DONE, STATUS_SKIPPED})

# Agent 状态常量
AGENT_IDLE = "idle"
AGENT_BUSY = "busy"


def _parse_capability_tokens(raw: str | None) -> set[str]:
    if not raw:
        return set()
    normalized = raw.replace("\n", ",").replace(";", ",").replace("|", ",")
    return {
        token.strip().lower()
        for token in normalized.split(",")
        if token.strip()
    }


def _derive_research_keywords(*texts: str, limit: int = 10) -> list[str]:
    """Derive compact keyword candidates from title/chapter text."""
    candidates: list[str] = []
    seen: set[str] = set()
    for text in texts:
        raw = str(text or "").strip()
        if not raw:
            continue
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", raw):
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(token)
        for token in re.findall(r"[\u4e00-\u9fff]{2,8}", raw):
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(token)
        if len(candidates) >= limit:
            break
    return candidates[:limit]


def _build_source_policy(mode: str) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "novel":
        return {
            "policy_name": "creative_reference_lite",
            "allowed_source_types": [
                "authoritative background references (optional)",
                "style guides",
                "historical/cultural references when explicitly needed",
            ],
            "preferred_domains": [
                "encyclopedia.org",
                "official museum/university pages",
                "public domain archives",
            ],
            "forbidden": [
                "fabricated quotes/citations",
                "fake data and fake institutions",
            ],
            "evidence_rule": "If no source is available, write without factual claims.",
        }
    return {
        "policy_name": "report_evidence_first",
        "allowed_source_types": [
            "peer-reviewed papers",
            "official standards/regulatory docs",
            "vendor or project official documentation",
            "recognized research institutes",
        ],
        "preferred_domains": [
            "arxiv.org",
            "openalex.org",
            "pubmed.ncbi.nlm.nih.gov",
            "nature.com",
            "science.org",
            "ieee.org",
            "acm.org",
            "w3.org",
            "ietf.org",
            "github.com/<official-org>",
        ],
        "forbidden": [
            "SEO farms",
            "anonymous content farms",
            "non-attributed social reposts",
            "fabricated references",
        ],
        "evidence_rule": "Major claims must map to evidence IDs. If evidence is missing, mark the claim as uncertain.",
    }


def _is_suspicious_node_output(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    lowered = text.lower()
    compact = lowered.replace(" ", "")
    if compact.startswith("<!doctypehtml"):
        return True
    if 'name="aliyun_waf_aa"' in lowered:
        return True
    html_like = compact.startswith("<html") or "<html" in compact
    markers = ("captcha", "cloudflare", "security check", "waf", "访问验证", "人机验证")
    return html_like and any(marker in lowered for marker in markers)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        parsed = json.loads(body)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _count_text_units(text: str) -> int:
    body = str(text or "")
    if not body:
        return 0
    han_count = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin_count = len(re.findall(r"[a-zA-Z]+", body))
    return han_count + latin_count


def _extract_word_budget_hint(text: str) -> int | None:
    body = str(text or "")
    match = re.search(r"目标补写约\s*(\d+)\s*字", body)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    return value if value > 0 else None


def _normalize_repair_targets(raw: Any) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except Exception:
            continue
        if value <= 0:
            continue
        if value not in out:
            out.append(value)
    return out


def _looks_like_review_or_consistency_json(text: str) -> bool:
    parsed = _parse_json_object(text)
    if not parsed:
        return False
    keys = {str(k).lower() for k in parsed.keys()}
    review_markers = {"score", "must_fix", "strongest_counterargument", "non_overlap_score"}
    consistency_markers = {"style_conflicts", "claim_conflicts", "duplicate_coverage", "repair_targets"}
    return bool(keys & review_markers) or bool(keys & consistency_markers)


def _looks_like_consistency_json(text: str) -> bool:
    parsed = _parse_json_object(text)
    if not parsed:
        return False
    keys = {str(k).lower() for k in parsed.keys()}
    consistency_markers = {"style_conflicts", "claim_conflicts", "duplicate_coverage", "repair_targets"}
    return bool(keys & consistency_markers)


def _is_invalid_output_for_role(role: str | None, content: str) -> bool:
    role_name = str(role or "").strip().lower()
    text = (content or "").strip()
    if not text:
        return True
    if role_name == "writer":
        return not is_valid_writer_output_text(text)
    if role_name == "reviewer":
        parsed = _parse_json_object(text)
        if not parsed:
            return True
        required = {"score", "must_fix", "feedback", "pass"}
        return not required.issubset({str(k).lower() for k in parsed.keys()})
    if role_name == "consistency":
        parsed = _parse_json_object(text)
        if not parsed:
            return True
        required = {"pass", "style_conflicts", "claim_conflicts", "repair_targets"}
        return not required.issubset({str(k).lower() for k in parsed.keys()})
    return False


# ---------------------------------------------------------------------------
# DAGScheduler
# ---------------------------------------------------------------------------

class DAGScheduler:
    """DAG 调度器：驱动单个 Task 的所有节点执行。

    每个 Task 对应一个 DAGScheduler 实例，通过 ``run()`` 启动后持续
    调度直到所有节点完成或不可恢复失败。

    设计要点：
    - 并发控制通过 ``asyncio.Semaphore`` 实现，限制同时运行的 LLM 调用数
    - 写作节点额外受 ``MAX_CONCURRENT_WRITERS`` 限制
    - 节点完成/失败后立即触发下一轮就绪计算，不等待下一个调度周期
    """

    def __init__(self, task_id: uuid.UUID) -> None:
        self.task_id = task_id
        self._stop = asyncio.Event()

        # 并发信号量
        self._llm_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)
        self._writer_semaphore = asyncio.Semaphore(settings.max_concurrent_writers)

        # 追踪运行中的节点 {node_id: agent_id}
        self._running_nodes: dict[uuid.UUID, uuid.UUID] = {}

        # 运行中节点的角色缓存 {node_id: role}
        self._cached_node_roles: dict[uuid.UUID, str] = {}

        # 就绪计算通知
        self._schedule_event = asyncio.Event()
        # task events 读取游标（用于消费 agent task_result）
        self._task_events_cursor = "0-0"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """主调度循环 — 持续驱动直到 DAG 完成或全部失败。"""
        log = logger.bind(task_id=str(self.task_id))
        log.info("DAGScheduler started")

        try:
            # 初始化：将所有无依赖的节点标为 ready
            await self._init_ready_nodes()
            # 修复重启后遗留的 running 节点（内存态丢失时会卡死）。
            try:
                await self._reconcile_orphan_running_nodes()
            except Exception:
                log.opt(exception=True).warning(
                    "failed to reconcile orphan running nodes on startup; continue without recovery"
                )

            while not self._stop.is_set():
                # 0. 消费节点执行结果
                await self._drain_task_results()

                # 1. 检查超时
                await self._check_timeouts()

                # 2. 调度就绪节点
                dispatched = await self._dispatch_ready_nodes()

                # 3. 检查是否所有节点都已进入终态
                if await self._all_nodes_terminal():
                    if await self._has_failed_nodes():
                        log.error("DAG completed with failed nodes")
                        await self._mark_task_failed("DAG completed with failed nodes")
                    else:
                        log.info("DAG completed — all nodes done")
                        terminal = await self._mark_task_done()
                        if terminal == "extended":
                            continue
                    break

                # 4. 检查是否死锁（没有 running 也没有 ready）
                if not dispatched and not self._running_nodes:
                    if not await self._control_blocks_deadlock() and await self._has_undone_nodes():
                        log.error("DAG deadlocked — no running/ready nodes remain")
                        await self._mark_task_failed("DAG deadlock: unreachable nodes")
                        break

                # 等待：有节点完成/超时时被唤醒，或超时 1 秒
                self._schedule_event.clear()
                try:
                    await asyncio.wait_for(self._schedule_event.wait(), timeout=1.0)
                except TimeoutError:
                    pass

        except Exception:
            log.opt(exception=True).error("DAGScheduler crashed")
            await self._mark_task_failed("Scheduler internal error")
        finally:
            await self.cleanup()
            log.info("DAGScheduler stopped")

    def stop(self) -> None:
        """外部请求停止调度。"""
        self._stop.set()
        self._schedule_event.set()

    def wake(self) -> None:
        """唤醒调度循环，触发一次即时重算。"""
        self._schedule_event.set()

    async def cleanup(self) -> None:
        """停止后清理运行中节点的超时监控和 Agent 状态。"""
        for node_id, agent_id in list(self._running_nodes.items()):
            await self._clear_timeout_watch(node_id)
            async with async_session_factory() as session:
                await session.execute(
                    update(Agent)
                    .where(Agent.id == agent_id)
                    .values(status=AGENT_IDLE)
                )
                await session.commit()
        self._running_nodes.clear()
        self._node_roles.clear()

    async def on_node_completed(
        self,
        node_id: uuid.UUID,
        result: str,
        agent_id: uuid.UUID,
    ) -> None:
        """Agent 完成节点后回调 — 更新状态并触发下一轮调度。"""
        log = logger.bind(task_id=str(self.task_id), node_id=str(node_id))

        async with async_session_factory() as session:
            node = await session.get(TaskNode, node_id)
            if node is None:
                return
            if node.status == STATUS_SKIPPED:
                await self.reconcile_skipped_node(node_id)
                log.info("skipped node completion callback reconciled")
                return

            tracked_agent_id = self._running_nodes.get(node_id)
            if (
                tracked_agent_id != agent_id
                or node.status != STATUS_RUNNING
                or node.assigned_agent != agent_id
            ):
                log.info("stale completion callback ignored")
                return

            await session.execute(
                update(TaskNode)
                .where(TaskNode.id == node_id)
                .values(
                    status=STATUS_DONE,
                    result=result,
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            # 释放 Agent
            await session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status=AGENT_IDLE)
            )
            await session.commit()

        # 更新 Redis DAG 状态快照
        await set_dag_node_status(self.task_id, str(node_id), STATUS_DONE)
        await self._clear_timeout_watch(node_id)

        self._running_nodes.pop(node_id, None)
        self._node_roles.pop(node_id, None)
        log.info("node completed")

        # 标记下游节点为 ready
        await self._activate_dependents(node_id)
        self._schedule_event.set()

    async def on_node_failed(
        self,
        node_id: uuid.UUID,
        error: str,
        agent_id: uuid.UUID,
    ) -> None:
        """Agent 执行失败回调 — 重试或标记失败。"""
        log = logger.bind(task_id=str(self.task_id), node_id=str(node_id))

        async with async_session_factory() as session:
            node = await session.get(TaskNode, node_id)
            if node is None:
                return
            if node.status == STATUS_SKIPPED:
                await self.reconcile_skipped_node(node_id)
                log.info("skipped node failure callback reconciled")
                return

            tracked_agent_id = self._running_nodes.get(node_id)
            if (
                tracked_agent_id != agent_id
                or node.status != STATUS_RUNNING
                or node.assigned_agent != agent_id
            ):
                log.info("stale failure callback ignored")
                return

            # 释放 Agent
            await session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status=AGENT_IDLE)
            )

            new_retry = node.retry_count + 1
            if new_retry < MAX_RETRIES:
                # 重试：回到 ready 队列
                await session.execute(
                    update(TaskNode)
                    .where(TaskNode.id == node_id)
                    .values(
                        status=STATUS_READY,
                        retry_count=new_retry,
                        assigned_agent=None,
                    )
                )
                await session.commit()
                await set_dag_node_status(self.task_id, str(node_id), STATUS_READY)
                await self._clear_timeout_watch(node_id)

                self._running_nodes.pop(node_id, None)
                self._node_roles.pop(node_id, None)
                log.warning("node failed (retry {}/{}): {}", new_retry, MAX_RETRIES, error)

                # 推入就绪队列，优先级降低
                await push_ready_node(str(node_id), priority=float(new_retry))
            else:
                # 超过最大重试次数
                await session.execute(
                    update(TaskNode)
                    .where(TaskNode.id == node_id)
                    .values(
                        status=STATUS_FAILED,
                        retry_count=new_retry,
                        result=f"FAILED after {MAX_RETRIES} retries: {error}",
                        finished_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                await session.commit()
                await set_dag_node_status(self.task_id, str(node_id), STATUS_FAILED)
                await self._clear_timeout_watch(node_id)

                self._running_nodes.pop(node_id, None)
                self._node_roles.pop(node_id, None)
                log.error("node permanently failed after {} retries", MAX_RETRIES)

            self._schedule_event.set()

    # ------------------------------------------------------------------
    # Internal — 初始化
    # ------------------------------------------------------------------

    async def _init_ready_nodes(self) -> None:
        """找出无前置依赖（或依赖为空）的节点，标记为 ready。"""
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_PENDING,
            )
            result = await session.execute(stmt)
            nodes = list(result.scalars().all())

            for node in nodes:
                deps = node.depends_on or []
                if not deps:
                    await session.execute(
                        update(TaskNode)
                        .where(TaskNode.id == node.id)
                        .values(status=STATUS_READY)
                    )
                    await set_dag_node_status(self.task_id, str(node.id), STATUS_READY)
                    await push_ready_node(str(node.id), priority=0.0)

            await session.commit()

    async def _reconcile_orphan_running_nodes(self) -> None:
        """Recover DB-running nodes that are not tracked in current scheduler memory.

        This happens after process restart or scheduler crash: TaskNode rows may stay
        in `running`, while `_running_nodes` is empty, causing permanent deadlock.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(TaskNode).where(
                    TaskNode.task_id == self.task_id,
                    TaskNode.status == STATUS_RUNNING,
                )
            )
            stale_running_nodes = list(result.scalars().all())
            if not stale_running_nodes:
                return

            for node in stale_running_nodes:
                await session.execute(
                    update(TaskNode)
                    .where(TaskNode.id == node.id, TaskNode.status == STATUS_RUNNING)
                    .values(
                        status=STATUS_READY,
                        assigned_agent=None,
                        started_at=None,
                    )
                )
                if node.assigned_agent is not None:
                    await session.execute(
                        update(Agent)
                        .where(Agent.id == node.assigned_agent)
                        .values(status=AGENT_IDLE)
                    )
            await session.commit()

        for node in stale_running_nodes:
            await set_dag_node_status(self.task_id, str(node.id), STATUS_READY)
            await push_ready_node(str(node.id), priority=float(getattr(node, "retry_count", 0) or 0))
            logger.bind(task_id=str(self.task_id), node_id=str(node.id)).warning(
                "recovered orphan running node -> ready"
            )

    # ------------------------------------------------------------------
    # Internal — 调度
    # ------------------------------------------------------------------

    async def _dispatch_ready_nodes(self) -> int:
        """调度所有就绪节点到空闲Agent。返回本轮分配数量。"""
        dispatched = 0

        async with async_session_factory() as session:
            control_status = await self._current_control_status(session)
            if control_status in CONTROL_BLOCKING_STATUSES:
                return 0

            await self._promote_satisfied_pending_nodes(session)
            routing_nodes = await self._load_routing_nodes(session)

            # 查询所有 ready 节点
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_READY,
            )
            result = await session.execute(stmt)
            ready_node_rows = sorted(
                [
                    {
                        "id": node.id,
                        "node": node,
                        "agent_role": node.agent_role,
                        "retry_count": getattr(node, "retry_count", 0),
                    }
                    for node in list(result.scalars().all())
                ],
                key=lambda row: (row.get("retry_count", 0), str(row.get("id"))),
            )

            for row in ready_node_rows:
                control_status = await self._current_control_status(session)
                if control_status in CONTROL_BLOCKING_STATUSES:
                    break

                # 并发控制检查
                agent_role = row.get("agent_role")
                if not self._can_dispatch(agent_role):
                    continue

                node_id = row.get("id")
                if not isinstance(node_id, uuid.UUID):
                    continue
                node = await session.get(TaskNode, node_id)
                if node is None or not hasattr(node, "agent_role"):
                    node = row.get("node")
                if node is None:
                    continue
                if hasattr(node, "status") and node.status != STATUS_READY:
                    continue

                # 匹配空闲 Agent
                routing_meta = routing_nodes.get(str(node.id), {})
                routing_mode = str(routing_meta.get("routing_mode") or "auto")
                match = await self._match_agent(
                    session,
                    role=node.agent_role,
                    required_capabilities=routing_meta.get("required_capabilities"),
                    preferred_agents=routing_meta.get("preferred_agents"),
                    routing_mode=routing_mode,
                )
                if isinstance(match, tuple):
                    agent, routing_reason = match
                else:
                    agent = match
                    routing_reason = "role_fallback"
                if agent is None:
                    await self._record_routing_result(
                        session,
                        node_id=node.id,
                        routing_reason=routing_reason,
                        routing_status="pending_match",
                    )
                    continue

                # 分配任务
                if await self._assign_node(
                    session,
                    node,
                    agent,
                    routing_reason=routing_reason,
                    routing_mode=routing_mode,
                ):
                    await self._record_routing_result(
                        session,
                        node_id=node.id,
                        routing_reason=routing_reason,
                        routing_status="assigned",
                    )
                    dispatched += 1

            await session.commit()

        return dispatched

    async def _load_routing_nodes(
        self,
        session: AsyncSession,
    ) -> dict[str, dict[str, Any]]:
        task = await session.get(Task, self.task_id)
        if task is None:
            return {}
        checkpoint = normalize_checkpoint_data(getattr(task, "checkpoint_data", None))
        raw = checkpoint.get("routing_nodes")
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

    async def _record_routing_result(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        routing_reason: str,
        routing_status: str,
    ) -> None:
        task = await session.get(Task, self.task_id)
        if task is None:
            return
        checkpoint = normalize_checkpoint_data(getattr(task, "checkpoint_data", None))
        current = checkpoint.get("routing_results")
        if not isinstance(current, dict):
            current = {}
        current[str(node_id)] = {
            "routing_reason": routing_reason,
            "routing_status": routing_status,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        checkpoint["routing_results"] = current
        task.checkpoint_data = checkpoint

    @staticmethod
    def _read_control_status(task: Task) -> str:
        control = normalize_checkpoint_data(
            getattr(task, "checkpoint_data", None),
        )["control"]
        return str(control.get("status") or CONTROL_ACTIVE)

    @staticmethod
    def _write_control_status(task: Task, status: str) -> None:
        checkpoint = normalize_checkpoint_data(getattr(task, "checkpoint_data", None))
        control_dict = checkpoint["control"]
        control_dict["status"] = status
        checkpoint["control"] = control_dict
        task.checkpoint_data = checkpoint

    async def _current_control_status(self, session: AsyncSession) -> str:
        task = await session.get(Task, self.task_id)
        if task is None:
            return CONTROL_ACTIVE

        control_status = self._read_control_status(task)
        if control_status != CONTROL_PAUSE_REQUESTED:
            return control_status

        # pause_requested 只在运行中节点全部结算后才可提升为 paused
        if self._running_nodes:
            return CONTROL_PAUSE_REQUESTED

        self._write_control_status(task, CONTROL_PAUSED)
        await session.commit()
        await self._emit_control_update(
            status=CONTROL_PAUSED,
            message="task paused",
        )
        return CONTROL_PAUSED

    async def _control_blocks_deadlock(self) -> bool:
        async with async_session_factory() as session:
            return await self._current_control_status(session) in CONTROL_BLOCKING_STATUSES

    async def _emit_control_update(self, *, status: str, message: str) -> None:
        control = {"status": status}
        try:
            await communicator.send_task_event(
                task_id=self.task_id,
                from_agent="scheduler",
                msg_type="dag_update",
                payload={"control": control},
            )
            await communicator.send_task_event(
                task_id=self.task_id,
                from_agent="scheduler",
                msg_type="log",
                payload={
                    "level": "info",
                    "message": message,
                    "control": control,
                },
            )
        except Exception:
            logger.bind(task_id=str(self.task_id), control_status=status).opt(
                exception=True
            ).warning("failed to emit scheduler control update")

    async def _promote_satisfied_pending_nodes(
        self,
        session: AsyncSession,
        *,
        changed_dependency_id: uuid.UUID | None = None,
    ) -> None:
        pending_stmt = select(TaskNode).where(
            TaskNode.task_id == self.task_id,
            TaskNode.status == STATUS_PENDING,
        )
        pending_result = await session.execute(pending_stmt)
        pending_nodes = list(pending_result.scalars().all())
        if not pending_nodes:
            return

        satisfied_stmt = select(TaskNode.id).where(
            TaskNode.task_id == self.task_id,
            TaskNode.status.in_(tuple(SATISFIED_DEPENDENCY_STATUSES)),
        )
        satisfied_result = await session.execute(satisfied_stmt)
        satisfied_ids = {row[0] for row in satisfied_result.all()}

        for node in pending_nodes:
            deps = node.depends_on or []
            if not deps:
                continue

            dep_uuids = {uuid.UUID(str(dep)) for dep in deps}
            if changed_dependency_id is not None and changed_dependency_id not in dep_uuids:
                continue
            if not dep_uuids.issubset(satisfied_ids):
                continue

            result = await session.execute(
                update(TaskNode)
                .where(
                    TaskNode.id == node.id,
                    TaskNode.status == STATUS_PENDING,
                )
                .values(status=STATUS_READY)
            )
            if result.rowcount != 1:
                continue
            await set_dag_node_status(self.task_id, str(node.id), STATUS_READY)
            await push_ready_node(str(node.id), priority=0.0)
            logger.bind(node_id=str(node.id)).debug(
                "node activated: all deps satisfied"
            )

    def _can_dispatch(self, agent_role: str | None) -> bool:
        """检查并发限制是否允许分配新节点。"""
        # 全局 LLM 并发限制
        running_count = len(self._running_nodes)
        if running_count >= settings.max_concurrent_llm_calls:
            return False

        # Writer 额外限制
        if agent_role == "writer":
            writer_count = sum(
                1 for nid in self._running_nodes
                if self._node_roles.get(nid) == "writer"
            )
            if writer_count >= settings.max_concurrent_writers:
                return False

        return True

    def _timeout_watch_member(self, node_id: uuid.UUID) -> str:
        return timeout_watch_member(self.task_id, node_id)

    def _resolve_node_timeout_seconds(self, *, node_role: str | None) -> float:
        role = str(node_role or "").strip().lower()
        if role == "writer":
            return float(max(1, settings.dag_writer_node_timeout_seconds))
        return float(max(1, settings.dag_node_timeout_seconds))

    async def _clear_timeout_watch(self, node_id: uuid.UUID) -> None:
        await remove_timeout_watch(self._timeout_watch_member(node_id))
        await remove_timeout_watch(str(node_id))

    async def reconcile_skipped_node(self, node_id: uuid.UUID) -> None:
        tracked_agent_id = self._running_nodes.pop(node_id, None)
        self._node_roles.pop(node_id, None)
        await self._clear_timeout_watch(node_id)

        async with async_session_factory() as session:
            node = await session.get(TaskNode, node_id)
            assigned_agent_id = tracked_agent_id
            if assigned_agent_id is None and node is not None:
                assigned_agent_id = getattr(node, "assigned_agent", None)
            await session.execute(
                update(TaskNode)
                .where(TaskNode.id == node_id)
                .values(assigned_agent=None)
            )
            if assigned_agent_id is not None:
                await session.execute(
                    update(Agent)
                    .where(Agent.id == assigned_agent_id)
                    .values(status=AGENT_IDLE)
                )
            await session.commit()

        self._schedule_event.set()

    @property
    def _node_roles(self) -> dict[uuid.UUID, str]:
        """当前 running 节点的角色映射。"""
        return self._cached_node_roles

    async def _match_agent(
        self,
        session: AsyncSession,
        role: str | None,
        required_capabilities: list[str] | None = None,
        preferred_agents: list[str] | None = None,
        routing_mode: str = "auto",
    ) -> tuple[Agent | None, str]:
        """按 explicit bind -> capability -> role fallback 匹配空闲 Agent。"""
        required_caps = {
            str(cap).strip().lower()
            for cap in (required_capabilities or [])
            if str(cap).strip()
        }
        preferred = {
            str(item).strip().lower()
            for item in (preferred_agents or [])
            if str(item).strip()
        }
        mode = routing_mode if routing_mode in {"auto", "capability_first", "strict_bind"} else "auto"

        stmt = select(Agent).where(Agent.status == AGENT_IDLE).order_by(Agent.created_at)
        result = await session.execute(stmt)
        scalar_result = result.scalars()
        idle_agents = list(scalar_result.all())
        if not idle_agents:
            return None, "no_idle_agent"
        idle_agents = await self._filter_alive_idle_agents(session, idle_agents)
        if not idle_agents:
            return None, "no_alive_idle_agent"

        if preferred:
            for agent in idle_agents:
                if str(agent.id).lower() in preferred or str(agent.name).strip().lower() in preferred:
                    if role and agent.role != role:
                        continue
                    if required_caps and not required_caps.issubset(_parse_capability_tokens(agent.capabilities)):
                        continue
                    return agent, "explicit_bind"
            if mode == "strict_bind":
                return None, "strict_bind_no_match"

        if required_caps:
            for agent in idle_agents:
                if role and agent.role != role:
                    continue
                if required_caps.issubset(_parse_capability_tokens(agent.capabilities)):
                    return agent, "capability_match"
            if mode == "strict_bind":
                return None, "strict_bind_no_match"

        if role:
            for agent in idle_agents:
                if agent.role == role:
                    return agent, "role_fallback"

        return idle_agents[0], "idle_fallback"

    async def _filter_alive_idle_agents(
        self,
        session: AsyncSession,
        idle_agents: list[Agent],
    ) -> list[Agent]:
        """Filter idle agents by recent heartbeat; stale rows become offline."""
        if not idle_agents:
            return []

        try:
            states = await get_all_agent_states([agent.id for agent in idle_agents])
        except Exception:
            logger.opt(exception=True).warning(
                "heartbeat lookup failed; falling back to DB idle agents only"
            )
            return idle_agents

        if not states:
            return idle_agents

        now_ts = time.time()
        alive_agents: list[Agent] = []
        stale_agent_ids: list[uuid.UUID] = []
        timeout_seconds = float(HEARTBEAT_TIMEOUT_SECONDS)

        for agent in idle_agents:
            state = states.get(str(agent.id))
            if not state:
                stale_agent_ids.append(agent.id)
                continue

            hb_raw = state.get("last_heartbeat", "0")
            runtime_status = str(state.get("status", "")).strip().lower()
            try:
                last_heartbeat = float(hb_raw)
            except (TypeError, ValueError):
                stale_agent_ids.append(agent.id)
                continue

            if (now_ts - last_heartbeat) >= timeout_seconds:
                stale_agent_ids.append(agent.id)
                continue

            if runtime_status not in {AGENT_IDLE, AGENT_BUSY}:
                stale_agent_ids.append(agent.id)
                continue

            if runtime_status == AGENT_IDLE:
                alive_agents.append(agent)

        if stale_agent_ids:
            await session.execute(
                update(Agent)
                .where(Agent.id.in_(stale_agent_ids))
                .values(status="offline")
            )

        return alive_agents

    async def _assign_node(
        self,
        session: AsyncSession,
        node: TaskNode,
        agent: Agent,
        *,
        routing_reason: str = "role_fallback",
        routing_mode: str = "auto",
    ) -> bool:
        """将节点分配给 Agent：更新DB + Redis + 发送消息。"""
        node_id = node.id
        node_title = node.title
        node_role = node.agent_role
        node_retry_count = int(getattr(node, "retry_count", 0))
        agent_id = agent.id
        agent_name = agent.name

        log = logger.bind(
            task_id=str(self.task_id),
            node_id=str(node_id),
            agent_id=str(agent_id),
        )

        # 更新 DB 状态
        assignment_payload = {
            "title": node_title,
            "agent_role": node_role,
            "retry_count": node_retry_count,
            "routing_reason": routing_reason,
            "routing_mode": routing_mode,
        }

        result = await session.execute(
            update(TaskNode)
            .where(
                TaskNode.id == node_id,
                TaskNode.status == STATUS_READY,
                TaskNode.assigned_agent.is_(None),
            )
            .values(
                status=STATUS_RUNNING,
                assigned_agent=agent.id,
                started_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        if result.rowcount != 1:
            log.info("node assignment lost ready-state race")
            return False
        await session.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(status=AGENT_BUSY)
        )
        await session.commit()

        self._running_nodes[node_id] = agent_id
        self._node_roles[node_id] = node_role or ""

        session.expire_all()
        current_node = await session.get(TaskNode, node_id)
        task = await session.get(Task, self.task_id)
        if (
            current_node is None
            or current_node.status != STATUS_RUNNING
            or current_node.assigned_agent != agent_id
            or task is None
            or self._read_control_status(task) in CONTROL_BLOCKING_STATUSES
        ):
            self._running_nodes.pop(node_id, None)
            self._node_roles.pop(node_id, None)
            if current_node is not None:
                await session.execute(
                    update(TaskNode)
                    .where(
                        TaskNode.id == node_id,
                        TaskNode.status == STATUS_RUNNING,
                        TaskNode.assigned_agent == agent_id,
                    )
                    .values(
                        status=STATUS_READY,
                        assigned_agent=None,
                        started_at=None,
                    )
                )
            await session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status=AGENT_IDLE)
            )
            await session.commit()
            log.info("node assignment aborted after control transition")
            return False

        try:
            try:
                assignment_payload = await self._build_assignment_payload(
                    session=session,
                    node_id=node_id,
                    node_title=node_title or "",
                    node_role=node_role or "",
                    node_retry_count=node_retry_count,
                    routing_reason=routing_reason,
                    routing_mode=routing_mode,
                )
            except Exception:
                logger.bind(task_id=str(self.task_id), node_id=str(node_id)).opt(
                    exception=True
                ).warning("failed to build rich assignment payload; fallback to minimal")

            await set_dag_node_status(self.task_id, str(node_id), STATUS_RUNNING)
            timeout_seconds = self._resolve_node_timeout_seconds(node_role=node_role)
            deadline = time.time() + timeout_seconds
            await add_timeout_watch(self._timeout_watch_member(node_id), deadline)
            await communicator.send_task_assignment(
                agent_id=agent_id,
                task_id=self.task_id,
                node_id=node_id,
                payload=assignment_payload,
            )
        except Exception:
            logger.bind(task_id=str(self.task_id), node_id=str(node_id)).opt(
                exception=True
            ).warning("node assignment failed before delivery boundary; reverting assignment")
            await self._revert_assignment_after_side_effect_failure(
                node_id=node_id,
                node_retry_count=node_retry_count,
                agent_id=agent_id,
            )
            return False

        try:
            await communicator.send_status_update(
                task_id=self.task_id,
                node_id=node_id,
                status=STATUS_RUNNING,
                extra={
                    "agent_name": agent_name,
                    "agent_id": str(agent_id),
                    "routing_reason": routing_reason,
                    "routing_mode": routing_mode,
                },
            )
        except Exception:
            logger.bind(task_id=str(self.task_id), node_id=str(node_id)).opt(
                exception=True
            ).warning("failed to emit running status update after assignment delivery")

        log.info("node assigned to agent {}", agent_name)
        return True

    async def _build_assignment_payload(
        self,
        *,
        session: AsyncSession,
        node_id: uuid.UUID,
        node_title: str,
        node_role: str,
        node_retry_count: int,
        routing_reason: str,
        routing_mode: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": node_title,
            "agent_role": node_role,
            "retry_count": node_retry_count,
            "routing_reason": routing_reason,
            "routing_mode": routing_mode,
        }
        stage_code = resolve_stage_code(role=node_role, title=node_title)
        payload["stage_code"] = stage_code
        payload["schema_version"] = SCHEMA_VERSION
        payload["stage_contract"] = json.dumps(
            get_stage_contract(stage_code),
            ensure_ascii=False,
            indent=2,
        )

        task = await session.get(Task, self.task_id)
        if task is not None:
            payload["mode"] = task.mode
            payload["target_words"] = int(task.target_words or 0)
        source_policy = _build_source_policy(payload.get("mode", ""))

        chapter_index, chapter_title = self._parse_chapter_meta(node_title)
        if chapter_index is not None:
            payload["chapter_index"] = chapter_index
            payload["chapter_title"] = chapter_title or node_title
        payload["research_keywords"] = _derive_research_keywords(
            task.title if task is not None else "",
            node_title,
            chapter_title,
        )
        payload["source_policy"] = source_policy

        if node_role == "outline":
            payload["title"] = node_title
            payload["source_policy"] = json.dumps(source_policy, ensure_ascii=False, indent=2)
            payload["research_keywords"] = ", ".join(payload.get("research_keywords", []))
            return payload

        outline_text = await self._load_outline_result(session)
        if outline_text:
            payload["full_outline"] = outline_text

        if node_role == "researcher":
            payload["title"] = node_title
            payload["source_policy"] = json.dumps(source_policy, ensure_ascii=False, indent=2)
            payload["research_keywords"] = ", ".join(payload.get("research_keywords", []))
            return payload

        writer_nodes = await self._load_writer_nodes(session)
        writer_count = self._primary_writer_count(writer_nodes)
        if task is not None and "target_words" not in payload:
            payload["target_words"] = int(task.target_words or 0)

        if node_role == "writer":
            target_words = int(payload.get("target_words") or 0)
            budget_hint = _extract_word_budget_hint(node_title)
            budget_hint_locked = False
            if budget_hint is not None:
                payload["target_words"] = budget_hint
                target_words = budget_hint
                budget_hint_locked = True
            is_expansion_pass = self._is_expansion_writer_title(node_title)
            payload["is_expansion_pass"] = is_expansion_pass
            if target_words > 0:
                chapter_budget = max(500, target_words // writer_count)
                if is_expansion_pass:
                    if budget_hint_locked:
                        payload["target_words"] = target_words
                    elif chapter_index is not None:
                        payload["target_words"] = max(450, min(2200, chapter_budget // 2))
                    else:
                        payload["target_words"] = max(2500, min(12000, int(target_words * 0.75)))
                else:
                    payload["target_words"] = chapter_budget
            payload.setdefault(
                "chapter_description",
                f"Focus on chapter scope: {chapter_title or node_title}",
            )
            if is_expansion_pass:
                payload["chapter_description"] = (
                    f"Expand chapter depth and evidence for: {chapter_title or node_title}"
                )
                payload["chapter_content"] = self._pick_writer_content_for_chapter(
                    writer_nodes,
                    chapter_index=chapter_index,
                )
            payload.setdefault(
                "context_bridges",
                "Ensure smooth transition from previous chapter to next chapter.",
            )
            payload.setdefault(
                "topic_claims",
                {
                    "chapter_index": chapter_index,
                    "owns": chapter_title or node_title,
                    "boundary": "Do not overlap with other chapters.",
                },
            )
            payload.setdefault("assigned_evidence", [])
            payload["title_level_rule"] = (
                "Heading depth must not exceed level-2. "
                "Allow only #/## or 1/1.1; forbid ### or 1.1.1+."
            )
            payload["evidence_rule"] = (
                "Major claims must map to evidence_trace; "
                "insufficient support must be marked as uncertainty."
            )
            payload["research_protocol"] = {
                "topic_anchor": chapter_title or node_title,
                "keyword_candidates": payload.get("research_keywords", []),
                "source_policy": source_policy,
                "query_blueprint": [
                    f"{chapter_title or node_title} definition",
                    f"{chapter_title or node_title} benchmark",
                    f"{chapter_title or node_title} limitations",
                ],
            }
            payload["source_policy"] = json.dumps(source_policy, ensure_ascii=False, indent=2)
            payload["research_protocol"] = json.dumps(
                payload["research_protocol"],
                ensure_ascii=False,
                indent=2,
            )
            payload["research_keywords"] = ", ".join(payload.get("research_keywords", []))
            return payload

        if node_role == "reviewer":
            chapter_content = self._pick_writer_content_for_chapter(
                writer_nodes,
                chapter_index=chapter_index,
            )
            payload["chapter_content"] = chapter_content
            payload.setdefault("chapter_description", chapter_title or node_title)
            payload.setdefault("topic_claims", {})
            payload.setdefault("assigned_evidence", [])
            payload.setdefault("overlap_findings", "none")
            payload["source_policy"] = json.dumps(source_policy, ensure_ascii=False, indent=2)
            payload["research_keywords"] = ", ".join(payload.get("research_keywords", []))
            payload["research_protocol"] = json.dumps(
                {
                    "topic_anchor": chapter_title or node_title,
                    "keyword_candidates": _derive_research_keywords(chapter_title or node_title),
                    "source_policy": source_policy,
                },
                ensure_ascii=False,
                indent=2,
            )
            return payload

        if node_role == "consistency":
            full_text = "\n\n".join(
                result for _, result in writer_nodes if result
            )
            payload["full_text"] = full_text
            payload["chapters_summary"] = "\n\n".join(
                f"- {title}: {result[:260]}"
                for title, result in writer_nodes
                if result
            )
            payload["topic_claims"] = {
                "global": "Keep cross-chapter facts, terminology, and style consistent.",
            }
            payload["chapter_metadata"] = [
                {
                    "chapter_title": title,
                    "word_count": max(0, len(result.split())),
                }
                for title, result in writer_nodes
            ]
            payload["source_policy"] = json.dumps(source_policy, ensure_ascii=False, indent=2)
            payload["research_keywords"] = ", ".join(payload.get("research_keywords", []))
            return payload

        return payload

    @staticmethod
    def _parse_chapter_meta(title: str) -> tuple[int | None, str]:
        text = (title or "").strip()
        if not text:
            return None, ""
        match = re.search(r"第\s*(\d+)\s*章[:：]?\s*(.*)", text)
        if not match:
            return None, text
        chapter_index = int(match.group(1))
        chapter_title = (match.group(2) or "").strip() or text
        return chapter_index, chapter_title

    @staticmethod
    def _is_expansion_writer_title(title: str) -> bool:
        text = (title or "").strip()
        if not text:
            return False
        markers = ("扩写", "补写", "整合", "篇幅补足")
        return any(marker in text for marker in markers)

    @classmethod
    def _is_primary_writer_title(cls, title: str) -> bool:
        return not cls._is_expansion_writer_title(title)

    @classmethod
    def _primary_writer_count(cls, writer_nodes: list[tuple[str, str]]) -> int:
        primary = [title for title, _ in writer_nodes if cls._is_primary_writer_title(title)]
        return max(1, len(primary) if primary else len(writer_nodes))

    async def _load_outline_result(self, session: AsyncSession) -> str:
        result = await session.execute(
            select(TaskNode.result)
            .where(
                TaskNode.task_id == self.task_id,
                TaskNode.agent_role == "outline",
                TaskNode.result.is_not(None),
            )
            .order_by(TaskNode.started_at.desc())
            .limit(1)
        )
        row = result.first()
        return str(row[0]) if row and row[0] else ""

    async def _load_writer_nodes(self, session: AsyncSession) -> list[tuple[str, str]]:
        result = await session.execute(
            select(TaskNode.title, TaskNode.result)
            .where(
                TaskNode.task_id == self.task_id,
                TaskNode.agent_role == "writer",
            )
            .order_by(TaskNode.title)
        )
        rows = result.all()
        return [
            (str(title or ""), extract_writer_markdown(str(content or "")))
            for title, content in rows
        ]

    def _pick_writer_content_for_chapter(
        self,
        writer_nodes: list[tuple[str, str]],
        *,
        chapter_index: int | None,
    ) -> str:
        if not writer_nodes:
            return ""
        if chapter_index is None:
            for _, content in writer_nodes:
                if content:
                    return content
            return ""
        marker = f"第{chapter_index}章"
        for title, content in writer_nodes:
            if marker in title and content:
                return content
        for _, content in writer_nodes:
            if content:
                return content
        return ""

    async def _revert_assignment_after_side_effect_failure(
        self,
        *,
        node_id: uuid.UUID,
        node_retry_count: int,
        agent_id: uuid.UUID,
    ) -> None:
        self._running_nodes.pop(node_id, None)
        self._node_roles.pop(node_id, None)
        await self._clear_timeout_watch(node_id)

        reverted_to_ready = False
        async with async_session_factory() as compensation_session:
            revert_result = await compensation_session.execute(
                update(TaskNode)
                .where(
                    TaskNode.id == node_id,
                    TaskNode.status == STATUS_RUNNING,
                    TaskNode.assigned_agent == agent_id,
                )
                .values(
                    status=STATUS_READY,
                    assigned_agent=None,
                    started_at=None,
                )
            )
            reverted_to_ready = revert_result.rowcount == 1
            await compensation_session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status=AGENT_IDLE)
            )
            await compensation_session.commit()

        if reverted_to_ready:
            await set_dag_node_status(self.task_id, str(node_id), STATUS_READY)
            await push_ready_node(str(node_id), priority=float(node_retry_count))

        self._schedule_event.set()

    # ------------------------------------------------------------------
    # Internal — 依赖激活
    # ------------------------------------------------------------------

    async def _activate_dependents(self, completed_node_id: uuid.UUID) -> None:
        """检查依赖于已完成节点的下游节点，如果所有依赖都满足则标为 ready。"""
        async with async_session_factory() as session:
            await self._promote_satisfied_pending_nodes(
                session,
                changed_dependency_id=completed_node_id,
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Internal — 超时处理
    # ------------------------------------------------------------------

    async def _drain_task_results(self) -> None:
        """消费 task events 中的 task_result 并推进节点状态。"""
        stream = task_events_key(self.task_id)
        try:
            messages = await xread_latest(
                {stream: self._task_events_cursor},
                count=100,
                block=1,
            )
        except Exception:
            logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                "task result drain failed"
            )
            return

        if not messages:
            return

        for message in messages:
            self._task_events_cursor = message.message_id
            try:
                envelope = MessageEnvelope.from_redis(message.data)
            except Exception:
                logger.bind(
                    task_id=str(self.task_id),
                    message_id=message.message_id,
                ).opt(exception=True).warning("malformed task event skipped")
                continue

            if envelope.msg_type != "task_result":
                continue

            node_raw = str(envelope.node_id or "").strip()
            agent_raw = str(envelope.from_agent or "").strip()
            if not node_raw or not agent_raw:
                continue

            try:
                node_id = uuid.UUID(node_raw)
                agent_id = uuid.UUID(agent_raw)
            except ValueError:
                logger.bind(
                    task_id=str(self.task_id),
                    node_id=node_raw,
                    agent_id=agent_raw,
                ).warning("task_result with non-uuid ids skipped")
                continue

            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            status = str(payload.get("status") or "").lower()
            if status == STATUS_DONE:
                output = str(payload.get("output") or "")
                if _is_suspicious_node_output(output):
                    await self.on_node_failed(
                        node_id=node_id,
                        error="Invalid node output: gateway/WAF challenge payload",
                        agent_id=agent_id,
                    )
                    continue
                async with async_session_factory() as session:
                    node_row = await session.execute(
                        select(TaskNode.agent_role, TaskNode.title, TaskNode.retry_count).where(TaskNode.id == node_id)
                    )
                    row = node_row.first()
                    node_role = str(row[0]) if row and row[0] else ""
                    node_title = str(row[1]) if row and row[1] else ""
                    node_retry_count = int(row[2]) if row and row[2] is not None else 0
                    if node_role == "writer":
                        valid_length, observed_units, min_units = await self._validate_writer_output_length(
                            session=session,
                            node_title=node_title,
                            output=output,
                        )
                        if not valid_length:
                            if node_retry_count >= (MAX_RETRIES - 1):
                                logger.bind(
                                    task_id=str(self.task_id),
                                    node_id=str(node_id),
                                    observed_units=observed_units,
                                    min_units=min_units,
                                ).warning(
                                    "writer output remains short after max retries; accepting and deferring to final expansion gate"
                                )
                                await self.on_node_completed(
                                    node_id=node_id,
                                    result=output,
                                    agent_id=agent_id,
                                )
                                continue
                            await self.on_node_failed(
                                node_id=node_id,
                                error=(
                                    "Writer output too short: "
                                    f"observed={observed_units}, min_required={min_units}"
                                ),
                                agent_id=agent_id,
                            )
                            continue
                    if node_role == "consistency":
                        parsed = _parse_json_object(output)
                        if isinstance(parsed, dict) and parsed.get("pass") is False:
                            repair_targets = _normalize_repair_targets(parsed.get("repair_targets"))
                            if repair_targets:
                                injected = await self._inject_consistency_repair_wave(
                                    session=session,
                                    repair_targets=repair_targets,
                                )
                                if injected:
                                    logger.bind(
                                        task_id=str(self.task_id),
                                        node_id=str(node_id),
                                        repair_targets=repair_targets,
                                    ).warning(
                                        "consistency failed; injected targeted repair wave"
                                    )
                                    await self.on_node_completed(
                                        node_id=node_id,
                                        result=output,
                                        agent_id=agent_id,
                                    )
                                    continue
                            if node_retry_count >= (MAX_RETRIES - 1):
                                logger.bind(
                                    task_id=str(self.task_id),
                                    node_id=str(node_id),
                                ).warning(
                                    "consistency remains pass=false after max retries; accepting and deferring to final gate"
                                )
                                await self.on_node_completed(
                                    node_id=node_id,
                                    result=output,
                                    agent_id=agent_id,
                                )
                                continue
                            await self.on_node_failed(
                                node_id=node_id,
                                error="Consistency check failed (pass=false), require repair/retry",
                                agent_id=agent_id,
                            )
                            continue
                if _is_invalid_output_for_role(node_role, output):
                    await self.on_node_failed(
                        node_id=node_id,
                        error=f"Invalid output shape for role={node_role or 'unknown'}",
                        agent_id=agent_id,
                    )
                    continue
                await self.on_node_completed(
                    node_id=node_id,
                    result=output,
                    agent_id=agent_id,
                )
            elif status == STATUS_FAILED:
                await self.on_node_failed(
                    node_id=node_id,
                    error=str(payload.get("error") or "Unknown agent failure"),
                    agent_id=agent_id,
                )

    async def _inject_consistency_repair_wave(
        self,
        *,
        session: AsyncSession,
        repair_targets: list[int],
    ) -> bool:
        writer_rows = await session.execute(
            select(TaskNode.title).where(
                TaskNode.task_id == self.task_id,
                TaskNode.agent_role == "writer",
            )
        )
        existing_titles = [str(row[0] or "") for row in writer_rows.all()]
        wave_count = sum(1 for title in existing_titles if "一致性定向修复（轮次" in title)
        if wave_count >= MAX_CONSISTENCY_REPAIR_WAVES:
            return False

        wave_no = wave_count + 1
        reviewer_ids: list[uuid.UUID] = []
        injected_writer_ids: list[uuid.UUID] = []

        for chapter_index in repair_targets[:4]:
            writer_id = uuid.uuid4()
            reviewer_id = uuid.uuid4()
            session.add(
                TaskNode(
                    id=writer_id,
                    task_id=self.task_id,
                    title=f"第{chapter_index}章：一致性定向修复（轮次{wave_no}）",
                    agent_role="writer",
                    status=STATUS_READY,
                    depends_on=[],
                    retry_count=0,
                )
            )
            session.add(
                TaskNode(
                    id=reviewer_id,
                    task_id=self.task_id,
                    title=f"第{chapter_index}章：一致性修复审查（轮次{wave_no}）",
                    agent_role="reviewer",
                    status=STATUS_PENDING,
                    depends_on=[writer_id],
                    retry_count=0,
                )
            )
            reviewer_ids.append(reviewer_id)
            injected_writer_ids.append(writer_id)

        if not reviewer_ids:
            return False

        session.add(
            TaskNode(
                id=uuid.uuid4(),
                task_id=self.task_id,
                title=f"一致性复核（轮次{wave_no}）",
                agent_role="consistency",
                status=STATUS_PENDING,
                depends_on=reviewer_ids,
                retry_count=0,
            )
        )
        await session.commit()

        for node_id in injected_writer_ids:
            await set_dag_node_status(self.task_id, str(node_id), STATUS_READY)
            await push_ready_node(str(node_id), priority=0.0)
        for node_id in reviewer_ids:
            await set_dag_node_status(self.task_id, str(node_id), STATUS_PENDING)
        return True

    async def _validate_writer_output_length(
        self,
        *,
        session: AsyncSession,
        node_title: str,
        output: str,
    ) -> tuple[bool, int, int]:
        """Validate writer output has enough content for long-form requests."""
        markdown = extract_writer_markdown(output)
        observed_units = _count_text_units(markdown)
        min_units = await self._writer_min_units_for_task(session=session, node_title=node_title)
        return observed_units >= min_units, observed_units, min_units

    async def _writer_min_units_for_task(
        self,
        *,
        session: AsyncSession,
        node_title: str,
    ) -> int:
        task = await session.get(Task, self.task_id)
        target_words = int(getattr(task, "target_words", 0) or 0)
        if target_words <= 0:
            return 300

        writer_rows = await session.execute(
            select(TaskNode.title).where(
                TaskNode.task_id == self.task_id,
                TaskNode.agent_role == "writer",
            )
        )
        writer_titles = [str(item[0] or "") for item in writer_rows.all()]
        primary_count = max(
            1,
            len([title for title in writer_titles if self._is_primary_writer_title(title)]),
        )
        chapter_budget = max(500, target_words // primary_count)
        is_expansion = self._is_expansion_writer_title(node_title)
        is_global_expansion = "全稿扩写" in (node_title or "")
        budget_hint = _extract_word_budget_hint(node_title)
        if budget_hint is not None:
            return max(500, min(3200, int(budget_hint * 0.45)))
        if is_global_expansion:
            return max(1400, min(6000, int(target_words * 0.2)))
        if is_expansion:
            return max(600, min(2200, int(chapter_budget * 0.45)))
        return max(900, min(3200, int(chapter_budget * 0.6)))

    async def _check_timeouts(self) -> None:
        """检查并处理超时节点。"""
        timed_out = await get_timed_out_nodes()
        if not timed_out:
            return

        for watch_member in timed_out:
            watch_task_id, node_id_str = parse_timeout_watch_member(watch_member)
            if watch_task_id is not None and watch_task_id != str(self.task_id):
                continue

            node_id = uuid.UUID(node_id_str)
            agent_id = self._running_nodes.get(node_id)
            if agent_id is None:
                # 仅清理明确属于当前 task 的 watch；未知归属的 legacy watch 交给其所有者处理
                if watch_task_id == str(self.task_id):
                    await self._clear_timeout_watch(node_id)
                continue

            logger.bind(
                task_id=str(self.task_id),
                node_id=node_id_str,
            ).warning("node timed out")

            await self.on_node_failed(
                node_id=node_id,
                error="Execution timeout",
                agent_id=agent_id,
            )

    # ------------------------------------------------------------------
    # Internal — 完成检测
    # ------------------------------------------------------------------

    async def _is_dag_complete(self) -> bool:
        """所有节点是否都已成功完成（done/skipped）。"""
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status.notin_(tuple(SUCCESS_NODE_STATUSES)),
            )
            result = await session.execute(stmt)
            return result.scalars().first() is None

    async def _all_nodes_terminal(self) -> bool:
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status.notin_(tuple(TERMINAL_NODE_STATUSES)),
            )
            result = await session.execute(stmt)
            return result.scalars().first() is None

    async def _has_failed_nodes(self) -> bool:
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_FAILED,
            )
            result = await session.execute(stmt)
            return result.scalars().first() is not None

    async def _has_undone_nodes(self) -> bool:
        """是否还有未完成且非失败的节点。"""
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status.notin_(tuple(TERMINAL_NODE_STATUSES)),
            )
            result = await session.execute(stmt)
            return result.scalars().first() is not None

    # ------------------------------------------------------------------
    # Internal — 任务状态更新
    # ------------------------------------------------------------------

    async def _mark_task_done(self) -> str:
        """Mark task done/fail, or extend DAG with auto-expansion wave.

        Returns:
            "completed" | "failed" | "extended"
        """
        fail_reason: str | None = None
        async with async_session_factory() as session:
            # Assemble writer outputs before publishing terminal task status.
            from app.services.long_text_fsm import LongTextFSM

            try:
                word_count_raw = await LongTextFSM(self.task_id).finalize_output(
                    session=session,
                    commit=False,
                )
                word_count: int | None = None
                try:
                    word_count = int(word_count_raw)
                except Exception:
                    logger.bind(task_id=str(self.task_id)).warning(
                        "skip finalize gate: non-integer word_count={}",
                        type(word_count_raw).__name__,
                    )
                task = await session.get(Task, self.task_id)
                target_words = 0
                try:
                    target_words = int(getattr(task, "target_words", 0) or 0)
                except Exception:
                    target_words = 0
                if word_count is not None and target_words > 0:
                    min_required = int(target_words * MIN_TARGET_WORD_RATIO)
                    if word_count < min_required:
                        created = await self._enqueue_auto_expansion_wave(
                            session=session,
                            target_words=target_words,
                            current_words=word_count,
                        )
                        if created:
                            await session.execute(
                                update(Task)
                                .where(Task.id == self.task_id)
                                .values(
                                    status="pending",
                                    error_message=None,
                                )
                            )
                            await session.commit()
                            self._schedule_event.set()
                            logger.bind(task_id=str(self.task_id)).warning(
                                "Output below target words ({} < {}), auto-expansion wave scheduled",
                                word_count,
                                min_required,
                            )
                            return "extended"
                        fail_reason = (
                            f"Output below target words: got={word_count}, "
                            f"required_min={min_required}, target={target_words}"
                        )
            except Exception:
                logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                    "failed to finalize task output before mark done"
                )
                fail_reason = "Failed to finalize output"
            await session.execute(
                update(Task)
                .where(Task.id == self.task_id)
                .values(
                    status="failed" if fail_reason else "completed",
                    fsm_state="failed" if fail_reason else "done",
                    error_message=fail_reason if fail_reason else None,
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        try:
            await communicator.send_status_update(
                task_id=self.task_id,
                status="failed" if fail_reason else "completed",
                from_agent="scheduler",
                extra={"reason": fail_reason} if fail_reason else None,
            )
            await communicator.send_task_event(
                task_id=self.task_id,
                from_agent="scheduler",
                msg_type="task_done",
                payload=(
                    {"status": "failed", "reason": fail_reason}
                    if fail_reason
                    else {"status": "completed"}
                ),
            )
        except Exception:
            logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                "failed to publish terminal done events"
            )
        if fail_reason:
            logger.bind(task_id=str(self.task_id)).error("task failed at finalize gate: {}", fail_reason)
            return "failed"
        return "completed"

    async def _enqueue_auto_expansion_wave(
        self,
        *,
        session: AsyncSession,
        target_words: int,
        current_words: int,
    ) -> bool:
        """Insert extra writer node(s) to expand full draft toward target words."""
        if target_words <= 0:
            return False
        wave_rows = await session.execute(
            select(TaskNode.id, TaskNode.title)
            .where(TaskNode.task_id == self.task_id)
            .where(TaskNode.agent_role == "writer")
        )
        wave_titles = [str(row[1] or "") for row in wave_rows.all()]
        existing_wave_numbers: set[int] = set()
        for title in wave_titles:
            match = re.search(r"自动补写轮次(\d+)", title)
            if not match:
                continue
            try:
                existing_wave_numbers.add(int(match.group(1)))
            except ValueError:
                continue
        existing_waves = len(existing_wave_numbers)
        if existing_waves >= AUTO_EXPANSION_MAX_WAVES:
            return False

        wave_no = existing_waves + 1
        gap = max(0, target_words - max(0, current_words))
        suggested_budget = max(1200, min(8000, int(gap * 1.1)))
        if gap >= 12000:
            expansion_nodes = 3
        elif gap >= 6000:
            expansion_nodes = 2
        else:
            expansion_nodes = 1
        per_node_budget = max(1200, int(suggested_budget / expansion_nodes))

        inserted_ids: list[uuid.UUID] = []
        for idx in range(expansion_nodes):
            suffix = f"（分片{idx + 1}/{expansion_nodes}）" if expansion_nodes > 1 else ""
            title = (
                f"自动补写轮次{wave_no}：全稿扩写与篇幅补足{suffix}"
                f"（目标补写约{per_node_budget}字）"
            )
            node_id = uuid.uuid4()
            inserted_ids.append(node_id)
            session.add(
                TaskNode(
                    id=node_id,
                    task_id=self.task_id,
                    title=title,
                    agent_role="writer",
                    status=STATUS_READY,
                    depends_on=[],
                    retry_count=0,
                )
            )
        await session.flush()
        for node_id in inserted_ids:
            await set_dag_node_status(self.task_id, str(node_id), STATUS_READY)
            await push_ready_node(str(node_id), priority=0.0)
        logger.bind(
            task_id=str(self.task_id),
            node_ids=[str(node_id) for node_id in inserted_ids],
            target_words=target_words,
            current_words=current_words,
            suggested_budget=suggested_budget,
            expansion_nodes=expansion_nodes,
            per_node_budget=per_node_budget,
        ).info("auto-expansion wave inserted")
        return True

    async def _mark_task_failed(self, reason: str) -> None:
        """标记 Task 为失败。"""
        async with async_session_factory() as session:
            await session.execute(
                update(Task)
                .where(Task.id == self.task_id)
                .values(
                    status="failed",
                    fsm_state="failed",
                    error_message=reason,
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        try:
            await communicator.send_status_update(
                task_id=self.task_id,
                status="failed",
                from_agent="scheduler",
                extra={"reason": reason},
            )
            await communicator.send_task_event(
                task_id=self.task_id,
                from_agent="scheduler",
                msg_type="task_done",
                payload={"status": "failed", "reason": reason},
            )
        except Exception:
            logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                "failed to publish terminal failed events"
            )
        logger.bind(task_id=str(self.task_id)).error("task failed: {}", reason)


# ---------------------------------------------------------------------------
# Scheduler Registry — 管理所有活跃的调度器实例
# ---------------------------------------------------------------------------

_active_schedulers: dict[uuid.UUID, DAGScheduler] = {}


async def start_scheduler(task_id: uuid.UUID) -> DAGScheduler:
    """为指定 Task 启动 DAG 调度器，返回实例。"""
    if task_id in _active_schedulers:
        logger.warning("scheduler already running for task {}", task_id)
        return _active_schedulers[task_id]

    scheduler = DAGScheduler(task_id)
    _active_schedulers[task_id] = scheduler

    # 启动调度循环（后台协程）
    asyncio.create_task(_run_and_cleanup(task_id, scheduler))
    return scheduler


async def _run_and_cleanup(task_id: uuid.UUID, scheduler: DAGScheduler) -> None:
    """运行调度器并在结束时从注册表中清理。"""
    try:
        await scheduler.run()
    finally:
        _active_schedulers.pop(task_id, None)


def stop_scheduler(task_id: uuid.UUID) -> None:
    """停止指定 Task 的调度器。"""
    scheduler = _active_schedulers.get(task_id)
    if scheduler:
        scheduler.stop()


def get_scheduler(task_id: uuid.UUID) -> DAGScheduler | None:
    """获取活跃的调度器实例（用于回调注入）。"""
    return _active_schedulers.get(task_id)
