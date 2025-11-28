"""
Favorites Management

Manages user's favorite celestial objects stored in the database.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.database.models import FavoriteModel


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "add_favorite",
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
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Check if already a favorite (fast indexed lookup)
            stmt = select(FavoriteModel).where(FavoriteModel.object_name == object_name)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                logger.debug(f"Object '{object_name}' is already a favorite")
                return False

            # Add new favorite
            favorite = FavoriteModel(
                object_name=object_name,
                object_type=object_type,
            )
            session.add(favorite)

            await session.commit()
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
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Find the favorite (fast indexed lookup)
            stmt = select(FavoriteModel).where(FavoriteModel.object_name == object_name)
            result = await session.execute(stmt)
            favorite = result.scalar_one_or_none()

            if not favorite:
                logger.debug(f"Object '{object_name}' was not in favorites")
                return False

            # Delete the favorite
            await session.delete(favorite)
            await session.commit()
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
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Fast indexed lookup
            stmt = select(FavoriteModel).where(FavoriteModel.object_name == object_name)
            result = await session.execute(stmt)
            favorite = result.scalar_one_or_none()

            return favorite is not None

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
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Get all favorites ordered by creation date
            stmt = select(FavoriteModel).order_by(FavoriteModel.created_at)
            result = await session.execute(stmt)
            favorites = result.scalars().all()

            # Convert to dict format for backward compatibility
            return [
                {
                    "name": fav.object_name,
                    "type": fav.object_type,
                }
                for fav in favorites
            ]

    except Exception as e:
        logger.error(f"Error getting favorites: {e}", exc_info=True)
        return []


async def clear_favorites() -> bool:
    """
    Clear all favorites.

    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import delete, func, select

            # Count favorites before deletion
            count_stmt = select(func.count(FavoriteModel.id))
            count_result = await session.execute(count_stmt)
            count = count_result.scalar() or 0

            if count > 0:
                # Delete all favorites
                stmt = delete(FavoriteModel)
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Cleared {count} favorites")
                return True

            return False

    except Exception as e:
        logger.error(f"Error clearing favorites: {e}", exc_info=True)
        return False
