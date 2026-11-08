"""
src/mitespotter_api/app.py
Litestar app factory

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin
from litestar import Litestar, Request, Response, Router
from litestar.config.csrf import CSRFConfig
from litestar.datastructures import State
from litestar.di import Provide
from litestar.exceptions import PermissionDeniedException
from litestar.openapi import OpenAPIConfig


from . import config as config_module
from .config import Config
from .db import make_alchemy_config
from .google import Google
from .mail import make_mailer
from .messages import messages
from .routes import auth, health, users
from .routes.auth import provide_config, provide_google, provide_mailer


CSRF_FAILURE = "CSRF token verification failed"  # Litestar's own wording


def permission_denied(request: Request, exc: PermissionDeniedException) -> Response:
    """Litestar's default 403 body, with its CSRF failure reworded for users (STYLE.md)"""
    detail = messages.request_expired if exc.detail == CSRF_FAILURE else exc.detail
    return Response({"status_code": exc.status_code, "detail": detail}, status_code=exc.status_code)


def create_app(config: Config | None = None) -> Litestar:
    config = config or config_module.config
    api = Router(
        path=config.api_prefix,
        route_handlers=[health.router, auth.router, users.router],
        dependencies={
            "config": Provide(provide_config, sync_to_thread=False),
            "mailer": Provide(provide_mailer, sync_to_thread=False),
            "google": Provide(provide_google, sync_to_thread=False),
        },
    )
    return Litestar(
        route_handlers=[api],
        plugins=[SQLAlchemyPlugin(config=make_alchemy_config(config))],
        state=State({"config": config, "mailer": make_mailer(config), "google": Google(config)}),
        csrf_config=CSRFConfig(
            secret=config.secret_key,
            cookie_name=config.csrf_cookie_name,
            header_name=config.csrf_header_name,
            cookie_secure=config.cookie_secure,
            cookie_samesite="lax",
        ),
        exception_handlers={PermissionDeniedException: permission_denied},
        openapi_config=OpenAPIConfig(
            title=config.api_title,
            version=config.api_version,
            path=f"{config.api_prefix}/schema",
        ),
        debug=config.debug,
    )


app = create_app()
