"""Fixtures shared by all tests.

Tests run against a REAL PostgreSQL database, separate from the dev one
("mediagent_test"). Reason: our business guarantees (no double booking, no
overlapping slots) are enforced BY the database, so a fake could never
prove them.
"""

import os
from pathlib import Path

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://mediagent:mediagent@localhost:5432/mediagent_test",
)
# Must happen BEFORE the first "app" import: app.config reads DATABASE_URL once,
# and everything (engine, Alembic) builds on it.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import models as m  # noqa: E402
from app.db.seed import seed  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import AppointmentService  # noqa: E402
from app.sql_repository import SqlRepository  # noqa: E402
from tests.helpers import NOW  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def _database():
    """Once per test run: make sure the test database exists and is migrated."""
    url = make_url(TEST_DATABASE_URL)
    # Safety net: the per-test reset TRUNCATES every table.
    assert url.database.endswith("_test"), (
        f"Refusing to run tests against database {url.database!r}: "
        "its name must end with '_test' so we never wipe real data."
    )
    # CREATE DATABASE cannot run inside a transaction -> AUTOCOMMIT, and we
    # connect to the built-in "postgres" database to issue it.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    # Build the schema with the REAL migrations (so they are tested too).
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


@pytest.fixture
def fresh_db(_database):
    """Before EACH test: empty every table, then load the demo seed."""
    tables = ", ".join(t.name for t in m.Base.metadata.sorted_tables)
    with SessionLocal.begin() as setup:  # commits when the block ends
        setup.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        seed(setup)


@pytest.fixture
def session(fresh_db):
    """The test's own session. Never committed: its changes die with the test."""
    with SessionLocal() as s:
        yield s
        s.rollback()


@pytest.fixture
def repo(session: Session) -> SqlRepository:
    return SqlRepository(session)


@pytest.fixture
def make_service(repo: SqlRepository):
    """Build a service whose clock is frozen at `now` (default: NOW)."""

    def _make(now=NOW) -> AppointmentService:
        return AppointmentService(repo, clock=lambda: now)

    return _make
