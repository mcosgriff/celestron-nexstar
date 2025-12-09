"""Add brightest_star column to asterisms table.

Adds a column to store the name of the brightest star in each asterism.
This is determined from the stars found within the asterism's MultiLineString geometry.

Revision ID: 20250207000000
Revises: 20250206000000
Create Date: 2025-02-07 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250207000000"
down_revision: str | Sequence[str] | None = "20250206000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add brightest_star column to asterisms table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "asterisms" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("asterisms")]
        if "brightest_star" not in columns:
            with op.batch_alter_table("asterisms") as batch_op:
                batch_op.add_column(sa.Column("brightest_star", sa.String(100), nullable=True))


def downgrade() -> None:
    """Remove brightest_star column from asterisms table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "asterisms" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("asterisms")]
        if "brightest_star" in columns:
            with op.batch_alter_table("asterisms") as batch_op:
                batch_op.drop_column("brightest_star")

