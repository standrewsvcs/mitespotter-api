"""
src/mitespotter_api/routes/health.py
Health check route handler

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from litestar import Router, get
from litestar.exceptions import ServiceUnavailableException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@get("/health", name="health_check", tags=["health"])
async def health_check() -> dict[str, str]:
    # Liveness check
    return {"status": "ok"}


@get("/health/db", name="health_check_db", tags=["health"])
async def health_check_db(session: AsyncSession) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        raise ServiceUnavailableException("Database is not available") from e
    return {"status": "ok", "database": "ok"}


router = Router(path="/", route_handlers=[health_check, health_check_db])
