"""
tests/test_usernames.py
Tests:
    src/mitespotter_api/usernames.py

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import random
import pytest

from mitespotter_api import usernames
from mitespotter_api.config import config


def test_generated_usernames_are_an_adjective_and_a_codebase_word():
    pool = set(usernames.words())
    for seed in range(50):
        adjective, word = usernames.generate(random.Random(seed)).split(" ")
        assert adjective in config.username_adjectives and word in pool


def test_generated_usernames_are_random():
    assert len({usernames.generate() for _ in range(50)}) > 40


def test_the_pool_comes_from_the_codebase():
    pool = usernames.words()
    assert len(pool) > 200
    assert list(pool) == sorted(set(pool))
    assert {"pyramids", "annotation", "phash", "hive"} <= set(pool)
    shortest, longest = config.username_word_lengths
    assert all(w.isalpha() and w.islower() and shortest <= len(w) <= longest for w in pool)
    assert not set(pool) & set(config.username_stopwords)


def test_words_in_splits_identifiers_and_drops_keywords_builtins_and_stopwords():
    source = "def flush_pyramid(session_token):\n    return len(Image) or None  # comment_words\n"
    assert usernames.words_in(source) == {"flush", "pyramid"}


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
