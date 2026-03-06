"""PostgreSQL 异步连接 — SQLAlchemy 2.0 async"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.postgres_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型继承此基类"""
    pass


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI Depends 注入用的 session 生成器"""
    async with async_session_factory() as session:
        yield session
