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
    push_ready_node,
    remove_timeout_watch,
    set_dag_node_status,
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

                # 3. 检查是否 DAG 已完成
                if await self._is_dag_complete():
                    log.info("DAG completed — all nodes done")
                    await self._mark_task_done()
                    break

                # 4. 检查是否死锁（没有 running 也没有 ready）
                if not dispatched and not self._running_nodes:
                    if await self._has_undone_nodes():
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
            log.info("DAGScheduler stopped")

    def stop(self) -> None:
        """外部请求停止调度。"""
        self._stop.set()
        self._schedule_event.set()

    async def on_node_completed(
        self,
        node_id: uuid.UUID,
        result: str,
        agent_id: uuid.UUID,
    ) -> None:
        """Agent 完成节点后回调 — 更新状态并触发下一轮调度。"""
        log = logger.bind(task_id=str(self.task_id), node_id=str(node_id))

        async with async_session_factory() as session:
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
        await remove_timeout_watch(str(node_id))

        self._running_nodes.pop(node_id, None)
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
                await remove_timeout_watch(str(node_id))

                self._running_nodes.pop(node_id, None)
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
                await remove_timeout_watch(str(node_id))

                self._running_nodes.pop(node_id, None)
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
            # 查询所有 ready 节点
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_READY,
            )
            result = await session.execute(stmt)
            ready_nodes = list(result.scalars().all())

            for node in ready_nodes:
                # 并发控制检查
                if not self._can_dispatch(node.agent_role):
                    continue

                # 匹配空闲 Agent
                agent = await self._match_agent(session, node.agent_role)
                if agent is None:
                    continue

                # 分配任务
                await self._assign_node(session, node, agent)
                dispatched += 1

            await session.commit()

        return dispatched

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

    @property
    def _node_roles(self) -> dict[uuid.UUID, str]:
        """延迟缓存：当前 running 节点的角色映射。"""
        if not hasattr(self, "_cached_node_roles"):
            self._cached_node_roles: dict[uuid.UUID, str] = {}
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
    ) -> None:
        """将节点分配给 Agent：更新DB + Redis + 发送消息。"""
        log = logger.bind(
            task_id=str(self.task_id),
            node_id=str(node.id),
            agent_id=str(agent.id),
        )

        # 更新 DB 状态
        await session.execute(
            update(TaskNode)
            .where(TaskNode.id == node.id)
            .values(
                status=STATUS_RUNNING,
                assigned_agent=agent.id,
                started_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.execute(
            update(Agent)
            .where(Agent.id == agent.id)
            .values(status=AGENT_BUSY)
        )

        # 更新 Redis 状态
        await set_dag_node_status(self.task_id, str(node.id), STATUS_RUNNING)

        # 设置超时监控
        deadline = time.time() + NODE_TIMEOUT_SECONDS
        await add_timeout_watch(str(node.id), deadline)

        # 追踪运行中的节点
        self._running_nodes[node.id] = agent.id
        self._node_roles[node.id] = node.agent_role or ""

        # 通过 Communicator 发送任务分配消息
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

        # 发送状态更新（供 WebSocket 转发）
        await communicator.send_status_update(
            task_id=self.task_id,
            node_id=node.id,
            status=STATUS_RUNNING,
            extra={"agent_name": agent.name, "agent_id": str(agent.id)},
        )

        log.info("node assigned to agent {}", agent.name)

    # ------------------------------------------------------------------
    # Internal — 依赖激活
    # ------------------------------------------------------------------

    async def _activate_dependents(self, completed_node_id: uuid.UUID) -> None:
        """检查依赖于已完成节点的下游节点，如果所有依赖都满足则标为 ready。"""
        async with async_session_factory() as session:
            # 获取所有 pending 节点
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_PENDING,
            )
            result = await session.execute(stmt)
            pending_nodes = list(result.scalars().all())

            # 获取当前所有已完成的节点 ID
            done_stmt = select(TaskNode.id).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status == STATUS_DONE,
            )
            done_result = await session.execute(done_stmt)
            done_ids = {row[0] for row in done_result.all()}

            for node in pending_nodes:
                deps = node.depends_on or []
                if not deps:
                    continue

                # 检查此节点的依赖中是否包含刚完成的节点
                dep_uuids = {uuid.UUID(str(d)) for d in deps}
                if completed_node_id not in dep_uuids:
                    continue

                # 检查所有依赖是否都已完成
                if dep_uuids.issubset(done_ids):
                    await session.execute(
                        update(TaskNode)
                        .where(TaskNode.id == node.id)
                        .values(status=STATUS_READY)
                    )
                    await set_dag_node_status(self.task_id, str(node.id), STATUS_READY)
                    await push_ready_node(str(node.id), priority=0.0)

                    logger.bind(node_id=str(node.id)).debug(
                        "node activated: all deps satisfied"
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

        for node_id_str in timed_out:
            node_id = uuid.UUID(node_id_str)
            agent_id = self._running_nodes.get(node_id)
            if agent_id is None:
                # 不在运行列表中，可能已被处理，清理即可
                await remove_timeout_watch(node_id_str)
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
        """所有节点是否都已完成（done）或失败（failed）。"""
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status.notin_([STATUS_DONE, STATUS_FAILED]),
            )
            result = await session.execute(stmt)
            return result.scalars().first() is None

    async def _has_undone_nodes(self) -> bool:
        """是否还有未完成且非失败的节点。"""
        async with async_session_factory() as session:
            stmt = select(TaskNode).where(
                TaskNode.task_id == self.task_id,
                TaskNode.status.notin_([STATUS_DONE, STATUS_FAILED]),
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

        await communicator.send_status_update(
            task_id=self.task_id,
            status="done",
            from_agent="scheduler",
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

        await communicator.send_status_update(
            task_id=self.task_id,
            status="failed",
            from_agent="scheduler",
            extra={"reason": reason},
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
