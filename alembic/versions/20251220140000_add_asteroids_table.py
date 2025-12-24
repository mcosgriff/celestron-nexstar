"""add asteroids table for asteroid visibility

Revision ID: 20251220140000
Revises: 20251220120000
Create Date: 2025-12-20 14:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251220140000"
down_revision = "20251220120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add asteroids table."""
    op.create_table(
        "asteroids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("designation", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("asteroid_type", sa.String(50), nullable=False),
        # Orbital elements
        sa.Column("semi_major_axis_au", sa.Float(), nullable=False),
        sa.Column("eccentricity", sa.Float(), nullable=False),
        sa.Column("inclination_deg", sa.Float(), nullable=False),
        sa.Column("ascending_node_deg", sa.Float(), nullable=False),
        sa.Column("arg_perihelion_deg", sa.Float(), nullable=False),
        sa.Column("mean_anomaly_deg", sa.Float(), nullable=False),
        sa.Column("epoch", sa.DateTime(timezone=True), nullable=False),
        # Photometric
        sa.Column("absolute_magnitude_h", sa.Float(), nullable=False),
        sa.Column("slope_g", sa.Float(), nullable=True),
        sa.Column("diameter_km", sa.Float(), nullable=True),
        sa.Column("albedo", sa.Float(), nullable=True),
        # Derived
        sa.Column("perihelion_au", sa.Float(), nullable=True),
        sa.Column("aphelion_au", sa.Float(), nullable=True),
        sa.Column("orbital_period_years", sa.Float(), nullable=True),
        # Metadata
        sa.Column("discovery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discoverer", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="seed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_asteroid_designation", "asteroids", ["designation"], unique=True)
    op.create_index("idx_asteroid_type", "asteroids", ["asteroid_type"])
    op.create_index("idx_asteroid_magnitude", "asteroids", ["absolute_magnitude_h"])
    op.create_index("idx_asteroid_name", "asteroids", ["name"])


def downgrade() -> None:
    """Remove asteroids table."""
    op.drop_index("idx_asteroid_name", table_name="asteroids")
    op.drop_index("idx_asteroid_magnitude", table_name="asteroids")
    op.drop_index("idx_asteroid_type", table_name="asteroids")
    op.drop_index("idx_asteroid_designation", table_name="asteroids")
    op.drop_table("asteroids")



