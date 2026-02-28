"""add product printful_id for Printful catalog sync

Revision ID: add_printful_id
Revises: add_link_code
Create Date: 2025-02-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_printful_id'
down_revision = 'add_link_code'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('product', sa.Column('printful_id', sa.String(length=32), nullable=True))
    try:
        op.create_unique_constraint('uq_product_printful_id', 'product', ['printful_id'])
    except Exception:
        pass


def downgrade():
    op.drop_constraint('uq_product_printful_id', 'product', type_='unique')
    op.drop_column('product', 'printful_id')
