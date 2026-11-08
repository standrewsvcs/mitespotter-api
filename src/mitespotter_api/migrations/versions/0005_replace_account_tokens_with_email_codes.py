"""Replace account tokens with email codes

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 00:21:44.902046

Replaces account_tokens with email_codes, keyed by address: accounts are created
only when their registration code is entered, so codes cannot reference users.
Open codes are short-lived and are not migrated.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('email_codes',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('code_hash', sa.Text(), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('anonymous', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("purpose IN ('register', 'recover')", name=op.f('ck_email_codes_purpose')),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_email_codes_attempts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_codes'))
    )
    op.create_index('uq_email_codes_open', 'email_codes', ['email', 'purpose'], unique=True, postgresql_where=sa.text('used_at IS NULL'))
    op.drop_index(op.f('uq_account_tokens_open'), table_name='account_tokens', postgresql_where='(used_at IS NULL)')
    op.drop_table('account_tokens')


def downgrade() -> None:
    op.drop_index('uq_email_codes_open', table_name='email_codes', postgresql_where=sa.text('used_at IS NULL'))
    op.drop_table('email_codes')
    op.create_table('account_tokens',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code_hash', sa.Text(), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.CheckConstraint("purpose IN ('verify', 'recover')", name=op.f('ck_account_tokens_purpose')),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_account_tokens_attempts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_account_token_user', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account_tokens'))
    )
    op.create_index('uq_account_tokens_open', 'account_tokens', ['user_id', 'purpose'], unique=True, postgresql_where=sa.text('used_at IS NULL'))
