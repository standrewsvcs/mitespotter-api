"""Create citext and categories

Revision ID: 0001
Revises: 
Create Date: 2026-11-07 20:17:07.881800

Creates the CITEXT extension and the categories table, seeded with the
categories in config.CATEGORIES (ids 1 and 2).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


CATEGORIES = (
    {"id": 1, "name": "debris", "supercategory": "non-mite"},
    {"id": 2, "name": "varroa destructor", "supercategory": "mite"},
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    categories = op.create_table('categories',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('supercategory', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('name', name=op.f('uq_categories_name'))
    )
    op.bulk_insert(categories, list(CATEGORIES))
    op.execute("SELECT setval(pg_get_serial_sequence('categories', 'id'), (SELECT MAX(id) FROM categories))")


def downgrade() -> None:
    op.drop_table('categories')
    op.execute("DROP EXTENSION IF EXISTS citext")
