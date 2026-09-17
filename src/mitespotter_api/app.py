"""
src/mitespotter_api/app.py
Litestar app factory

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from litestar import Litestar
from litestar.di import Provide


from .db import db_session
from .routes import health, auth


def create_app(debug=False) -> Litestar:
    return Litestar(
        route_handlers=[
            health.router,
            auth.router
        ],
        dependencies={"session": Provide(db_session)},
        debug=debug,
    )


app = create_app()
