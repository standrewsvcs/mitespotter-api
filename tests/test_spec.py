"""
tests/test_spec.py
Spec-sync tests: constants in config.py must match planning.md

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mitespotter_api import config


PLANNING = (Path(__file__).resolve().parent.parent / "planning.md").read_text(encoding="utf-8")


def test_snapshot_disclaimer():
    assert config.config.snapshot_disclaimer in PLANNING


def test_coco_contributor_and_description():
    assert f'"contributor": "{config.config.coco_contributor}"' in PLANNING
    assert f'"description": "{config.config.coco_description}"' in PLANNING


def test_manifest_filename():
    assert f"`{config.config.manifest_filename}`" in PLANNING


@pytest.mark.parametrize("category", config.config.categories, ids=lambda c: c.name)
def test_categories_match_the_seed(category):
    assert f"({category.id}, '{category.name}', '{category.supercategory}')" in PLANNING


def test_report_reasons_match_the_check_constraint():
    block = re.search(r"CHECK \(reason IN \((.*?)\)\)", PLANNING, re.S).group(1)
    assert tuple(re.findall(r"'(\w+)'", block)) == config.config.report_reasons


def test_split_thresholds():
    assert f"X={config.config.split_train_below}, Y={config.config.split_val_below}" in PLANNING


def test_splits_match_the_check_constraint():
    assert f"CHECK (split IN {tuple(config.config.splits)!r})".replace('"', "'") in PLANNING.replace('"', "'")


def test_immutable_cache_control():
    assert f"`Cache-Control: {config.config.immutable_cache_control}`" in PLANNING
