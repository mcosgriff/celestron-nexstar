"""
Observations Management

Manages observation logs for celestial objects stored in the database.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.database.models import ObservationModel


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "add_observation",
    "delete_observation",
    "get_observation",
    "get_observations",
    "get_observations_by_object",
    "update_observation",
]


async def add_observation(
    object_name: str,
    observed_at: datetime | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
    location_name: str | None = None,
    seeing_quality: int | None = None,
    transparency: int | None = None,
    sky_brightness: float | None = None,
    weather_notes: str | None = None,
    telescope: str | None = None,
    eyepiece: str | None = None,
    filters: str | None = None,
    notes: str | None = None,
    rating: int | None = None,
    image_path: str | None = None,
    sketch_path: str | None = None,
) -> int | None:
    """
    Add an observation log entry.

    Args:
        object_name: Name of the observed object
        observed_at: Date/time of observation (default: now)
        location_lat: Observer latitude
        location_lon: Observer longitude
        location_name: Observer location name
        seeing_quality: Seeing quality (1-5 scale)
        transparency: Transparency (1-5 scale)
        sky_brightness: Sky brightness (SQM value)
        weather_notes: Weather notes
        telescope: Telescope used
        eyepiece: Eyepiece used
        filters: Filters used
        notes: Observation notes
        rating: Rating (1-5 stars)
        image_path: Path to observation image
        sketch_path: Path to observation sketch

    Returns:
        Observation ID if created successfully, None otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Get object from database to find its ID and type
            obj = await db.get_by_name(object_name)
            if not obj:
                logger.error(f"Object '{object_name}' not found in database")
                return None

            # Query the database model to get the ID
            # We need to search the appropriate table based on object_type
            model_class = db._get_model_class(obj.object_type)
            stmt = select(model_class).where(model_class.name == object_name).limit(1)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                logger.error(f"Could not find database model for '{object_name}'")
                return None

            object_id = model.id
            object_type = obj.object_type.value

            # Use current time if not provided
            if observed_at is None:
                observed_at = datetime.now(UTC)
            elif observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)

            # Create observation
            observation = ObservationModel(
                object_type=object_type,
                object_id=object_id,
                observed_at=observed_at,
                location_lat=location_lat,
                location_lon=location_lon,
                location_name=location_name,
                seeing_quality=seeing_quality,
                transparency=transparency,
                sky_brightness=sky_brightness,
                weather_notes=weather_notes,
                telescope=telescope,
                eyepiece=eyepiece,
                filters=filters,
                notes=notes,
                rating=rating,
                image_path=image_path,
                sketch_path=sketch_path,
            )
            session.add(observation)
            await session.commit()
            await session.refresh(observation)
            logger.info(f"Added observation for '{object_name}' (ID: {observation.id})")
            return observation.id
    except Exception as e:
        logger.error(f"Error adding observation: {e}", exc_info=True)
        return None


async def get_observation(observation_id: int) -> ObservationModel | None:
    """
    Get an observation by ID.

    Args:
        observation_id: Observation ID

    Returns:
        ObservationModel if found, None otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            observation = await session.get(ObservationModel, observation_id)
            return observation
    except Exception as e:
        logger.error(f"Error getting observation: {e}", exc_info=True)
        return None


async def get_observations(
    limit: int | None = None,
    offset: int = 0,
    order_by: str = "observed_at",
    order_desc: bool = True,
) -> list[ObservationModel]:
    """
    Get all observations.

    Args:
        limit: Maximum number of observations to return
        offset: Number of observations to skip
        order_by: Field to order by (default: observed_at)
        order_desc: Order descending (default: True)

    Returns:
        List of ObservationModel instances
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(ObservationModel)
            if order_by == "observed_at":
                if order_desc:
                    stmt = stmt.order_by(ObservationModel.observed_at.desc())
                else:
                    stmt = stmt.order_by(ObservationModel.observed_at.asc())
            if limit:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    except Exception as e:
        logger.error(f"Error getting observations: {e}", exc_info=True)
        return []


