"""
src/mitespotter_api/db.py
advanced-alchemy database and Alembic configuration

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from typing import Any, Literal


from advanced_alchemy.extensions.litestar import (
    AlembicAsyncConfig,
    EngineConfig,
    SQLAlchemyAsyncConfig,
)
from alembic.autogenerate import render
from sqlalchemy.types import TypeDecorator


from .config import Config


def make_alchemy_config(config: Config) -> SQLAlchemyAsyncConfig:
    """Build the advanced-alchemy config: engine, autocommitting session dependency and Alembic.

    The schema is only ever changed through Alembic, so create_all is off.
    Building the config parses the URL and creates no connection.
    """
    return SQLAlchemyAsyncConfig(
        connection_string=config.database_url,
        engine_config=EngineConfig(
            echo=config.sql_echo,
            pool_pre_ping=True,
            # Sessions run in UTC, so every timestamptz (e.g. DEFAULT now()) is read back in UTC
            connect_args={"options": "-c timezone=UTC"},
        ),
        before_send_handler="autocommit",
        session_dependency_key=config.session_dependency_key,
        create_all=False,
        alembic_config=AlembicAsyncConfig(
            script_location=str(config.migrations_dir),
            script_config=str(config.alembic_ini),
            version_table_name=config.alembic_version_table,
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
