"""
src/mitespotter_api/usernames.py
Usernames: chosen at registration, or generated ("nimble longstepper")

Generated names are random word pairs, never derived from ids and never
numbered; if pairs keep colliding, a second adjective is added.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import random
import re
import secrets
from collections.abc import Iterator


from .config import config


_PATTERN = re.compile(config.username_pattern)
_SYSTEM_RANDOM = secrets.SystemRandom()


def normalise(name: str) -> str:
    """Trims and collapses runs of whitespace to one space"""
    return " ".join(name.split())


def is_valid(name: str) -> bool:
    return config.username_min_length <= len(name) <= config.username_max_length and bool(_PATTERN.match(name))


def candidates(rng: random.Random = _SYSTEM_RANDOM) -> Iterator[str]:
    """Random "adjective noun" pairs, then "adjective adjective noun" triples"""
    adjectives, nouns = config.username_adjectives, config.username_nouns
    for _ in range(config.username_generation_attempts):
        yield f"{rng.choice(adjectives)} {rng.choice(nouns)}"
    for _ in range(config.username_generation_attempts):
        first, second = rng.sample(adjectives, 2)
        yield f"{first} {second} {rng.choice(nouns)}"
