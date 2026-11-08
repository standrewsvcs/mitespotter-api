"""
src/mitespotter_api/jobs/cleanup.py
Delete expired sessions, and email codes that are used or expired

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from dataclasses import dataclass
from datetime import UTC, datetime


from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession


from ..config import config
from ..models import EmailCode, UserSession


@dataclass(frozen=True)
class CleanupResult:
    sessions: int
    codes: int


async def purge_expired(db: AsyncSession, now: datetime | None = None) -> CleanupResult:
    """Codes are kept for config.code_retention after use or expiry, then deleted"""
    now = now or datetime.now(UTC)
    sessions = await db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    cutoff = now - config.code_retention
    codes = await db.execute(delete(EmailCode).where(
        or_(EmailCode.used_at <= cutoff, EmailCode.expires_at <= cutoff)
    ))
    return CleanupResult(sessions=sessions.rowcount, codes=codes.rowcount)
