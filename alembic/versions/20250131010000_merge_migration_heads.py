"""Merge migration heads

Revision ID: 20250131010000
Revises: ('20250130000000', '20250131000000')
Create Date: 2025-01-31 01:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250131010000"
down_revision: str | Sequence[str] | None = ("20250130000000", "20250131000000")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration - no changes needed, just combines the two branches."""
    # This is a merge migration - no actual schema changes
    pass


def downgrade() -> None:
    """Merge migration - no changes needed."""
    # This is a merge migration - no actual schema changes
    pass

