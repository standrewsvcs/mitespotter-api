"""
src/mitespotter_api/__init__.py
Entry point and server runner

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""


def main() -> None:
    import uvicorn

    from .config import settings

    uvicorn.run(
        "mitespotter_api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "dev",
        log_level="debug" if settings.debug else "info",
    )
