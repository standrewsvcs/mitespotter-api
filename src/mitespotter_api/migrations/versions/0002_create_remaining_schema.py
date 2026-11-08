"""Create remaining schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 22:45:41.023890

Creates users, images, mailing, annotations, image_events, annotation_events
and reports, with the constraints and indices in planning.md "Live Data Format".
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('username', postgresql.CITEXT(), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=True),
    sa.Column('hashed_password', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('anonymous', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_ai_model', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_table('images',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('sha256', sa.Text(), nullable=False),
    sa.Column('phash', sa.Numeric(precision=20, scale=0), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('date_captured', sa.DateTime(timezone=True), nullable=False),
    sa.Column('uploader_id', sa.BigInteger(), nullable=False),
    sa.Column('split', sa.Text(), nullable=False),
    sa.Column('hive', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("split IN ('train', 'val', 'test')", name=op.f('ck_image_split')),
    sa.CheckConstraint('phash >= 0 AND phash <= 18446744073709551615', name=op.f('ck_image_phash')),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], name='fk_image_uploader', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_images')),
    sa.UniqueConstraint('sha256', name=op.f('uq_images_sha256'))
    )
    op.create_index('idx_images_date_captured', 'images', ['date_captured'], unique=False)
    op.create_table('mailing',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_mailing_user', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('email', name=op.f('pk_mailing'))
    )
    op.create_table('annotations',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('image_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('bbox_x', sa.REAL(), nullable=False),
    sa.Column('bbox_y', sa.REAL(), nullable=False),
    sa.Column('bbox_width', sa.REAL(), nullable=False),
    sa.Column('bbox_height', sa.REAL(), nullable=False),
    sa.Column('area', sa.REAL(), sa.Computed('bbox_width * bbox_height', persisted=True), nullable=False),
    sa.Column('is_crowd', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('bbox_width > 0 AND bbox_height > 0', name=op.f('ck_annotation_bbox')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name='fk_annotation_category', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['image_id'], ['images.id'], name='fk_annotation_image', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_annotation_user', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_annotations'))
    )
    op.create_index('idx_annotations_image_id', 'annotations', ['image_id'], unique=False)
    op.create_table('image_events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('image_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('time', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("type IN ('upload', 'complete', 'verify', 'reject', 'delete')", name=op.f('ck_image_events_type')),
    sa.ForeignKeyConstraint(['image_id'], ['images.id'], name='fk_event_image', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_event_user', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_image_events'))
    )
    op.create_index('idx_image_events_image_id_id', 'image_events', ['image_id', 'id'], unique=False)
    op.create_index('idx_image_events_user_id', 'image_events', ['user_id', 'id'], unique=False)
    op.create_table('reports',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('image_id', sa.BigInteger(), nullable=False),
    sa.Column('reporter_id', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolver_id', sa.BigInteger(), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("reason <> 'other' OR notes IS NOT NULL", name=op.f('ck_report_other_notes')),
    sa.CheckConstraint("reason IN ('not_a_board', 'duplicate', 'unusable_quality', 'personal_or_inappropriate', 'incorrect_annotations', 'other')", name=op.f('ck_report_reason')),
    sa.CheckConstraint('(resolver_id IS NULL) = (resolved_at IS NULL)', name=op.f('ck_report_resolved')),
    sa.ForeignKeyConstraint(['image_id'], ['images.id'], name='fk_report_image', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], name='fk_report_reporter', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['resolver_id'], ['users.id'], name='fk_report_resolver', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reports'))
    )
    op.create_index('idx_reports_image_id', 'reports', ['image_id'], unique=False)
    op.create_index('idx_reports_open', 'reports', ['created_at'], unique=False, postgresql_where=sa.text('resolved_at IS NULL'))
    op.create_index('uq_reports_open', 'reports', ['reporter_id', 'image_id'], unique=True, postgresql_where=sa.text('resolved_at IS NULL'))
    op.create_table('annotation_events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('annotation_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('bbox_x', sa.REAL(), nullable=False),
    sa.Column('bbox_y', sa.REAL(), nullable=False),
    sa.Column('bbox_width', sa.REAL(), nullable=False),
    sa.Column('bbox_height', sa.REAL(), nullable=False),
    sa.Column('area', sa.REAL(), sa.Computed('bbox_width * bbox_height', persisted=True), nullable=False),
    sa.Column('confidence', sa.REAL(), nullable=True),
    sa.Column('time', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("type IN ('create', 'update', 'confirm', 'delete')", name=op.f('ck_annotation_events_type')),
    sa.CheckConstraint('bbox_width > 0 AND bbox_height > 0', name=op.f('ck_annotation_events_bbox')),
    sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name=op.f('ck_annotation_events_confidence')),
    sa.ForeignKeyConstraint(['annotation_id'], ['annotations.id'], name='fk_event_annotation', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name='fk_event_category', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_event_user', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_annotation_events'))
    )
    op.create_index('idx_annotation_events_annotation_id_id', 'annotation_events', ['annotation_id', 'id'], unique=False)
    op.create_index('idx_annotation_events_user_id', 'annotation_events', ['user_id', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_annotation_events_user_id', table_name='annotation_events')
    op.drop_index('idx_annotation_events_annotation_id_id', table_name='annotation_events')
    op.drop_table('annotation_events')
    op.drop_index('uq_reports_open', table_name='reports', postgresql_where=sa.text('resolved_at IS NULL'))
    op.drop_index('idx_reports_open', table_name='reports', postgresql_where=sa.text('resolved_at IS NULL'))
    op.drop_index('idx_reports_image_id', table_name='reports')
    op.drop_table('reports')
    op.drop_index('idx_image_events_user_id', table_name='image_events')
    op.drop_index('idx_image_events_image_id_id', table_name='image_events')
    op.drop_table('image_events')
    op.drop_index('idx_annotations_image_id', table_name='annotations')
    op.drop_table('annotations')
    op.drop_table('mailing')
    op.drop_index('idx_images_date_captured', table_name='images')
    op.drop_table('images')
    op.drop_table('users')
