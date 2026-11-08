"""
tests/test_jobs.py
Tests:
    src/mitespotter_api/jobs/

Needs MITESPOTTER_TEST_DATABASE_URL (see tests/conftest.py).

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from mitespotter_api.jobs.__main__ import main
from mitespotter_api.jobs.cleanup import CleanupResult, purge_expired
from mitespotter_api.models import EmailCode, User, UserSession


NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


async def test_purge_expired(db):
    user = User(username="tidy keeper")
    db.add(user)
    await db.flush()
    hour, day = timedelta(hours=1), timedelta(days=1)
    db.add_all([
        UserSession(user_id=user.id, token_hash="expired", expires_at=NOW - hour),
        UserSession(user_id=user.id, token_hash="live", expires_at=NOW + hour),
        EmailCode(email="a@example.org", purpose="register", code_hash="c", expires_at=NOW + hour),  # open
        EmailCode(email="b@example.org", purpose="register", code_hash="c", expires_at=NOW - hour),  # expired, recent
        EmailCode(email="c@example.org", purpose="register", code_hash="c", expires_at=NOW - 2 * day),  # expired, old
        EmailCode(email="d@example.org", purpose="recover", code_hash="c", expires_at=NOW + hour,
                  used_at=NOW - 2 * day),  # used, old
    ])
    await db.flush()

    assert await purge_expired(db, now=NOW) == CleanupResult(sessions=1, codes=2)

    assert await db.scalar(select(UserSession.token_hash)) == "live"
    remaining = (await db.scalars(select(EmailCode.email).order_by(EmailCode.email))).all()
    assert remaining == ["a@example.org", "b@example.org"]


async def test_purge_expired_defaults_to_now(db):
    assert await purge_expired(db) == CleanupResult(sessions=0, codes=0)


def test_cleanup_command(make_config, migrated_database_factory, capsys):
    assert main(["cleanup"], config=make_config(migrated_database_factory())) == 0
    assert capsys.readouterr().out.strip() == "Deleted 0 expired sessions and 0 old email codes"


def test_unknown_job_is_rejected(capsys):
    with pytest.raises(SystemExit):
        main(["nightly"])
    assert "invalid choice" in capsys.readouterr().err
