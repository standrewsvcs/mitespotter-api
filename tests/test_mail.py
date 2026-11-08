"""
tests/test_mail.py
Tests:
    src/mitespotter_api/mail.py

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import json

import httpx
import pytest

from mitespotter_api.mail import (
    Email,
    OutboxMailer,
    ResendMailer,
    code_email,
    make_mailer,
    send_safely,
)


EMAIL = Email(to="hilda@example.org", subject="Your Mitespotter code", text="Your Mitespotter code is 123456.")


def _resend(handler) -> ResendMailer:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ResendMailer("re_key", "Mitespotter <noreply@mitespotter.org>", "https://api.resend.com/emails", client)


async def test_resend_request_shape():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "e1"})

    await _resend(handler).send(EMAIL)

    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_key"
    assert json.loads(request.content) == {
        "from": "Mitespotter <noreply@mitespotter.org>",
        "to": ["hilda@example.org"],
        "subject": EMAIL.subject,
        "text": EMAIL.text,
    }


async def test_resend_errors_raise():
    with pytest.raises(httpx.HTTPStatusError):
        await _resend(lambda request: httpx.Response(422)).send(EMAIL)


async def test_resend_without_a_client_opens_its_own(monkeypatch):
    sent = []

    async def fake_post(self, url, json, headers):
        sent.append(url)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    await ResendMailer("k", "s", "https://api.resend.com/emails").send(EMAIL)
    assert sent == ["https://api.resend.com/emails"]


async def test_outbox_keeps_and_logs(caplog):
    outbox = OutboxMailer()
    with caplog.at_level("INFO"):
        await outbox.send(EMAIL)
    assert outbox.sent == [EMAIL]
    assert "123456" in caplog.text


async def test_send_safely_logs_failures_without_content(caplog):
    await send_safely(_resend(lambda request: httpx.Response(500)), EMAIL)
    assert "Sending an email failed" in caplog.text
    assert "123456" not in caplog.text


def test_make_mailer(make_config):
    assert isinstance(make_mailer(make_config()), OutboxMailer)
    mailer = make_mailer(make_config(MITESPOTTER_MAILER="resend", MITESPOTTER_RESEND_API_KEY="re_x"))
    assert isinstance(mailer, ResendMailer)
    assert mailer.api_key == "re_x"


@pytest.mark.parametrize(("kind", "subject"), [
    ("register", "Your Mitespotter verification code"),
    ("register_existing", "Your Mitespotter sign-in code"),
    ("recover", "Your Mitespotter recovery code"),
])
def test_code_emails(make_config, kind, subject):
    email = code_email("laurie@example.org", "004217", make_config(), kind)
    assert (email.to, email.subject) == ("laurie@example.org", subject)
    assert "004217" in email.text and "15 minutes" in email.text


def test_unknown_code_email(make_config):
    with pytest.raises(ValueError, match="Unknown code email"):
        code_email("a@example.org", "1", make_config(), "welcome")
