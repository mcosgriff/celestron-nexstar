"""Migrate favorites from user_preferences to favorites table

Revision ID: 20250201020001
Revises: 20250201020000
Create Date: 2025-02-01 02:00:01.000000

"""
from collections.abc import Sequence
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20250201020001"
down_revision: str | Sequence[str] | None = "20250201020000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate existing favorites from user_preferences to favorites table."""
    conn = op.get_bind()

    # Check if user_preferences table exists
    inspector = sa.inspect(conn)
    if "user_preferences" not in inspector.get_table_names():
        return

    # Check if favorites preference exists
    result = conn.execute(
        text("SELECT value FROM user_preferences WHERE key = 'favorites'")
    ).fetchone()

    if not result:
        # No existing favorites to migrate
        return

    try:
        # Parse JSON favorites
        favorites_json = result[0]
        favorites = json.loads(favorites_json)

        if not favorites:
            # Empty favorites list
            return

        # Insert favorites into new table
        for fav in favorites:
            object_name = fav.get("name")
            object_type = fav.get("type")

            if not object_name:
                continue

            # Use INSERT OR IGNORE to handle duplicates gracefully
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO favorites (object_name, object_type, created_at)
                    VALUES (:object_name, :object_type, datetime('now'))
                """),
                {"object_name": object_name, "object_type": object_type}
            )

        # Alembic will commit the transaction automatically
        # Optionally remove the old preference (commented out to preserve data)
        # conn.execute(text("DELETE FROM user_preferences WHERE key = 'favorites'"))

    except (json.JSONDecodeError, KeyError, Exception) as e:
        # If migration fails, log but don't fail the migration
        # The old data will remain in user_preferences
        # Alembic will handle rollback if needed
        print(f"Warning: Failed to migrate favorites: {e}")


def downgrade() -> None:
    """Migrate favorites back to user_preferences (if needed)."""
    conn = op.get_bind()

    # Check if favorites table exists
    inspector = sa.inspect(conn)
    if "favorites" not in inspector.get_table_names():
        return

    # Get all favorites
    result = conn.execute(
        text("SELECT object_name, object_type FROM favorites ORDER BY created_at")
    ).fetchall()

    if not result:
        return

    # Convert to JSON format
    favorites = [
        {"name": row[0], "type": row[1]} for row in result
    ]
    favorites_json = json.dumps(favorites)

    # Insert or update in user_preferences
    conn.execute(
        text("""
            INSERT OR REPLACE INTO user_preferences (key, value, category, description, created_at, updated_at)
            VALUES ('favorites', :value, 'gui', 'User''s favorite celestial objects', datetime('now'), datetime('now'))
        """),
        {"value": favorites_json}
    )
    # Alembic will commit the transaction automatically
