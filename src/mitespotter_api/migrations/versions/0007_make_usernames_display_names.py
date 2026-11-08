"""Make usernames display names and require a name for credit

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08 01:01:19.175630

Usernames become display names: no longer unique, plain TEXT. Accounts need a
name for credit unless anonymous (ck_users_credit); existing nameless accounts
are made anonymous first.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.alter_column('users', 'username', type_=sa.Text(), postgresql_using='username::text')
    op.alter_column('email_codes', 'username', type_=sa.Text(), postgresql_using='username::text')
    op.execute("UPDATE users SET anonymous = true WHERE name IS NULL AND NOT anonymous")
    op.create_check_constraint(op.f('ck_users_credit'), 'users', 'anonymous OR name IS NOT NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_users_credit'), 'users', type_='check')
    op.alter_column('email_codes', 'username', type_=postgresql.CITEXT(), postgresql_using='username::citext')
    op.alter_column('users', 'username', type_=postgresql.CITEXT(), postgresql_using='username::citext')
    # Shared usernames must become unique again: number every repeat after the first
    op.execute("""
        UPDATE users SET username = users.username || ' ' || numbered.n
        FROM (
            SELECT id, row_number() OVER (PARTITION BY lower(username) ORDER BY id) - 1 AS n FROM users
        ) AS numbered
        WHERE users.id = numbered.id AND numbered.n > 0
    """)
    op.create_unique_constraint(op.f('uq_users_username'), 'users', ['username'])
