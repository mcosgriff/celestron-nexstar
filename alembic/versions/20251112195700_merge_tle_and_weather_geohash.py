"""merge_tle_and_weather_geohash

Revision ID: 20251112195700
Revises: 3c4d5e6f7a8b, 20251112195646
Create Date: 2025-11-12 19:57:00.000000

"""

from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "20251112195700"
down_revision: str | Sequence[str] | None = ("3c4d5e6f7a8b", "20251112195646")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge branches: tle_data table and weather_forecast geohash."""
    # This is a merge migration - no schema changes needed
    # Both branches are independent and can coexist
    pass


def downgrade() -> None:
    """Downgrade merge migration."""
    # Merge migrations typically don't have a meaningful downgrade
    pass
