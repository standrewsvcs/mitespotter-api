"""Add chosen usernames to email codes

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08 00:54:38.599705

Stores the username chosen at registration with its code, applied when the
account is created. Generated usernames no longer derive from ids.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('email_codes', sa.Column('username', postgresql.CITEXT(), nullable=True))


def downgrade() -> None:
    op.drop_column('email_codes', 'username')
