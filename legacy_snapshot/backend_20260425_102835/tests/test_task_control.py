"""Service-level task control tests (Stage 2 RED)."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.redis_streams import timeout_watch_member
from app.services.task_control import (
    _retry_node_in_memory,
    _skip_node_in_memory,
    TaskControlError,
    ensure_pause_allowed,
    ensure_resume_allowed,
    pause_task,
    resume_task,
    retry_node,
    skip_node,
)


def _build_task(
    *,
    status: str = "pending",
    control_status: str = "active",
    nodes: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    checkpoint = {"control": {"status": control_status}}
    return SimpleNamespace(
        status=status,
        checkpoint_data=checkpoint,
        nodes=nodes or [],
    )


def _build_node(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        agent_role="writer",
        started_at="started",
        finished_at="finished",
        assigned_agent=uuid.uuid4(),
        result="result",
        retry_count=0,
    )


def test_pause_allowed_for_pending_or_running_tasks() -> None:
    for status in ("pending", "running"):
        ensure_pause_allowed(_build_task(status=status))


def test_pause_rejected_for_terminal_tasks() -> None:
    terminal_task = _build_task(status="done")
    with pytest.raises(TaskControlError):
        ensure_pause_allowed(terminal_task)


@pytest.mark.parametrize("control_status", ["pause_requested", "paused"])
def test_pause_rejected_when_control_state_is_not_active(control_status: str) -> None:
    task = _build_task(status="running", control_status=control_status)
    with pytest.raises(TaskControlError):
        ensure_pause_allowed(task)


def test_resume_only_allowed_for_paused_control_state() -> None:
    ensure_resume_allowed(_build_task(control_status="paused"))
    with pytest.raises(TaskControlError):
        ensure_resume_allowed(_build_task(control_status="active"))


def test_resume_rejected_for_terminal_task_even_if_paused() -> None:
    with pytest.raises(TaskControlError):
        ensure_resume_allowed(_build_task(status="done", control_status="paused"))


def test_skip_requires_node_id() -> None:
    task = _build_task(nodes=[_build_node("pending")])
    with pytest.raises(TaskControlError):
        _skip_node_in_memory(task, node_id=None)


@pytest.mark.parametrize("status", ["pending", "ready", "running"])
def test_skip_allowed_for_pending_ready_or_running_nodes(status: str) -> None:
    node = _build_node(status)
    task = _build_task(nodes=[node])
    _skip_node_in_memory(task, node_id=node.id)
    assert node.status == "skipped"


def test_retry_allowed_only_for_failed_or_skipped_nodes() -> None:
    for status in ("failed", "skipped"):
        node = _build_node(status)
        task = _build_task(nodes=[node])
        _retry_node_in_memory(task, node_id=node.id)
        assert node.status == "ready"

    node = _build_node("done")
    task = _build_task(nodes=[node])
    with pytest.raises(TaskControlError):
        _retry_node_in_memory(task, node_id=node.id)


def test_retry_skipped_node_with_unmet_dependencies_returns_to_pending() -> None:
    upstream = _build_node("pending")
    dependent = _build_node("skipped")
    dependent.depends_on = [upstream.id]
    task = _build_task(nodes=[upstream, dependent])

    _retry_node_in_memory(task, node_id=dependent.id)

    assert dependent.status == "pending"


def test_retry_skipped_node_rejected_after_downstream_progress() -> None:
    skipped = _build_node("skipped")
    downstream = _build_node("done")
    downstream.depends_on = [skipped.id]
    task = _build_task(nodes=[skipped, downstream])

    with pytest.raises(TaskControlError, match="dependent progress"):
        _retry_node_in_memory(task, node_id=skipped.id)


def test_retry_clears_terminal_execution_fields_before_requeue() -> None:
    node = _build_node("failed")
    task = _build_task(nodes=[node])
    _retry_node_in_memory(task, node_id=node.id)
    assert node.started_at is None
    assert node.finished_at is None
    assert node.result is None
    assert node.assigned_agent is None


def test_retry_resets_retry_budget_for_manual_retry() -> None:
    node = _build_node("failed")
    node.retry_count = 3
    task = _build_task(nodes=[node])

    _retry_node_in_memory(task, node_id=node.id)

    assert node.retry_count == 0


@pytest.mark.asyncio
async def test_retry_node_wakes_scheduler_after_requeue() -> None:
    task_id = uuid.uuid4()
    node = _build_node("failed")
    node.retry_count = 2
    task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    scheduler = MagicMock()
    retry_result = MagicMock()
    retry_result.rowcount = 1
    session.execute = AsyncMock(return_value=retry_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._load_task_nodes", new=AsyncMock(return_value=[node])),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch(
            "app.services.task_control.get_scheduler",
            return_value=scheduler,
            create=True,
        ),
    ):
        await retry_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    scheduler.wake.assert_called_once()


@pytest.mark.asyncio
async def test_pause_task_emits_dag_and_log_updates() -> None:
    task_id = uuid.uuid4()
    task = _build_task(status="running", control_status="active")
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=None, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await pause_task(
            session,
            task_id,
            user_id="user-1",
            is_admin=False,
        )

    msg_types = [call.kwargs["msg_type"] for call in communicator.send_task_event.await_args_list]
    assert "dag_update" in msg_types
    assert "log" in msg_types


@pytest.mark.asyncio
async def test_resume_task_emits_dag_and_log_updates() -> None:
    task_id = uuid.uuid4()
    task = _build_task(status="running", control_status="paused")
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=None, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await resume_task(
            session,
            task_id,
            user_id="user-1",
            is_admin=False,
        )

    msg_types = [call.kwargs["msg_type"] for call in communicator.send_task_event.await_args_list]
    assert "dag_update" in msg_types
    assert "log" in msg_types


@pytest.mark.asyncio
async def test_skip_node_emits_node_update_plus_dag_and_log_updates() -> None:
    task_id = uuid.uuid4()
    node = _build_node("running")
    task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    scheduler = MagicMock()
    scheduler.reconcile_skipped_node = AsyncMock()
    skip_result = MagicMock()
    skip_result.rowcount = 1
    session.execute = AsyncMock(return_value=skip_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._get_persisted_node_or_raise", new=AsyncMock(return_value=node)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=scheduler, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await skip_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    scheduler.reconcile_skipped_node.assert_awaited_once_with(node.id)
    communicator.send_status_update.assert_awaited_once()
    msg_types = [call.kwargs["msg_type"] for call in communicator.send_task_event.await_args_list]
    assert "dag_update" in msg_types
    assert "log" in msg_types


@pytest.mark.asyncio
async def test_skip_node_reconciles_scheduler_after_commit_even_if_snapshot_was_not_running() -> None:
    task_id = uuid.uuid4()
    node = _build_node("ready")
    task = SimpleNamespace(status="running", checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    scheduler = MagicMock()
    scheduler.reconcile_skipped_node = AsyncMock()
    skip_result = MagicMock()
    skip_result.rowcount = 1
    session.execute = AsyncMock(return_value=skip_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._get_persisted_node_or_raise", new=AsyncMock(return_value=node)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=scheduler, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await skip_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    scheduler.reconcile_skipped_node.assert_awaited_once_with(node.id)


@pytest.mark.asyncio
async def test_skip_node_does_not_reconcile_scheduler_when_commit_fails() -> None:
    task_id = uuid.uuid4()
    node = _build_node("running")
    task = SimpleNamespace(status="running", checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    scheduler = MagicMock()
    scheduler.reconcile_skipped_node = AsyncMock()
    skip_result = MagicMock()
    skip_result.rowcount = 1
    session.execute = AsyncMock(return_value=skip_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._get_persisted_node_or_raise", new=AsyncMock(return_value=node)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(side_effect=RuntimeError("commit failed")),
        ),
        patch("app.services.task_control.get_scheduler", return_value=scheduler, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            await skip_node(
                session,
                task_id,
                node_id=node.id,
                user_id="user-1",
                is_admin=False,
            )

    scheduler.reconcile_skipped_node.assert_not_called()


@pytest.mark.asyncio
async def test_skip_node_returns_committed_detail_when_reconcile_fails_after_commit() -> None:
    task_id = uuid.uuid4()
    node = _build_node("running")
    task = SimpleNamespace(status="running", checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    scheduler = MagicMock()
    scheduler.reconcile_skipped_node = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    skip_result = MagicMock()
    skip_result.rowcount = 1
    session.execute = AsyncMock(return_value=skip_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._get_persisted_node_or_raise", new=AsyncMock(return_value=node)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id), "status": "running"}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=scheduler, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        detail = await skip_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    assert detail["id"] == str(task_id)
    communicator.send_status_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_running_node_without_scheduler_releases_agent_and_timeout_watch() -> None:
    task_id = uuid.uuid4()
    node = _build_node("running")
    original_agent_id = node.assigned_agent
    task = SimpleNamespace(status="running", checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    skip_result = MagicMock()
    skip_result.rowcount = 1
    session.execute = AsyncMock(side_effect=[skip_result, MagicMock()])

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._get_persisted_node_or_raise", new=AsyncMock(return_value=node)),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=None, create=True),
        patch("app.services.task_control.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await skip_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    assert session.execute.await_count == 2
    idle_update = session.execute.await_args_list[1].args[0]
    assert str(idle_update.compile().params["id_1"]) == str(original_agent_id)
    assert idle_update.compile().params["status"] == "idle"
    assert [call.args[0] for call in mock_remove_watch.await_args_list] == [
        timeout_watch_member(task_id, node.id),
        str(node.id),
    ]


@pytest.mark.asyncio
async def test_retry_node_emits_node_update_plus_dag_and_log_updates() -> None:
    task_id = uuid.uuid4()
    node = _build_node("failed")
    task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    communicator = MagicMock()
    communicator.send_task_event = AsyncMock()
    communicator.send_status_update = AsyncMock()
    retry_result = MagicMock()
    retry_result.rowcount = 1
    session.execute = AsyncMock(return_value=retry_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._load_task_nodes", new=AsyncMock(return_value=[node])),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.get_scheduler", return_value=None, create=True),
        patch("app.services.task_control.communicator", communicator, create=True),
    ):
        await retry_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    communicator.send_status_update.assert_awaited_once()
    msg_types = [call.kwargs["msg_type"] for call in communicator.send_task_event.await_args_list]
    assert "dag_update" in msg_types
    assert "log" in msg_types


@pytest.mark.asyncio
async def test_retry_node_resets_budget_then_scheduler_can_dispatch_same_node() -> None:
    task_id = uuid.uuid4()
    node = _build_node("failed")
    node.retry_count = 2
    task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()
    retry_result = MagicMock()
    retry_result.rowcount = 1
    session.execute = AsyncMock(return_value=retry_result)

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._load_task_nodes", new=AsyncMock(return_value=[node])),
        patch(
            "app.services.task_control._commit_and_refresh_detail",
            new=AsyncMock(return_value={"id": str(task_id)}),
        ),
        patch("app.services.task_control.communicator") as mock_comm,
        patch("app.services.task_control.get_scheduler", return_value=None, create=True),
    ):
        mock_comm.send_task_event = AsyncMock()
        mock_comm.send_status_update = AsyncMock()
        await retry_node(
            session,
            task_id,
            node_id=node.id,
            user_id="user-1",
            is_admin=False,
        )

    assert session.execute.await_count == 1
    retry_update = session.execute.await_args_list[0].args[0]
    params = retry_update.compile().params
    assert params["status"] == "ready"
    assert params["retry_count"] == 0

    from app.services.dag_scheduler import DAGScheduler

    scheduler = DAGScheduler(task_id)
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.name = "writer-1"
    agent.role = "writer"

    with (
        patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
        patch.object(scheduler, "_match_agent", new=AsyncMock(return_value=agent)),
        patch.object(scheduler, "_assign_node", new_callable=AsyncMock) as mock_assign,
    ):
        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = []
        ready_result = MagicMock()
        ready_result.scalars.return_value.all.return_value = [node]
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=task)
        mock_session.execute = AsyncMock(side_effect=[pending_result, ready_result])
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        dispatched = await scheduler._dispatch_ready_nodes()

    assert dispatched == 1
    mock_assign.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_node_rejects_terminal_task_status() -> None:
    task_id = uuid.uuid4()
    node = _build_node("failed")
    task = SimpleNamespace(status="failed", checkpoint_data={"control": {"status": "active"}})
    session = AsyncMock()

    with (
        patch("app.services.task_control._get_visible_task", new=AsyncMock(return_value=task)),
        patch("app.services.task_control._load_task_nodes", new=AsyncMock(return_value=[node])),
    ):
        with pytest.raises(TaskControlError, match="retry not allowed for task status 'failed'"):
            await retry_node(
                session,
                task_id,
                node_id=node.id,
                user_id="user-1",
                is_admin=False,
            )


def test_skip_and_retry_public_contract_are_task_scoped_async_handlers() -> None:
    assert inspect.iscoroutinefunction(skip_node)
    assert inspect.iscoroutinefunction(retry_node)
