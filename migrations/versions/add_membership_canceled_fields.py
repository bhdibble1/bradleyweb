"""add membership canceled_at and cancel_at_period_end

Revision ID: add_memb_cancel
Revises: add_order_stripe_sess
Create Date: 2025-02-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


revision = 'add_memb_cancel'
down_revision = 'add_order_stripe_sess'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('membership', sa.Column('canceled_at', sa.DateTime(), nullable=True))
    except OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise
    try:
        op.add_column('membership', sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='0'))
    except OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise


def downgrade():
    op.drop_column('membership', 'cancel_at_period_end')
    op.drop_column('membership', 'canceled_at')
