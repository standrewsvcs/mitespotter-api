"""
tests/test___init__.py
Tests:
    src/mitespotter_api/__init__.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
import sys
import types


def test_main_runs_uvicorn_with_config(monkeypatch):
    calls = []
    fake_uvicorn = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    from mitespotter_api import main
    from mitespotter_api.config import config
    main()

    (args, kwargs), = calls
    assert args == ("mitespotter_api.app:app",)
    assert kwargs["host"] == config.host
    assert kwargs["port"] == config.port
    assert kwargs["reload"] is (config.environment == "dev")
    assert kwargs["log_level"] == ("debug" if config.debug else "info")
