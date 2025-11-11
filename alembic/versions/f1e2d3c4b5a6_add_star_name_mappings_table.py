"""add_star_name_mappings_table

Revision ID: f1e2d3c4b5a6
Revises: a7f3b8c9d2e1
Create Date: 2025-01-27 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1e2d3c4b5a6"
down_revision: str | Sequence[str] | None = "a7f3b8c9d2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "star_name_mappings",
        sa.Column("hr_number", sa.Integer(), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=False),
        sa.Column("bayer_designation", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("hr_number"),
    )
    with op.batch_alter_table("star_name_mappings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_star_name_mappings_common_name"), ["common_name"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("star_name_mappings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_star_name_mappings_common_name"))
    op.drop_table("star_name_mappings")

