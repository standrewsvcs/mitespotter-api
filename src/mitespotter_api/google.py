"""
src/mitespotter_api/google.py
Google sign-in: OpenID Connect authorization code flow with PKCE, state and nonce

The flow's secrets travel in a short-lived cookie signed with the secret key.
The ID token is verified against Google's published keys (iss, aud, exp, nonce,
email_verified) before any identity is trusted.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode


import httpx
import msgspec
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet


from .config import Config


JWKS_CACHE_SECONDS = 3600


class GoogleError(Exception):
    """Any failure of the Google flow; never trust the identity"""


@dataclass(frozen=True)
class GoogleFlow:
    state: str
    nonce: str
    verifier: str
    expires_at: int


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Google:
    def __init__(
        self,
        config: Config,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.client = client
        self.now = now
        self._keys: KeySet | None = None
        self._keys_expire_at = 0.0

    # MARK: Flow cookie

    def _sign(self, payload: bytes) -> str:
        return _b64url(hmac.new(self.config.secret_key.encode(), payload, hashlib.sha256).digest())

    def flow_to_cookie(self, flow: GoogleFlow) -> str:
        payload = msgspec.json.encode(flow)
        return f"{_b64url(payload)}.{self._sign(payload)}"

    def flow_from_cookie(self, cookie: str | None) -> GoogleFlow:
        try:
            encoded, signature = (cookie or "").split(".")
            payload = _b64url_decode(encoded)
        except ValueError as e:
            raise GoogleError("Malformed flow cookie") from e
        if not hmac.compare_digest(signature, self._sign(payload)):
            raise GoogleError("Flow cookie signature mismatch")
        flow = msgspec.json.decode(payload, type=GoogleFlow)
        if flow.expires_at < self.now():
            raise GoogleError("Flow expired")
        return flow

    # MARK: Steps

    def start(self) -> tuple[str, GoogleFlow]:
        """The URL to send the browser to, and the flow to keep in the cookie"""
        if not self.config.google_enabled:
            raise GoogleError("Google sign-in is not configured")
        flow = GoogleFlow(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            verifier=secrets.token_urlsafe(64),
            expires_at=int(self.now() + self.config.google_flow_lifetime.total_seconds()),
        )
        challenge = _b64url(hashlib.sha256(flow.verifier.encode("ascii")).digest())
        query = urlencode({
            "client_id": self.config.google_client_id,
            "redirect_uri": self.config.google_redirect_uri,
            "response_type": "code",
            "scope": self.config.google_scopes,
            "state": flow.state,
            "nonce": flow.nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })
        return f"{self.config.google_authorization_endpoint}?{query}", flow

    async def finish(self, flow: GoogleFlow, state: str | None, code: str | None) -> GoogleIdentity:
        """Exchange the callback's code and verify the ID token"""
        if not state or not code or not hmac.compare_digest(state, flow.state):
            raise GoogleError("State mismatch or missing code")
        tokens = await self._post(self.config.google_token_endpoint, {
            "code": code,
            "client_id": self.config.google_client_id,
            "client_secret": self.config.google_client_secret,
            "redirect_uri": self.config.google_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": flow.verifier,
        })
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise GoogleError("No ID token")
        return self.verify_id_token(id_token, flow.nonce, await self._jwks())

    def verify_id_token(self, id_token: str, nonce: str, keys: KeySet) -> GoogleIdentity:
        try:
            token = jwt.decode(id_token, keys, algorithms=["RS256"])
            jwt.JWTClaimsRegistry(
                now=int(self.now()),
                leeway=60,
                iss={"essential": True, "values": [self.config.google_issuer, "accounts.google.com"]},
                aud={"essential": True, "value": self.config.google_client_id},
                exp={"essential": True},
                sub={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(token.claims)
        except (JoseError, ValueError) as e:
            raise GoogleError("Invalid ID token") from e
        claims = token.claims
        email = claims.get("email")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise GoogleError("Google has not verified this email")
        name = claims.get("name")
        return GoogleIdentity(sub=str(claims["sub"]), email=email, name=name if isinstance(name, str) else None)

    # MARK: HTTP

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            if self.client is not None:
                response = await self.client.request(method, url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise GoogleError(f"Request to {url} failed") from e
        if not isinstance(body, dict):
            raise GoogleError(f"Unexpected response from {url}")
        return body

    async def _post(self, url: str, form: dict[str, str | None]) -> dict:
        return await self._request("POST", url, data=form)

    async def _jwks(self) -> KeySet:
        if self._keys is None or self._keys_expire_at < self.now():
            self._keys = KeySet.import_key_set(await self._request("GET", self.config.google_jwks_uri))
            self._keys_expire_at = self.now() + JWKS_CACHE_SECONDS
        return self._keys
