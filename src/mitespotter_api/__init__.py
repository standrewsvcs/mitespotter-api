"""
src/mitespotter_api/__init__.py
Entry point and server runner

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from .app import app, create_app
from .config import HOST, PORT, DEBUG, ENVIRONMENT


def main() -> None:
    import uvicorn
    uvicorn.run(
        "mitespotter_api.app:app",
        host=HOST,
        port=PORT,
        reload=ENVIRONMENT == "dev",
        log_level="debug" if DEBUG else "info",
    )
