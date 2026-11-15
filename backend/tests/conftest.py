"""
Pytest Fixtures and Test Configuration for Mission Forge Backend
Provides isolated test database, dependency overrides, and async HTTP test client.
Uses pure asyncio execution for maximum reliability across Python runtimes.
"""

import os
import asyncio
import inspect
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.core.database import Base, get_db


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "asyncio: mark test as async coroutine")


def pytest_sessionfinish(session, exitstatus):
    """Ensure global SQLAlchemy async engine is disposed so worker threads terminate cleanly."""
    try:
        from backend.app.core.database import engine as global_engine
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(global_engine.dispose())
        finally:
            loop.close()
    except Exception:
        pass


def pytest_pyfunc_call(pyfuncitem):
    """Hook to execute coroutine test functions in an asyncio event loop."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            testargs = {
                arg: pyfuncitem.funcargs[arg]
                for arg in pyfuncitem._fixtureinfo.argnames
            }
            loop.run_until_complete(pyfuncitem.obj(**testargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        return True
    return None


@pytest.fixture(autouse=True)
def reset_fdir_engine_state():
    """Ensures clean FDIR engine state between test cases."""
    from backend.app.fdir.engine import fdir_engine
    fdir_engine.reset()
    yield
    fdir_engine.reset()


@pytest.fixture(scope="session")
def test_db_setup():
    """
    Creates an isolated temporary SQLite database for the test suite.
    Ensures tests cannot modify the development database.
    """
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, "test_isolated.db")
    test_db_url = f"sqlite+aiosqlite:///{test_db_path}"

    engine = create_async_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )

    async def _init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_init_tables())

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    yield engine, session_factory

    async def _cleanup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    loop.run_until_complete(_cleanup())
    loop.close()

    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        os.rmdir(temp_dir)
    except OSError:
        pass


@pytest.fixture
def db_session(test_db_setup):
    """Provides an isolated session factory for tests with explicit lifecycle teardown."""
    _, session_factory = test_db_setup
    session = session_factory()
    yield session
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(session.close())
    finally:
        loop.close()


@pytest.fixture
def async_client(test_db_setup):
    """Provides an async HTTP client configured with the test database dependency."""
    _, session_factory = test_db_setup

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")

    from backend.app.dossier.service import set_session_factory
    set_session_factory(session_factory)

    yield client

    set_session_factory(None)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(client.aclose())
    loop.close()
    app.dependency_overrides.clear()
