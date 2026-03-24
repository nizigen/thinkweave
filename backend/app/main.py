"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.redis_client import close_redis, redis_client
from app.routers import (
    agents_router,
    tasks_router,
    nodes_router,
    export_router,
    ws_router,
)
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭时的资源管理"""
    logger.info("Hierarch 后端启动中...")

    # 检查 Redis 连接
    try:
        await redis_client.ping()
        logger.info("Redis 连接成功")
    except Exception as e:
        logger.warning(f"Redis 连接失败: {e}")

    yield

    # 关闭资源
    await engine.dispose()
    await close_redis()
    logger.info("Hierarch 后端已关闭")


app = FastAPI(
    title="Hierarch — 层级化 Agent 编排系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 开发阶段允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(nodes_router)
app.include_router(export_router)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "hierarch"}