async def get_observations_by_object(
    object_name: str,
    limit: int | None = None,
) -> list[ObservationModel]:
    """
    Get all observations for a specific object.

    Args:
        object_name: Name of the object
        limit: Maximum number of observations to return

    Returns:
        List of ObservationModel instances
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            # Get object to find its ID and type
            obj = await db.get_by_name(object_name)
            if not obj:
                logger.warning(f"Object '{object_name}' not found in database")
                return []

            # Query the database model to get the ID
            model_class = db._get_model_class(obj.object_type)
            stmt = select(model_class).where(model_class.name == object_name).limit(1)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if not model:
                return []

            object_id = model.id
            object_type = obj.object_type.value

            # Query observations
            obs_stmt = (
                select(ObservationModel)
                .where(
                    ObservationModel.object_type == object_type,
                    ObservationModel.object_id == object_id,
                )
                .order_by(ObservationModel.observed_at.desc())
            )
            if limit:
                obs_stmt = obs_stmt.limit(limit)
            obs_result = await session.execute(obs_stmt)
            return list(obs_result.scalars().all())
    except Exception as e:
        logger.error(f"Error getting observations for object: {e}", exc_info=True)
        return []


async def update_observation(
    observation_id: int,
    observed_at: datetime | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
    location_name: str | None = None,
    seeing_quality: int | None = None,
    transparency: int | None = None,
    sky_brightness: float | None = None,
    weather_notes: str | None = None,
    telescope: str | None = None,
    eyepiece: str | None = None,
    filters: str | None = None,
    notes: str | None = None,
    rating: int | None = None,
    image_path: str | None = None,
    sketch_path: str | None = None,
) -> bool:
    """
    Update an observation log entry.

    Args:
        observation_id: Observation ID to update
        observed_at: Date/time of observation
        location_lat: Observer latitude
        location_lon: Observer longitude
        location_name: Observer location name
        seeing_quality: Seeing quality (1-5 scale)
        transparency: Transparency (1-5 scale)
        sky_brightness: Sky brightness (SQM value)
        weather_notes: Weather notes
        telescope: Telescope used
        eyepiece: Eyepiece used
        filters: Filters used
        notes: Observation notes
        rating: Rating (1-5 stars)
        image_path: Path to observation image
        sketch_path: Path to observation sketch

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            observation = await session.get(ObservationModel, observation_id)
            if not observation:
                logger.error(f"Observation {observation_id} not found")
                return False

            # Update fields if provided
            if observed_at is not None:
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=UTC)
                observation.observed_at = observed_at
            if location_lat is not None:
                observation.location_lat = location_lat
            if location_lon is not None:
                observation.location_lon = location_lon
            if location_name is not None:
                observation.location_name = location_name
            if seeing_quality is not None:
                observation.seeing_quality = seeing_quality
            if transparency is not None:
                observation.transparency = transparency
            if sky_brightness is not None:
                observation.sky_brightness = sky_brightness
            if weather_notes is not None:
                observation.weather_notes = weather_notes
            if telescope is not None:
                observation.telescope = telescope
            if eyepiece is not None:
                observation.eyepiece = eyepiece
            if filters is not None:
                observation.filters = filters
            if notes is not None:
                observation.notes = notes
            if rating is not None:
                observation.rating = rating
            if image_path is not None:
                observation.image_path = image_path
            if sketch_path is not None:
                observation.sketch_path = sketch_path

            await session.commit()
            logger.info(f"Updated observation {observation_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating observation: {e}", exc_info=True)
        return False


async def delete_observation(observation_id: int) -> bool:
    """
    Delete an observation log entry.

    Args:
        observation_id: Observation ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            observation = await session.get(ObservationModel, observation_id)
            if not observation:
                logger.error(f"Observation {observation_id} not found")
                return False

            await session.delete(observation)
            await session.commit()
            logger.info(f"Deleted observation {observation_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting observation: {e}", exc_info=True)
        return False
