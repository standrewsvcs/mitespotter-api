"""
tests/test_app.py
Tests:
    src/mitespotter_api/app.py

Created: 2026-09-17
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import pytest
from litestar.testing import TestClient


@pytest.fixture
def client(make_config):
    from mitespotter_api.app import create_app
    with TestClient(app=create_app(make_config())) as client:
        yield client


def test_module_app_uses_default_config():
    from mitespotter_api import config
    from mitespotter_api.app import app
    assert app.debug is config.config.debug


def test_debug_follows_config(make_config):
    from mitespotter_api.app import create_app
    assert create_app(make_config(MITESPOTTER_DEBUG="false")).debug is False
    assert create_app(make_config(MITESPOTTER_DEBUG="true")).debug is True


def test_every_route_is_under_api(make_config):
    from mitespotter_api.app import API_PREFIX, create_app
    paths = {route.path for route in create_app(make_config()).routes}
    assert paths
    assert all(path == API_PREFIX or path.startswith(f"{API_PREFIX}/") for path in paths)


def test_health_is_served_under_api(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/health", "/health/db", "/schema/openapi.json"])
def test_unprefixed_paths_are_gone(client, path):
    assert client.get(path).status_code == 404


def test_openapi_schema_is_served_under_api(client):
    response = client.get("/api/schema/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Mitespotter API"
    assert "/api/health" in schema["paths"]
