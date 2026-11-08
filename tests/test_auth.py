"""
tests/test_auth.py
Tests:
    src/mitespotter_api/auth.py
    src/mitespotter_api/models.py (User password helpers, relationships)

Needs MITESPOTTER_TEST_DATABASE_URL (see tests/conftest.py).

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from litestar.exceptions import ClientException, NotAuthorizedException, PermissionDeniedException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload

from mitespotter_api import auth as auth_module
from mitespotter_api.auth import Auth, register, request_recovery
from mitespotter_api.config import config
from mitespotter_api.google import GoogleIdentity
from mitespotter_api.mail import Email
from mitespotter_api.messages import messages
from mitespotter_api.models import EmailCode, User, UserSession, hash_password


PASSWORD = "correct horse battery"


def _code_of(email: Email) -> str:
    return re.search(r"\b(\d{6})\b", email.text).group(1)


async def _account(db, email="hilda@example.org", password=PASSWORD, **kwargs) -> User:
    result = await register(db, email, password, kwargs.pop("name", "Hilda"), kwargs.pop("anonymous", False))
    return (await Auth.from_code(db, email, "register", _code_of(result))).user


async def _sessions(db, user: User) -> int:
    return await db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id))


# MARK: Construction

def test_auth_cannot_be_constructed_directly():
    with pytest.raises(TypeError, match="signing in"):
        Auth(object(), None, None, None)


# MARK: Registration

async def test_registration_emails_a_code_and_creates_nothing_yet(db):
    result = await register(db, "nolan@example.org", PASSWORD, "Nolan", True)

    assert isinstance(result, Email)
    assert result.to == "nolan@example.org"
    assert re.fullmatch(r"\d{6}", _code_of(result))
    assert await db.scalar(select(User).where(User.email == "nolan@example.org")) is None


async def test_entering_the_code_creates_a_verified_account(db):
    result = await register(db, "Nolan@Example.org", PASSWORD, "Nolan", True)
    auth = await Auth.from_code(db, "nolan@example.org", "register", _code_of(result))

    user = auth.user
    assert user.email == "Nolan@Example.org"
    assert (user.name, user.anonymous) == ("Nolan", True)
    assert user.email_verified_at is not None
    assert user.is_registered
    assert user.check_password(PASSWORD)
    assert re.fullmatch(r"[a-z]+ [a-z]+( \d+)?", user.username)
    assert auth.cookie_value and auth.user_session.token_hash != auth.cookie_value
    auth.require_registered()


async def test_usernames_are_numbered_when_taken(db, monkeypatch):
    monkeypatch.setattr(auth_module.usernames, "base", lambda user_id: "buzzy finder")
    first = await _account(db, "a@example.org")
    second = await _account(db, "b@example.org")
    assert (first.username, second.username) == ("buzzy finder", "buzzy finder 1")


async def test_same_password_signs_you_in(db):
    user = await _account(db)
    result = await register(db, "HILDA@example.org", PASSWORD, None, False)
    assert isinstance(result, Auth)
    assert result.user.id == user.id


async def test_different_password_emails_a_code_and_changes_nothing_yet(db):
    user = await _account(db)
    result = await register(db, "hilda@example.org", "a different password", "Someone", True)

    assert isinstance(result, Email)
    await db.refresh(user)
    assert user.check_password(PASSWORD)
    assert (user.name, user.anonymous) == ("Hilda", False)


async def test_entering_that_code_sets_the_new_password_and_ends_other_sessions(db):
    user = await _account(db)
    await Auth.login(db, "hilda@example.org", PASSWORD)
    result = await register(db, "hilda@example.org", "a different password", None, False)

    auth = await Auth.from_code(db, "hilda@example.org", "register", _code_of(result))

    assert auth.user.id == user.id
    assert auth.user.check_password("a different password")
    assert not auth.user.check_password(PASSWORD)
    assert await _sessions(db, user) == 1


async def test_a_google_account_gains_a_password_through_registration(db):
    auth = await Auth.from_google(db, GoogleIdentity(sub="g1", email="mia@example.org", name="Mia"))
    assert auth.user.hashed_password is None

    result = await register(db, "mia@example.org", PASSWORD, None, False)
    await Auth.from_code(db, "mia@example.org", "register", _code_of(result))
    assert (await Auth.login(db, "mia@example.org", PASSWORD)).user.id == auth.user.id


async def test_ai_models_cannot_take_a_password(db):
    user = await _account(db, "model@example.org")
    user.is_ai_model = True
    await db.flush()
    result = await register(db, "model@example.org", "another password", None, False)
    with pytest.raises(ClientException, match=messages.code_invalid):
        await Auth.from_code(db, "model@example.org", "register", _code_of(result))


# MARK: Codes

async def test_wrong_codes_count_and_run_out(db):
    result = await register(db, "lucas@example.org", PASSWORD, None, False)
    code = _code_of(result)
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    for _ in range(config.code_attempts):
        with pytest.raises(ClientException, match=messages.code_invalid):
            await Auth.from_code(db, "lucas@example.org", "register", wrong)
    with pytest.raises(ClientException, match=messages.code_invalid):
        await Auth.from_code(db, "lucas@example.org", "register", code)  # even the right code, now


async def test_codes_expire(db):
    result = await register(db, "lucas@example.org", PASSWORD, None, False)
    await db.execute(update(EmailCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    with pytest.raises(ClientException, match=messages.code_invalid):
        await Auth.from_code(db, "lucas@example.org", "register", _code_of(result))


async def test_codes_are_single_use(db):
    result = await register(db, "lucas@example.org", PASSWORD, None, False)
    await Auth.from_code(db, "lucas@example.org", "register", _code_of(result))
    with pytest.raises(ClientException, match=messages.code_invalid):
        await Auth.from_code(db, "lucas@example.org", "register", _code_of(result))


async def test_codes_are_bound_to_their_purpose(db):
    user = await _account(db)
    result = await request_recovery(db, user.email, "new password here")
    with pytest.raises(ClientException):
        await Auth.from_code(db, user.email, "register", _code_of(result))


async def test_within_a_minute_no_new_email_but_the_latest_details_apply(db):
    first = await register(db, "ping@example.org", PASSWORD, "Ping", False)
    again = await register(db, "ping@example.org", "the corrected password", "Ping Li", True)
    assert again is None  # no second email within the resend interval

    auth = await Auth.from_code(db, "ping@example.org", "register", _code_of(first))
    assert auth.user.check_password("the corrected password")
    assert (auth.user.name, auth.user.anonymous) == ("Ping Li", True)


async def test_a_new_code_replaces_the_old_one_after_a_minute(db):
    first = await register(db, "ping@example.org", PASSWORD, None, False)
    await db.execute(update(EmailCode).values(created_at=datetime.now(UTC) - timedelta(minutes=2)))
    second = await register(db, "ping@example.org", PASSWORD, None, False)

    assert isinstance(second, Email)
    with pytest.raises(ClientException):
        await Auth.from_code(db, "ping@example.org", "register", _code_of(first))
    await Auth.from_code(db, "ping@example.org", "register", _code_of(second))


async def test_an_expired_open_code_is_replaced_at_once(db):
    await register(db, "ping@example.org", PASSWORD, None, False)
    await db.execute(update(EmailCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert isinstance(await register(db, "ping@example.org", PASSWORD, None, False), Email)


async def test_codes_are_stored_only_as_hashes(db):
    result = await register(db, "ping@example.org", PASSWORD, None, False)
    row = await db.scalar(select(EmailCode).where(EmailCode.email == "ping@example.org"))
    assert _code_of(result) not in row.code_hash
    assert PASSWORD not in (row.password_hash or "")


# MARK: Recovery

async def test_recovery_for_an_unknown_address_sends_nothing(db):
    assert await request_recovery(db, "nobody@example.org", "new password here") is None
    assert await db.scalar(select(func.count()).select_from(EmailCode)) == 0


async def test_recovery_sets_the_password_and_ends_every_session(db):
    user = await _account(db)
    await Auth.login(db, user.email, PASSWORD)
    result = await request_recovery(db, user.email, "my new password")

    auth = await Auth.from_code(db, user.email, "recover", _code_of(result))

    assert auth.user.check_password("my new password")
    assert await _sessions(db, user) == 1  # only the new one


async def test_recovery_code_for_a_deleted_account_is_refused(db):
    user = await _account(db)
    result = await request_recovery(db, user.email, "my new password")
    await db.delete(user)
    await db.flush()
    with pytest.raises(ClientException):
        await Auth.from_code(db, "hilda@example.org", "recover", _code_of(result))


# MARK: Sign in

async def test_login(db):
    user = await _account(db)
    auth = await Auth.login(db, "HILDA@example.org", PASSWORD)
    assert auth.user.id == user.id


@pytest.mark.parametrize(("email", "password"), [
    ("hilda@example.org", "wrong password"),
    ("nobody@example.org", PASSWORD),
])
async def test_login_failures_say_the_same(db, email, password):
    await _account(db)
    with pytest.raises(NotAuthorizedException, match=messages.login_failed):
        await Auth.login(db, email, password)


async def test_ai_models_cannot_log_in(db):
    user = await _account(db)
    user.is_ai_model = True
    with pytest.raises(NotAuthorizedException):
        await Auth.login(db, user.email, PASSWORD)


async def test_outdated_hashes_are_upgraded(db):
    user = await _account(db)
    user.hashed_password = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    await db.flush()
    old = user.hashed_password

    await Auth.login(db, user.email, PASSWORD)

    assert user.hashed_password != old
    assert user.check_password(PASSWORD)


# MARK: Cookies

async def test_cookie_round_trip(db):
    auth = await Auth.login(db, (await _account(db)).email, PASSWORD)
    again = await Auth.from_cookie(db, auth.cookie_value)
    assert again.user.id == auth.user.id
    assert again.cookie_value is None  # no new session


@pytest.mark.parametrize("cookie", [None, "", "not-a-session"])
async def test_missing_or_unknown_cookies_are_refused(db, cookie):
    with pytest.raises(NotAuthorizedException, match=messages.sign_in_required):
        await Auth.from_cookie(db, cookie)


async def test_expired_sessions_are_refused(db):
    auth = await Auth.login(db, (await _account(db)).email, PASSWORD)
    auth.user_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.flush()
    with pytest.raises(NotAuthorizedException):
        await Auth.from_cookie(db, auth.cookie_value)


# MARK: Behaviour

async def test_logout_ends_only_this_session(db):
    user = await _account(db)
    first = await Auth.login(db, user.email, PASSWORD)
    second = await Auth.login(db, user.email, PASSWORD)
    await first.logout()
    with pytest.raises(NotAuthorizedException):
        await Auth.from_cookie(db, first.cookie_value)
    await Auth.from_cookie(db, second.cookie_value)


async def test_logout_everywhere(db):
    user = await _account(db)
    first = await Auth.login(db, user.email, PASSWORD)
    await Auth.login(db, user.email, PASSWORD)
    await first.logout_everywhere()
    assert await _sessions(db, user) == 0


async def test_change_password_keeps_only_this_session(db):
    user = await _account(db)
    auth = await Auth.login(db, user.email, PASSWORD)
    await Auth.login(db, user.email, PASSWORD)

    with pytest.raises(ClientException, match=messages.password_wrong):
        await auth.change_password("not it", "whatever new")
    await auth.change_password(PASSWORD, "a brand new password")

    assert user.check_password("a brand new password")
    assert await _sessions(db, user) == 1
    await Auth.from_cookie(db, auth.cookie_value)


async def test_unregistered_users_cannot_contribute(db):
    auth = await Auth.from_google(db, GoogleIdentity(sub="g2", email="john@example.org", name=None))
    auth.user.email_verified_at = None
    with pytest.raises(PermissionDeniedException, match=messages.verify_to_contribute):
        auth.require_registered()


async def test_sessions_relationship(db):
    user = await _account(db)
    await Auth.login(db, user.email, PASSWORD)
    loaded = await db.scalar(select(User).options(selectinload(User.sessions)).where(User.id == user.id))
    assert len(loaded.sessions) == 2
    with pytest.raises(Exception, match="lazy='raise'"):
        (await db.scalar(select(UserSession).limit(1).execution_options(populate_existing=True))).user  # noqa: B018


# MARK: Google

async def test_google_creates_a_verified_account_without_a_password(db):
    auth = await Auth.from_google(db, GoogleIdentity(sub="g3", email="laurie@example.org", name="Laurie"))
    user = auth.user
    assert (user.google_sub, user.name, user.hashed_password) == ("g3", "Laurie", None)
    assert user.is_registered


async def test_google_signs_in_a_known_account(db):
    first = await Auth.from_google(db, GoogleIdentity(sub="g4", email="laurie@example.org", name=None))
    again = await Auth.from_google(db, GoogleIdentity(sub="g4", email="changed@example.org", name=None))
    assert again.user.id == first.user.id


async def test_google_links_a_matching_email_account_which_keeps_its_password(db):
    user = await _account(db)
    auth = await Auth.from_google(db, GoogleIdentity(sub="g5", email="HILDA@example.org", name="H"))
    assert auth.user.id == user.id
    assert user.google_sub == "g5"
    assert user.check_password(PASSWORD)
    assert user.name == "Hilda"


async def test_google_refuses_ai_models(db):
    auth = await Auth.from_google(db, GoogleIdentity(sub="g6", email="bot@example.org", name=None))
    auth.user.is_ai_model = True
    with pytest.raises(NotAuthorizedException):
        await Auth.from_google(db, GoogleIdentity(sub="g6", email="bot@example.org", name=None))


async def test_link_google(db):
    user = await _account(db)
    auth = await Auth.login(db, user.email, PASSWORD)
    await auth.link_google(GoogleIdentity(sub="g7", email="other@example.org", name=None))
    assert user.google_sub == "g7"
    await auth.link_google(GoogleIdentity(sub="g7", email="other@example.org", name=None))  # again: fine


async def test_a_google_account_cannot_be_linked_twice(db):
    await Auth.from_google(db, GoogleIdentity(sub="g8", email="taken@example.org", name=None))
    auth = await Auth.login(db, (await _account(db)).email, PASSWORD)
    with pytest.raises(ClientException, match=messages.google_in_use):
        await auth.link_google(GoogleIdentity(sub="g8", email="taken@example.org", name=None))


# MARK: Password helpers

def test_hash_password_is_argon2_and_salted():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first.startswith("$argon2id$") and first != second


def test_check_password_without_a_hash():
    assert User(username="x").check_password(PASSWORD) is False


def test_corrupt_hashes_fail_closed():
    assert User(username="x", hashed_password="not-a-hash").check_password(PASSWORD) is False


# MARK: Username race

async def test_a_username_taken_meanwhile_is_retried_with_the_next_number(db, monkeypatch):
    real_generate = auth_module.usernames.generate
    monkeypatch.setattr(auth_module.usernames, "base", lambda user_id: "plucky scout")
    await _account(db, "first@example.org")  # takes "plucky scout"
    calls = []

    def generate_blind_to_the_first_lookup(user_id, taken):
        calls.append(set(taken))
        return real_generate(user_id, set() if len(calls) == 1 else taken)  # first try collides

    monkeypatch.setattr(auth_module.usernames, "generate", generate_blind_to_the_first_lookup)
    user = await _account(db, "second@example.org")

    assert user.username == "plucky scout 1"
    assert len(calls) == 2


async def test_other_integrity_errors_are_not_retried(db):
    await _account(db, "dup@example.org")
    with pytest.raises(IntegrityError):
        await auth_module._create_user(db, email="dup@example.org")


async def test_username_attempts_run_out(db, monkeypatch):
    monkeypatch.setattr(auth_module.usernames, "base", lambda user_id: "steady sentry")
    await _account(db, "taken@example.org")
    monkeypatch.setattr(auth_module.usernames, "generate", lambda user_id, taken: "steady sentry")
    with pytest.raises(RuntimeError, match="No free username"):
        await auth_module._create_user(db, email="next@example.org")


# MARK: Which email

async def test_each_path_sends_its_own_email(db):
    new = await register(db, "kate@example.org", PASSWORD, None, False)
    assert new.subject == messages.email_register_subject
    await Auth.from_code(db, "kate@example.org", "register", _code_of(new))

    existing = await register(db, "kate@example.org", "another password", None, False)
    assert existing.subject == messages.email_register_existing_subject
    assert "signs you in with the password you just chose" in existing.text

    recovery = await request_recovery(db, "kate@example.org", "yet another password")
    assert recovery.subject == messages.email_recover_subject
