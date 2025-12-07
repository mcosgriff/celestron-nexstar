"""
Observations Management

Manages observation logs for celestial objects stored in the database.
Uses native DuckDB API for maximum performance.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from celestron_nexstar.api.database.duckdb_connection import get_duckdb_connection
from celestron_nexstar.api.database.duckdb_database import DuckDBCatalogDatabase


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "Observation",
    "add_observation",
    "delete_observation",
    "get_observation",
    "get_observations",
    "get_observations_by_object",
    "update_observation",
]


@dataclass
class Observation:
    """Observation data structure."""

    id: int
    object_type: str
    object_id: int
    object_name: str | None  # Store name for reference
    observed_at: datetime
    location_lat: float | None
    location_lon: float | None
    location_geohash: str | None
    location_name: str | None
    seeing_quality: int | None
    transparency: int | None
    sky_brightness: float | None
    weather_notes: str | None
    telescope: str | None
    eyepiece: str | None
    filters: str | None
    notes: str | None
    rating: int | None
    image_path: str | None
    sketch_path: str | None
    created_at: datetime
    updated_at: datetime


async def _get_object_id_and_type(object_name: str) -> tuple[int, str] | None:
    """
    Get object ID and type from DuckDB database.

    For objects in our DuckDB tables (planets, moons, asterisms, constellations),
    returns the actual ID. For stars and DSOs from starplot, generates a hash-based ID.

    Args:
        object_name: Name of the object

    Returns:
        Tuple of (object_id, object_type) or None if not found
    """
    con = get_duckdb_connection()

    # Try to find in our custom tables first (planets, moons, asterisms, constellations)
    query = """
        SELECT 'planet' as object_type, id, name FROM planets WHERE name = ?
        UNION ALL
        SELECT 'moon' as object_type, id, name FROM moons WHERE name = ?
        UNION ALL
        SELECT 'asterism' as object_type, id, name FROM asterisms WHERE name = ?
        UNION ALL
        SELECT 'constellation' as object_type, id, name FROM constellations WHERE name = ?
        LIMIT 1
    """
    result = con.execute(query, [object_name] * 4).fetchone()
    if result:
        return (result[1], result[0])  # (id, object_type)

    # For stars and DSOs from starplot, we don't have IDs in our database
    # Use a hash of the name as a stable ID
    # Get the object to determine its type

    db = DuckDBCatalogDatabase()
    obj = await db.get_by_name(object_name)
    if obj:
        # Generate a stable hash-based ID for stars/DSOs
        # Use first 8 bytes of MD5 hash as integer (positive)
        hash_obj = hashlib.md5(object_name.encode())
        object_id = int(hash_obj.hexdigest()[:8], 16) % (2**31)  # Keep it in int32 range
        return (object_id, obj.object_type.value)

    return None


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
        con = get_duckdb_connection()

        # Get object ID and type
        obj_info = await _get_object_id_and_type(object_name)
        if not obj_info:
            logger.error(f"Object '{object_name}' not found in database")
            return None

        object_id, object_type = obj_info

        # Use current time if not provided
        if observed_at is None:
            observed_at = datetime.now(UTC)
        elif observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)

        # Calculate geohash if location provided
        location_geohash = None
        if location_lat is not None and location_lon is not None:
            from celestron_nexstar.api.location.geohash_utils import encode

            location_geohash = encode(location_lat, location_lon)

        # Insert observation and get ID
        # DuckDB supports RETURNING clause
        insert_query = """
            INSERT INTO observations (
                object_type, object_id, observed_at,
                location_lat, location_lon, location_geohash, location_name,
                seeing_quality, transparency, sky_brightness, weather_notes,
                telescope, eyepiece, filters, notes, rating,
                image_path, sketch_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """
        result = con.execute(
            insert_query,
            [
                object_type,
                object_id,
                observed_at.isoformat(),
                location_lat,
                location_lon,
                location_geohash,
                location_name,
                seeing_quality,
                transparency,
                sky_brightness,
                weather_notes,
                telescope,
                eyepiece,
                filters,
                notes,
                rating,
                image_path,
                sketch_path,
            ],
        ).fetchone()

        if result:
            observation_id = result[0]
            logger.info(f"Added observation for '{object_name}' (ID: {observation_id})")
            return observation_id
        return None

    except Exception as e:
        logger.error(f"Error adding observation: {e}", exc_info=True)
        return None


def _row_to_observation(row: tuple) -> Observation:
    """Convert a database row to an Observation dataclass."""
    from datetime import datetime

    def parse_datetime(value: str | datetime | None) -> datetime | None:
        """Parse datetime from string or return as-is if already datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Try ISO format first
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                # Fallback to dateutil parser
                try:
                    from dateutil.parser import parse as parse_date

                    return parse_date(value)
                except Exception:
                    logger.warning(f"Could not parse datetime: {value}")
                    return None
        return None

    return Observation(
        id=row[0],
        object_type=row[1],
        object_id=row[2],
        object_name=None,  # Not stored in table, would need to look up
        observed_at=parse_datetime(row[3]) or datetime.now(UTC),
        location_lat=row[4],
        location_lon=row[5],
        location_geohash=row[6],
        location_name=row[7],
        seeing_quality=row[8],
        transparency=row[9],
        sky_brightness=row[10],
        weather_notes=row[11],
        telescope=row[12],
        eyepiece=row[13],
        filters=row[14],
        notes=row[15],
        rating=row[16],
        image_path=row[17],
        sketch_path=row[18],
        created_at=parse_datetime(row[19]) or datetime.now(UTC),
        updated_at=parse_datetime(row[20]) or datetime.now(UTC),
    )


async def get_observation(observation_id: int) -> Observation | None:
    """
    Get an observation by ID.

    Args:
        observation_id: Observation ID

    Returns:
        Observation if found, None otherwise
    """
    try:
        con = get_duckdb_connection()

        query = """
            SELECT id, object_type, object_id, observed_at,
                   location_lat, location_lon, location_geohash, location_name,
                   seeing_quality, transparency, sky_brightness, weather_notes,
                   telescope, eyepiece, filters, notes, rating,
                   image_path, sketch_path, created_at, updated_at
            FROM observations
            WHERE id = ?
        """
        result = con.execute(query, [observation_id]).fetchone()
        if result:
            return _row_to_observation(result)
        return None

    except Exception as e:
        logger.error(f"Error getting observation: {e}", exc_info=True)
        return None


async def get_observations(
    limit: int | None = None,
    offset: int = 0,
    order_by: str = "observed_at",
    order_desc: bool = True,
) -> list[Observation]:
    """
    Get all observations.

    Args:
        limit: Maximum number of observations to return
        offset: Number of observations to skip
        order_by: Field to order by (default: observed_at)
        order_desc: Order descending (default: True)

    Returns:
        List of Observation instances
    """
    try:
        con = get_duckdb_connection()

        # Build query
        order_direction = "DESC" if order_desc else "ASC"
        query = f"""
            SELECT id, object_type, object_id, observed_at,
                   location_lat, location_lon, location_geohash, location_name,
                   seeing_quality, transparency, sky_brightness, weather_notes,
                   telescope, eyepiece, filters, notes, rating,
                   image_path, sketch_path, created_at, updated_at
            FROM observations
            ORDER BY {order_by} {order_direction}
        """
        if limit:
            query += f" LIMIT {limit}"
        if offset:
            query += f" OFFSET {offset}"

        results = con.execute(query).fetchall()
        return [_row_to_observation(row) for row in results]

    except Exception as e:
        logger.error(f"Error getting observations: {e}", exc_info=True)
        return []


async def get_observations_by_object(
    object_name: str,
    limit: int | None = None,
) -> list[Observation]:
    """
    Get all observations for a specific object.

    Args:
        object_name: Name of the object
        limit: Maximum number of observations to return

    Returns:
        List of Observation instances
    """
    try:
        con = get_duckdb_connection()

        # Get object ID and type
        obj_info = await _get_object_id_and_type(object_name)
        if not obj_info:
            logger.warning(f"Object '{object_name}' not found in database")
            return []

        object_id, object_type = obj_info

        # Query observations
        query = """
            SELECT id, object_type, object_id, observed_at,
                   location_lat, location_lon, location_geohash, location_name,
                   seeing_quality, transparency, sky_brightness, weather_notes,
                   telescope, eyepiece, filters, notes, rating,
                   image_path, sketch_path, created_at, updated_at
            FROM observations
            WHERE object_type = ? AND object_id = ?
            ORDER BY observed_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        results = con.execute(query, [object_type, object_id]).fetchall()
        return [_row_to_observation(row) for row in results]

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
        con = get_duckdb_connection()

        # Check if observation exists
        check_query = "SELECT id FROM observations WHERE id = ?"
        if not con.execute(check_query, [observation_id]).fetchone():
            logger.error(f"Observation {observation_id} not found")
            return False

        # Build UPDATE query with only provided fields
        updates = []
        params = []

        if observed_at is not None:
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            updates.append("observed_at = ?")
            params.append(observed_at.isoformat())
        if location_lat is not None:
            updates.append("location_lat = ?")
            params.append(location_lat)
        if location_lon is not None:
            updates.append("location_lon = ?")
            params.append(location_lon)
        if location_name is not None:
            updates.append("location_name = ?")
            params.append(location_name)
        if seeing_quality is not None:
            updates.append("seeing_quality = ?")
            params.append(seeing_quality)
        if transparency is not None:
            updates.append("transparency = ?")
            params.append(transparency)
        if sky_brightness is not None:
            updates.append("sky_brightness = ?")
            params.append(sky_brightness)
        if weather_notes is not None:
            updates.append("weather_notes = ?")
            params.append(weather_notes)
        if telescope is not None:
            updates.append("telescope = ?")
            params.append(telescope)
        if eyepiece is not None:
            updates.append("eyepiece = ?")
            params.append(eyepiece)
        if filters is not None:
            updates.append("filters = ?")
            params.append(filters)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if image_path is not None:
            updates.append("image_path = ?")
            params.append(image_path)
        if sketch_path is not None:
            updates.append("sketch_path = ?")
            params.append(sketch_path)

        # Update geohash if location changed
        if location_lat is not None and location_lon is not None:
            from celestron_nexstar.api.location.geohash_utils import encode

            location_geohash = encode(location_lat, location_lon)
            updates.append("location_geohash = ?")
            params.append(location_geohash)

        if not updates:
            logger.warning("No fields to update")
            return False

        # Add updated_at timestamp
        updates.append("updated_at = CURRENT_TIMESTAMP")

        # Execute update
        update_query = f"UPDATE observations SET {', '.join(updates)} WHERE id = ?"
        params.append(observation_id)
        con.execute(update_query, params)

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
        con = get_duckdb_connection()

        # Check if exists
        check_query = "SELECT id FROM observations WHERE id = ?"
        if not con.execute(check_query, [observation_id]).fetchone():
            logger.error(f"Observation {observation_id} not found")
            return False

        # Delete
        delete_query = "DELETE FROM observations WHERE id = ?"
        con.execute(delete_query, [observation_id])

        logger.info(f"Deleted observation {observation_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting observation: {e}", exc_info=True)
        return False
