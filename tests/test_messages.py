"""
tests/test_messages.py
Tests:
    src/mitespotter_api/messages.py
    src/mitespotter_api/messages.toml (rules in STYLE.md)

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
import string
from pathlib import Path

import pytest

from mitespotter_api.config import config
from mitespotter_api.messages import Messages, messages


SRC = Path(__file__).resolve().parent.parent / "src" / "mitespotter_api"
TEMPLATES = {
    f"email_{kind}_{part}": ({"code", "minutes"} if part == "body" else set())
    for kind in ("register", "register_existing", "recover") for part in ("subject", "body")
}
NARRATION = ("will be", "if an account", "if your account", "an email has been", "token", "session", "authenticat", "!")


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_code_email_has_a_template():
    from mitespotter_api.mail import CODE_EMAILS
    assert {f"email_{kind}_{part}" for kind in CODE_EMAILS for part in ("subject", "body")} == set(TEMPLATES)
    assert set(TEMPLATES) <= set(messages.keys())


@pytest.mark.parametrize("kind", ["register", "register_existing", "recover"])
def test_code_emails_say_what_to_do_if_it_was_not_you(kind):
    assert "Ignore this email" in getattr(messages, f"email_{kind}_body")


@pytest.mark.parametrize("key", messages.keys())
def test_style(key):
    text = getattr(messages, key)
    assert text == text.strip() and text
    lowered = text.lower()
    assert not any(phrase in lowered for phrase in NARRATION), text
    if key.endswith("_subject"):
        assert not text.endswith(".")
    else:
        assert text.endswith(".")
    assert _placeholders(text) == TEMPLATES.get(key, set())


def test_every_message_used_in_code_exists():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r"\bmessages\.([a-z_]+)\b", path.read_text(encoding="utf-8")))
    used -= {"keys", "load", "py", "toml"}  # method names and file names in docstrings
    used |= set(TEMPLATES)  # looked up by kind in mail.code_email
    assert used, "no messages found in code"
    assert used <= set(messages.keys())


def test_redirect_message_keys_exist():
    routes = (SRC / "routes" / "auth.py").read_text(encoding="utf-8")
    keys = set(re.findall(r"message=([a-z_]+)", routes))
    assert keys == {"google_failed", "google_linked", "google_in_use"}
    assert keys <= set(messages.keys())


def test_password_message_matches_the_minimum():
    assert str(config.password_min_length) in messages.password_too_short


def test_unknown_key_raises():
    with pytest.raises(AttributeError, match="No message 'nope'"):
        messages.nope


def test_messages_are_read_only():
    with pytest.raises(AttributeError, match="read-only"):
        messages.signed_in = "Hi."


def test_non_string_messages_are_rejected(tmp_path):
    path = tmp_path / "m.toml"
    path.write_text("count = 3\n", encoding="utf-8")
    with pytest.raises(TypeError, match="'count' must be a string"):
        Messages.load(path)
