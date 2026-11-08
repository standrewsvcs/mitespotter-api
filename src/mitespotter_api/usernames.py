"""
src/mitespotter_api/usernames.py
Usernames generated from user ids: "nimble longstepper", "buzzy finder 1"

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import random
from collections.abc import Collection


from .config import config


def base(user_id: int) -> str:
    """The adjective and noun for an id; the same id always gives the same pair"""
    rng = random.Random(user_id)
    return f"{rng.choice(config.username_adjectives)} {rng.choice(config.username_nouns)}"


def generate(user_id: int, taken: Collection[str]) -> str:
    """The base name, or the base name and the lowest free number; `taken` compares case-insensitively"""
    taken_lower = {name.lower() for name in taken}
    name = base(user_id)
    if name not in taken_lower:
        return name
    number = 1
    while f"{name} {number}" in taken_lower:
        number += 1
    return f"{name} {number}"
