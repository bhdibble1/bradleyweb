"""initial schema1

Revision ID: 2951f1f18431
Revises:
Create Date: 2025-08-28 20:44:10.158879

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2951f1f18431'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create all tables for fresh DB (e.g. SQLite). Safe to run: adds columns if table exists (Postgres).
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('password', sa.String(length=150), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_table(
        'product',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(length=100), nullable=False),
        sa.Column('product_description', sa.String(length=100), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('product_image', sa.String(), nullable=False),
        sa.Column('featured', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('price', sa.Float(), nullable=False, server_default='0'),
        sa.Column('category', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'order',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_date', sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column('total', sa.Float(), nullable=False, server_default='0'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('tracking_number', sa.String(length=100), nullable=True),
        sa.Column('tracking_status', sa.String(length=100), nullable=True),
        sa.Column('tracking_carrier', sa.String(length=100), nullable=True),
        sa.Column('tracking_url', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='pending'),
        sa.Column('inventory_reduced', sa.Boolean(), nullable=True),
        sa.Column('confirmation_sent', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'order_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('subtotal', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['product.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('order_item')
    op.drop_table('order')
    op.drop_table('product')
    op.drop_table('user')
