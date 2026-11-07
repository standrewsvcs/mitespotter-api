"""
tests/test_schema.py
Tests the migrated schema against Postgres:
    src/mitespotter_api/models.py
    src/mitespotter_api/migrations/versions/

Needs MITESPOTTER_TEST_DATABASE_URL (see tests/conftest.py).

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mitespotter_api.models import (
    UINT64_MAX,
    Annotation,
    AnnotationEvent,
    Image,
    ImageEvent,
    Mailing,
    Report,
    User,
)


PLANNING = Path(__file__).resolve().parent.parent / "planning.md"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


# MARK: Parity with planning.md

# Every column, constraint and index, without the names Postgres or the naming
# convention choose for primary keys, unique constraints and their indexes.
CATALOG_SQL = """
SELECT 'column', table_name, column_name, data_type, is_nullable,
       coalesce(column_default, ''), is_identity, coalesce(identity_generation, ''),
       coalesce(generation_expression, '')
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name <> 'alembic_version'
UNION ALL
SELECT 'constraint', conrelid::regclass::text, contype::text, pg_get_constraintdef(oid),
       CASE WHEN contype IN ('c', 'f') THEN conname ELSE '' END, '', '', '', ''
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace AND conrelid::regclass::text <> 'alembic_version'
UNION ALL
SELECT 'index', tablename, regexp_replace(indexdef, 'INDEX \\S+ ON', 'INDEX ON'),
       CASE WHEN indexname LIKE 'idx\\_%' OR indexname LIKE 'uq\\_reports\\_%' THEN indexname ELSE '' END,
       '', '', '', '', ''
