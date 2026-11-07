"""
src/mitespotter_api/models.py
SQLAlchemy models (advanced-alchemy bases); see planning.md "Live Data Format"

Created: 2026-11-07
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from advanced_alchemy.base import DefaultBase
from sqlalchemy import Identity, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class Category(DefaultBase):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    supercategory: Mapped[str] = mapped_column(Text)
