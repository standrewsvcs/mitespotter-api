"""
tests/test___init__.py
Tests:
    src/mitespotter_api/__init__.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""


def test_main():
    from mitespotter_api import main
    assert callable(main)
