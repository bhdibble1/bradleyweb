"""add affiliate_book table for amazon links

Revision ID: add_affiliate_books
Revises: add_mailing_list
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa


revision = "add_affiliate_books"
down_revision = "add_mailing_list"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "affiliate_book",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("amazon_url", sa.String(length=2048), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("affiliate_book")

