"""
tests/test___init__.py
Tests:
    src/mitespotter_api/__init__.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
import sys
import types


def test_main_runs_uvicorn_with_settings(monkeypatch):
    calls = []
    fake_uvicorn = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    from mitespotter_api import main
    from mitespotter_api.config import settings
    main()

    (args, kwargs), = calls
    assert args == ("mitespotter_api.app:app",)
    assert kwargs["host"] == settings.host
    assert kwargs["port"] == settings.port
    assert kwargs["reload"] is (settings.environment == "dev")
    assert kwargs["log_level"] == ("debug" if settings.debug else "info")
