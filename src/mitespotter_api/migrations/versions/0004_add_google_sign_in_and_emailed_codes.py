"""Add Google sign-in and emailed codes

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 00:00:25.267723

Adds users.google_sub for Google sign-in, and replaces emailed link tokens with
emailed codes: account_tokens gets code_hash and attempts, one open code per user
per purpose. Open tokens are short-lived and deleted rather than migrated.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM account_tokens")
    op.drop_index('idx_account_tokens_open', table_name='account_tokens', postgresql_where=sa.text('used_at IS NULL'))
    op.drop_constraint('uq_account_tokens_token_hash', 'account_tokens', type_='unique')
    op.drop_column('account_tokens', 'token_hash')
    op.add_column('account_tokens', sa.Column('code_hash', sa.Text(), nullable=False))
    op.add_column('account_tokens', sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint(op.f('ck_account_tokens_attempts'), 'account_tokens', 'attempts >= 0')
    op.create_index('uq_account_tokens_open', 'account_tokens', ['user_id', 'purpose'], unique=True, postgresql_where=sa.text('used_at IS NULL'))
    op.add_column('users', sa.Column('google_sub', sa.Text(), nullable=True))
    op.create_unique_constraint(op.f('uq_users_google_sub'), 'users', ['google_sub'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_users_google_sub'), 'users', type_='unique')
    op.drop_column('users', 'google_sub')
    op.execute("DELETE FROM account_tokens")
    op.drop_index('uq_account_tokens_open', table_name='account_tokens', postgresql_where=sa.text('used_at IS NULL'))
    op.drop_constraint(op.f('ck_account_tokens_attempts'), 'account_tokens', type_='check')
    op.drop_column('account_tokens', 'attempts')
    op.drop_column('account_tokens', 'code_hash')
    op.add_column('account_tokens', sa.Column('token_hash', sa.Text(), nullable=False))
    op.create_unique_constraint(op.f('uq_account_tokens_token_hash'), 'account_tokens', ['token_hash'])
    op.create_index('idx_account_tokens_open', 'account_tokens', ['user_id', 'purpose'], unique=False, postgresql_where=sa.text('used_at IS NULL'))
