"""
src/mitespotter_api/__init__.py
Entry point and server runner

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""


def main() -> None:
    import uvicorn

    from .config import config

    uvicorn.run(
        "mitespotter_api.app:app",
        host=config.host,
        port=config.port,
        reload=config.environment == "dev",
        log_level="debug" if config.debug else "info",
    )
