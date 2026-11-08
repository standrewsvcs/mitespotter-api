"""
src/mitespotter_api/mail.py
Outgoing email: Resend in production, an in-memory outbox in development and tests

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


import httpx


from .config import Config
from .messages import messages


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


@runtime_checkable
class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class OutboxMailer:
    """Keeps sent emails in memory and logs them; never use in production"""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)
        logger.info("Outbox email to %s: %s | %s", email.to, email.subject, email.text)


class ResendMailer:
    """Sends through Resend's HTTP API"""

    def __init__(self, api_key: str, sender: str, url: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.sender = sender
        self.url = url
        self.client = client

    async def send(self, email: Email) -> None:
        payload = {"from": self.sender, "to": [email.to], "subject": email.subject, "text": email.text}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.client is not None:
            response = await self.client.post(self.url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()


async def send_safely(mailer: Mailer, email: Email) -> None:
    """Background-task wrapper: a failed send is logged (without its content), never raised"""
    try:
        await mailer.send(email)
    except Exception:
        logger.exception("Sending an email failed")


def make_mailer(config: Config) -> Mailer:
    if config.mailer == "resend":
        return ResendMailer(config.resend_api_key or "", config.email_from, config.resend_api_url)
    return OutboxMailer()


CODE_EMAILS = ("register", "register_existing", "recover")


def code_email(to: str, code: str, config: Config, kind: str) -> Email:
    """kind: "register" (new address), "register_existing" (signs in with the new password) or "recover" """
    if kind not in CODE_EMAILS:
        raise ValueError(f"Unknown code email {kind!r}")
    minutes = int(config.code_lifetime.total_seconds() // 60)
    return Email(
        to=to,
        subject=getattr(messages, f"email_{kind}_subject"),
        text=getattr(messages, f"email_{kind}_body").format(code=code, minutes=minutes),
    )
