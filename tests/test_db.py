"""
tests/test_db.py
Tests:
    src/mitespotter_api/db.py

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


def test_alchemy_config(make_config):
    from mitespotter_api.db import SESSION_DEPENDENCY_KEY, make_alchemy_config

    config = make_alchemy_config(make_config("postgresql+psycopg://u:p@db.example/mitespotter"))

    assert config.connection_string == "postgresql+psycopg://u:p@db.example/mitespotter"
    assert config.session_dependency_key == SESSION_DEPENDENCY_KEY == "db_session"
    assert config.create_all is False               # schema only changes through Alembic
    assert callable(config.before_send_handler)     # "autocommit" resolved to a handler
    assert config.engine_config.echo is False
    assert config.engine_config.pool_pre_ping is True


def test_sql_echo_follows_config(make_config):
    from mitespotter_api.db import make_alchemy_config
    config = make_alchemy_config(make_config(MITESPOTTER_SQL_ECHO="true"))
    assert config.engine_config.echo is True


def test_alembic_config_points_into_the_package(make_config):
    from mitespotter_api.db import ALEMBIC_INI, MIGRATIONS_DIR, VERSION_TABLE, make_alchemy_config

    alembic = make_alchemy_config(make_config()).alembic_config

    assert alembic.script_location == str(MIGRATIONS_DIR)
    assert alembic.script_config == str(ALEMBIC_INI)
    assert alembic.version_table_name == VERSION_TABLE == "alembic_version"
    assert (MIGRATIONS_DIR / "env.py").is_file()
    assert ALEMBIC_INI.is_file()
    assert any((MIGRATIONS_DIR / "versions").glob("0001_*.py"))


def _autogen_context():
    from alembic.autogenerate.api import AutogenContext
    from alembic.migration import MigrationContext
    from sqlalchemy.dialects import postgresql

    return AutogenContext(MigrationContext.configure(dialect=postgresql.dialect(), opts={"sqlalchemy_module_prefix": "sa.", "user_module_prefix": "sa."}))


def test_render_item_renders_type_decorators_as_their_impl():
    from mitespotter_api.db import render_item
    from mitespotter_api.models import UInt64

    assert render_item("type", UInt64(), _autogen_context()) == "sa.Numeric(precision=20, scale=0)"


def test_render_item_defers_everything_else_to_alembic():
    from sqlalchemy import Integer

    from mitespotter_api.db import render_item

    assert render_item("type", Integer(), _autogen_context()) is False
    assert render_item("server_default", "now()", _autogen_context()) is False


async def test_sessions_read_timestamps_in_utc_whatever_the_server_zone(make_config, database_factory):
    """DEFAULT now() and every timestamptz come back as UTC instants, even if the
    database is configured for a zone with daylight saving."""
    from datetime import timedelta

    import psycopg
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from mitespotter_api.db import make_alchemy_config

    url = database_factory()
    name = make_url(url).database
    admin = make_url(url).set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"ALTER DATABASE \"{name}\" SET timezone = 'America/New_York'")

    engine = make_alchemy_config(make_config(url)).get_engine()
    try:
        async with engine.connect() as conn:
            zone, now, summer = (await conn.execute(text(
                "SELECT current_setting('TimeZone'), now(), '2026-07-01 12:00:00+02'::timestamptz"
            ))).one()
    finally:
        await engine.dispose()

    assert zone == "UTC"
    assert now.utcoffset() == timedelta(0)
    assert summer.utcoffset() == timedelta(0)
    assert summer.hour == 10
