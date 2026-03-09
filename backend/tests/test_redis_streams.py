"""Tests for redis_streams.py and communicator.py — Step 3.1

使用 fakeredis 模拟 Redis，不依赖真实 Redis 实例。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.redis_streams import (
    READY_NODES_KEY,
    SYSTEM_LOGS_KEY,
    TIMEOUT_WATCH_KEY,
    MessageEnvelope,
    StreamMessage,
    add_timeout_watch,
    agent_inbox_key,
    agent_state_key,
    delete_agent_state,
    delete_dag_state,
    ensure_consumer_group,
    get_agent_state,
    get_dag_state,
    get_timed_out_nodes,
    pop_ready_nodes,
    push_ready_node,
    remove_timeout_watch,
    set_agent_state,
    set_dag_node_status,
    task_dag_state_key,
    task_events_key,
    xack,
    xadd,
    xreadgroup,
)


# ---------------------------------------------------------------------------
# MessageEnvelope 序列化 / 反序列化
# ---------------------------------------------------------------------------


class TestMessageEnvelope:
    def test_to_redis_returns_string_values(self):
        env = MessageEnvelope(
            msg_type="task_assign",
            from_agent="scheduler",
            to_agent="agent-1",
            task_id="t1",
            node_id="n1",
            payload={"key": "value"},
        )
        data = env.to_redis()
        assert isinstance(data["msg_id"], str)
        assert data["msg_type"] == "task_assign"
        assert data["from_agent"] == "scheduler"
        assert data["to_agent"] == "agent-1"
        assert json.loads(data["payload"]) == {"key": "value"}
        assert isinstance(data["timestamp"], str)
        assert data["ttl"] == "60"

    def test_from_redis_round_trip(self):
        original = MessageEnvelope(
            msg_type="task_result",
            from_agent="writer_1",
            task_id="t-100",
            node_id="n-200",
            payload={"score": 85},
            ttl=120,
        )
        serialized = original.to_redis()
        restored = MessageEnvelope.from_redis(serialized)

        assert restored.msg_id == original.msg_id
        assert restored.msg_type == "task_result"
        assert restored.from_agent == "writer_1"
        assert restored.task_id == "t-100"
        assert restored.node_id == "n-200"
        assert restored.payload == {"score": 85}
        assert restored.ttl == 120

    def test_from_redis_with_empty_data(self):
        env = MessageEnvelope.from_redis({})
        assert env.msg_id == ""
        assert env.msg_type == ""
        assert env.payload == {}
        assert env.ttl == 60

    def test_frozen_immutability(self):
        env = MessageEnvelope(msg_type="test")
        with pytest.raises(AttributeError):
            env.msg_type = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


class TestKeyBuilders:
    def test_agent_inbox_key(self):
        assert agent_inbox_key("abc") == "agent:abc:inbox"

    def test_agent_inbox_key_uuid(self):
        uid = uuid.uuid4()
        assert agent_inbox_key(uid) == f"agent:{uid}:inbox"

    def test_task_events_key(self):
        assert task_events_key("t1") == "task:t1:events"

    def test_agent_state_key(self):
        assert agent_state_key("a1") == "agent:a1:state"

    def test_task_dag_state_key(self):
        assert task_dag_state_key("t1") == "task:t1:dag_state"


# ---------------------------------------------------------------------------
# Redis Stream 操作 (使用 mock)
# ---------------------------------------------------------------------------


class TestEnsureConsumerGroup:
    @pytest.mark.asyncio
    async def test_creates_group(self):
        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        await ensure_consumer_group("stream:test", "group1", r=mock_redis)
        mock_redis.xgroup_create.assert_awaited_once_with(
            "stream:test", "group1", id="0", mkstream=True,
        )

    @pytest.mark.asyncio
    async def test_ignores_busygroup_error(self):
        import redis.asyncio as aioredis

        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock(
            side_effect=aioredis.ResponseError("BUSYGROUP Consumer Group name already exists"),
        )
        # Should not raise
        await ensure_consumer_group("stream:test", "group1", r=mock_redis)

    @pytest.mark.asyncio
    async def test_raises_non_busygroup_error(self):
        import redis.asyncio as aioredis

        mock_redis = AsyncMock()
        mock_redis.xgroup_create = AsyncMock(
            side_effect=aioredis.ResponseError("WRONGTYPE some other error"),
        )
        with pytest.raises(aioredis.ResponseError, match="WRONGTYPE"):
            await ensure_consumer_group("stream:test", "group1", r=mock_redis)


class TestXadd:
    @pytest.mark.asyncio
    async def test_xadd_calls_redis(self):
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value="1234-0")

        env = MessageEnvelope(msg_type="test", payload={"k": "v"})
        mid = await xadd("mystream", env, r=mock_redis)

        assert mid == "1234-0"
        mock_redis.xadd.assert_awaited_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "mystream"

    @pytest.mark.asyncio
    async def test_xadd_maxlen(self):
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value="1234-0")

        env = MessageEnvelope(msg_type="test")
        await xadd("s", env, maxlen=500, r=mock_redis)

        call_kwargs = mock_redis.xadd.call_args
        assert call_kwargs[1]["maxlen"] == 500


class TestXreadgroup:
    @pytest.mark.asyncio
    async def test_returns_empty_on_none(self):
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = AsyncMock(return_value=None)

        msgs = await xreadgroup("g", "c", {"s": ">"}, r=mock_redis)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_parses_messages(self):
        mock_redis = AsyncMock()
        mock_redis.xreadgroup = AsyncMock(return_value=[
            ("stream:a", [
                ("1-0", {"msg_type": "task_assign", "payload": "{}"}),
                ("2-0", {"msg_type": "heartbeat", "payload": "{}"}),
            ]),
        ])

        msgs = await xreadgroup("g", "c", {"stream:a": ">"}, r=mock_redis)
        assert len(msgs) == 2
        assert msgs[0].stream == "stream:a"
        assert msgs[0].message_id == "1-0"
        assert msgs[1].data["msg_type"] == "heartbeat"


class TestXack:
    @pytest.mark.asyncio
    async def test_xack_delegates(self):
        mock_redis = AsyncMock()
        mock_redis.xack = AsyncMock(return_value=1)

        result = await xack("s", "g", "1-0", "2-0", r=mock_redis)
        assert result == 1
        mock_redis.xack.assert_awaited_once_with("s", "g", "1-0", "2-0")


# ---------------------------------------------------------------------------
# Sorted Set — 超时监控
# ---------------------------------------------------------------------------


class TestTimeoutWatch:
    @pytest.mark.asyncio
    async def test_add_and_get(self):
        mock_redis = AsyncMock()
        mock_redis.zadd = AsyncMock()
        await add_timeout_watch("n1", 1000.0, r=mock_redis)
        mock_redis.zadd.assert_awaited_once_with(TIMEOUT_WATCH_KEY, {"n1": 1000.0})

    @pytest.mark.asyncio
    async def test_remove(self):
        mock_redis = AsyncMock()
        mock_redis.zrem = AsyncMock()
        await remove_timeout_watch("n1", r=mock_redis)
        mock_redis.zrem.assert_awaited_once_with(TIMEOUT_WATCH_KEY, "n1")

    @pytest.mark.asyncio
    async def test_get_timed_out_nodes(self):
        mock_redis = AsyncMock()
        mock_redis.zrangebyscore = AsyncMock(return_value=["n1", "n2"])
        result = await get_timed_out_nodes(r=mock_redis)
        assert result == ["n1", "n2"]


# ---------------------------------------------------------------------------
# Sorted Set — 就绪节点
# ---------------------------------------------------------------------------


class TestReadyNodes:
    @pytest.mark.asyncio
    async def test_push_and_pop(self):
        mock_redis = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zpopmin = AsyncMock(return_value=[("n1", 0.0), ("n2", 1.0)])

        await push_ready_node("n1", priority=0.0, r=mock_redis)
        mock_redis.zadd.assert_awaited_once_with(READY_NODES_KEY, {"n1": 0.0})

        result = await pop_ready_nodes(count=5, r=mock_redis)
        assert result == ["n1", "n2"]


# ---------------------------------------------------------------------------
# Hash — Agent 状态
# ---------------------------------------------------------------------------


class TestAgentState:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={
            "status": "busy",
            "current_task": "t1",
            "last_heartbeat": "1000.0",
        })

        await set_agent_state("a1", {"status": "busy", "current_task": "t1"}, r=mock_redis)
        mock_redis.hset.assert_awaited_once()

        state = await get_agent_state("a1", r=mock_redis)
        assert state["status"] == "busy"

    @pytest.mark.asyncio
    async def test_delete(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        await delete_agent_state("a1", r=mock_redis)
        mock_redis.delete.assert_awaited_once_with("agent:a1:state")


# ---------------------------------------------------------------------------
# Hash — DAG 状态
# ---------------------------------------------------------------------------


class TestDagState:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"n1": "running", "n2": "pending"})

        await set_dag_node_status("t1", "n1", "running", r=mock_redis)
        state = await get_dag_state("t1", r=mock_redis)
        assert state == {"n1": "running", "n2": "pending"}

    @pytest.mark.asyncio
    async def test_delete_dag(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        await delete_dag_state("t1", r=mock_redis)
        mock_redis.delete.assert_awaited_once_with("task:t1:dag_state")
