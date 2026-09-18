"""
tests/conftest.py
Autouse fixture with baseline for all tests

Created: 2026-09-18
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from pathlib import Path

import pytest


# The minimum environment config.py needs in order to import.
# Values the application has a sensible default for are deliberately absent.
BASELINE_ENV = {
    "MITESPOTTER_DATABASE_URL": "postgresql+psycopg://localhost/mitespotter_test",
}


@pytest.fixture(autouse=True)
def baseline_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Apply the baseline environment to every test.

    MITESPOTTER_DATA_DIR is pinned to a temporary directory so no test can
    write into the repository's data/ tree. monkeypatch restores the real
    environment afterwards.
    """
    monkeypatch.setenv("MITESPOTTER_DATA_DIR", str(tmp_path / "data"))
    for name, value in BASELINE_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def required_env() -> dict[str, str]:
    """A copy of BASELINE_ENV for tests that build their own environment."""
    return dict(BASELINE_ENV)
