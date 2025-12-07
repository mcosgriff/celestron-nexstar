"""
Favorites Management

Manages user's favorite celestial objects stored in the database.
Uses native DuckDB API for maximum performance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from celestron_nexstar.api.database.duckdb_connection import get_duckdb_connection


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "add_favorite",
    "are_favorites",
    "clear_favorites",
    "get_favorites",
    "is_favorite",
    "remove_favorite",
]


async def add_favorite(object_name: str, object_type: str | None = None) -> bool:
    """
    Add an object to favorites.

    Args:
        object_name: Name of the object to add
        object_type: Optional object type (for categorization)

    Returns:
        True if added successfully, False otherwise
    """
    try:
        con = get_duckdb_connection()

        # Check if already a favorite (fast indexed lookup)
        check_query = "SELECT id FROM favorites WHERE object_name = ?"
        existing = con.execute(check_query, [object_name]).fetchone()

        if existing:
            logger.debug(f"Object '{object_name}' is already a favorite")
            return False

        # Add new favorite
        insert_query = """
            INSERT INTO favorites (object_name, object_type)
            VALUES (?, ?)
        """
        con.execute(insert_query, [object_name, object_type])
        logger.info(f"Added '{object_name}' to favorites")
        return True

    except Exception as e:
        logger.error(f"Error adding favorite: {e}", exc_info=True)
        return False


async def remove_favorite(object_name: str) -> bool:
    """
    Remove an object from favorites.

    Args:
        object_name: Name of the object to remove

    Returns:
        True if removed successfully, False otherwise
    """
    try:
        con = get_duckdb_connection()

        # Check if exists
        check_query = "SELECT id FROM favorites WHERE object_name = ?"
        existing = con.execute(check_query, [object_name]).fetchone()

        if not existing:
            logger.debug(f"Object '{object_name}' was not in favorites")
            return False

        # Delete the favorite
        delete_query = "DELETE FROM favorites WHERE object_name = ?"
        con.execute(delete_query, [object_name])
        logger.info(f"Removed '{object_name}' from favorites")
        return True

    except Exception as e:
        logger.error(f"Error removing favorite: {e}", exc_info=True)
        return False


async def is_favorite(object_name: str) -> bool:
    """
    Check if an object is a favorite.

    Args:
        object_name: Name of the object to check

    Returns:
        True if the object is a favorite, False otherwise
    """
    try:
        con = get_duckdb_connection()

        # Fast indexed lookup
        query = "SELECT id FROM favorites WHERE object_name = ?"
        result = con.execute(query, [object_name]).fetchone()

        return result is not None

    except Exception as e:
        logger.error(f"Error checking favorite: {e}", exc_info=True)
        return False


async def get_favorites() -> list[dict[str, str | None]]:
    """
    Get all favorite objects.

    Returns:
        List of favorite objects, each as a dict with 'name' and optional 'type'
    """
    try:
        con = get_duckdb_connection()

        # Get all favorites ordered by creation date
        query = "SELECT object_name, object_type FROM favorites ORDER BY created_at"
        results = con.execute(query).fetchall()

        # Convert to dict format for backward compatibility
        return [
            {
                "name": row[0],
                "type": row[1],
            }
            for row in results
        ]

    except Exception as e:
        logger.error(f"Error getting favorites: {e}", exc_info=True)
        return []


async def are_favorites(object_names: list[str]) -> dict[str, bool]:
    """
    Check if multiple objects are favorites in a single database query.

    This is much more efficient than calling is_favorite() multiple times,
    especially for large lists, as it uses a single query.

    Args:
        object_names: List of object names to check

    Returns:
        Dictionary mapping object names to their favorite status (True/False)
    """
    if not object_names:
        return {}

    try:
        con = get_duckdb_connection()

        # Single query with IN clause for all objects
        # Use parameterized query with placeholders
        placeholders = ",".join("?" * len(object_names))
        query = f"SELECT object_name FROM favorites WHERE object_name IN ({placeholders})"
        results = con.execute(query, object_names).fetchall()
        favorite_names = {row[0] for row in results}

        # Build result dict - True if in favorites, False otherwise
        return {name: name in favorite_names for name in object_names}

    except Exception as e:
        logger.error(f"Error checking favorites batch: {e}", exc_info=True)
        # Return all False on error
        return dict.fromkeys(object_names, False)


async def clear_favorites() -> bool:
    """
    Clear all favorites.

    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        con = get_duckdb_connection()

        # Count favorites before deletion
        count_query = "SELECT COUNT(*) FROM favorites"
        count = con.execute(count_query).fetchone()[0] or 0

        if count > 0:
            # Delete all favorites
            delete_query = "DELETE FROM favorites"
            con.execute(delete_query)
            logger.info(f"Cleared {count} favorites")
            return True

        return False

    except Exception as e:
        logger.error(f"Error clearing favorites: {e}", exc_info=True)
        return False
