"""
tests/test_usernames.py
Tests:
    src/mitespotter_api/usernames.py

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from mitespotter_api import usernames
from mitespotter_api.config import config


def test_base_is_an_adjective_and_a_noun():
    adjective, noun = usernames.base(1).split(" ")
    assert adjective in config.username_adjectives
    assert noun in config.username_nouns


def test_base_is_deterministic_per_id():
    assert usernames.base(42) == usernames.base(42)
    assert len({usernames.base(i) for i in range(1, 200)}) > 150


def test_free_base_is_used_as_is():
    assert usernames.generate(7, taken=[]) == usernames.base(7)


def test_lowest_free_number_is_appended():
    name = usernames.base(7)
    assert usernames.generate(7, taken=[name]) == f"{name} 1"
    assert usernames.generate(7, taken=[name, f"{name} 1", f"{name} 3"]) == f"{name} 2"


def test_taken_is_case_insensitive():
    name = usernames.base(7)
    assert usernames.generate(7, taken=[name.upper()]) == f"{name} 1"
