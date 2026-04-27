"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine
from app.redis_client import close_redis, redis_client
from app.services.runtime_bootstrap import (
    bootstrap_runtime_agents,
    shutdown_runtime_agents,
)
from app.routers import (
    agents_router,
    tasks_router,
    nodes_router,
    export_router,
    outline_router,
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

    try:
        started = await bootstrap_runtime_agents()
        logger.info("Runtime agents bootstrapped: {}", started)
    except Exception:
        logger.opt(exception=True).warning("Runtime agent bootstrap failed")

    yield

    # 关闭资源
    try:
        await shutdown_runtime_agents()
    except Exception:
        logger.opt(exception=True).warning("Runtime agent shutdown failed")
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
app.include_router(outline_router)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "hierarch"}


_frontend_dist = Path(settings.frontend_dist_dir).expanduser().resolve() if settings.frontend_dist_dir else None
if _frontend_dist and (_frontend_dist / "index.html").exists():
    assets_dir = _frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    def _ensure_not_backend_path(path: str) -> None:
        blocked_prefixes = ("api/", "ws/", "docs", "redoc", "openapi.json", "health")
        normalized = path.strip("/")
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in blocked_prefixes):
            raise HTTPException(status_code=404, detail="Not found")

    @app.get("/", include_in_schema=False)
    async def serve_frontend_index() -> FileResponse:
        return FileResponse(_frontend_dist / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend_spa(full_path: str) -> FileResponse:
        _ensure_not_backend_path(full_path)
        requested = (_frontend_dist / full_path).resolve()
        if requested.is_file() and requested.is_relative_to(_frontend_dist):
            return FileResponse(requested)
        return FileResponse(_frontend_dist / "index.html")
