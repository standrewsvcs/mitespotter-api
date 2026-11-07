"""
tests/test_models.py
Tests:
    src/mitespotter_api/models.py

Database behaviour of the schema is tested in tests/test_schema.py.

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql

from mitespotter_api import config, models


TABLES = {
    "users", "images", "categories", "mailing",
    "annotations", "image_events", "annotation_events", "reports",
    "user_sessions", "account_tokens",
}


def test_every_planned_table_has_a_model():
    assert set(models.Category.metadata.tables) == TABLES


def test_category_to_dict():
    category = models.Category(id=2, name="varroa destructor", supercategory="mite")
    assert category.to_dict() == {"id": 2, "name": "varroa destructor", "supercategory": "mite"}


# MARK: UInt64

@pytest.mark.parametrize("value", [0, 1, 2**63, models.UINT64_MAX])
def test_uint64_round_trips_without_precision_loss(value):
    uint64 = models.UInt64()
    dialect = postgresql.dialect()
    bound = uint64.process_bind_param(value, dialect)
    assert bound == Decimal(value)
    assert uint64.process_result_value(bound, dialect) == value


def test_uint64_passes_none_through():
    uint64 = models.UInt64()
    assert uint64.process_bind_param(None, postgresql.dialect()) is None
    assert uint64.process_result_value(None, postgresql.dialect()) is None


def test_uint64_max():
    assert models.UINT64_MAX == 18446744073709551615


# MARK: Constraints

def _checks(model) -> dict[str, str]:
    return {
        c.name: str(c.sqltext)
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }


def test_check_constraints_keep_their_planned_names():
    names = {name for model in (models.Image, models.Annotation, models.ImageEvent, models.AnnotationEvent, models.Report,
                                models.AccountToken)
             for name in _checks(model)}
    assert names == {
        "ck_image_split", "ck_image_phash", "ck_annotation_bbox",
        "ck_image_events_type", "ck_annotation_events_type", "ck_annotation_events_bbox",
        "ck_annotation_events_confidence",
        "ck_report_reason", "ck_report_other_notes", "ck_report_resolved",
        "ck_account_tokens_purpose",
    }


@pytest.mark.parametrize(("model", "name", "values"), [
    (models.Image, "ck_image_split", config.config.splits),
    (models.ImageEvent, "ck_image_events_type", config.config.image_event_types),
    (models.AnnotationEvent, "ck_annotation_events_type", config.config.annotation_event_types),
    (models.Report, "ck_report_reason", config.config.report_reasons),
    (models.AccountToken, "ck_account_tokens_purpose", config.config.account_token_purposes),
])
def test_value_checks_are_built_from_config(model, name, values):
    assert _checks(model)[name].endswith(f"IN ({', '.join(repr(v) for v in values)})")


def test_area_is_a_stored_generated_column():
    for model in (models.Annotation, models.AnnotationEvent):
        computed = model.__table__.c.area.computed
        assert str(computed.sqltext) == "bbox_width * bbox_height"
        assert computed.persisted is True


@pytest.mark.parametrize(("model", "column", "target", "ondelete"), [
    (models.Image, "uploader_id", "users.id", "RESTRICT"),
    (models.Mailing, "user_id", "users.id", "SET NULL"),
    (models.Annotation, "image_id", "images.id", "CASCADE"),
    (models.Annotation, "user_id", "users.id", "RESTRICT"),
    (models.Annotation, "category_id", "categories.id", "RESTRICT"),
    (models.ImageEvent, "image_id", "images.id", "CASCADE"),
    (models.ImageEvent, "user_id", "users.id", "RESTRICT"),
    (models.AnnotationEvent, "annotation_id", "annotations.id", "CASCADE"),
    (models.AnnotationEvent, "category_id", "categories.id", "RESTRICT"),
    (models.Report, "image_id", "images.id", "RESTRICT"),
    (models.Report, "resolver_id", "users.id", "RESTRICT"),
    (models.UserSession, "user_id", "users.id", "CASCADE"),
    (models.AccountToken, "user_id", "users.id", "CASCADE"),
])
def test_foreign_keys(model, column, target, ondelete):
    (fk,) = model.__table__.c[column].foreign_keys
    assert fk.target_fullname == target
    assert fk.ondelete == ondelete
