"""Add equipment tables (eyepieces, filters, cameras)

Revision ID: 20250201020002
Revises: 20250201020001
Create Date: 2025-02-01 02:00:02.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250201020002"
down_revision: str | Sequence[str] | None = "20250201020001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create equipment tables."""
    # Create eyepieces table
    op.create_table(
        "eyepieces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("focal_length_mm", sa.Float(), nullable=False),
        sa.Column("apparent_fov_deg", sa.Float(), nullable=False, server_default="50.0"),
        sa.Column("barrel_size_mm", sa.Float(), nullable=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eyepieces_name", "eyepieces", ["name"])
    op.create_index("ix_eyepieces_focal_length", "eyepieces", ["focal_length_mm"])

    # Create filters table
    op.create_table(
        "filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("filter_type", sa.String(length=50), nullable=False),
        sa.Column("barrel_size_mm", sa.Float(), nullable=True),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("transmission_percent", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filters_name", "filters", ["name"])
    op.create_index("ix_filters_type", "filters", ["filter_type"])

    # Create cameras table
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sensor_width_mm", sa.Float(), nullable=False),
        sa.Column("sensor_height_mm", sa.Float(), nullable=False),
        sa.Column("pixel_width_um", sa.Float(), nullable=True),
        sa.Column("pixel_height_um", sa.Float(), nullable=True),
        sa.Column("resolution_width", sa.Integer(), nullable=True),
        sa.Column("resolution_height", sa.Integer(), nullable=True),
        sa.Column("camera_type", sa.String(length=50), nullable=False, server_default="DSLR"),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cameras_name", "cameras", ["name"])
    op.create_index("ix_cameras_type", "cameras", ["camera_type"])


def downgrade() -> None:
    """Drop equipment tables."""
    op.drop_index("ix_cameras_type", table_name="cameras")
    op.drop_index("ix_cameras_name", table_name="cameras")
    op.drop_table("cameras")
    op.drop_index("ix_filters_type", table_name="filters")
    op.drop_index("ix_filters_name", table_name="filters")
    op.drop_table("filters")
    op.drop_index("ix_eyepieces_focal_length", table_name="eyepieces")
    op.drop_index("ix_eyepieces_name", table_name="eyepieces")
    op.drop_table("eyepieces")
