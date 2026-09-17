"""
tests/test_app.py
Tests:
    src/mitespotter_api/app.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""


def test_create_app():
    from mitespotter_api.app import create_app
    app = create_app()
    assert app is not None
