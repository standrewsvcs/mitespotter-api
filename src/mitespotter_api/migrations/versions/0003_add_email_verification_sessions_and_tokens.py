"""Add email verification, sessions and account tokens

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07 23:48:14.177265

Adds users.email_verified_at, user_sessions (revocable browser sessions) and
account_tokens (single-use email verification and recovery links); see
planning.md "Accounts & Authentication".
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('account_tokens',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("purpose IN ('verify', 'recover')", name=op.f('ck_account_tokens_purpose')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_account_token_user', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_account_tokens_token_hash'))
    )
    op.create_index('idx_account_tokens_open', 'account_tokens', ['user_id', 'purpose'], unique=False, postgresql_where=sa.text('used_at IS NULL'))
    op.create_table('user_sessions',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_session_user', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_sessions_token_hash'))
    )
    op.create_index('idx_user_sessions_user_id', 'user_sessions', ['user_id'], unique=False)
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'email_verified_at')
    op.drop_index('idx_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index('idx_account_tokens_open', table_name='account_tokens', postgresql_where=sa.text('used_at IS NULL'))
    op.drop_table('account_tokens')
