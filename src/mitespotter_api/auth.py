"""
src/mitespotter_api/auth.py
Auth: holding one means being signed in

An Auth is only created by a successful sign-in: a session cookie, a password,
an emailed code or Google. It carries the user and the behaviour of a signed-in
user. The unauthenticated steps (registering, asking for a recovery code) are
module functions; they either sign in, returning an Auth, or return the email
to send. See planning.md "Accounts & Authentication".

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import hashlib
import hmac
import secrets
from datetime import UTC, datetime


from litestar.exceptions import ClientException, NotAuthorizedException, PermissionDeniedException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload


from .config import config
from .google import GoogleIdentity
from .mail import Email, code_email
from .messages import messages
from .models import EmailCode, User, UserSession, check_password_hash, hash_password
from . import usernames


_KEY = object()


# MARK: Helpers

def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code_hash(email: str, purpose: str, code: str) -> str:
    message = f"{purpose}:{email.strip().lower()}:{code}".encode()
    return hmac.new(config.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(10 ** config.code_digits):0{config.code_digits}d}"


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email.strip()))


def _violates(error: IntegrityError, constraint: str) -> bool:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None) == constraint


async def username_taken(db: AsyncSession, username: str, by_other_than: User | None = None) -> bool:
    statement = select(User.id).where(User.username == username)
    if by_other_than is not None:
        statement = statement.where(User.id != by_other_than.id)
    return await db.scalar(statement) is not None


async def _create_user(db: AsyncSession, username: str | None = None, **fields) -> User:
    """The chosen username, else a generated one. A name taken meanwhile (another
    account, or the unique index losing a race) moves on to the next candidate."""
    for candidate in ([username] if username else []) + list(usernames.candidates()):
        if await username_taken(db, candidate):
            continue
        user = User(username=candidate, **fields)
        try:
            async with db.begin_nested():
                db.add(user)
                await db.flush()
        except IntegrityError as e:
            if not _violates(e, "uq_users_username"):
                raise
            continue
        return user
    raise RuntimeError("No free username")


async def _revoke_sessions(db: AsyncSession, user: User, keep: UserSession | None = None) -> None:
    statement = delete(UserSession).where(UserSession.user_id == user.id)
    if keep is not None:
        statement = statement.where(UserSession.id != keep.id)
    await db.execute(statement)


async def _issue_code(db: AsyncSession, email: str, purpose: str, kind: str, **details) -> Email | None:
    """Store a code with the details it applies; returns the email to send, or None within the resend interval"""
    email = email.strip()
    open_code = await db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.used_at.is_(None))
        .with_for_update()
    )
    now = _now()
    if open_code is not None and open_code.expires_at > now and open_code.created_at > now - config.code_resend_interval:
        for name, value in details.items():  # the latest details win; the emailed code stays valid
            setattr(open_code, name, value)
        await db.flush()
        return None
    if open_code is not None:
        open_code.used_at = now  # replaced
        await db.flush()
    code = _new_code()
    db.add(EmailCode(
        email=email,
        purpose=purpose,
        code_hash=_code_hash(email, purpose, code),
        expires_at=now + config.code_lifetime,
        **details,
    ))
    await db.flush()
    return code_email(email, code, config, kind)


# MARK: Unauthenticated steps

async def register(
    db: AsyncSession, email: str, password: str, name: str | None, anonymous: bool, username: str | None = None,
) -> Auth | Email | None:
    """Your password matches the account at this address: signed in. Otherwise a code is emailed (or was, within the
    last minute); entering it creates the account or sets the new password.

    A chosen username is checked first, whatever the address, so the answer never depends on whether it exists.
    It applies to new accounts only; if it is taken by the time the code is entered, a generated one is used.
    """
    if username is not None and await username_taken(db, username):
        raise ClientException(messages.username_taken)
    user = await _user_by_email(db, email)
    matched = user.check_password(password) if user is not None else check_password_hash(None, password)
    if user is not None and matched:
        return await Auth._start(db, user)
    return await _issue_code(
        db, email, "register", "register" if user is None else "register_existing",
        password_hash=hash_password(password), name=name, anonymous=anonymous, username=username,
    )


async def request_recovery(db: AsyncSession, email: str, password: str) -> Email | None:
    """A recovery code for an existing address, None otherwise; the caller answers the same either way"""
    password_hash = hash_password(password)  # same work whether or not the address exists
    if await _user_by_email(db, email) is None:
        return None
    return await _issue_code(db, email, "recover", "recover", password_hash=password_hash)


# MARK: Auth

class Auth:
    """A signed-in user. Constructed only by the sign-in classmethods."""

    __slots__ = ("_db", "cookie_value", "user", "user_session")

    def __init__(self, key: object, db: AsyncSession, user: User, user_session: UserSession,
                 cookie_value: str | None = None) -> None:
        if key is not _KEY:
            raise TypeError("An Auth is created by signing in")
        self._db = db
        self.user = user
        self.user_session = user_session
        self.cookie_value = cookie_value  # set only when a new session was started

    @classmethod
    async def _start(cls, db: AsyncSession, user: User) -> Auth:
        cookie_value = secrets.token_urlsafe(32)
        user_session = UserSession(
            user_id=user.id,
            token_hash=_sha256(cookie_value),
            expires_at=_now() + config.session_lifetime,
        )
        db.add(user_session)
        await db.flush()
        return cls(_KEY, db, user, user_session, cookie_value)

    # MARK: Sign-in paths

    @classmethod
    async def from_cookie(cls, db: AsyncSession, cookie_value: str | None) -> Auth:
        if not cookie_value:
            raise NotAuthorizedException(messages.sign_in_required)
        user_session = await db.scalar(
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(UserSession.token_hash == _sha256(cookie_value), UserSession.expires_at > _now())
        )
        if user_session is None:
            raise NotAuthorizedException(messages.sign_in_required)
        user_session.last_seen_at = _now()
        return cls(_KEY, db, user_session.user, user_session)

    @classmethod
    async def login(cls, db: AsyncSession, email: str, password: str) -> Auth:
        user = await _user_by_email(db, email)
        if user is None:
            check_password_hash(None, password)  # same work as a real check
            raise NotAuthorizedException(messages.login_failed)
        if not user.check_password(password):
            raise NotAuthorizedException(messages.login_failed)
        return await cls._start(db, user)

    @classmethod
    async def from_code(cls, db: AsyncSession, email: str, purpose: str, code: str) -> Auth:
        """Entering an emailed code: creates the account or sets its password, verifies the email, signs you in"""
        email = email.strip()
        row = await db.scalar(
            select(EmailCode)
            .where(EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.used_at.is_(None))
            .with_for_update()
        )
        now = _now()
        if row is None or row.expires_at <= now or row.attempts >= config.code_attempts:
            raise ClientException(messages.code_invalid)
        if not hmac.compare_digest(row.code_hash, _code_hash(email, purpose, code.strip())):
            row.attempts += 1
            await db.commit()  # the attempt must count even though the request fails
            raise ClientException(messages.code_invalid)
        row.used_at = now

        user = await _user_by_email(db, email)
        if user is None:
            if purpose != "register":
                raise ClientException(messages.code_invalid)
            user = await _create_user(
                db, username=row.username, email=row.email, name=row.name, anonymous=bool(row.anonymous),
                hashed_password=row.password_hash, email_verified_at=now,
            )
        elif user.is_ai_model:
            raise ClientException(messages.code_invalid)
        else:
            user.hashed_password = row.password_hash
            user.email_verified_at = user.email_verified_at or now
            await _revoke_sessions(db, user)
        return await cls._start(db, user)

    @classmethod
    async def from_google(cls, db: AsyncSession, identity: GoogleIdentity) -> Auth:
        """Known Google account: signed in. Matching email: linked. Otherwise: a new account."""
        user = await db.scalar(select(User).where(User.google_sub == identity.sub))
        if user is None:
            user = await _user_by_email(db, identity.email)
            if user is not None:
                user.google_sub = identity.sub
                user.email_verified_at = user.email_verified_at or _now()
            else:
                user = await _create_user(
                    db, email=identity.email, name=identity.name, google_sub=identity.sub, email_verified_at=_now(),
                )
        if user.is_ai_model:
            raise NotAuthorizedException(messages.login_failed)
        return await cls._start(db, user)

    # MARK: Behaviour

    def require_registered(self) -> None:
        if not self.user.is_registered:
            raise PermissionDeniedException(messages.verify_to_contribute)

    async def logout(self) -> None:
        await self._db.execute(delete(UserSession).where(UserSession.id == self.user_session.id))

    async def logout_everywhere(self) -> None:
        await _revoke_sessions(self._db, self.user)

    async def change_password(self, current: str, new: str) -> None:
        if not self.user.check_password(current):
            raise ClientException(messages.password_wrong)
        self.user.set_password(new)
        await _revoke_sessions(self._db, self.user, keep=self.user_session)

    async def change_username(self, username: str) -> None:
        if await username_taken(self._db, username, by_other_than=self.user):
            raise ClientException(messages.username_taken)
        try:
            async with self._db.begin_nested():
                self.user.username = username
                await self._db.flush()
        except IntegrityError as e:  # taken between the check and the update
            raise ClientException(messages.username_taken) from e

    async def link_google(self, identity: GoogleIdentity) -> None:
        owner = await self._db.scalar(select(User).where(User.google_sub == identity.sub))
        if owner is not None and owner.id != self.user.id:
            raise ClientException(messages.google_in_use)
        self.user.google_sub = identity.sub
