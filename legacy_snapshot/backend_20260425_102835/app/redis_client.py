"""Redis 异步客户端 — 用于 Streams / Hash / Sorted Set"""

import redis.asyncio as aioredis

from app.config import settings

redis_client: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端实例"""
    return redis_client


async def close_redis() -> None:
    """关闭 Redis 连接"""
    await redis_client.aclose()
