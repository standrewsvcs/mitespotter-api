"""
src/mitespotter_api/db.py
advanced-alchemy database and Alembic configuration

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from pathlib import Path
from typing import Any, Literal


from advanced_alchemy.extensions.litestar import (
    AlembicAsyncConfig,
    EngineConfig,
    SQLAlchemyAsyncConfig,
)


from alembic.autogenerate import render
from sqlalchemy.types import TypeDecorator


from .config import Settings


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
ALEMBIC_INI = MIGRATIONS_DIR / "alembic.ini"
VERSION_TABLE = "alembic_version"
SESSION_DEPENDENCY_KEY = "db_session"


def make_alchemy_config(settings: Settings) -> SQLAlchemyAsyncConfig:
    """Build the advanced-alchemy config: engine, autocommitting session dependency and Alembic.

    The schema is only ever changed through Alembic, so create_all is off.
    Building the config parses the URL and creates no connection.
    """
    return SQLAlchemyAsyncConfig(
        connection_string=settings.database_url,
        engine_config=EngineConfig(echo=settings.sql_echo, pool_pre_ping=True),
        before_send_handler="autocommit",
        session_dependency_key=SESSION_DEPENDENCY_KEY,
        create_all=False,
        alembic_config=AlembicAsyncConfig(
            script_location=str(MIGRATIONS_DIR),
            script_config=str(ALEMBIC_INI),
            version_table_name=VERSION_TABLE,
            render_as_batch=False,  # batch mode is for SQLite; Postgres alters in place
        ),
    )


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | Literal[False]:
    """Alembic autogenerate hook (see migrations/env.py).

    Renders custom TypeDecorators such as models.UInt64 as their underlying
    type, so revisions only depend on `sa`. False means Alembic's default rendering.
    """
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return render._repr_type(obj.impl, autogen_context)  # noqa: SLF001
    return False
