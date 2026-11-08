"""
tests/test_routes_auth.py
End to end:
    src/mitespotter_api/routes/auth.py
    src/mitespotter_api/app.py (CSRF, rate limiting)

Needs MITESPOTTER_TEST_DATABASE_URL (see tests/conftest.py).

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from litestar.testing import TestClient

from mitespotter_api.app import create_app
from mitespotter_api.google import Google, GoogleError, GoogleIdentity
from mitespotter_api.messages import messages
from mitespotter_api.routes.auth import client_ip


PASSWORD = "correct horse battery"
GOOGLE_ENV = {"MITESPOTTER_GOOGLE_CLIENT_ID": "client-id", "MITESPOTTER_GOOGLE_CLIENT_SECRET": "client-secret"}


@pytest.fixture(scope="module")
def app_database(migrated_database_factory):
    return migrated_database_factory()


class Client:
    """A TestClient that carries the CSRF header and exposes the outbox"""

    def __init__(self, client: TestClient) -> None:
        self.http = client
        self.app = client.app
        client.get("/api/health")  # receives the CSRF cookie

    @property
    def outbox(self):
        return self.app.state.mailer.sent

    def post(self, path: str, json: dict | None = None, **kwargs):
        headers = {"x-csrftoken": self.http.cookies.get("mitespotter_csrf", ""), **kwargs.pop("headers", {})}
        return self.http.post(path, json=json or {}, headers=headers, **kwargs)

    def get(self, path: str, **kwargs):
        return self.http.get(path, **kwargs)

    def last_code(self) -> str:
        return re.search(r"\b(\d{6})\b", self.outbox[-1].text).group(1)

    def register(self, email: str, password: str = PASSWORD, **extra):
        return self.post("/api/auth/register", {"email": email, "email_confirmation": email, "password": password, **extra})

    def enter_code(self, email: str, purpose: str = "register", code: str | None = None):
        return self.post("/api/auth/code", {"email": email, "purpose": purpose, "code": code or self.last_code()})

    def account(self, email: str, password: str = PASSWORD):
        assert self.register(email, password).status_code == 202
        assert self.enter_code(email).status_code == 200


@pytest.fixture
def make_client(make_config, app_database):
    clients = []

    def _make(base_url: str = "http://testserver.local", **env) -> Client:
        http = TestClient(app=create_app(make_config(app_database, **env)), base_url=base_url)
        http.__enter__()
        clients.append(http)
        return Client(http)

    yield _make
    for http in clients:
        http.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def _session_cookie(response) -> str:
    (header,) = [h for h in response.headers.get_list("set-cookie") if h.startswith("mitespotter_session=")]
    return header


# MARK: Registration

def test_register_then_enter_the_code(client):
    response = client.register("nolan@example.org", name="Nolan", anonymous=True)
    assert response.status_code == 202
    assert response.json() == {"message": messages.code_sent_register}
    assert "mitespotter_session" not in response.headers.get("set-cookie", "")
    assert client.outbox[-1].to == "nolan@example.org"
    assert client.get("/api/auth/me").status_code == 401

    response = client.enter_code("nolan@example.org")
    assert response.status_code == 200
    assert response.json() == {"message": messages.signed_in}
    cookie = _session_cookie(response).lower()
    assert "httponly" in cookie and "path=/api" in cookie and "samesite=lax" in cookie and "secure" not in cookie

    me = client.get("/api/auth/me").json()
    assert me["email"] == "nolan@example.org"
    assert (me["name"], me["anonymous"], me["registered"], me["has_password"], me["google_linked"]) == (
        "Nolan", True, True, True, False,
    )


def test_a_new_address_and_an_existing_one_look_the_same(make_client):
    owner = make_client()
    owner.account("hilda@example.org")

    stranger = make_client()
    existing = stranger.register("hilda@example.org", "a different password")
    new = stranger.register("someone.new@example.org", "a different password")

    assert (existing.status_code, existing.json()) == (new.status_code, new.json())
    assert existing.headers.get("set-cookie") == new.headers.get("set-cookie")


def test_registering_with_your_password_signs_you_in(make_client):
    make_client().account("laurie@example.org")
    response = make_client().register("laurie@example.org")
    assert response.status_code == 200
    assert response.json() == {"message": messages.signed_in}
    assert _session_cookie(response)


@pytest.mark.parametrize(("body", "message"), [
    ({"email": "a@example.org", "email_confirmation": "b@example.org", "password": PASSWORD}, messages.emails_differ),
    ({"email": "not-an-email", "email_confirmation": "not-an-email", "password": PASSWORD}, messages.email_invalid),
    ({"email": "a@example.org", "email_confirmation": "A@example.org ", "password": "short"}, messages.password_too_short),
])
def test_registration_checks(client, body, message):
    response = client.post("/api/auth/register", body)
    assert response.status_code == 400
    assert response.json()["detail"] == message


def test_a_wrong_code_is_refused(client):
    client.register("lucas@example.org")
    response = client.enter_code("lucas@example.org", code="000000" if client.last_code() != "000000" else "111111")
    assert response.status_code == 400
    assert response.json()["detail"] == messages.code_invalid


def test_a_failed_email_still_answers(make_client):
    client = make_client()

    async def broken(email):
        raise RuntimeError("Resend is down")

    client.app.state.mailer = SimpleNamespace(send=broken)
    assert client.register("ping@example.org").status_code == 202


# MARK: Sign in and out

def test_login_logout(client):
    client.account("john@example.org")
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    wrong = client.post("/api/auth/login", {"email": "john@example.org", "password": "nope nope"})
    assert (wrong.status_code, wrong.json()["detail"]) == (401, messages.login_failed)

    response = client.post("/api/auth/login", {"email": "john@example.org", "password": PASSWORD})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    response = client.post("/api/auth/logout")
    assert response.json() == {"message": messages.signed_out}
    assert 'mitespotter_session=""' in _session_cookie(response) or "max-age=0" in _session_cookie(response).lower()
    assert client.get("/api/auth/me").json()["detail"] == messages.sign_in_required


def test_logout_everywhere(make_client):
    laptop, phone = make_client(), make_client()
    laptop.account("mia@example.org")
    phone.post("/api/auth/login", {"email": "mia@example.org", "password": PASSWORD})

    response = laptop.post("/api/auth/logout-everywhere")
    assert response.json() == {"message": messages.signed_out_everywhere}
    assert phone.get("/api/auth/me").status_code == 401


def test_change_password(client):
    client.account("michael@example.org")
    body = {"current_password": "wrong one", "new_password": "a brand new password"}
    assert client.post("/api/auth/change-password", body).json()["detail"] == messages.password_wrong
    body = {"current_password": PASSWORD, "new_password": "short"}
    assert client.post("/api/auth/change-password", body).json()["detail"] == messages.password_too_short
    body = {"current_password": PASSWORD, "new_password": "a brand new password"}
    assert client.post("/api/auth/change-password", body).json() == {"message": messages.password_changed}


# MARK: Recovery

def test_recovery_answers_the_same_for_known_and_unknown_addresses(make_client):
    make_client().account("andy@example.org")
    client = make_client()
    sent_before = len(client.outbox)

    known = client.post("/api/auth/recover", {"email": "andy@example.org", "password": "my new password"})
    unknown = client.post("/api/auth/recover", {"email": "nobody@example.org", "password": "my new password"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"message": messages.code_sent_recover}
    assert [e.to for e in client.outbox[sent_before:]] == ["andy@example.org"]

    assert client.enter_code("andy@example.org", "recover").status_code == 200
    login = make_client().post("/api/auth/login", {"email": "andy@example.org", "password": "my new password"})
    assert login.status_code == 200


def test_recovery_checks(client):
    response = client.post("/api/auth/recover", {"email": "andy@example.org", "password": "short"})
    assert response.json()["detail"] == messages.password_too_short


# MARK: Protection

def test_posts_need_the_csrf_header(client):
    response = client.http.post("/api/auth/login", json={"email": "x@example.org", "password": PASSWORD})
    assert response.status_code == 403


def test_auth_routes_are_rate_limited_per_client_ip(client):
    limit = client.app.state.config.auth_rate_limit[1]
    body = {"email": "x@example.org", "password": "whatever pass"}
    headers = {"cf-connecting-ip": "203.0.113.9"}
    statuses = [client.post("/api/auth/login", body, headers=headers).status_code for _ in range(limit + 1)]
    assert statuses[:limit] == [401] * limit
    assert statuses[-1] == 429
    assert client.post("/api/auth/login", body, headers={"cf-connecting-ip": "203.0.113.10"}).status_code == 401
    assert all(client.get("/api/health").status_code == 200 for _ in range(limit + 1))


def test_client_ip():
    request = SimpleNamespace(headers={"cf-connecting-ip": " 198.51.100.1 "}, client=SimpleNamespace(host="10.0.0.1"))
    assert client_ip(request) == "198.51.100.1"
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))
    assert client_ip(request) == "10.0.0.1"
    assert client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


def test_cookies_are_secure_over_https(make_client):
    client = make_client(base_url="https://testserver.local", MITESPOTTER_PUBLIC_URL="https://mitespotter.org")
    client.register("secure@example.org")
    assert "secure" in _session_cookie(client.enter_code("secure@example.org")).lower()


# MARK: Google

class StubGoogle(Google):
    """The real start and cookie; finish answers with a fixed identity (verification is tested in test_google)"""

    identity: GoogleIdentity | None = None

    async def finish(self, flow, state, code):
        if self.identity is None or state != flow.state:
            raise GoogleError("stub")
        return self.identity


def _google_client(make_client, identity: GoogleIdentity | None) -> tuple[Client, StubGoogle]:
    client = make_client(**GOOGLE_ENV)
    stub = StubGoogle(client.app.state.config)
    stub.identity = identity
    client.app.state.google = stub
    return client, stub


def _google_round_trip(client: Client):
    start = client.get("/api/auth/google", follow_redirects=False)
    assert start.status_code in (302, 307)
    state = dict(p.split("=", 1) for p in urlparse(start.headers["location"]).query.split("&"))["state"]
    return client.get(f"/api/auth/google/callback?state={state}&code=c", follow_redirects=False)


def test_google_unavailable_without_credentials(client):
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.status_code == 503
    assert response.json()["detail"] == messages.google_unavailable


def test_google_start_redirects_with_a_flow_cookie(make_client):
    client, _ = _google_client(make_client, None)
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    flow_cookie = [h for h in response.headers.get_list("set-cookie") if h.startswith("mitespotter_google=")]
    assert flow_cookie and "path=/api/auth/google" in flow_cookie[0].lower()


def test_google_signs_you_in(make_client):
    client, _ = _google_client(make_client, GoogleIdentity(sub="r1", email="ping.google@example.org", name="Ping"))
    response = _google_round_trip(client)
    assert response.headers["location"] == "http://127.0.0.1:6776/"
    assert _session_cookie(response)
    me = client.get("/api/auth/me").json()
    assert (me["google_linked"], me["has_password"], me["registered"]) == (True, False, True)


def test_google_failure_redirects_with_a_message(make_client):
    client, _ = _google_client(make_client, None)
    response = _google_round_trip(client)
    assert response.headers["location"].endswith("/auth?message=google_failed")
    no_cookie = client.get("/api/auth/google/callback?state=x&code=c", follow_redirects=False)
    assert no_cookie.headers["location"].endswith("/auth?message=google_failed")


def test_google_links_when_signed_in(make_client):
    client, _ = _google_client(make_client, GoogleIdentity(sub="r2", email="different@example.org", name=None))
    client.account("linker@example.org")
    response = _google_round_trip(client)
    assert response.headers["location"].endswith("/account?message=google_linked")
    assert client.get("/api/auth/me").json()["google_linked"] is True


def test_google_in_use_by_another_account(make_client):
    other, _ = _google_client(make_client, GoogleIdentity(sub="r3", email="owner3@example.org", name=None))
    _google_round_trip(other)

    client, _ = _google_client(make_client, GoogleIdentity(sub="r3", email="owner3@example.org", name=None))
    client.account("second3@example.org")
    assert _google_round_trip(client).headers["location"].endswith("/account?message=google_in_use")


def test_google_refuses_ai_models(make_client, app_database):
    import psycopg
    from sqlalchemy.engine import make_url

    client, _ = _google_client(make_client, GoogleIdentity(sub="r4", email="bot4@example.org", name=None))
    _google_round_trip(client)
    dsn = make_url(app_database).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as conn:
        conn.execute("UPDATE users SET is_ai_model = true WHERE google_sub = 'r4'")

    fresh, _ = _google_client(make_client, GoogleIdentity(sub="r4", email="bot4@example.org", name=None))
    assert _google_round_trip(fresh).headers["location"].endswith("/auth?message=google_failed")
