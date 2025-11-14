"""add_variable_stars_comets_eclipses_bortle_tables

Revision ID: 30477aac527b
Revises: 3007dcb04010
Create Date: 2025-11-13 20:28:05.550718

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "30477aac527b"
down_revision: str | Sequence[str] | None = "3007dcb04010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tables for variable stars, comets, eclipses, and Bortle characteristics."""
    # Check if tables already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Create variable_stars table
    if "variable_stars" not in existing_tables:
        op.create_table(
            "variable_stars",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("designation", sa.String(length=50), nullable=False),
            sa.Column("variable_type", sa.String(length=50), nullable=False),
            sa.Column("period_days", sa.Float(), nullable=False),
            sa.Column("magnitude_min", sa.Float(), nullable=False),
            sa.Column("magnitude_max", sa.Float(), nullable=False),
            sa.Column("ra_hours", sa.Float(), nullable=False),
            sa.Column("dec_degrees", sa.Float(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_variable_star_name", "variable_stars", ["name"], unique=True)
        op.create_index("idx_variable_type", "variable_stars", ["variable_type"], unique=False)
        op.create_index("idx_position", "variable_stars", ["ra_hours", "dec_degrees"], unique=False)

    # Create comets table
    if "comets" not in existing_tables:
        op.create_table(
            "comets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("designation", sa.String(length=50), nullable=False),
            sa.Column("perihelion_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("perihelion_distance_au", sa.Float(), nullable=False),
            sa.Column("peak_magnitude", sa.Float(), nullable=False),
            sa.Column("peak_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_periodic", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("period_years", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_comet_name", "comets", ["name"], unique=True)
        op.create_index("idx_comet_designation", "comets", ["designation"], unique=True)
        op.create_index("idx_perihelion_date", "comets", ["perihelion_date"], unique=False)
        op.create_index("idx_peak_date", "comets", ["peak_date"], unique=False)
        op.create_index("idx_is_periodic", "comets", ["is_periodic"], unique=False)

    # Create eclipses table
    if "eclipses" not in existing_tables:
        op.create_table(
            "eclipses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("eclipse_type", sa.String(length=50), nullable=False),
            sa.Column("date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("magnitude", sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_eclipse_type", "eclipses", ["eclipse_type"], unique=False)
        op.create_index("idx_eclipse_date", "eclipses", ["date"], unique=False)
        op.create_index("idx_type_date", "eclipses", ["eclipse_type", "date"], unique=False)

    # Create bortle_characteristics table
    if "bortle_characteristics" not in existing_tables:
        op.create_table(
            "bortle_characteristics",
            sa.Column("bortle_class", sa.Integer(), nullable=False),
            sa.Column("sqm_min", sa.Float(), nullable=False),
            sa.Column("sqm_max", sa.Float(), nullable=False),
            sa.Column("naked_eye_mag", sa.Float(), nullable=False),
            sa.Column("milky_way", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("airglow", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("zodiacal_light", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("recommendations", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("bortle_class"),
        )
        op.create_index("idx_sqm_range", "bortle_characteristics", ["sqm_min", "sqm_max"], unique=False)


def downgrade() -> None:
    """Drop tables for variable stars, comets, eclipses, and Bortle characteristics."""
    # Check if tables exist before dropping
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "bortle_characteristics" in existing_tables:
        op.drop_index("idx_sqm_range", table_name="bortle_characteristics")
        op.drop_table("bortle_characteristics")

    if "eclipses" in existing_tables:
        op.drop_index("idx_type_date", table_name="eclipses")
        op.drop_index("idx_eclipse_date", table_name="eclipses")
        op.drop_index("idx_eclipse_type", table_name="eclipses")
        op.drop_table("eclipses")

    if "comets" in existing_tables:
        op.drop_index("idx_is_periodic", table_name="comets")
        op.drop_index("idx_peak_date", table_name="comets")
        op.drop_index("idx_perihelion_date", table_name="comets")
        op.drop_index("idx_comet_designation", table_name="comets")
        op.drop_index("idx_comet_name", table_name="comets")
        op.drop_table("comets")

    if "variable_stars" in existing_tables:
        op.drop_index("idx_position", table_name="variable_stars")
        op.drop_index("idx_variable_type", table_name="variable_stars")
        op.drop_index("idx_variable_star_name", table_name="variable_stars")
        op.drop_table("variable_stars")
