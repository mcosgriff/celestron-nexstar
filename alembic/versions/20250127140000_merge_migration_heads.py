"""merge migration heads

Revision ID: 20250127140000
Revises: ('30477aac527b', '20250127130000')
Create Date: 2025-01-27 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250127140000"
down_revision: str | Sequence[str] | None = ("30477aac527b", "20250127130000")
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
