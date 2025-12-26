"""Update galaxy nebula cluster indexes to use constellation_id

Revision ID: 648fa53bd17a
Revises: 20250123000000
Create Date: 2025-12-25 20:29:55.164934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '648fa53bd17a'
down_revision: Union[str, Sequence[str], None] = '20250123000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - update indexes to use constellation_id foreign key."""
    # Note: Using batch mode for SQLite compatibility with DROP INDEX IF EXISTS

    # Galaxies: Drop old index on constellation string, create new index on constellation_id
    with op.batch_alter_table('galaxies') as batch_op:
        batch_op.drop_index('idx_galaxy_constellation_magnitude', if_exists=True)
        batch_op.create_index('idx_galaxy_constellation_id_magnitude', ['constellation_id', 'magnitude'])

    # Nebulae: Drop old index on constellation string, create new index on constellation_id
    with op.batch_alter_table('nebulae') as batch_op:
        batch_op.drop_index('idx_nebula_constellation_magnitude', if_exists=True)
        batch_op.create_index('idx_nebula_constellation_id_magnitude', ['constellation_id', 'magnitude'])

    # Clusters: Drop old index on constellation string, create new index on constellation_id
    with op.batch_alter_table('clusters') as batch_op:
        batch_op.drop_index('idx_cluster_constellation_magnitude', if_exists=True)
        batch_op.create_index('idx_cluster_constellation_id_magnitude', ['constellation_id', 'magnitude'])


def downgrade() -> None:
    """Downgrade schema - restore indexes on constellation string field."""
    # Galaxies: Drop new index, restore old index
    with op.batch_alter_table('galaxies') as batch_op:
        batch_op.drop_index('idx_galaxy_constellation_id_magnitude', if_exists=True)
        batch_op.create_index('idx_galaxy_constellation_magnitude', ['constellation', 'magnitude'])

    # Nebulae: Drop new index, restore old index
    with op.batch_alter_table('nebulae') as batch_op:
        batch_op.drop_index('idx_nebula_constellation_id_magnitude', if_exists=True)
        batch_op.create_index('idx_nebula_constellation_magnitude', ['constellation', 'magnitude'])

    # Clusters: Drop new index, restore old index
    with op.batch_alter_table('clusters') as batch_op:
        batch_op.drop_index('idx_cluster_constellation_id_magnitude', if_exists=True)
        batch_op.create_index('idx_cluster_constellation_magnitude', ['constellation', 'magnitude'])
