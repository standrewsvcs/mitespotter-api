"""
tests/test_routes_dev.py
Tests:
    src/mitespotter_api/routes/dev.py
    src/mitespotter_api/dev.html

The page is checked against the API itself (OpenAPI paths, request structs) so it can't drift.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import get_args, get_type_hints

import msgspec
import pytest
from litestar.routes import HTTPRoute
from litestar.testing import TestClient

from mitespotter_api import schemas
from mitespotter_api.app import create_app


PROD_ENV = {"MITESPOTTER_ENV": "prod", "MITESPOTTER_SECRET_KEY": "s3cret", "MITESPOTTER_RESEND_API_KEY": "re_test"}


@pytest.fixture
def client(make_config):
    with TestClient(app=create_app(make_config())) as client:
        yield client


@pytest.fixture
def page(client) -> str:
    return client.get("/api/dev").text


class Forms(HTMLParser):
    """Each form's method, path and named fields; plus every href, src and action"""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict] = []
        self.links: list[str] = []
        self._form: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.links += [value for name, value in attrs if name in ("href", "src", "action") and value is not None]
        if tag == "form":
            self._form = {"method": attributes.get("data-method"), "path": attributes.get("data-path"), "fields": []}
            self.forms.append(self._form)
        elif tag in ("input", "select", "textarea") and self._form is not None and attributes.get("name"):
            self._form["fields"].append(attributes["name"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None


def parse(page: str) -> Forms:
    parser = Forms()
    parser.feed(page)
    return parser


def openapi_path(path: str) -> str:
    """'/api/users/{user_id:int}' -> '/api/users/{user_id}'"""
    return re.sub(r"\{(\w+):\w+\}", r"{\1}", path)


def data_struct(app, path: str, method: str):
    for route in app.routes:
        if isinstance(route, HTTPRoute) and openapi_path(route.path) == path:
            for handler in route.route_handlers:
                if method in handler.http_methods:
                    data = handler.parsed_fn_signature.parameters.get("data")
                    return True, data.annotation if data else None
    return False, None


# MARK: Serving

def test_page_is_served_as_html(client):
    response = client.get("/api/dev")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Mitespotter dev</title>" in response.text
    assert "{{" not in response.text


def test_page_is_404_when_switched_off(make_config):
    with TestClient(app=create_app(make_config(MITESPOTTER_DEV_PAGE="false"))) as client:
        assert client.get("/api/dev").status_code == 404


def test_page_is_404_in_prod_by_default(make_config):
    with TestClient(app=create_app(make_config(**PROD_ENV))) as client:
        assert client.get("/api/dev").status_code == 404


def test_page_can_be_switched_on_in_prod(make_config):
    with TestClient(app=create_app(make_config(**PROD_ENV, MITESPOTTER_DEV_PAGE="true"))) as client:
        assert client.get("/api/dev").status_code == 200


def test_page_is_not_in_the_openapi_schema(client):
    assert "/api/dev" not in client.get("/api/schema/openapi.json").json()["paths"]


def test_page_carries_the_csrf_names(make_config, page):
    config = make_config()
    assert f'data-csrf-cookie="{config.csrf_cookie_name}"' in page
    assert f'data-csrf-header="{config.csrf_header_name}"' in page


# MARK: Security headers

def test_security_headers(client):
    headers = client.get("/api/dev").headers
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp


def test_csp_nonce_matches_the_page_and_changes_per_request(client):
    nonces = []
    for _ in range(2):
        response = client.get("/api/dev")
        csp = response.headers["content-security-policy"]
        script = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
        style = re.search(r"style-src 'nonce-([^']+)'", csp).group(1)
        assert script == style
        in_page = re.findall(r'nonce="([^"]*)"', response.text)
        assert len(in_page) == response.text.count("<script") + response.text.count("<style") == 2
        assert set(in_page) == {script}
        nonces.append(script)
    assert nonces[0] != nonces[1]


# MARK: The page against the API

def test_page_has_no_external_urls(page):
    assert not re.search(r"(?i)\b(?:https?|wss?|ftp|data|javascript):", page)
    assert not re.search(r"(?i)<link|\bsrc=|@import|url\(", page)  # nothing loaded from anywhere
    assert not re.search(r"""["'`]//""", page)  # nothing protocol-relative
    links = parse(page).links
    assert links
    assert all(link.startswith("#") or link.startswith("/api/") for link in links)


def test_every_api_path_the_page_uses_exists(client, page):
    schema_paths = set(client.get("/api/schema/openapi.json").json()["paths"])
    used = set(re.findall(r"""["'](/api/[^"'\s]*)["']""", page))
    assert {"/api/health", "/api/auth/me", "/api/auth/google", "/api/users/{user_id}"} <= used
    assert used <= schema_paths


def test_forms_cover_every_account_endpoint(page):
    paths = {form["path"] for form in parse(page).forms}
    assert paths == {
        "/api/auth/me", "/api/auth/register", "/api/auth/code", "/api/auth/login", "/api/auth/logout",
        "/api/auth/logout-everywhere", "/api/auth/recover", "/api/auth/change-password", "/api/auth/profile",
        "/api/users/{user_id}",
    }


def test_form_methods_exist(client, page):
    for form in parse(page).forms:
        exists, _ = data_struct(client.app, form["path"], form["method"].upper())
        assert exists, f"{form['method']} {form['path']}"


def test_post_bodies_match_the_request_structs(client, page):
    for form in parse(page).forms:
        if form["method"] != "post":
            continue
        _, struct = data_struct(client.app, form["path"], "POST")
        fields = set(form["fields"])
        if struct is None:
            assert not fields, form["path"]
            continue
        assert getattr(schemas, struct.__name__) is struct
        info = msgspec.structs.fields(struct)
        names = {field.encode_name for field in info}
        required = {field.encode_name for field in info if field.required}
        assert fields <= names, f"{form['path']} sends unknown fields {fields - names}"
        assert required <= fields, f"{form['path']} misses required fields {required - fields}"


def test_get_forms_only_fill_path_parameters(page):
    for form in parse(page).forms:
        if form["method"] == "get":
            assert set(form["fields"]) == set(re.findall(r"\{(\w+)\}", form["path"]))


def test_purpose_choices_match_the_code_entry_struct(page):
    purposes = get_args(get_type_hints(schemas.CodeEntry)["purpose"])
    assert set(re.findall(r'<option value="(\w+)"', page)) == set(purposes)
