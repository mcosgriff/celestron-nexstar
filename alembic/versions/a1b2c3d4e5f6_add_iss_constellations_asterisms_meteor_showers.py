"""Add ISS passes, constellations, asterisms, and meteor showers tables

Revision ID: a1b2c3d4e5f6
Revises: 2a973e257b4d
Create Date: 2025-01-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "2a973e257b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tables for ISS passes, constellations, asterisms, and meteor showers."""
    # Check if tables already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Create iss_passes table
    if "iss_passes" not in existing_tables:
        op.create_table(
            "iss_passes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("rise_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("set_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False),
            sa.Column("max_altitude_deg", sa.Float(), nullable=False),
            sa.Column("magnitude", sa.Float(), nullable=True),
            sa.Column("rise_azimuth_deg", sa.Float(), nullable=False),
            sa.Column("max_azimuth_deg", sa.Float(), nullable=False),
            sa.Column("set_azimuth_deg", sa.Float(), nullable=False),
            sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # Create indexes using IF NOT EXISTS (SQLite supports this)
    # This handles cases where table/indexes might already exist from partial migrations
    indexes_to_create = [
        ("ix_iss_passes_latitude", ["latitude"]),
        ("ix_iss_passes_longitude", ["longitude"]),
        ("ix_iss_passes_rise_time", ["rise_time"]),
        ("ix_iss_passes_fetched_at", ["fetched_at"]),
        ("idx_location_rise_time", ["latitude", "longitude", "rise_time"]),
        ("idx_location_fetched", ["latitude", "longitude", "fetched_at"]),
    ]

    for index_name, columns in indexes_to_create:
        try:
            columns_str = ", ".join(columns)
            op.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON iss_passes ({columns_str})")
        except Exception:
            # Index might already exist or table doesn't exist yet, ignore
            # (shouldn't happen with IF NOT EXISTS, but be safe)
            pass

    # Create constellations table
    if "constellations" not in existing_tables:
        op.create_table(
            "constellations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=50), nullable=False),
            sa.Column("abbreviation", sa.String(length=3), nullable=False),
            sa.Column("common_name", sa.String(length=100), nullable=True),
            sa.Column("ra_hours", sa.Float(), nullable=False),
            sa.Column("dec_degrees", sa.Float(), nullable=False),
            sa.Column("ra_min_hours", sa.Float(), nullable=False),
            sa.Column("ra_max_hours", sa.Float(), nullable=False),
            sa.Column("dec_min_degrees", sa.Float(), nullable=False),
            sa.Column("dec_max_degrees", sa.Float(), nullable=False),
            sa.Column("area_sq_deg", sa.Float(), nullable=True),
            sa.Column("brightest_star", sa.String(length=100), nullable=True),
            sa.Column("mythology", sa.Text(), nullable=True),
            sa.Column("season", sa.String(length=20), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
            sa.UniqueConstraint("abbreviation"),
        )

    # Create indexes for constellations
    if "constellations" in existing_tables or "constellations" not in existing_tables:  # Always try to create indexes
        with op.batch_alter_table("constellations", schema=None) as batch_op:
            const_indexes = (
                [idx["name"] for idx in inspector.get_indexes("constellations")]
                if "constellations" in inspector.get_table_names()
                else []
            )
            if "ix_constellations_name" not in const_indexes:
                batch_op.create_index(batch_op.f("ix_constellations_name"), ["name"], unique=False)

    # Create asterisms table
    if "asterisms" not in existing_tables:
        op.create_table(
            "asterisms",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("alt_names", sa.String(length=255), nullable=True),
            sa.Column("ra_hours", sa.Float(), nullable=False),
            sa.Column("dec_degrees", sa.Float(), nullable=False),
            sa.Column("size_degrees", sa.Float(), nullable=True),
            sa.Column("parent_constellation", sa.String(length=50), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("stars", sa.Text(), nullable=True),
            sa.Column("season", sa.String(length=20), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    # Create indexes for asterisms
    if "asterisms" in existing_tables or "asterisms" not in existing_tables:
        with op.batch_alter_table("asterisms", schema=None) as batch_op:
            asterism_indexes = (
                [idx["name"] for idx in inspector.get_indexes("asterisms")]
                if "asterisms" in inspector.get_table_names()
                else []
            )
            if "ix_asterisms_name" not in asterism_indexes:
                batch_op.create_index(batch_op.f("ix_asterisms_name"), ["name"], unique=False)

    # Create meteor_showers table
    if "meteor_showers" not in existing_tables:
        op.create_table(
            "meteor_showers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("code", sa.String(length=3), nullable=True),
            sa.Column("start_month", sa.Integer(), nullable=False),
            sa.Column("start_day", sa.Integer(), nullable=False),
            sa.Column("end_month", sa.Integer(), nullable=False),
            sa.Column("end_day", sa.Integer(), nullable=False),
            sa.Column("peak_month", sa.Integer(), nullable=False),
            sa.Column("peak_day", sa.Integer(), nullable=False),
            sa.Column("radiant_ra_hours", sa.Float(), nullable=False),
            sa.Column("radiant_dec_degrees", sa.Float(), nullable=False),
            sa.Column("radiant_constellation", sa.String(length=50), nullable=True),
            sa.Column("zhr_peak", sa.Integer(), nullable=False),
            sa.Column("velocity_km_s", sa.Float(), nullable=True),
            sa.Column("parent_comet", sa.String(length=100), nullable=True),
            sa.Column("best_time", sa.String(length=50), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    # Create indexes for meteor_showers
    if "meteor_showers" in existing_tables or "meteor_showers" not in existing_tables:
        with op.batch_alter_table("meteor_showers", schema=None) as batch_op:
            meteor_indexes = (
                [idx["name"] for idx in inspector.get_indexes("meteor_showers")]
                if "meteor_showers" in inspector.get_table_names()
                else []
            )
            if "ix_meteor_showers_name" not in meteor_indexes:
                batch_op.create_index(batch_op.f("ix_meteor_showers_name"), ["name"], unique=False)
            if "ix_meteor_showers_peak_month" not in meteor_indexes:
                batch_op.create_index(batch_op.f("ix_meteor_showers_peak_month"), ["peak_month"], unique=False)
            if "ix_meteor_showers_peak_day" not in meteor_indexes:
                batch_op.create_index(batch_op.f("ix_meteor_showers_peak_day"), ["peak_day"], unique=False)
            if "idx_peak_date" not in meteor_indexes:
                batch_op.create_index("idx_peak_date", ["peak_month", "peak_day"], unique=False)


def downgrade() -> None:
    """Remove tables for ISS passes, constellations, asterisms, and meteor showers."""
    with op.batch_alter_table("meteor_showers", schema=None) as batch_op:
        batch_op.drop_index("idx_peak_date")
        batch_op.drop_index(batch_op.f("ix_meteor_showers_peak_day"))
        batch_op.drop_index(batch_op.f("ix_meteor_showers_peak_month"))
        batch_op.drop_index(batch_op.f("ix_meteor_showers_name"))

    op.drop_table("meteor_showers")

    with op.batch_alter_table("asterisms", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_asterisms_name"))

    op.drop_table("asterisms")

    with op.batch_alter_table("constellations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_constellations_name"))

    op.drop_table("constellations")

    with op.batch_alter_table("iss_passes", schema=None) as batch_op:
        batch_op.drop_index("idx_location_fetched")
        batch_op.drop_index("idx_location_rise_time")
        batch_op.drop_index(batch_op.f("ix_iss_passes_fetched_at"))
        batch_op.drop_index(batch_op.f("ix_iss_passes_rise_time"))
        batch_op.drop_index(batch_op.f("ix_iss_passes_longitude"))
        batch_op.drop_index(batch_op.f("ix_iss_passes_latitude"))

    op.drop_table("iss_passes")
