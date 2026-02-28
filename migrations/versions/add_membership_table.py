"""add membership table

Revision ID: add_membership
Revises: 2951f1f18431
Create Date: 2025-02-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_membership'
down_revision = '2951f1f18431'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'membership',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=False),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('tier', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id')
    )


def downgrade():
    op.drop_table('membership')
