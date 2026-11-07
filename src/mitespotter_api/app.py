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


from . import config as config_module
from .config import Config
from .db import make_alchemy_config
from .routes import auth, health


def create_app(config: Config | None = None) -> Litestar:
    config = config or config_module.config
    api = Router(path=config.api_prefix, route_handlers=[health.router, auth.router])
    return Litestar(
        route_handlers=[api],
        plugins=[SQLAlchemyPlugin(config=make_alchemy_config(config))],
        openapi_config=OpenAPIConfig(
            title=config.api_title,
            version=config.api_version,
            path=f"{config.api_prefix}/schema",
        ),
        debug=config.debug,
    )


app = create_app()
