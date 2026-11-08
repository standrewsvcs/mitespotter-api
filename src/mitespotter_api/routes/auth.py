"""
src/mitespotter_api/routes/auth.py
Authentication route handlers; see planning.md "Accounts & Authentication"

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import re
from typing import Annotated, Any


from litestar import Request, Response, Router, get, post
from litestar.background_tasks import BackgroundTask
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.params import FromQuery, QueryParameter
from litestar.exceptions import ClientException, NotAuthorizedException, ServiceUnavailableException
from litestar.response import Redirect
from litestar.status_codes import HTTP_200_OK, HTTP_202_ACCEPTED
from msgspec import UNSET
from sqlalchemy.ext.asyncio import AsyncSession


from ..auth import Auth, register as register_account, request_recovery
from ..config import Config, config as app_config
from ..google import Google, GoogleError
from ..mail import Email, Mailer, send_safely
from ..messages import messages
from .. import usernames
from ..schemas import ChangePassword, CodeEntry, Login, Me, Message, Profile, Recover, Register


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# MARK: Dependencies

def client_ip(request: Request[Any, Any, Any]) -> str:
    """Cloudflare's CF-Connecting-IP in production, else the peer address"""
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"


async def provide_auth(request: Request, db_session: NamedDependency[AsyncSession]) -> Auth:
    """Signed in, or 401: holding an Auth means being signed in"""
    config: Config = request.app.state.config
    return await Auth.from_cookie(db_session, request.cookies.get(config.session_cookie_name))


def provide_config(state: State) -> Config:
    return state.config


def provide_mailer(state: State) -> Mailer:
    return state.mailer


def provide_google(state: State) -> Google:
    return state.google


# MARK: Helpers

def _check_email(email: str) -> str:
    email = email.strip()
    if not EMAIL_PATTERN.match(email):
        raise ClientException(messages.email_invalid)
    return email


def _check_password(password: str, config: Config) -> str:
    if len(password) < config.password_min_length:
        raise ClientException(messages.password_too_short)
    return password


def _check_username(username: str) -> str:
    username = usernames.normalise(username)
    if not usernames.is_valid(username):
        raise ClientException(messages.username_invalid)
    return username


def _clean_name(name: str | None) -> str | None:
    return " ".join(name.split()) or None if name else None


def _set_session_cookie(response: Response[Any], auth: Auth, config: Config) -> None:
    if auth.cookie_value is not None:
        response.set_cookie(
            config.session_cookie_name,
            auth.cookie_value,
            max_age=int(config.session_lifetime.total_seconds()),
            path=config.api_prefix,
            secure=config.cookie_secure,
            httponly=True,
            samesite="lax",
        )


def _signed_in(auth: Auth, config: Config) -> Response[Message]:
    response = Response(Message(messages.signed_in), status_code=HTTP_200_OK)
    _set_session_cookie(response, auth, config)
    return response


def _signed_out(config: Config, message: str) -> Response[Message]:
    response = Response(Message(message), status_code=HTTP_200_OK)
    response.delete_cookie(config.session_cookie_name, path=config.api_prefix)
    return response


def _code_sent(message: str, mailer: Mailer, email: Email | None) -> Response[Message]:
    background = BackgroundTask(send_safely, mailer, email) if email is not None else None
    return Response(Message(message), status_code=HTTP_202_ACCEPTED, background=background)


# MARK: Handlers

@get("/me")
async def me(auth: NamedDependency[Auth]) -> Me:
    user = auth.user
    return Me(
        username=user.username,
        name=user.name,
        email=user.email,
        anonymous=user.anonymous,
        registered=user.is_registered,
        has_password=user.hashed_password is not None,
        google_linked=user.google_sub is not None,
    )


@post("/register", status_code=HTTP_200_OK)
async def register(
    data: Register, db_session: NamedDependency[AsyncSession], config: NamedDependency[Config], mailer: NamedDependency[Mailer],
) -> Response[Message]:
    email = _check_email(data.email)
    if email.lower() != data.email_confirmation.strip().lower():
        raise ClientException(messages.emails_differ)
    _check_password(data.password, config)
    username = _check_username(data.username) if data.username else None
    result = await register_account(db_session, email, data.password, _clean_name(data.name), data.anonymous, username)
    if isinstance(result, Auth):
        return _signed_in(result, config)
    return _code_sent(messages.code_sent_register, mailer, result)


@post("/login", status_code=HTTP_200_OK)
async def login(data: Login, db_session: NamedDependency[AsyncSession], config: NamedDependency[Config]) -> Response[Message]:
    return _signed_in(await Auth.login(db_session, data.email, data.password), config)


@post("/logout", status_code=HTTP_200_OK)
async def logout(auth: NamedDependency[Auth], config: NamedDependency[Config]) -> Response[Message]:
    await auth.logout()
    return _signed_out(config, messages.signed_out)


