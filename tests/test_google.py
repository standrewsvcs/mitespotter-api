"""
tests/test_google.py
Tests:
    src/mitespotter_api/google.py

Google is replaced by a local RSA key and an httpx MockTransport.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from mitespotter_api.google import Google, GoogleError, GoogleFlow, GoogleIdentity


NOW = 1_800_000_000
GOOGLE_ENV = {
    "MITESPOTTER_GOOGLE_CLIENT_ID": "client-id",
    "MITESPOTTER_GOOGLE_CLIENT_SECRET": "client-secret",
    "MITESPOTTER_PUBLIC_URL": "https://mitespotter.org",
}
KEY = RSAKey.generate_key(2048, parameters={"kid": "k1"}, private=True)
JWKS = KeySet([KEY]).as_dict(private=False)


def id_token(nonce: str = "n", key: RSAKey = KEY, **overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com", "aud": "client-id", "sub": "1098",
        "email": "mia@example.org", "email_verified": True, "name": "Mia",
        "iat": NOW, "exp": NOW + 3600, "nonce": nonce,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode({"alg": "RS256", "kid": "k1"}, claims, key)


class FakeGoogle:
    """Answers the token and JWKS endpoints"""

    def __init__(self, token: str | None = None, token_status: int = 200) -> None:
        self.token = token
        self.token_status = token_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json=JWKS)
        return httpx.Response(self.token_status, json={"id_token": self.token} if self.token else {})


@pytest.fixture
def google_config(make_config):
    return make_config(**GOOGLE_ENV)


def _google(config, fake: FakeGoogle | None = None, now: float = NOW) -> Google:
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake or FakeGoogle()))
    return Google(config, client=client, now=lambda: now)


# MARK: Start

def test_start_builds_the_authorization_url(google_config):
    url, flow = _google(google_config).start()
    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert query["client_id"] == "client-id"
    assert query["redirect_uri"] == "https://mitespotter.org/api/auth/google/callback"
    assert query["response_type"] == "code"
    assert query["scope"] == "openid email profile"
    assert query["state"] == flow.state
    assert query["nonce"] == flow.nonce
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] and query["code_challenge"] != flow.verifier
    assert flow.expires_at == NOW + 600


def test_start_needs_credentials(make_config):
    with pytest.raises(GoogleError, match="not configured"):
        _google(make_config()).start()


# MARK: Flow cookie

def test_flow_cookie_round_trip(google_config):
    google = _google(google_config)
    _, flow = google.start()
    assert google.flow_from_cookie(google.flow_to_cookie(flow)) == flow


@pytest.mark.parametrize("cookie", [None, "", "abc", "a.b.c", "e30.bad"])
def test_malformed_flow_cookies_are_rejected(google_config, cookie):
    with pytest.raises(GoogleError):
        _google(google_config).flow_from_cookie(cookie)


def test_tampered_flow_cookie_is_rejected(google_config):
    google = _google(google_config)
    _, flow = google.start()
    encoded, signature = google.flow_to_cookie(flow).split(".")
    other = google.flow_to_cookie(GoogleFlow("evil", flow.nonce, flow.verifier, flow.expires_at)).split(".")[0]
    with pytest.raises(GoogleError, match="signature"):
        google.flow_from_cookie(f"{other}.{signature}")


def test_expired_flow_cookie_is_rejected(google_config):
    _, flow = _google(google_config).start()
    later = _google(google_config, now=NOW + 601)
    with pytest.raises(GoogleError, match="expired"):
        later.flow_from_cookie(later.flow_to_cookie(flow))


# MARK: Finish

async def test_finish_exchanges_the_code_and_verifies_the_token(google_config):
    flow = GoogleFlow("s", "n", "v", NOW + 600)
    fake = FakeGoogle(id_token())
    identity = await _google(google_config, fake).finish(flow, "s", "auth-code")

    assert identity == GoogleIdentity(sub="1098", email="mia@example.org", name="Mia")
    token_request = fake.requests[0]
    form = parse_qs(token_request.content.decode())
    assert form["code"] == ["auth-code"]
    assert form["code_verifier"] == ["v"]
    assert form["grant_type"] == ["authorization_code"]
    assert form["redirect_uri"] == ["https://mitespotter.org/api/auth/google/callback"]


async def test_jwks_are_cached(google_config):
    fake = FakeGoogle(id_token())
    google = _google(google_config, fake)
    flow = GoogleFlow("s", "n", "v", NOW + 600)
    await google.finish(flow, "s", "c")
    await google.finish(flow, "s", "c")
    assert sum(r.url.path.endswith("/certs") for r in fake.requests) == 1


@pytest.mark.parametrize(("state", "code"), [("other", "c"), (None, "c"), ("s", None)])
async def test_finish_rejects_bad_callbacks(google_config, state, code):
    with pytest.raises(GoogleError, match="State"):
        await _google(google_config, FakeGoogle(id_token())).finish(GoogleFlow("s", "n", "v", NOW + 600), state, code)


@pytest.mark.parametrize("fake", [FakeGoogle(token=None), FakeGoogle(id_token(), token_status=400)])
async def test_finish_rejects_failed_exchanges(google_config, fake):
    with pytest.raises(GoogleError):
        await _google(google_config, fake).finish(GoogleFlow("s", "n", "v", NOW + 600), "s", "c")


async def test_non_object_responses_are_rejected(google_config):
    google = _google(google_config, lambda request: httpx.Response(200, json=["not", "an", "object"]))
    with pytest.raises(GoogleError, match="Unexpected"):
        await google.finish(GoogleFlow("s", "n", "v", NOW + 600), "s", "c")


async def test_finish_without_a_client_opens_its_own(google_config, monkeypatch):
    async def fake_request(self, method, url, **kwargs):
        body = JWKS if url.endswith("/certs") else {"id_token": id_token()}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    identity = await Google(google_config, now=lambda: NOW).finish(GoogleFlow("s", "n", "v", NOW + 600), "s", "c")
    assert identity.sub == "1098"


# MARK: ID token

@pytest.mark.parametrize("claims", [
    {"aud": "someone-else"},
    {"iss": "https://evil.example"},
    {"exp": NOW - 3600},
    {"nonce": "other"},
    {"sub": None},
    {"email_verified": False},
    {"email": None},
])
def test_untrustworthy_id_tokens_are_rejected(google_config, claims):
    with pytest.raises(GoogleError):
        _google(google_config).verify_id_token(id_token(**claims), "n", KeySet.import_key_set(JWKS))


def test_tokens_signed_by_another_key_are_rejected(google_config):
    other = RSAKey.generate_key(2048, parameters={"kid": "k1"}, private=True)
    with pytest.raises(GoogleError):
        _google(google_config).verify_id_token(id_token(key=other), "n", KeySet.import_key_set(JWKS))


def test_short_issuer_and_missing_name_are_accepted(google_config):
    identity = _google(google_config).verify_id_token(
        id_token(iss="accounts.google.com", name=None), "n", KeySet.import_key_set(JWKS),
    )
    assert identity.name is None
