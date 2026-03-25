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
from app.services import communicator
from app.services.redis_streams import (
    add_timeout_watch,
    get_dag_state,
    get_timed_out_nodes,
    parse_timeout_watch_member,
    push_ready_node,
    remove_timeout_watch,
    set_dag_node_status,
    timeout_watch_member,
)
from app.utils.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
NODE_TIMEOUT_SECONDS = 120  # 单节点执行超时

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

            while not self._stop.is_set():
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
                        await self._mark_task_done()
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

            # 查询所有 ready 节点
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_READY,
            )
            result = await session.execute(stmt)
            ready_nodes = sorted(
                list(result.scalars().all()),
                key=lambda node: (getattr(node, "retry_count", 0), str(node.id)),
            )

            for node in ready_nodes:
                control_status = await self._current_control_status(session)
                if control_status in CONTROL_BLOCKING_STATUSES:
                    break

                # 并发控制检查
                if not self._can_dispatch(node.agent_role):
                    continue

                # 匹配空闲 Agent
                agent = await self._match_agent(session, node.agent_role)
                if agent is None:
                    continue

                # 分配任务
                if await self._assign_node(session, node, agent):
                    dispatched += 1

            await session.commit()

        return dispatched

    @staticmethod
    def _read_control_status(task: Task) -> str:
        checkpoint_data = getattr(task, "checkpoint_data", None)
        if not isinstance(checkpoint_data, dict):
            return CONTROL_ACTIVE
        control = checkpoint_data.get("control")
        if not isinstance(control, dict):
            return CONTROL_ACTIVE
        return str(control.get("status") or CONTROL_ACTIVE)

    @staticmethod
    def _write_control_status(task: Task, status: str) -> None:
        checkpoint_data = getattr(task, "checkpoint_data", None)
        checkpoint = dict(checkpoint_data) if isinstance(checkpoint_data, dict) else {}
        control = checkpoint.get("control")
        control_dict = dict(control) if isinstance(control, dict) else {}
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
    ) -> Agent | None:
        """按角色 + 空闲状态匹配 Agent，优先选负载最低的。"""
        stmt = (
            select(Agent)
            .where(
                Agent.status == AGENT_IDLE,
            )
        )
        if role:
            stmt = stmt.where(Agent.role == role)

        # 按创建时间排序（简单的负载平衡，先注册的优先）
        stmt = stmt.order_by(Agent.created_at)

        result = await session.execute(stmt)
        return result.scalars().first()

    async def _assign_node(
        self,
        session: AsyncSession,
        node: TaskNode,
        agent: Agent,
    ) -> bool:
        """将节点分配给 Agent：更新DB + Redis + 发送消息。"""
        log = logger.bind(
            task_id=str(self.task_id),
            node_id=str(node.id),
            agent_id=str(agent.id),
        )

        # 更新 DB 状态
        result = await session.execute(
            update(TaskNode)
            .where(
                TaskNode.id == node.id,
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
            .where(Agent.id == agent.id)
            .values(status=AGENT_BUSY)
        )
        await session.commit()

        self._running_nodes[node.id] = agent.id
        self._node_roles[node.id] = node.agent_role or ""

        session.expire_all()
        current_node = await session.get(TaskNode, node.id)
        task = await session.get(Task, self.task_id)
        if (
            current_node is None
            or current_node.status != STATUS_RUNNING
            or current_node.assigned_agent != agent.id
            or task is None
            or self._read_control_status(task) in CONTROL_BLOCKING_STATUSES
        ):
            self._running_nodes.pop(node.id, None)
            self._node_roles.pop(node.id, None)
            if current_node is not None:
                await session.execute(
                    update(TaskNode)
                    .where(
                        TaskNode.id == node.id,
                        TaskNode.status == STATUS_RUNNING,
                        TaskNode.assigned_agent == agent.id,
                    )
                    .values(
                        status=STATUS_READY,
                        assigned_agent=None,
                        started_at=None,
                    )
                )
            await session.execute(
                update(Agent)
                .where(Agent.id == agent.id)
                .values(status=AGENT_IDLE)
            )
            await session.commit()
            log.info("node assignment aborted after control transition")
            return False

        try:
            await set_dag_node_status(self.task_id, str(node.id), STATUS_RUNNING)
            deadline = time.time() + NODE_TIMEOUT_SECONDS
            await add_timeout_watch(self._timeout_watch_member(node.id), deadline)
            await communicator.send_task_assignment(
                agent_id=agent.id,
                task_id=self.task_id,
                node_id=node.id,
                payload={
                    "title": node.title,
                    "agent_role": node.agent_role,
                    "retry_count": node.retry_count,
                },
            )
        except Exception:
            logger.bind(task_id=str(self.task_id), node_id=str(node.id)).opt(
                exception=True
            ).warning("node assignment failed before delivery boundary; reverting assignment")
            await self._revert_assignment_after_side_effect_failure(node, agent)
            return False

        try:
            await communicator.send_status_update(
                task_id=self.task_id,
                node_id=node.id,
                status=STATUS_RUNNING,
                extra={"agent_name": agent.name, "agent_id": str(agent.id)},
            )
        except Exception:
            logger.bind(task_id=str(self.task_id), node_id=str(node.id)).opt(
                exception=True
            ).warning("failed to emit running status update after assignment delivery")

        log.info("node assigned to agent {}", agent.name)
        return True

    async def _revert_assignment_after_side_effect_failure(
        self,
        node: TaskNode,
        agent: Agent,
    ) -> None:
        self._running_nodes.pop(node.id, None)
        self._node_roles.pop(node.id, None)
        await self._clear_timeout_watch(node.id)

        reverted_to_ready = False
        async with async_session_factory() as compensation_session:
            revert_result = await compensation_session.execute(
                update(TaskNode)
                .where(
                    TaskNode.id == node.id,
                    TaskNode.status == STATUS_RUNNING,
                    TaskNode.assigned_agent == agent.id,
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
                .where(Agent.id == agent.id)
                .values(status=AGENT_IDLE)
            )
            await compensation_session.commit()

        if reverted_to_ready:
            await set_dag_node_status(self.task_id, str(node.id), STATUS_READY)
            await push_ready_node(str(node.id), priority=float(node.retry_count))

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

    async def _mark_task_done(self) -> None:
        """标记 Task 为完成。"""
        async with async_session_factory() as session:
            await session.execute(
                update(Task)
                .where(Task.id == self.task_id)
                .values(
                    status="done",
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

        try:
            await communicator.send_status_update(
                task_id=self.task_id,
                status="done",
                from_agent="scheduler",
            )
            await communicator.send_task_event(
                task_id=self.task_id,
                from_agent="scheduler",
                msg_type="task_done",
                payload={"status": "done"},
            )
        except Exception:
            logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                "failed to publish terminal done events"
            )

    async def _mark_task_failed(self, reason: str) -> None:
        """标记 Task 为失败。"""
        async with async_session_factory() as session:
            await session.execute(
                update(Task)
                .where(Task.id == self.task_id)
                .values(
                    status="failed",
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
