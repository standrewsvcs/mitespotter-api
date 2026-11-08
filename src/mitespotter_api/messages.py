"""
src/mitespotter_api/messages.py
User-facing text, loaded from messages.toml; rules in STYLE.md

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType


MESSAGES_PATH = Path(__file__).resolve().parent / "messages.toml"


class Messages:
    """Read-only access to messages by attribute; an unknown key raises AttributeError"""

    __slots__ = ("_by_key",)

    def __init__(self, by_key: Mapping[str, str]) -> None:
        for key, value in by_key.items():
            if not isinstance(value, str):
                raise TypeError(f"Message {key!r} must be a string")
        object.__setattr__(self, "_by_key", MappingProxyType(dict(by_key)))

    @classmethod
    def load(cls, path: Path = MESSAGES_PATH) -> Messages:
        with path.open("rb") as f:
            return cls(tomllib.load(f))

    def __getattr__(self, key: str) -> str:
        try:
            return self._by_key[key]
        except KeyError:
            raise AttributeError(f"No message {key!r} in messages.toml") from None

    def __setattr__(self, key: str, value: object) -> None:
        raise AttributeError("Messages are read-only")

    def keys(self) -> tuple[str, ...]:
        return tuple(self._by_key)


messages = Messages.load()
