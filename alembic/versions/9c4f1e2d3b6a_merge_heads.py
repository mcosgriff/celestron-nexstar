"""merge_heads

Revision ID: 9c4f1e2d3b6a
Revises: 2ff2e82927af, 8a1b2c3d4e5f
Create Date: 2026-01-05 12:10:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "9c4f1e2d3b6a"
down_revision: Union[str, Sequence[str], None] = ("2ff2e82927af", "8a1b2c3d4e5f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge heads."""
    pass


def downgrade() -> None:
    """Downgrade merge."""
    pass
