"""
src/mitespotter_api/routes/auth.py
Authentication route handlers

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from litestar import Router, post, get, patch, delete
from litestar.di import Provide


from ..db import db_session


router = Router(
    path="/auth",
    route_handlers=[],
    dependencies={"session": Provide(db_session)},
)
