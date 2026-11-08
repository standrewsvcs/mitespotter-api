"""
tests/test_routes_users.py
Tests:
    src/mitespotter_api/routes/users.py

Needs MITESPOTTER_TEST_DATABASE_URL (see tests/conftest.py).

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from mitespotter_api.messages import messages

from test_routes_auth import app_database, make_client  # noqa: F401  (fixtures)


def test_public_profile_shows_name_and_link_but_never_email(make_client):  # noqa: F811
    client = make_client()
    client.register("public@example.org", name="Hilda Brandt", username="queen bee")
    client.enter_code("public@example.org")
    me = client.get("/api/auth/me").json()
    assert me["profile_url"] == f"http://127.0.0.1:6776/u/{me['id']}"

    profile = make_client().get(f"/api/users/{me['id']}").json()  # anyone, signed in or not
    assert profile == {"id": me["id"], "username": "queen bee", "name": "Hilda Brandt", "url": me["profile_url"]}
    assert "public@example.org" not in str(profile)


def test_anonymous_profiles_hide_the_name(make_client):  # noqa: F811
    client = make_client()
    client.register("hidden@example.org", name="Secret Name", anonymous=True)
    client.enter_code("hidden@example.org")
    me = client.get("/api/auth/me").json()
    profile = client.get(f"/api/users/{me['id']}").json()
    assert profile["name"] is None
    assert profile["username"] == me["username"]


def test_missing_profiles(make_client):  # noqa: F811
    response = make_client().get("/api/users/999999999")
    assert (response.status_code, response.json()["detail"]) == (404, messages.profile_not_found)
