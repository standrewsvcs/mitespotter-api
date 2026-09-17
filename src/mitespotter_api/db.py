"""
src/mitespotter_api/routes/db.py
Database session and initialisation

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


from .config import DATABASE_URL, SQL_ECHO


# create_async_engine parses the URL and builds a pool without opening a connection;
# this module can be safely imported without touching the database
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=SQL_ECHO, pool_pre_ping=True)


# expire_on_commit=False is required for async sessions
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def db_session() -> AsyncIterator[AsyncSession]:
    """PLitestar dependency yielding an async database session"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialise the database extensions and create tables if they don't exist"""
    from . import models

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS CITEXT;"))
        await conn.run_sync(models.Base.metadata.create_all)


async def close_db() -> None:
    """Close the database engine"""
    await engine.dispose()


@asynccontextmanager
async def db_lifespan(app: Any) -> AsyncIterator[None]:
    """`Litestar(..., lifespan=[db_lifespan])` context manager to initialise and close the database"""
    await init_db()
    try:
        yield
    finally:
        await close_db()
