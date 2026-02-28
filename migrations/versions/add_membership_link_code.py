"""add membership link_code and nullable user_id

Revision ID: add_link_code
Revises: add_membership
Create Date: 2025-02-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_link_code'
down_revision = 'add_membership'
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    """Return True if column exists on table (SQLite or PostgreSQL)."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result)
    if dialect == "postgresql":
        result = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
        ), {"t": table, "c": column})
        return result.scalar() is not None
    return False


def upgrade():
    conn = op.get_bind()
    if not _column_exists(conn, "membership", "link_code"):
        op.add_column('membership', sa.Column('link_code', sa.String(length=64), nullable=True))
    try:
        op.create_unique_constraint('uq_membership_link_code', 'membership', ['link_code'])
    except Exception:
        pass  # constraint may already exist
    try:
        with op.batch_alter_table('membership', schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=True)
    except Exception:
        pass  # may already be nullable


def downgrade():
    with op.batch_alter_table('membership', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
    op.drop_constraint('uq_membership_link_code', 'membership', type_='unique')
    op.drop_column('membership', 'link_code')
