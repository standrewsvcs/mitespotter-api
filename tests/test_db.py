"""
tests/test_db.py
Tests:
    src/mitespotter_api/db.py

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


def test_alchemy_config(make_settings):
    from mitespotter_api.db import SESSION_DEPENDENCY_KEY, make_alchemy_config

    config = make_alchemy_config(make_settings("postgresql+psycopg://u:p@db.example/mitespotter"))

    assert config.connection_string == "postgresql+psycopg://u:p@db.example/mitespotter"
    assert config.session_dependency_key == SESSION_DEPENDENCY_KEY == "db_session"
    assert config.create_all is False               # schema only changes through Alembic
    assert callable(config.before_send_handler)     # "autocommit" resolved to a handler
    assert config.engine_config.echo is False
    assert config.engine_config.pool_pre_ping is True


def test_sql_echo_follows_settings(make_settings):
    from mitespotter_api.db import make_alchemy_config
    config = make_alchemy_config(make_settings(MITESPOTTER_SQL_ECHO="true"))
    assert config.engine_config.echo is True


def test_alembic_config_points_into_the_package(make_settings):
    from mitespotter_api.db import ALEMBIC_INI, MIGRATIONS_DIR, VERSION_TABLE, make_alchemy_config

    alembic = make_alchemy_config(make_settings()).alembic_config

    assert alembic.script_location == str(MIGRATIONS_DIR)
    assert alembic.script_config == str(ALEMBIC_INI)
    assert alembic.version_table_name == VERSION_TABLE == "alembic_version"
    assert (MIGRATIONS_DIR / "env.py").is_file()
    assert ALEMBIC_INI.is_file()
    assert any((MIGRATIONS_DIR / "versions").glob("0001_*.py"))
