"""add mailing_list_entry table for guide signups

Revision ID: add_mailing_list
Revises: add_memb_cancel
Create Date: 2025-03-01

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_mailing_list'
down_revision = 'add_memb_cancel'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'mailing_list_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='quit_nicotine_guide'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('mailing_list_entry')
