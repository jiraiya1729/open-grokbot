import os
from collections.abc import Generator

import psycopg
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from alembic import command
from app.infrastructure.providers import (
    ModelProvider,
    ModelRequest,
    StopEvent,
    TextDelta,
    ToolDefinition,
)

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://grokbot:grokbot@localhost:5432/grokbot_test",
)
# Add connect_timeout so tests fail fast when DB is unavailable rather than hanging
_base_url = TEST_DATABASE_URL.split("?")[0]
TEST_DATABASE_URL_WITH_TIMEOUT = _base_url + "?connect_timeout=5"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL_WITH_TIMEOUT
os.environ["ENABLE_INLINE_WORKER"] = "false"

_DB_AVAILABLE = False


class TestModelProvider(ModelProvider):
    name = "test"

    def stream(self, request: ModelRequest):
        yield (
            f"I'm {request.bot_name}, your {request.role_title}. "
            f"Following my brief - {request.instructions} - ready."
        )

    def stream_structured(self, request: ModelRequest, tools: list[ToolDefinition]):
        yield TextDelta(
            text=(
                f"I'm {request.bot_name}, your {request.role_title}. "
                f"Following my brief - {request.instructions} - ready."
            )
        )
        yield StopEvent(stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 20})


class TestModelRouter:
    def __init__(self) -> None:
        self.provider = TestModelProvider()

    def route(self, capability: str = "general") -> TestModelProvider:
        del capability
        return self.provider


def _create_test_database() -> None:
    psycopg_url = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    admin_url = psycopg_url.rsplit("/", 1)[0] + "/postgres"
    database_name = psycopg_url.rsplit("/", 1)[1]
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if not exists:
            connection.execute(f'CREATE DATABASE "{database_name}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Generator[None]:
    global _DB_AVAILABLE
    try:
        _create_test_database()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        _DB_AVAILABLE = True
    except (psycopg.OperationalError, OperationalError) as exc:
        _DB_AVAILABLE = False
        import warnings

        warnings.warn(
            f"Test database unavailable — integration tests will be skipped: {exc}",
            stacklevel=1,
        )
    yield


@pytest.fixture(autouse=True)
def clean_database(migrated_database: None, request: pytest.FixtureRequest) -> Generator[None]:
    del migrated_database
    is_integration = request.node.get_closest_marker("integration") is not None
    if not _DB_AVAILABLE:
        if is_integration:
            pytest.skip("Database unavailable")
        yield
        return
    import sqlalchemy.exc

    from app.core.database import engine

    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE users CASCADE"))
            connection.execute(text("TRUNCATE langgraph.checkpoints CASCADE"))
            connection.execute(text("TRUNCATE langgraph.checkpoint_blobs CASCADE"))
            connection.execute(text("TRUNCATE langgraph.checkpoint_writes CASCADE"))
    except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError):
        if is_integration:
            pytest.skip("Database unavailable")
        yield
        return
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    import app.agents.runtime as runtime
    import app.api.routes.chat.conversations as conversation_routes
    from app.main import app

    monkeypatch.setattr(conversation_routes, "dispatch_run", lambda run: None)
    monkeypatch.setattr(runtime.inngest_client, "send_sync", lambda event: [])
    monkeypatch.setattr(runtime, "model_router", TestModelRouter())
    with TestClient(app) as test_client:
        yield test_client
