"""
src/mitespotter_api/jobs/__main__.py
Command line for scheduled jobs: `uv run python -m mitespotter_api.jobs cleanup`

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import argparse
import asyncio
import sys


from sqlalchemy.ext.asyncio import AsyncSession


from ..config import Config, config as default_config
from ..db import make_alchemy_config
from .cleanup import purge_expired


async def cleanup(config: Config) -> str:
    engine = make_alchemy_config(config).get_engine()
    try:
        async with engine.begin() as conn:
            async with AsyncSession(bind=conn) as db:
                result = await purge_expired(db)
    finally:
        await engine.dispose()
    return f"Deleted {result.sessions} expired sessions and {result.codes} old email codes"


JOBS = {"cleanup": cleanup}


def main(argv: list[str] | None = None, config: Config = default_config) -> int:
    parser = argparse.ArgumentParser(prog="python -m mitespotter_api.jobs")
    parser.add_argument("job", choices=sorted(JOBS))
    args = parser.parse_args(argv)
    print(asyncio.run(JOBS[args.job](config)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
