"""
src/mitespotter_api/schemas.py
API payloads (msgspec)

Lengths are bounded here; user-facing checks with style-sheet messages live in the routes.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from typing import Annotated, Literal


from msgspec import Meta, Struct


from .config import config


Email = Annotated[str, Meta(max_length=254)]
Password = Annotated[str, Meta(max_length=config.password_max_length)]
Name = Annotated[str, Meta(max_length=200)]
Code = Annotated[str, Meta(max_length=16)]
Username = Annotated[str, Meta(max_length=100)]  # normalised and checked against config in the routes


class Register(Struct, forbid_unknown_fields=True):
    email: Email
    email_confirmation: Email
    password: Password
    name: Name | None = None
    anonymous: bool = False
    username: Username | None = None  # generated when left out


class Login(Struct, forbid_unknown_fields=True):
    email: Email
    password: Password


class Recover(Struct, forbid_unknown_fields=True):
    email: Email
    password: Password  # the new password, applied when the code is entered


class CodeEntry(Struct, forbid_unknown_fields=True):
    email: Email
    purpose: Literal["register", "recover"]
    code: Code


class ChangePassword(Struct, forbid_unknown_fields=True):
    current_password: Password
    new_password: Password


class ChangeUsername(Struct, forbid_unknown_fields=True):
    username: Username


class Message(Struct):
    message: str


class Me(Struct):
    username: str
    name: str | None
    email: str | None
    anonymous: bool
    registered: bool
    has_password: bool
    google_linked: bool
