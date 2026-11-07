"""
tests/test_models.py
Tests:
    src/mitespotter_api/models.py

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


def test_category_table_matches_the_schema():
    from mitespotter_api.models import Category

    table = Category.__table__
    assert table.name == "categories"
    assert [c.name for c in table.columns] == ["id", "name", "supercategory"]
    assert table.c.id.primary_key and table.c.id.identity is not None
    assert table.c.name.unique and not table.c.name.nullable
    assert not table.c.supercategory.nullable


def test_category_to_dict():
    from mitespotter_api.models import Category
    category = Category(id=2, name="varroa destructor", supercategory="mite")
    assert category.to_dict() == {"id": 2, "name": "varroa destructor", "supercategory": "mite"}
