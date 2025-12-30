"""add_variable_type_id_to_variable_stars

Revision ID: 2ff2e82927af
Revises: f1af6e2ecaf5
Create Date: 2025-12-29 20:00:28.074475

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ff2e82927af'
down_revision: Union[str, Sequence[str], None] = 'f1af6e2ecaf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def _index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:table AND name=:index"
        ),
        {"table": table_name, "index": index_name}
    )
    return result.fetchone() is not None


def upgrade() -> None:
    """Upgrade schema."""
    # Add variable_type_id column, index, and foreign key if they don't exist
    if not _column_exists("variable_stars", "variable_type_id"):
        with op.batch_alter_table("variable_stars", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("variable_type_id", sa.Integer(), nullable=True)
            )
            batch_op.create_index(
                batch_op.f("ix_variable_stars_variable_type_id"),
                ["variable_type_id"],
                unique=False
            )
            batch_op.create_foreign_key(
                "fk_variable_stars_variable_type_id",
                "object_types",
                ["variable_type_id"],
                ["id"],
                ondelete="SET NULL"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key, index, and column if they exist
    if _column_exists("variable_stars", "variable_type_id"):
        with op.batch_alter_table("variable_stars", schema=None) as batch_op:
            batch_op.drop_constraint(
                "fk_variable_stars_variable_type_id", type_="foreignkey"
            )
            batch_op.drop_index(batch_op.f("ix_variable_stars_variable_type_id"))
            batch_op.drop_column("variable_type_id")
