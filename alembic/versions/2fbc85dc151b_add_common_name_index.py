"""add_common_name_index

Revision ID: 2fbc85dc151b
Revises: 24a9158bd045
Create Date: 2025-11-07 23:43:16.938150

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2fbc85dc151b"
down_revision: Union[str, Sequence[str], None] = "24a9158bd045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add index on common_name column for autocompletion performance."""
    op.create_index("idx_common_name", "objects", ["common_name"])


def downgrade() -> None:
    """Remove index on common_name column."""
    op.drop_index("idx_common_name", table_name="objects")
