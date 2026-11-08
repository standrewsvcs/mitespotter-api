"""
src/mitespotter_api/usernames.py
Usernames: chosen, or two random words drawn from this codebase ("flush pyramid")

Usernames are display names, not identifiers: several people may share one.
The word pool is every identifier in the package's own source, split on
underscores, filtered to plain lowercase words, minus keywords and stopwords.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


import builtins
import io
import keyword
import random
import re
import secrets
import tokenize
from functools import cache
from pathlib import Path


from .config import config


_PACKAGE_DIR = Path(__file__).resolve().parent
_PATTERN = re.compile(config.username_pattern)
_SYSTEM_RANDOM = secrets.SystemRandom()


def normalise(name: str) -> str:
    """Trims and collapses runs of whitespace to one space"""
    return " ".join(name.split())


def is_valid(name: str) -> bool:
    return config.username_min_length <= len(name) <= config.username_max_length and bool(_PATTERN.match(name))


def words_in(source: str) -> set[str]:
    shortest, longest = config.username_word_lengths
    excluded = set(keyword.kwlist) | set(dir(builtins)) | set(config.username_stopwords)
    found: set[str] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.NAME:
            continue
        for part in token.string.split("_"):
            if part.isascii() and part.isalpha() and part.islower() and shortest <= len(part) <= longest:
                found.add(part)
    return found - excluded


@cache
def words() -> tuple[str, ...]:
    """Sorted word pool from every .py file in the package (migrations excluded)"""
    pool: set[str] = set()
    for path in sorted(_PACKAGE_DIR.rglob("*.py")):
        if "migrations" not in path.parts:
            pool |= words_in(path.read_text(encoding="utf-8"))
    return tuple(sorted(pool))


def generate(rng: random.Random = _SYSTEM_RANDOM) -> str:
    """Two different random words from the pool"""
    first, second = rng.sample(words(), 2)
    return f"{first} {second}"
