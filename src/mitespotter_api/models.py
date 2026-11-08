"""
src/mitespotter_api/models.py
SQLAlchemy models (advanced-alchemy bases); see planning.md "Live Data Format"

Every change here needs an Alembic revision; tests/test_migrations.py fails
if the migrated schema and these models differ.

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from datetime import datetime
from decimal import Decimal
from functools import cache
from typing import Any


from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from advanced_alchemy.base import DefaultBase
from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Dialect,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import conv
from sqlalchemy.types import TypeDecorator


from .config import config


UINT64_MAX = 2**64 - 1


# MARK: Passwords

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@cache
def _dummy_hash() -> str:
    return _hasher.hash("mitespotter dummy password")


def check_password_hash(password_hash: str | None, password: str) -> bool:
    """Constant work whether or not there is a hash, so timing reveals nothing"""
    try:
        return _hasher.verify(password_hash or _dummy_hash(), password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


# MARK: Helpers

class UInt64(TypeDecorator[int]):
    """Unsigned 64-bit integer stored as NUMERIC(20); Postgres has no unsigned BIGINT"""
    impl = Numeric(20, 0)
    cache_ok = True

    def process_bind_param(self, value: int | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> int | None:
        return None if value is None else int(value)


# conv() keeps the planning.md constraint names exactly, instead of the metadata
# naming convention prefixing them a second time (ck_images_ck_image_split).

def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _id(type_: Any = BigInteger) -> Mapped[int]:
    return mapped_column(type_, Identity(), primary_key=True)


def _timestamptz(nullable: bool = False, now: bool = False, **kwargs: Any) -> Any:
    return mapped_column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if now else None,
        **kwargs,
    )


def _fk(target: str, ondelete: str, name: str, nullable: bool = False, type_: Any = BigInteger) -> Any:
    return mapped_column(type_, ForeignKey(target, ondelete=ondelete, name=name), nullable=nullable)


_BBOX_CHECK = "bbox_width > 0 AND bbox_height > 0"
_AREA = Computed("bbox_width * bbox_height", persisted=True)


# MARK: Base tables

class User(DefaultBase):
    __tablename__ = "users"

    id: Mapped[int] = _id()
    name: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str] = mapped_column(CITEXT, unique=True)  # auto-generated from id, distinguishes anonymous users
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    hashed_password: Mapped[str | None] = mapped_column(Text)
    google_sub: Mapped[str | None] = mapped_column(Text, unique=True)  # OpenID Connect subject
    email_verified_at: Mapped[datetime | None] = _timestamptz(nullable=True)
    created_at: Mapped[datetime] = _timestamptz(now=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, server_default=false())
    is_ai_model: Mapped[bool] = mapped_column(Boolean, server_default=false())

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True, lazy="raise",
    )

    @property
    def is_registered(self) -> bool:
        """A verified email and a way to sign in"""
        return self.email_verified_at is not None and (self.hashed_password is not None or self.google_sub is not None)

    def set_password(self, password: str) -> None:
        self.hashed_password = hash_password(password)

    def check_password(self, password: str) -> bool:
        """Check a password; upgrades an outdated hash in place. AI models never use passwords."""
        if self.is_ai_model or not check_password_hash(self.hashed_password, password):
            return False
        if _hasher.check_needs_rehash(self.hashed_password):
            self.set_password(password)
        return True


class Image(DefaultBase):
    __tablename__ = "images"
    __table_args__ = (
        CheckConstraint(_in("split", config.splits), name=conv("ck_image_split")),
        CheckConstraint(f"phash >= 0 AND phash <= {UINT64_MAX}", name=conv("ck_image_phash")),
        Index("idx_images_date_captured", "date_captured"),
    )

    id: Mapped[int] = _id()
    sha256: Mapped[str] = mapped_column(Text, unique=True)
    phash: Mapped[int] = mapped_column(UInt64)  # ImageHash pHash is uint64
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    date_captured: Mapped[datetime] = _timestamptz()
    uploader_id: Mapped[int] = _fk("users.id", "RESTRICT", "fk_image_uploader")
    split: Mapped[str] = mapped_column(Text)
    hive: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = _timestamptz(nullable=True)


class Category(DefaultBase):
    __tablename__ = "categories"

    id: Mapped[int] = _id(Integer)
    name: Mapped[str] = mapped_column(Text, unique=True)
    supercategory: Mapped[str] = mapped_column(Text)


class Mailing(DefaultBase):
    __tablename__ = "mailing"

    email: Mapped[str] = mapped_column(CITEXT, primary_key=True)
    user_id: Mapped[int | None] = _fk("users.id", "SET NULL", "fk_mailing_user", nullable=True)


# MARK: Dependent tables

class UserSession(DefaultBase):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("idx_user_sessions_user_id", "user_id"),)

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _fk("users.id", "CASCADE", "fk_session_user")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)  # sha256 of the cookie's session id
    created_at: Mapped[datetime] = _timestamptz(now=True)
    last_seen_at: Mapped[datetime] = _timestamptz(now=True)
    expires_at: Mapped[datetime] = _timestamptz()

    user: Mapped[User] = relationship(back_populates="sessions", lazy="raise")


class EmailCode(DefaultBase):
    """A code emailed to an address; entering it completes a registration or a recovery"""
    __tablename__ = "email_codes"
    __table_args__ = (
        CheckConstraint(_in("purpose", config.email_code_purposes), name=conv("ck_email_codes_purpose")),
        CheckConstraint("attempts >= 0", name=conv("ck_email_codes_attempts")),
        # One open code per address per purpose
        Index("uq_email_codes_open", "email", "purpose", unique=True, postgresql_where=text("used_at IS NULL")),
    )

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(CITEXT)
    purpose: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)  # HMAC of the emailed code
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    password_hash: Mapped[str | None] = mapped_column(Text)  # the password chosen at registration or recovery
    name: Mapped[str | None] = mapped_column(Text)  # registration details, applied when the code is entered
    anonymous: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _timestamptz(now=True)
    expires_at: Mapped[datetime] = _timestamptz()
    used_at: Mapped[datetime | None] = _timestamptz(nullable=True)


class Annotation(DefaultBase):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint(_BBOX_CHECK, name=conv("ck_annotation_bbox")),
        Index("idx_annotations_image_id", "image_id"),
    )

    id: Mapped[int] = _id()
    image_id: Mapped[int] = _fk("images.id", "CASCADE", "fk_annotation_image")
    user_id: Mapped[int] = _fk("users.id", "RESTRICT", "fk_annotation_user")
    category_id: Mapped[int] = _fk("categories.id", "RESTRICT", "fk_annotation_category", type_=Integer)
    bbox_x: Mapped[float] = mapped_column(REAL)
    bbox_y: Mapped[float] = mapped_column(REAL)
    bbox_width: Mapped[float] = mapped_column(REAL)
    bbox_height: Mapped[float] = mapped_column(REAL)
    area: Mapped[float] = mapped_column(REAL, _AREA)
    is_crowd: Mapped[bool] = mapped_column(Boolean, server_default=false())  # exported as COCO's `iscrowd`
    created_at: Mapped[datetime] = _timestamptz(now=True)
    updated_at: Mapped[datetime] = _timestamptz(now=True, onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = _timestamptz(nullable=True)
    deleted_at: Mapped[datetime | None] = _timestamptz(nullable=True)


class ImageEvent(DefaultBase):
    __tablename__ = "image_events"
    __table_args__ = (
        CheckConstraint(_in("type", config.image_event_types), name=conv("ck_image_events_type")),
        Index("idx_image_events_image_id_id", "image_id", "id"),
        Index("idx_image_events_user_id", "user_id", "id"),
    )

    id: Mapped[int] = _id()
    image_id: Mapped[int] = _fk("images.id", "CASCADE", "fk_event_image")
    user_id: Mapped[int] = _fk("users.id", "RESTRICT", "fk_event_user")
    type: Mapped[str] = mapped_column(Text)
    time: Mapped[datetime] = _timestamptz()


class AnnotationEvent(DefaultBase):
    __tablename__ = "annotation_events"
    __table_args__ = (
        CheckConstraint(_in("type", config.annotation_event_types), name=conv("ck_annotation_events_type")),
        CheckConstraint(_BBOX_CHECK, name=conv("ck_annotation_events_bbox")),
        # Only model annotations carry a confidence.
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=conv("ck_annotation_events_confidence"),
        ),
        Index("idx_annotation_events_annotation_id_id", "annotation_id", "id"),
        Index("idx_annotation_events_user_id", "user_id", "id"),
    )

    id: Mapped[int] = _id()
    annotation_id: Mapped[int] = _fk("annotations.id", "CASCADE", "fk_event_annotation")
    user_id: Mapped[int] = _fk("users.id", "RESTRICT", "fk_event_user")
    type: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = _fk("categories.id", "RESTRICT", "fk_event_category", type_=Integer)
    bbox_x: Mapped[float] = mapped_column(REAL)
    bbox_y: Mapped[float] = mapped_column(REAL)
    bbox_width: Mapped[float] = mapped_column(REAL)
    bbox_height: Mapped[float] = mapped_column(REAL)
    area: Mapped[float] = mapped_column(REAL, _AREA)
    confidence: Mapped[float | None] = mapped_column(REAL)
    time: Mapped[datetime] = _timestamptz()


class Report(DefaultBase):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(_in("reason", config.report_reasons), name=conv("ck_report_reason")),
        CheckConstraint("reason <> 'other' OR notes IS NOT NULL", name=conv("ck_report_other_notes")),
        CheckConstraint("(resolver_id IS NULL) = (resolved_at IS NULL)", name=conv("ck_report_resolved")),
        # One open report per user per image
        Index(
            "uq_reports_open", "reporter_id", "image_id",
            unique=True, postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("idx_reports_image_id", "image_id"),
        Index("idx_reports_open", "created_at", postgresql_where=text("resolved_at IS NULL")),
    )

    id: Mapped[int] = _id()
    image_id: Mapped[int] = _fk("images.id", "RESTRICT", "fk_report_image")
    reporter_id: Mapped[int] = _fk("users.id", "RESTRICT", "fk_report_reporter")
    reason: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamptz(now=True)
    resolver_id: Mapped[int | None] = _fk("users.id", "RESTRICT", "fk_report_resolver", nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = _timestamptz(nullable=True)
