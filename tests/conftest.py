"""
tests/conftest.py
Baseline environment for all tests, plus real-Postgres database fixtures

Created: 2026-09-18
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


# The minimum environment config.py needs in order to import.
# Values the application has a sensible default for are deliberately absent.
BASELINE_ENV = {
    "MITESPOTTER_DATABASE_URL": "postgresql+psycopg://localhost/mitespotter_test",
}

# Postgres the database tests may create and drop databases on.
# Any database name in the URL is ignored; only the server and credentials are used.
TEST_DATABASE_URL_VAR = "MITESPOTTER_TEST_DATABASE_URL"


def pytest_configure(config: pytest.Config) -> None:
    """Apply the baseline before collection, since test modules may import config at module level."""
    os.environ.update(BASELINE_ENV)


@pytest.fixture(autouse=True)
def baseline_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Apply the baseline environment to every test.

    MITESPOTTER_DATA_DIR is pinned to a temporary directory so no test can
    write into the repository's data/ tree. monkeypatch restores the real
    environment afterwards.
    """
    monkeypatch.setenv("MITESPOTTER_DATA_DIR", str(tmp_path / "data"))
    for name, value in BASELINE_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def required_env() -> dict[str, str]:
    """A copy of BASELINE_ENV for tests that build their own environment."""
    return dict(BASELINE_ENV)


@pytest.fixture
def make_settings(tmp_path: Path):
    """Build Settings from an explicit environment, without touching os.environ."""
    from mitespotter_api.config import Settings

    def _make(database_url: str = BASELINE_ENV["MITESPOTTER_DATABASE_URL"], **env: str):
        return Settings.from_env({
            "MITESPOTTER_ENV": "test",
            "MITESPOTTER_SQL_ECHO": "false",
            "MITESPOTTER_DATA_DIR": str(tmp_path / "data"),
            "MITESPOTTER_DATABASE_URL": database_url,
            **env,
        })

    return _make


# MARK: Database

def _upgrade(database_url: str, revision: str = "head") -> None:
    from advanced_alchemy.alembic.commands import AlembicCommands

    from mitespotter_api.config import Settings
    from mitespotter_api.db import make_alchemy_config

    settings = Settings.from_env({"MITESPOTTER_DATABASE_URL": database_url, "MITESPOTTER_SQL_ECHO": "false"})
    AlembicCommands(sqlalchemy_config=make_alchemy_config(settings)).upgrade(revision)


@pytest.fixture(scope="session")
def database_factory() -> Iterator[Callable[[], str]]:
    """Create uniquely named, empty databases on the test server; all are dropped at the end.

    Skips when MITESPOTTER_TEST_DATABASE_URL is not set.
    """
    raw = os.environ.get(TEST_DATABASE_URL_VAR, "").strip()
    if not raw:
        pytest.skip(f"{TEST_DATABASE_URL_VAR} is not set; skipping tests that need Postgres")

    import psycopg
    from sqlalchemy.engine import make_url

    server = make_url(raw)
    admin_dsn = server.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    created: list[str] = []

    def _create() -> str:
        name = f"mitespotter_test_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        return server.set(drivername="postgresql+psycopg", database=name).render_as_string(hide_password=False)

    yield _create

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        for name in created:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def database_url(database_factory: Callable[[], str]) -> str:
    """A database migrated to head, shared by the test session."""
    url = database_factory()
    _upgrade(url)
    return url
