"""add order stripe_session_id for idempotent order creation (webhook + redirect)

Revision ID: add_order_stripe_sess
Revises: add_printful_id
Create Date: 2025-02-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


revision = 'add_order_stripe_sess'
down_revision = 'add_printful_id'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('order', sa.Column('stripe_session_id', sa.String(length=255), nullable=True))
    except OperationalError as e:
        if 'duplicate column' not in str(e).lower():
            raise
    try:
        op.create_unique_constraint('uq_order_stripe_session_id', 'order', ['stripe_session_id'])
    except OperationalError as e:
        if 'already exists' not in str(e).lower() and 'duplicate' not in str(e).lower():
            raise


def downgrade():
    op.drop_constraint('uq_order_stripe_session_id', 'order', type_='unique')
    op.drop_column('order', 'stripe_session_id')
