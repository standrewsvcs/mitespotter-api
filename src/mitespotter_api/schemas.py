"""
src/mitespotter_api/schemas.py
API payloads (msgspec)

Lengths are bounded here; user-facing checks with style-sheet messages live in the routes.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from typing import Annotated, Literal


from msgspec import UNSET, Meta, Struct, UnsetType


from .config import config


Email = Annotated[str, Meta(max_length=254)]
Password = Annotated[str, Meta(max_length=config.password_max_length)]
Name = Annotated[str, Meta(max_length=config.name_max_length)]
Code = Annotated[str, Meta(max_length=16)]
Username = Annotated[str, Meta(max_length=100)]  # normalised and checked against config in the routes


class Register(Struct, forbid_unknown_fields=True):
    email: Email
    email_confirmation: Email
    password: Password
    name: Name | None = None  # required unless anonymous, for credit
    anonymous: bool = False
    username: Username | None = None  # generated when left out; may be shared


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


class Profile(Struct, forbid_unknown_fields=True):
    """Fields left out stay as they are"""
    name: Name | None | UnsetType = UNSET
    username: Username | UnsetType = UNSET
    anonymous: bool | UnsetType = UNSET


class Message(Struct):
    message: str


class PublicProfile(Struct):
    """What other people see"""
    id: int
    username: str
    name: str | None  # None when anonymous
    url: str


class Me(Struct):
    id: int
    profile_url: str
    username: str
    name: str | None
    email: str | None
    anonymous: bool
    registered: bool
    has_password: bool
    google_linked: bool
