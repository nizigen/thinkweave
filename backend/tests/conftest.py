"""Test configuration and fixtures."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app


@pytest_asyncio.fixture
async def db_session():
    """Test session with a per-test engine — avoids event loop cross-contamination."""
    test_engine = create_async_engine(settings.postgres_url, echo=False)
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with factory() as session:
        yield session
        await session.rollback()

    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Async HTTP test client with DB session override."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
