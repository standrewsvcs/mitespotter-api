"""
tests/test_health.py
Tests:
    src/mitespotter_api/routes/health.py

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from litestar.testing import TestClient


def _get(settings, path: str):
    from mitespotter_api.app import create_app
    with TestClient(app=create_app(settings)) as client:
        return client.get(path)


def test_liveness_does_not_need_the_database(make_settings):
    # Nothing listens on port 1, so any database access would fail
    response = _get(make_settings("postgresql+psycopg://nobody@127.0.0.1:1/none"), "/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_check_reports_unavailable_database(make_settings):
    response = _get(make_settings("postgresql+psycopg://nobody@127.0.0.1:1/none"), "/api/health/db")
    assert response.status_code == 503
    assert "Database is not available" in response.text


def test_db_check_against_a_real_database(make_settings, database_url):
    response = _get(make_settings(database_url), "/api/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
