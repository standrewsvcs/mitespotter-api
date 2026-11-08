"""
tests/test_usernames.py
Tests:
    src/mitespotter_api/usernames.py

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import random
import re

import pytest

from mitespotter_api import usernames
from mitespotter_api.config import config


def test_candidates_are_word_pairs_then_triples_without_numbers():
    names = list(usernames.candidates(random.Random(1)))
    n = config.username_generation_attempts
    assert len(names) == 2 * n
    for name in names[:n]:
        adjective, noun = name.split(" ")
        assert adjective in config.username_adjectives and noun in config.username_nouns
    for name in names[n:]:
        first, second, noun = name.split(" ")
        assert first != second
        assert {first, second} <= set(config.username_adjectives) and noun in config.username_nouns
    assert not any(re.search(r"\d", name) for name in names)


def test_candidates_are_random_not_derived_from_anything():
    assert len({next(usernames.candidates()) for _ in range(50)}) > 25


@pytest.mark.parametrize(("raw", "normalised"), [
    ("  Buzzy   Finder ", "Buzzy Finder"),
    ("hilda", "hilda"),
    ("a\\tb", "a\\tb"),
])
def test_normalise(raw, normalised):
    assert usernames.normalise(raw) == normalised


@pytest.mark.parametrize("name", ["hil", "Hilda the Beekeeper", "mite.spotter_99", "a-b", "x" * 30])
def test_valid_usernames(name):
    assert usernames.is_valid(name)


@pytest.mark.parametrize("name", ["", "ab", "x" * 31, " hilda", "hilda ", "-hilda", "hilda.", "hil@da", "émile", "a\\tb"])
def test_invalid_usernames(name):
    assert not usernames.is_valid(name)
