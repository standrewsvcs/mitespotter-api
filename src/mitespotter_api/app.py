"""
src/mitespotter_api/app.py
Litestar app factory

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin
from litestar import Litestar, Router
from litestar.openapi import OpenAPIConfig


from . import config
from .config import Settings
from .db import make_alchemy_config
from .routes import auth, health


API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> Litestar:
    settings = settings or config.settings
    api = Router(path=API_PREFIX, route_handlers=[health.router, auth.router])
    return Litestar(
        route_handlers=[api],
        plugins=[SQLAlchemyPlugin(config=make_alchemy_config(settings))],
        openapi_config=OpenAPIConfig(
            title="Mitespotter API",
            version="0.1.0",
            path=f"{API_PREFIX}/schema",
        ),
        debug=settings.debug,
    )


app = create_app()