@post("/logout-everywhere", status_code=HTTP_200_OK)
async def logout_everywhere(auth: NamedDependency[Auth], config: NamedDependency[Config]) -> Response[Message]:
    await auth.logout_everywhere()
    return _signed_out(config, messages.signed_out_everywhere)


@post("/recover", status_code=HTTP_202_ACCEPTED)
async def recover(
    data: Recover, db_session: NamedDependency[AsyncSession], config: NamedDependency[Config], mailer: NamedDependency[Mailer],
) -> Response[Message]:
    email = _check_email(data.email)
    _check_password(data.password, config)
    return _code_sent(messages.code_sent_recover, mailer, await request_recovery(db_session, email, data.password))


@post("/code", status_code=HTTP_200_OK)
async def enter_code(data: CodeEntry, db_session: NamedDependency[AsyncSession], config: NamedDependency[Config]) -> Response[Message]:
    return _signed_in(await Auth.from_code(db_session, data.email, data.purpose, data.code), config)


@post("/change-password", status_code=HTTP_200_OK)
async def change_password(auth: NamedDependency[Auth], data: ChangePassword, config: NamedDependency[Config]) -> Message:
    _check_password(data.new_password, config)
    await auth.change_password(data.current_password, data.new_password)
    return Message(messages.password_changed)


@post("/profile", status_code=HTTP_200_OK)
async def update_profile(auth: NamedDependency[Auth], data: Profile) -> Message:
    changes: dict[str, Any] = {}
    if data.name is not UNSET:
        changes["name"] = _clean_name(data.name)
    if data.username is not UNSET:
        changes["username"] = _check_username(data.username)
    if data.anonymous is not UNSET:
        changes["anonymous"] = data.anonymous
    await auth.update_profile(**changes)
    return Message(messages.profile_saved)


@get("/google")
async def google_start(google: NamedDependency[Google], config: NamedDependency[Config]) -> Redirect:
    try:
        url, flow = google.start()
    except GoogleError as e:
        raise ServiceUnavailableException(messages.google_unavailable) from e
    response = Redirect(url)
    response.set_cookie(
        config.google_flow_cookie_name,
        google.flow_to_cookie(flow),
        max_age=int(config.google_flow_lifetime.total_seconds()),
        path=f"{config.api_prefix}/auth/google",
        secure=config.cookie_secure,
        httponly=True,
        samesite="lax",  # sent on Google's top-level redirect back
    )
    return response


async def _google_outcome(
    request: Request[Any, Any, Any], db: AsyncSession, google: Google, config: Config,
    state: str | None, code: str | None,
) -> Redirect:
    """Redirects carry a message key for the frontend to show from messages.toml"""
    try:
        flow = google.flow_from_cookie(request.cookies.get(config.google_flow_cookie_name))
        identity = await google.finish(flow, state, code)
    except GoogleError:
        return Redirect(f"{config.public_url}/auth?message=google_failed")
    try:
        current: Auth | None = await Auth.from_cookie(db, request.cookies.get(config.session_cookie_name))
    except NotAuthorizedException:
        current = None
    try:
        if current is not None:
            await current.link_google(identity)
            return Redirect(f"{config.public_url}/account?message=google_linked")
        auth = await Auth.from_google(db, identity)
    except NotAuthorizedException:  # a ClientException too, so first
        return Redirect(f"{config.public_url}/auth?message=google_failed")
    except ClientException:
        return Redirect(f"{config.public_url}/account?message=google_in_use")
    response = Redirect(f"{config.public_url}/")
    _set_session_cookie(response, auth, config)
    return response


@get("/google/callback")
async def google_callback(
    request: Request[Any, Any, Any],
    db_session: NamedDependency[AsyncSession],
    google: NamedDependency[Google],
    config: NamedDependency[Config],
    oauth_state: Annotated[str | None, QueryParameter(name="state")] = None,
    code: FromQuery[str | None] = None,
) -> Redirect:
    """Back from Google: signed in (or Google linked, if already signed in), then to the site"""
    response = await _google_outcome(request, db_session, google, config, oauth_state, code)
    response.delete_cookie(config.google_flow_cookie_name, path=f"{config.api_prefix}/auth/google")
    return response


router = Router(
    path="/auth",
    route_handlers=[
        me, register, login, logout, logout_everywhere, recover, enter_code, change_password, update_profile,
        google_start, google_callback,
    ],
    middleware=[RateLimitConfig(rate_limit=app_config.auth_rate_limit, identifier_for_request=client_ip).middleware],
    dependencies={
        "auth": Provide(provide_auth),
        "config": Provide(provide_config, sync_to_thread=False),
        "mailer": Provide(provide_mailer, sync_to_thread=False),
        "google": Provide(provide_google, sync_to_thread=False),
    },
)
