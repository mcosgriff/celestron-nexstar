"""Add asterism column to stars table and junction tables for foreign keys.

Adds:
1. asterism column to stars table (for backward compatibility, stores comma-separated names)
2. star_constellation junction table (many-to-many with foreign keys)
3. star_asterism junction table (many-to-many with foreign keys)
4. Enables foreign key constraints

Revision ID: 20250208000000
Revises: 20250207000000
Create Date: 2025-02-08 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250208000000"
down_revision: str | Sequence[str] | None = "20250207000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add asterism column and junction tables with foreign keys."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Enable foreign keys
    conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    # Add asterism column to stars table (for backward compatibility)
    if "stars" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("stars")]
        if "asterism" not in columns:
            with op.batch_alter_table("stars") as batch_op:
                batch_op.add_column(sa.Column("asterism", sa.String(255), nullable=True))
                # Add index for faster queries
                batch_op.create_index("ix_stars_asterism", ["asterism"])

    # Create star_constellation junction table (many-to-many)
    # Note: In practice, each star belongs to one constellation, but we use junction table
    # for consistency and to support foreign keys
    if "star_constellation" not in existing_tables:
        op.create_table(
            "star_constellation",
            sa.Column("star_id", sa.Integer(), nullable=False),
            sa.Column("constellation_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["constellation_id"], ["constellations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["star_id"], ["stars.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("star_id", "constellation_id"),
        )
        op.create_index("ix_star_constellation_star_id", "star_constellation", ["star_id"])
        op.create_index("ix_star_constellation_constellation_id", "star_constellation", ["constellation_id"])

    # Create star_asterism junction table (many-to-many)
    if "star_asterism" not in existing_tables:
        op.create_table(
            "star_asterism",
            sa.Column("star_id", sa.Integer(), nullable=False),
            sa.Column("asterism_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["asterism_id"], ["asterisms.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["star_id"], ["stars.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("star_id", "asterism_id"),
        )
        op.create_index("ix_star_asterism_star_id", "star_asterism", ["star_id"])
        op.create_index("ix_star_asterism_asterism_id", "star_asterism", ["asterism_id"])


def downgrade() -> None:
    """Remove junction tables and asterism column."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Drop junction tables
    if "star_asterism" in existing_tables:
        op.drop_table("star_asterism")
    if "star_constellation" in existing_tables:
        op.drop_table("star_constellation")

    # Remove asterism column from stars table
    if "stars" in existing_tables:
        columns = [col["name"] for col in inspector.get_columns("stars")]
        if "asterism" in columns:
            with op.batch_alter_table("stars") as batch_op:
                batch_op.drop_index("ix_stars_asterism")
                batch_op.drop_column("asterism")