FROM pg_indexes
WHERE schemaname = 'public' AND tablename <> 'alembic_version'
ORDER BY 1, 2, 3, 4
"""


def _catalog(url: str) -> list[tuple]:
    with psycopg.connect(_dsn(url)) as conn:
        return conn.execute(CATALOG_SQL).fetchall()


def test_migrated_schema_matches_the_planning_sql(database_factory, database_url):
    sql = re.search(r"```sql\n(.*?)```", PLANNING.read_text(encoding="utf-8"), re.S).group(1)
    spec_url = database_factory()
    with psycopg.connect(_dsn(spec_url), autocommit=True) as conn:
        conn.execute(sql)

    spec, migrated = _catalog(spec_url), _catalog(database_url)
    assert len(spec) > 100
    assert migrated == spec


# MARK: Behaviour

@pytest.fixture(scope="module")
def engine(database_url):
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """A session whose work is rolled back after the test"""
    with engine.connect() as conn:
        transaction = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


def _rejected(session: Session, *objects, constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint), session.begin_nested():
        session.add_all(objects)
        session.flush()


def _user(session: Session, username: str = "user_1", **kwargs) -> User:
    user = User(username=username, **kwargs)
    session.add(user)
    session.flush()
    return user


def _image(session: Session, uploader: User, sha256: str = "a" * 64, **kwargs) -> Image:
    fields = {"phash": 1, "width": 4032, "height": 3024, "date_captured": NOW, "split": "train", **kwargs}
    image = Image(sha256=sha256, uploader_id=uploader.id, **fields)
    session.add(image)
    session.flush()
    return image


def _annotation(session: Session, image: Image, user: User, **kwargs) -> Annotation:
    fields = {"category_id": 2, "bbox_x": 412.05, "bbox_y": 114.87, "bbox_width": 11.0, "bbox_height": 8.5, **kwargs}
    annotation = Annotation(image_id=image.id, user_id=user.id, **fields)
    session.add(annotation)
    session.flush()
    return annotation


def _annotation_event(annotation: Annotation, user: User, **kwargs) -> AnnotationEvent:
    fields = {
        "type": "create", "category_id": 2, "bbox_x": 1.0, "bbox_y": 1.0,
        "bbox_width": 2.0, "bbox_height": 3.0, "time": NOW, **kwargs,
    }
    return AnnotationEvent(annotation_id=annotation.id, user_id=user.id, **fields)


def _report(image: Image, reporter: User, **kwargs) -> Report:
    return Report(image_id=image.id, reporter_id=reporter.id, **{"reason": "duplicate", **kwargs})


# MARK: Users and mailing

def test_user_defaults(session):
    user = _user(session)
    session.refresh(user)
    assert user.anonymous is False
    assert user.is_ai_model is False
    assert user.created_at.tzinfo is not None


def test_username_and_email_are_case_insensitively_unique(session):
    _user(session, "Hilda", email="hilda@example.org")
    _rejected(session, User(username="hilda"), constraint="uq_users_username")
    _rejected(session, User(username="other", email="HILDA@example.org"), constraint="uq_users_email")


def test_username_lookup_is_case_insensitive(session):
    _user(session, "Nolan")
    assert session.scalar(select(User.username).where(User.username == "NOLAN")) == "Nolan"


def test_mailing_survives_user_deletion(session):
    user = _user(session)
    session.add(Mailing(email="Nolan@Example.org", user_id=user.id))
    session.flush()
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert session.execute(text("SELECT user_id FROM mailing")).scalar_one() is None
    _rejected(session, Mailing(email="nolan@example.org"), constraint="pk_mailing")


# MARK: Images

def test_phash_holds_the_full_uint64_range(session):
    uploader = _user(session)
    image = _image(session, uploader, phash=UINT64_MAX)
    session.expire_all()
    assert session.get(Image, image.id).phash == UINT64_MAX


@pytest.mark.parametrize("phash", [-1, UINT64_MAX + 1])
def test_phash_outside_uint64_is_rejected(session, phash):
    uploader = _user(session)
    _rejected(session, Image(sha256="b" * 64, phash=phash, width=1, height=1, date_captured=NOW,
                             uploader_id=uploader.id, split="train"), constraint="ck_image_phash")


def test_split_is_checked(session):
    uploader = _user(session)
    _rejected(session, Image(sha256="b" * 64, phash=1, width=1, height=1, date_captured=NOW,
                             uploader_id=uploader.id, split="holdout"), constraint="ck_image_split")


def test_duplicate_sha256_is_rejected(session):
    uploader = _user(session)
    _image(session, uploader)
    _rejected(session, Image(sha256="a" * 64, phash=2, width=1, height=1, date_captured=NOW,
                             uploader_id=uploader.id, split="val"), constraint="uq_images_sha256")


def test_uploader_cannot_be_deleted_while_they_have_images(session):
    uploader = _user(session)
    _image(session, uploader)
    with pytest.raises(IntegrityError, match="fk_image_uploader"), session.begin_nested():
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": uploader.id})


# MARK: Annotations

def test_area_is_generated(session):
    user = _user(session)
    annotation = _annotation(session, _image(session, user), user, bbox_width=11.0, bbox_height=8.5)
    session.refresh(annotation)
    assert annotation.area == pytest.approx(93.5)


def test_annotation_defaults_and_updated_at(session):
    user = _user(session)
    annotation = _annotation(session, _image(session, user), user)
    session.refresh(annotation)
    assert annotation.is_crowd is False
    assert annotation.updated_at == annotation.created_at

    # now() is fixed for the test's transaction, so start from an old timestamp
    old = datetime(2020, 1, 1, tzinfo=UTC)
    annotation.updated_at = old
    session.flush()
    annotation.bbox_x = 1.0
    session.flush()
    session.refresh(annotation)
    assert annotation.updated_at > old


@pytest.mark.parametrize(("width", "height"), [(0, 1), (1, 0), (-1, 1)])
def test_annotation_bbox_must_have_area(session, width, height):
    user = _user(session)
    image = _image(session, user)
    _rejected(session, Annotation(image_id=image.id, user_id=user.id, category_id=2, bbox_x=0, bbox_y=0,
                                  bbox_width=width, bbox_height=height), constraint="ck_annotation_bbox")


def test_annotation_category_must_exist(session):
    user = _user(session)
    image = _image(session, user)
    _rejected(session, Annotation(image_id=image.id, user_id=user.id, category_id=99, bbox_x=0, bbox_y=0,
                                  bbox_width=1, bbox_height=1), constraint="fk_annotation_category")


def test_deleting_an_image_cascades_to_annotations_and_events(session):
    user = _user(session)
    image = _image(session, user)
    annotation = _annotation(session, image, user)
    session.add_all([
        ImageEvent(image_id=image.id, user_id=user.id, type="upload", time=NOW),
        _annotation_event(annotation, user),
    ])
    session.flush()

    session.execute(text("DELETE FROM images WHERE id = :id"), {"id": image.id})
    counts = session.execute(text(
        "SELECT (SELECT count(*) FROM annotations), (SELECT count(*) FROM image_events),"
        " (SELECT count(*) FROM annotation_events)"
    )).one()
    assert tuple(counts) == (0, 0, 0)


# MARK: Events

def test_image_event_type_is_checked(session):
    user = _user(session)
    image = _image(session, user)
    session.add(ImageEvent(image_id=image.id, user_id=user.id, type="verify", time=NOW))
    session.flush()
    _rejected(session, ImageEvent(image_id=image.id, user_id=user.id, type="approve", time=NOW),
              constraint="ck_image_events_type")


@pytest.mark.parametrize(("fields", "constraint"), [
    ({"type": "accept"}, "ck_annotation_events_type"),
    ({"bbox_width": 0.0}, "ck_annotation_events_bbox"),
    ({"confidence": 1.5}, "ck_annotation_events_confidence"),
    ({"confidence": -0.1}, "ck_annotation_events_confidence"),
    ({"category_id": 99}, "fk_event_category"),
])
def test_annotation_event_checks(session, fields, constraint):
    user = _user(session)
    annotation = _annotation(session, _image(session, user), user)
    _rejected(session, _annotation_event(annotation, user, **fields), constraint=constraint)


@pytest.mark.parametrize("confidence", [None, 0.0, 0.5, 1.0])
def test_annotation_event_confidence_range(session, confidence):
    user = _user(session)
    annotation = _annotation(session, _image(session, user), user)
    event = _annotation_event(annotation, user, confidence=confidence)
    session.add(event)
    session.flush()
    session.refresh(event)
    assert event.area == pytest.approx(6.0)


# MARK: Reports

def test_other_needs_notes(session):
    user = _user(session)
    image = _image(session, user)
    _rejected(session, _report(image, user, reason="other"), constraint="ck_report_other_notes")
    session.add(_report(image, user, reason="other", notes="Blurry hive photo"))
    session.flush()


def test_unknown_reason_is_rejected(session):
    user = _user(session)
    _rejected(session, _report(_image(session, user), user, reason="spam"), constraint="ck_report_reason")


@pytest.mark.parametrize("fields", [{"resolved_at": NOW}, {"resolver": True}])
def test_resolver_and_resolved_at_go_together(session, fields):
    user = _user(session)
    image = _image(session, user)
    report = _report(image, user)
    if fields.pop("resolver", False):
        report.resolver_id = user.id
    for name, value in fields.items():
        setattr(report, name, value)
    _rejected(session, report, constraint="ck_report_resolved")


def test_one_open_report_per_user_per_image(session):
    reporter = _user(session)
    image = _image(session, reporter)
    first = _report(image, reporter)
    session.add(first)
    session.flush()
    _rejected(session, _report(image, reporter, reason="not_a_board"), constraint="uq_reports_open")

    first.resolver_id, first.resolved_at = reporter.id, NOW  # withdrawn
    session.flush()
    session.add(_report(image, reporter, reason="not_a_board"))
    session.flush()
    assert session.scalar(text("SELECT count(*) FROM reports")) == 2


def test_reported_images_cannot_be_hard_deleted(session):
    user = _user(session)
    image = _image(session, user)
    session.add(_report(image, user))
    session.flush()
    with pytest.raises(IntegrityError, match="fk_report_image"), session.begin_nested():
        session.execute(text("DELETE FROM images WHERE id = :id"), {"id": image.id})
