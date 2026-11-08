"""
src/mitespotter_api/routes/users.py
Public profiles: what other people see, and the link you can copy and share

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from litestar import Router, get
from litestar.di import NamedDependency
from litestar.exceptions import NotFoundException
from litestar.params import FromPath
from sqlalchemy.ext.asyncio import AsyncSession


from ..config import Config
from ..messages import messages
from ..models import User
from ..schemas import PublicProfile


def public_profile_of(user: User, config: Config) -> PublicProfile:
    """Never the email; the name only if you aren't anonymous"""
    return PublicProfile(
        id=user.id,
        username=user.username,
        name=None if user.anonymous else user.name,
        url=config.profile_url(user.id),
    )


@get("/{user_id:int}")
async def public_profile(
    user_id: FromPath[int], db_session: NamedDependency[AsyncSession], config: NamedDependency[Config],
) -> PublicProfile:
    user = await db_session.get(User, user_id)
    if user is None:
        raise NotFoundException(messages.profile_not_found)
    return public_profile_of(user, config)


router = Router(path="/users", route_handlers=[public_profile])
