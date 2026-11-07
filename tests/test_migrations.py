"""
tests/test_migrations.py
Tests:
    src/mitespotter_api/migrations/

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import psycopg
from sqlalchemy.engine import make_url


def _query(url: str, sql: str) -> list[tuple]:
    dsn = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as conn:
        return conn.execute(sql).fetchall()


def _commands(url: str):
    from advanced_alchemy.alembic.commands import AlembicCommands

    from mitespotter_api.config import Settings
    from mitespotter_api.db import make_alchemy_config

    settings = Settings.from_env({"MITESPOTTER_DATABASE_URL": url, "MITESPOTTER_SQL_ECHO": "false"})
    return AlembicCommands(sqlalchemy_config=make_alchemy_config(settings))


def test_head_seeds_the_configured_categories(database_url):
    from mitespotter_api.config import CATEGORIES

    rows = _query(database_url, "SELECT id, name, supercategory FROM categories ORDER BY id")
    assert rows == [(c.id, c.name, c.supercategory) for c in CATEGORIES]


def test_head_creates_citext(database_url):
    assert _query(database_url, "SELECT 1 FROM pg_extension WHERE extname = 'citext'") == [(1,)]


def test_category_identity_continues_after_the_seed(database_url):
    rows = _query(database_url, "SELECT last_value FROM categories_id_seq")
    assert rows == [(2,)]


def test_head_matches_the_models(database_url):
    """No differences between the migrated schema and models.py (autogenerate would be empty)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from mitespotter_api.models import Category  # all models share its metadata

    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Category.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_downgrade_to_base_and_back(database_factory):
    url = database_factory()
    commands = _commands(url)

    commands.upgrade("head")
    commands.downgrade("base")
    for table in ("categories", "users", "images", "annotations", "reports"):
        assert _query(url, f"SELECT to_regclass('{table}')") == [(None,)]
    assert _query(url, "SELECT 1 FROM pg_extension WHERE extname = 'citext'") == []

    commands.upgrade("head")
    assert len(_query(url, "SELECT id FROM categories")) == 2


def test_offline_mode_renders_sql_without_a_database(capsys):
    # Nothing listens on port 1: offline mode must not connect
    _commands("postgresql+psycopg://nobody@127.0.0.1:1/none").upgrade("head", sql=True)
    sql = capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS citext" in sql
    assert "CREATE TABLE categories" in sql
    assert "CREATE UNIQUE INDEX uq_reports_open ON reports (reporter_id, image_id) WHERE resolved_at IS NULL" in sql
    assert "INSERT INTO alembic_version" in sql
