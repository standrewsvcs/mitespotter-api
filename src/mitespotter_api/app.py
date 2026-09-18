"""
src/mitespotter_api/app.py
Litestar app factory

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from litestar import Litestar
from litestar.di import Provide
from sqlalchemy.ext.asyncio import AsyncSession


from .config import DEBUG
from .db import db_lifespan, db_session
from .routes import health, auth


def create_app(debug=DEBUG) -> Litestar:
    return Litestar(
        lifespan=[db_lifespan],
        route_handlers=[
            health.router,
            auth.router
        ],
        dependencies={"session": (db_session)},
        debug=debug,
    )


app = create_app()
