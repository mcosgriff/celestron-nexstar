"""
DuckDB Native Access Functions

Native DuckDB query functions for all database models.
These replace SQLAlchemy ORM with direct DuckDB queries for better performance.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

from celestron_nexstar.api.database.duckdb_connection import get_duckdb_connection
from celestron_nexstar.api.database.duckdb_models import (
    TLE,
    BortleCharacteristics,
    Camera,
    Comet,
    DarkSkySite,
    Eclipse,
    EphemerisFile,
    Eyepiece,
    Filter,
    HistoricalWeather,
    ISSPass,
    LightPollutionGrid,
    MeteorShower,
    RSSFeed,
    SpaceEvent,
    StarNameMapping,
    UserPreference,
    VariableStar,
    WeatherForecast,
)


logger = logging.getLogger(__name__)

# ============================================================================
# User Preferences
# ============================================================================


def get_user_preference(key: str) -> UserPreference | None:
    """Get a user preference by key."""
    con = get_duckdb_connection()
    result = con.execute(
        "SELECT key, value, category, description, created_at, updated_at FROM user_preferences WHERE key = ?",
        [key],
    ).fetchone()
    if not result:
        return None
    return UserPreference(
        key=result[0],
        value=result[1],
        category=result[2],
        description=result[3],
        created_at=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
        updated_at=datetime.fromisoformat(result[5]) if isinstance(result[5], str) else result[5],
    )


def set_user_preference(key: str, value: str, category: str, description: str | None = None) -> None:
    """Set a user preference (creates or updates)."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO user_preferences (key, value, category, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            updated_at = EXCLUDED.updated_at
        """,
        [key, value, category, description, now, now],
    )


def create_user_preference(key: str, value: str, category: str, description: str | None = None) -> None:
    """Create a new user preference (fails if key already exists)."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO user_preferences (key, value, category, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [key, value, category, description, now, now],
    )


def update_user_preference(
    key: str,
    value: str,
    category: str | None = None,
    description: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Update an existing user preference (fails if key doesn't exist)."""
    con = get_duckdb_connection()
    now = (updated_at if updated_at else datetime.now(UTC)).isoformat()
    if category is not None and description is not None:
        con.execute(
            """
            UPDATE user_preferences
            SET value = ?, category = ?, description = ?, updated_at = ?
            WHERE key = ?
            """,
            [value, category, description, now, key],
        )
    elif category is not None:
        con.execute(
            """
            UPDATE user_preferences
            SET value = ?, category = ?, updated_at = ?
            WHERE key = ?
            """,
            [value, category, now, key],
        )
    else:
        con.execute(
            """
            UPDATE user_preferences
            SET value = ?, updated_at = ?
            WHERE key = ?
            """,
            [value, now, key],
        )


def get_user_preferences_by_category(category: str) -> list[UserPreference]:
    """Get all user preferences in a category."""
    con = get_duckdb_connection()
    results = con.execute(
        "SELECT key, value, category, description, created_at, updated_at FROM user_preferences WHERE category = ?",
        [category],
    ).fetchall()
    return [
        UserPreference(
            key=row[0],
            value=row[1],
            category=row[2],
            description=row[3],
            created_at=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
            updated_at=datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5],
        )
        for row in results
    ]


def delete_user_preference(key: str) -> None:
    """Delete a user preference."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM user_preferences WHERE key = ?", [key])


# ============================================================================
# Equipment - Eyepieces
# ============================================================================


def get_eyepiece(eyepiece_id: int) -> Eyepiece | None:
    """Get an eyepiece by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, focal_length_mm, apparent_fov_deg, barrel_size_mm, manufacturer, model, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM eyepieces WHERE id = ?
        """,
        [eyepiece_id],
    ).fetchone()
    if not result:
        return None
    return Eyepiece(
        id=result[0],
        name=result[1],
        focal_length_mm=result[2],
        apparent_fov_deg=result[3],
        barrel_size_mm=result[4],
        manufacturer=result[5],
        model=result[6],
        notes=result[7],
        usage_count=result[8],
        last_used_at=datetime.fromisoformat(result[9]) if result[9] and isinstance(result[9], str) else result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_all_eyepieces() -> list[Eyepiece]:
    """Get all eyepieces."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, name, focal_length_mm, apparent_fov_deg, barrel_size_mm, manufacturer, model, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM eyepieces ORDER BY name
        """
    ).fetchall()
    return [
        Eyepiece(
            id=row[0],
            name=row[1],
            focal_length_mm=row[2],
            apparent_fov_deg=row[3],
            barrel_size_mm=row[4],
            manufacturer=row[5],
            model=row[6],
            notes=row[7],
            usage_count=row[8],
            last_used_at=datetime.fromisoformat(row[9]) if row[9] and isinstance(row[9], str) else row[9],
            created_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
            updated_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
        )
        for row in results
    ]


def create_eyepiece(
    name: str,
    focal_length_mm: float,
    apparent_fov_deg: float = 50.0,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> int:
    """Create a new eyepiece. Returns the ID of the created eyepiece."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO eyepieces (name, focal_length_mm, apparent_fov_deg, barrel_size_mm, manufacturer, model, notes,
                              usage_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        [name, focal_length_mm, apparent_fov_deg, barrel_size_mm, manufacturer, model, notes, now, now],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_eyepiece(eyepiece_id: int, **kwargs: Any) -> None:
    """Update an eyepiece. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    for key, value in kwargs.items():
        if key in ("name", "focal_length_mm", "apparent_fov_deg", "barrel_size_mm", "manufacturer", "model", "notes"):
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(eyepiece_id)
    con.execute(f"UPDATE eyepieces SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_eyepiece(eyepiece_id: int) -> None:
    """Delete an eyepiece."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM eyepieces WHERE id = ?", [eyepiece_id])


# ============================================================================
# Equipment - Filters
# ============================================================================


def get_filter(filter_id: int) -> Filter | None:
    """Get a filter by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, filter_type, barrel_size_mm, manufacturer, model, transmission_percent, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM filters WHERE id = ?
        """,
        [filter_id],
    ).fetchone()
    if not result:
        return None
    return Filter(
        id=result[0],
        name=result[1],
        filter_type=result[2],
        barrel_size_mm=result[3],
        manufacturer=result[4],
        model=result[5],
        transmission_percent=result[6],
        notes=result[7],
        usage_count=result[8],
        last_used_at=datetime.fromisoformat(result[9]) if result[9] and isinstance(result[9], str) else result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_all_filters() -> list[Filter]:
    """Get all filters."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, name, filter_type, barrel_size_mm, manufacturer, model, transmission_percent, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM filters ORDER BY name
        """
    ).fetchall()
    return [
        Filter(
            id=row[0],
            name=row[1],
            filter_type=row[2],
            barrel_size_mm=row[3],
            manufacturer=row[4],
            model=row[5],
            transmission_percent=row[6],
            notes=row[7],
            usage_count=row[8],
            last_used_at=datetime.fromisoformat(row[9]) if row[9] and isinstance(row[9], str) else row[9],
            created_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
            updated_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
        )
        for row in results
    ]


def create_filter(
    name: str,
    filter_type: str,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    transmission_percent: float | None = None,
    notes: str | None = None,
) -> int:
    """Create a new filter. Returns the ID of the created filter."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO filters (name, filter_type, barrel_size_mm, manufacturer, model, transmission_percent, notes,
                            usage_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        [name, filter_type, barrel_size_mm, manufacturer, model, transmission_percent, notes, now, now],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_filter(filter_id: int, **kwargs: Any) -> None:
    """Update a filter. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    for key, value in kwargs.items():
        if key in ("name", "filter_type", "barrel_size_mm", "manufacturer", "model", "transmission_percent", "notes"):
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(filter_id)
    con.execute(f"UPDATE filters SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_filter(filter_id: int) -> None:
    """Delete a filter."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM filters WHERE id = ?", [filter_id])


# ============================================================================
# Equipment - Cameras
# ============================================================================


def get_camera(camera_id: int) -> Camera | None:
    """Get a camera by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, sensor_width_mm, sensor_height_mm, pixel_width_um, pixel_height_um,
               resolution_width, resolution_height, camera_type, manufacturer, model, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM cameras WHERE id = ?
        """,
        [camera_id],
    ).fetchone()
    if not result:
        return None
    return Camera(
        id=result[0],
        name=result[1],
        sensor_width_mm=result[2] or 0.0,  # Handle NULL
        sensor_height_mm=result[3] or 0.0,  # Handle NULL
        pixel_width_um=result[4],
        pixel_height_um=result[5],
        resolution_width=result[6],
        resolution_height=result[7],
        camera_type=result[8],
        manufacturer=result[9],
        model=result[10],
        notes=result[11],
        usage_count=result[12],
        last_used_at=datetime.fromisoformat(result[13]) if result[13] and isinstance(result[13], str) else result[13],
        created_at=datetime.fromisoformat(result[14]) if isinstance(result[14], str) else result[14],
        updated_at=datetime.fromisoformat(result[15]) if isinstance(result[15], str) else result[15],
    )


def get_all_cameras() -> list[Camera]:
    """Get all cameras."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, name, sensor_width_mm, sensor_height_mm, pixel_width_um, pixel_height_um,
               resolution_width, resolution_height, camera_type, manufacturer, model, notes,
               usage_count, last_used_at, created_at, updated_at
        FROM cameras ORDER BY name
        """
    ).fetchall()
    return [
        Camera(
            id=row[0],
            name=row[1],
            sensor_width_mm=row[2] or 0.0,
            sensor_height_mm=row[3] or 0.0,
            pixel_width_um=row[4],
            pixel_height_um=row[5],
            resolution_width=row[6],
            resolution_height=row[7],
            camera_type=row[8],
            manufacturer=row[9],
            model=row[10],
            notes=row[11],
            usage_count=row[12],
            last_used_at=datetime.fromisoformat(row[13]) if row[13] and isinstance(row[13], str) else row[13],
            created_at=datetime.fromisoformat(row[14]) if isinstance(row[14], str) else row[14],
            updated_at=datetime.fromisoformat(row[15]) if isinstance(row[15], str) else row[15],
        )
        for row in results
    ]


def create_camera(
    name: str,
    sensor_width_mm: float,
    sensor_height_mm: float,
    camera_type: str = "DSLR",
    pixel_width_um: float | None = None,
    pixel_height_um: float | None = None,
    resolution_width: int | None = None,
    resolution_height: int | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> int:
    """Create a new camera. Returns the ID of the created camera."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO cameras (name, sensor_width_mm, sensor_height_mm, pixel_width_um, pixel_height_um,
                            resolution_width, resolution_height, camera_type, manufacturer, model, notes,
                            usage_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        [
            name,
            sensor_width_mm,
            sensor_height_mm,
            pixel_width_um,
            pixel_height_um,
            resolution_width,
            resolution_height,
            camera_type,
            manufacturer,
            model,
            notes,
            now,
            now,
        ],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_camera(camera_id: int, **kwargs: Any) -> None:
    """Update a camera. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = (
        "name",
        "sensor_width_mm",
        "sensor_height_mm",
        "pixel_width_um",
        "pixel_height_um",
        "resolution_width",
        "resolution_height",
        "camera_type",
        "manufacturer",
        "model",
        "notes",
    )
    for key, value in kwargs.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(camera_id)
    con.execute(f"UPDATE cameras SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_camera(camera_id: int) -> None:
    """Delete a camera."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM cameras WHERE id = ?", [camera_id])


# ============================================================================
# Weather Forecast
# ============================================================================


def get_weather_forecast(latitude: float, longitude: float, forecast_timestamp: datetime) -> WeatherForecast | None:
    """Get a weather forecast for a specific location and timestamp."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, latitude, longitude, geohash, forecast_timestamp, temperature_f, dew_point_f,
               humidity_percent, cloud_cover_percent, wind_speed_mph, seeing_score, fetched_at
        FROM weather_forecast
        WHERE latitude = ? AND longitude = ? AND forecast_timestamp = ?
        """,
        [latitude, longitude, forecast_timestamp.isoformat()],
    ).fetchone()
    if not result:
        return None
    return WeatherForecast(
        id=result[0],
        latitude=result[1],
        longitude=result[2],
        geohash=result[3],
        forecast_timestamp=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
        temperature_f=result[5],
        dew_point_f=result[6],
        humidity_percent=result[7],
        cloud_cover_percent=result[8],
        wind_speed_mph=result[9],
        seeing_score=result[10],
        fetched_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_weather_forecasts_for_location(
    latitude: float, longitude: float, start_time: datetime | None = None, end_time: datetime | None = None
) -> list[WeatherForecast]:
    """Get all weather forecasts for a location, optionally filtered by time range."""
    con = get_duckdb_connection()
    query = """
        SELECT id, latitude, longitude, geohash, forecast_timestamp, temperature_f, dew_point_f,
               humidity_percent, cloud_cover_percent, wind_speed_mph, seeing_score, fetched_at
        FROM weather_forecast
        WHERE latitude = ? AND longitude = ?
    """
    params = [latitude, longitude]
    if start_time:
        query += " AND forecast_timestamp >= ?"
        params.append(start_time.isoformat())
    if end_time:
        query += " AND forecast_timestamp <= ?"
        params.append(end_time.isoformat())
    query += " ORDER BY forecast_timestamp"
    results = con.execute(query, params).fetchall()
    return [
        WeatherForecast(
            id=row[0],
            latitude=row[1],
            longitude=row[2],
            geohash=row[3],
            forecast_timestamp=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
            temperature_f=row[5],
            dew_point_f=row[6],
            humidity_percent=row[7],
            cloud_cover_percent=row[8],
            wind_speed_mph=row[9],
            seeing_score=row[10],
            fetched_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
        )
        for row in results
    ]


# Lock for weather forecast ID generation to prevent race conditions
_weather_forecast_lock = threading.Lock()


def create_weather_forecast(
    latitude: float,
    longitude: float,
    forecast_timestamp: datetime,
    geohash: str | None = None,
    temperature_f: float | None = None,
    dew_point_f: float | None = None,
    humidity_percent: float | None = None,
    cloud_cover_percent: float | None = None,
    wind_speed_mph: float | None = None,
    seeing_score: float | None = None,
    fetched_at: datetime | None = None,
) -> int:
    """Create a new weather forecast. Returns the ID of the created forecast."""
    if fetched_at is None:
        fetched_at = datetime.now(UTC)

    # Use lock to prevent race condition when calculating next ID
    with _weather_forecast_lock:
        con = get_duckdb_connection()
        # DuckDB doesn't auto-increment INTEGER PRIMARY KEY - calculate next ID
        # Use transaction to ensure atomicity and prevent write-write conflicts
        try:
            con.execute("BEGIN TRANSACTION")
            max_id_result = con.execute("SELECT COALESCE(MAX(id), 0) FROM weather_forecast").fetchone()
            next_id = (max_id_result[0] if max_id_result else 0) + 1

            con.execute(
                """
                INSERT INTO weather_forecast (id, latitude, longitude, geohash, forecast_timestamp, temperature_f,
                                             dew_point_f, humidity_percent, cloud_cover_percent, wind_speed_mph,
                                             seeing_score, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    next_id,
                    latitude,
                    longitude,
                    geohash,
                    forecast_timestamp.isoformat(),
                    temperature_f,
                    dew_point_f,
                    humidity_percent,
                    cloud_cover_percent,
                    wind_speed_mph,
                    seeing_score,
                    fetched_at.isoformat(),
                ],
            )
            con.execute("COMMIT")
            return next_id
        except Exception as e:
            con.execute("ROLLBACK")
            logger.error(f"Error creating weather forecast: {e}")
            raise


def update_weather_forecast(
    forecast_id: int,
    latitude: float | None = None,
    longitude: float | None = None,
    geohash: str | None = None,
    forecast_timestamp: datetime | None = None,
    temperature_f: float | None = None,
    dew_point_f: float | None = None,
    humidity_percent: float | None = None,
    cloud_cover_percent: float | None = None,
    wind_speed_mph: float | None = None,
    seeing_score: float | None = None,
    fetched_at: datetime | None = None,
) -> None:
    """Update an existing weather forecast."""
    # Build UPDATE query dynamically based on provided parameters
    updates = []
    params = []

    if latitude is not None:
        updates.append("latitude = ?")
        params.append(latitude)
    if longitude is not None:
        updates.append("longitude = ?")
        params.append(longitude)
    if geohash is not None:
        updates.append("geohash = ?")
        params.append(geohash)
    if forecast_timestamp is not None:
        updates.append("forecast_timestamp = ?")
        params.append(forecast_timestamp.isoformat())
    if temperature_f is not None:
        updates.append("temperature_f = ?")
        params.append(temperature_f)
    if dew_point_f is not None:
        updates.append("dew_point_f = ?")
        params.append(dew_point_f)
    if humidity_percent is not None:
        updates.append("humidity_percent = ?")
        params.append(humidity_percent)
    if cloud_cover_percent is not None:
        updates.append("cloud_cover_percent = ?")
        params.append(cloud_cover_percent)
    if wind_speed_mph is not None:
        updates.append("wind_speed_mph = ?")
        params.append(wind_speed_mph)
    if seeing_score is not None:
        updates.append("seeing_score = ?")
        params.append(seeing_score)
    if fetched_at is not None:
        updates.append("fetched_at = ?")
        params.append(fetched_at.isoformat())

    if not updates:
        return  # Nothing to update

    params.append(forecast_id)
    query = f"UPDATE weather_forecast SET {', '.join(updates)} WHERE id = ?"
    
    # Retry logic for write-write conflicts
    max_retries = 3
    retry_delay = 0.01  # Start with 10ms
    
    for attempt in range(max_retries):
        try:
            # Use lock to prevent write-write conflicts in DuckDB
            with _weather_forecast_lock:
                con = get_duckdb_connection()
                
                # Ensure any previous transaction is rolled back
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass  # No active transaction, that's fine
                
                # Use transaction to ensure atomicity and prevent write-write conflicts
                try:
                    con.execute("BEGIN TRANSACTION")
                    con.execute(query, params)
                    con.execute("COMMIT")
                    return  # Success
                except Exception as e:
                    try:
                        con.execute("ROLLBACK")
                    except Exception:
                        pass  # Ignore rollback errors
                    raise
        except Exception as e:
            error_msg = str(e).lower()
            if "write-write conflict" in error_msg or "transactioncontext" in error_msg:
                if attempt < max_retries - 1:
                    # Exponential backoff
                    time.sleep(retry_delay * (2 ** attempt))
                    logger.debug(f"Retrying weather forecast update for id {forecast_id} (attempt {attempt + 1}/{max_retries})")
                    continue
                else:
                    logger.error(f"Error updating weather forecast {forecast_id} after {max_retries} attempts: {e}")
                    raise
            else:
                # Non-retryable error
                logger.error(f"Error updating weather forecast {forecast_id}: {e}")
                raise


def delete_old_weather_forecasts(latitude: float, longitude: float, before_timestamp: datetime) -> int:
    """Delete weather forecasts older than the specified timestamp. Returns number of rows deleted."""
    # Use lock to prevent write-write conflicts in DuckDB
    with _weather_forecast_lock:
        con = get_duckdb_connection()
        # Use transaction to ensure atomicity and prevent write-write conflicts
        try:
            con.execute("BEGIN TRANSACTION")
            result = con.execute(
                "DELETE FROM weather_forecast WHERE latitude = ? AND longitude = ? AND fetched_at < ?",
                [latitude, longitude, before_timestamp.isoformat()],
            )
            con.execute("COMMIT")
            return result.rowcount if hasattr(result, "rowcount") else 0
        except Exception as e:
            con.execute("ROLLBACK")
            logger.error(f"Error deleting old weather forecasts: {e}")
            raise


# ============================================================================
# Historical Weather
# ============================================================================


def get_historical_weather(latitude: float, longitude: float, month: int) -> HistoricalWeather | None:
    """Get historical weather data for a location and month."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, latitude, longitude, geohash, month, avg_cloud_cover_percent, min_cloud_cover_percent,
               max_cloud_cover_percent, p25_cloud_cover_percent, p40_cloud_cover_percent,
               p60_cloud_cover_percent, p75_cloud_cover_percent, std_dev_cloud_cover_percent,
               years_of_data, fetched_at
        FROM historical_weather
        WHERE latitude = ? AND longitude = ? AND month = ?
        """,
        [latitude, longitude, month],
    ).fetchone()
    if not result:
        return None
    return HistoricalWeather(
        id=result[0],
        latitude=result[1],
        longitude=result[2],
        geohash=result[3],
        month=result[4],
        avg_cloud_cover_percent=result[5],
        min_cloud_cover_percent=result[6],
        max_cloud_cover_percent=result[7],
        p25_cloud_cover_percent=result[8],
        p40_cloud_cover_percent=result[9],
        p60_cloud_cover_percent=result[10],
        p75_cloud_cover_percent=result[11],
        std_dev_cloud_cover_percent=result[12],
        years_of_data=result[13],
        fetched_at=datetime.fromisoformat(result[14]) if isinstance(result[14], str) else result[14],
    )


def create_or_update_historical_weather(
    latitude: float,
    longitude: float,
    month: int,
    geohash: str | None = None,
    avg_cloud_cover_percent: float | None = None,
    min_cloud_cover_percent: float | None = None,
    max_cloud_cover_percent: float | None = None,
    p25_cloud_cover_percent: float | None = None,
    p40_cloud_cover_percent: float | None = None,
    p60_cloud_cover_percent: float | None = None,
    p75_cloud_cover_percent: float | None = None,
    std_dev_cloud_cover_percent: float | None = None,
    years_of_data: int | None = None,
    fetched_at: datetime | None = None,
) -> int:
    """Create or update historical weather data. Returns the ID."""
    con = get_duckdb_connection()
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    # Check if exists
    existing = con.execute(
        "SELECT id FROM historical_weather WHERE latitude = ? AND longitude = ? AND month = ?",
        [latitude, longitude, month],
    ).fetchone()
    if existing:
        # Update
        con.execute(
            """
            UPDATE historical_weather
            SET geohash = ?, avg_cloud_cover_percent = ?, min_cloud_cover_percent = ?,
                max_cloud_cover_percent = ?, p25_cloud_cover_percent = ?, p40_cloud_cover_percent = ?,
                p60_cloud_cover_percent = ?, p75_cloud_cover_percent = ?, std_dev_cloud_cover_percent = ?,
                years_of_data = ?, fetched_at = ?
            WHERE latitude = ? AND longitude = ? AND month = ?
            """,
            [
                geohash,
                avg_cloud_cover_percent,
                min_cloud_cover_percent,
                max_cloud_cover_percent,
                p25_cloud_cover_percent,
                p40_cloud_cover_percent,
                p60_cloud_cover_percent,
                p75_cloud_cover_percent,
                std_dev_cloud_cover_percent,
                years_of_data,
                fetched_at.isoformat(),
                latitude,
                longitude,
                month,
            ],
        )
        return existing[0]
    else:
        # Insert - DuckDB doesn't auto-increment INTEGER PRIMARY KEY - calculate next ID
        max_id_result = con.execute("SELECT COALESCE(MAX(id), 0) FROM historical_weather").fetchone()
        next_id = (max_id_result[0] if max_id_result else 0) + 1

        con.execute(
            """
            INSERT INTO historical_weather (id, latitude, longitude, geohash, month, avg_cloud_cover_percent,
                                           min_cloud_cover_percent, max_cloud_cover_percent,
                                           p25_cloud_cover_percent, p40_cloud_cover_percent,
                                           p60_cloud_cover_percent, p75_cloud_cover_percent,
                                           std_dev_cloud_cover_percent, years_of_data, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                next_id,
                latitude,
                longitude,
                geohash,
                month,
                avg_cloud_cover_percent,
                min_cloud_cover_percent,
                max_cloud_cover_percent,
                p25_cloud_cover_percent,
                p40_cloud_cover_percent,
                p60_cloud_cover_percent,
                p75_cloud_cover_percent,
                std_dev_cloud_cover_percent,
                years_of_data,
                fetched_at.isoformat(),
            ],
        )
        return next_id


# ============================================================================
# Light Pollution Grid
# ============================================================================


def get_light_pollution_grid_point(latitude: float, longitude: float) -> LightPollutionGrid | None:
    """Get a light pollution grid point by coordinates."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, latitude, longitude, geohash, sqm_value, region, created_at
        FROM light_pollution_grid
        WHERE latitude = ? AND longitude = ?
        """,
        [latitude, longitude],
    ).fetchone()
    if not result:
        return None
    return LightPollutionGrid(
        id=result[0],
        latitude=result[1],
        longitude=result[2],
        geohash=result[3],
        sqm_value=result[4],
        region=result[5],
        created_at=result[6],
    )


def get_light_pollution_grid_points_by_geohash(geohash_prefix: str, limit: int = 100) -> list[LightPollutionGrid]:
    """Get light pollution grid points matching a geohash prefix."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, latitude, longitude, geohash, sqm_value, region, created_at
        FROM light_pollution_grid
        WHERE geohash LIKE ?
        LIMIT ?
        """,
        [f"{geohash_prefix}%", limit],
    ).fetchall()
    return [
        LightPollutionGrid(
            id=row[0],
            latitude=row[1],
            longitude=row[2],
            geohash=row[3],
            sqm_value=row[4],
            region=row[5],
            created_at=row[6],
        )
        for row in results
    ]


def create_or_update_light_pollution_grid_point(
    latitude: float,
    longitude: float,
    geohash: str,
    sqm_value: float,
    region: str | None = None,
    created_at: str | None = None,
) -> int:
    """Create or update a light pollution grid point. Returns the ID."""
    con = get_duckdb_connection()
    if created_at is None:
        created_at = datetime.now(UTC).isoformat()
    # Check if exists
    existing = con.execute(
        "SELECT id FROM light_pollution_grid WHERE latitude = ? AND longitude = ?",
        [latitude, longitude],
    ).fetchone()
    if existing:
        # Update
        con.execute(
            "UPDATE light_pollution_grid SET geohash = ?, sqm_value = ?, region = ?, created_at = ? WHERE id = ?",
            [geohash, sqm_value, region, created_at, existing[0]],
        )
        return existing[0]
    else:
        # Insert
        con.execute(
            "INSERT INTO light_pollution_grid (latitude, longitude, geohash, sqm_value, region, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [latitude, longitude, geohash, sqm_value, region, created_at],
        )
        result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
        return result[0] if result else 0


# ============================================================================
# ISS Passes
# ============================================================================


def get_iss_pass(iss_pass_id: int) -> ISSPass | None:
    """Get an ISS pass by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, latitude, longitude, geohash, rise_time, max_time, set_time, duration_seconds,
               max_altitude_deg, magnitude, rise_azimuth_deg, max_azimuth_deg, set_azimuth_deg,
               is_visible, fetched_at
        FROM iss_passes WHERE id = ?
        """,
        [iss_pass_id],
    ).fetchone()
    if not result:
        return None
    return ISSPass(
        id=result[0],
        latitude=result[1],
        longitude=result[2],
        geohash=result[3],
        rise_time=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
        max_time=datetime.fromisoformat(result[5]) if isinstance(result[5], str) else result[5],
        set_time=datetime.fromisoformat(result[6]) if isinstance(result[6], str) else result[6],
        duration_seconds=result[7],
        max_altitude_deg=result[8],
        magnitude=result[9],
        rise_azimuth_deg=result[10],
        max_azimuth_deg=result[11],
        set_azimuth_deg=result[12],
        is_visible=bool(result[13]),
        fetched_at=datetime.fromisoformat(result[14]) if isinstance(result[14], str) else result[14],
    )


def get_iss_passes_for_location(
    latitude: float, longitude: float, start_time: datetime | None = None, limit: int = 50
) -> list[ISSPass]:
    """Get ISS passes for a location, optionally filtered by start time."""
    con = get_duckdb_connection()
    query = """
        SELECT id, latitude, longitude, geohash, rise_time, max_time, set_time, duration_seconds,
               max_altitude_deg, magnitude, rise_azimuth_deg, max_azimuth_deg, set_azimuth_deg,
               is_visible, fetched_at
        FROM iss_passes
        WHERE latitude = ? AND longitude = ?
    """
    params = [latitude, longitude]
    if start_time:
        query += " AND rise_time >= ?"
        params.append(start_time.isoformat())
    query += " ORDER BY rise_time LIMIT ?"
    params.append(limit)
    results = con.execute(query, params).fetchall()
    return [
        ISSPass(
            id=row[0],
            latitude=row[1],
            longitude=row[2],
            geohash=row[3],
            rise_time=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
            max_time=datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5],
            set_time=datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
            duration_seconds=row[7],
            max_altitude_deg=row[8],
            magnitude=row[9],
            rise_azimuth_deg=row[10],
            max_azimuth_deg=row[11],
            set_azimuth_deg=row[12],
            is_visible=bool(row[13]),
            fetched_at=datetime.fromisoformat(row[14]) if isinstance(row[14], str) else row[14],
        )
        for row in results
    ]


def create_iss_pass(
    latitude: float,
    longitude: float,
    rise_time: datetime,
    max_time: datetime,
    set_time: datetime,
    duration_seconds: int,
    max_altitude_deg: float,
    rise_azimuth_deg: float,
    max_azimuth_deg: float,
    set_azimuth_deg: float,
    geohash: str | None = None,
    magnitude: float | None = None,
    is_visible: bool = True,
    fetched_at: datetime | None = None,
) -> int:
    """Create a new ISS pass. Returns the ID."""
    con = get_duckdb_connection()
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    # Convert numpy.bool to Python bool for DuckDB compatibility
    is_visible_bool = bool(is_visible) if is_visible is not None else True
    con.execute(
        """
        INSERT INTO iss_passes (latitude, longitude, geohash, rise_time, max_time, set_time,
                               duration_seconds, max_altitude_deg, magnitude, rise_azimuth_deg,
                               max_azimuth_deg, set_azimuth_deg, is_visible, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            latitude,
            longitude,
            geohash,
            rise_time.isoformat(),
            max_time.isoformat(),
            set_time.isoformat(),
            duration_seconds,
            max_altitude_deg,
            magnitude,
            rise_azimuth_deg,
            max_azimuth_deg,
            set_azimuth_deg,
            is_visible_bool,
            fetched_at.isoformat(),
        ],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def delete_old_iss_passes(latitude: float, longitude: float, before_timestamp: datetime) -> int:
    """Delete ISS passes older than the specified timestamp. Returns number of rows deleted."""
    con = get_duckdb_connection()
    result = con.execute(
        "DELETE FROM iss_passes WHERE latitude = ? AND longitude = ? AND fetched_at < ?",
        [latitude, longitude, before_timestamp.isoformat()],
    )
    return result.rowcount if hasattr(result, "rowcount") else 0


# ============================================================================
# Dark Sky Sites
# ============================================================================


def get_dark_sky_site(site_id: int) -> DarkSkySite | None:
    """Get a dark sky site by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, latitude, longitude, geohash, bortle_class, sqm_value, description, notes,
               created_at, updated_at
        FROM dark_sky_sites WHERE id = ?
        """,
        [site_id],
    ).fetchone()
    if not result:
        return None
    return DarkSkySite(
        id=result[0],
        name=result[1],
        latitude=result[2],
        longitude=result[3],
        geohash=result[4],
        bortle_class=result[5],
        sqm_value=result[6],
        description=result[7],
        notes=result[8],
        created_at=datetime.fromisoformat(result[9]) if isinstance(result[9], str) else result[9],
        updated_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
    )


def get_dark_sky_site_by_name(name: str) -> DarkSkySite | None:
    """Get a dark sky site by name."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, latitude, longitude, geohash, bortle_class, sqm_value, description, notes,
               created_at, updated_at
        FROM dark_sky_sites WHERE name = ?
        """,
        [name],
    ).fetchone()
    if not result:
        return None
    return DarkSkySite(
        id=result[0],
        name=result[1],
        latitude=result[2],
        longitude=result[3],
        geohash=result[4],
        bortle_class=result[5],
        sqm_value=result[6],
        description=result[7],
        notes=result[8],
        created_at=datetime.fromisoformat(result[9]) if isinstance(result[9], str) else result[9],
        updated_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
    )


def get_all_dark_sky_sites() -> list[DarkSkySite]:
    """Get all dark sky sites."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, name, latitude, longitude, geohash, bortle_class, sqm_value, description, notes,
               created_at, updated_at
        FROM dark_sky_sites ORDER BY name
        """
    ).fetchall()
    return [
        DarkSkySite(
            id=row[0],
            name=row[1],
            latitude=row[2],
            longitude=row[3],
            geohash=row[4],
            bortle_class=row[5],
            sqm_value=row[6],
            description=row[7],
            notes=row[8],
            created_at=datetime.fromisoformat(row[9]) if isinstance(row[9], str) else row[9],
            updated_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
        )
        for row in results
    ]


def create_dark_sky_site(
    name: str,
    latitude: float,
    longitude: float,
    bortle_class: int,
    sqm_value: float,
    description: str,
    geohash: str | None = None,
    notes: str | None = None,
) -> int:
    """Create a new dark sky site. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO dark_sky_sites (name, latitude, longitude, geohash, bortle_class, sqm_value,
                                   description, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [name, latitude, longitude, geohash, bortle_class, sqm_value, description, notes, now, now],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_dark_sky_site(site_id: int, **kwargs: Any) -> None:
    """Update a dark sky site. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = ("name", "latitude", "longitude", "geohash", "bortle_class", "sqm_value", "description", "notes")
    for key, value in kwargs.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(site_id)
    con.execute(f"UPDATE dark_sky_sites SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_dark_sky_site(site_id: int) -> None:
    """Delete a dark sky site."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM dark_sky_sites WHERE id = ?", [site_id])


# ============================================================================
# Space Events
# ============================================================================


def get_space_event(event_id: int) -> SpaceEvent | None:
    """Get a space event by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, event_type, date, description, min_latitude, max_latitude, min_longitude,
               max_longitude, dark_sky_required, min_bortle_class, equipment_needed, viewing_notes,
               source, url, created_at, updated_at
        FROM space_events WHERE id = ?
        """,
        [event_id],
    ).fetchone()
    if not result:
        return None
    return SpaceEvent(
        id=result[0],
        name=result[1],
        event_type=result[2],
        date=datetime.fromisoformat(result[3]) if isinstance(result[3], str) else result[3],
        description=result[4],
        min_latitude=result[5],
        max_latitude=result[6],
        min_longitude=result[7],
        max_longitude=result[8],
        dark_sky_required=bool(result[9]),
        min_bortle_class=result[10],
        equipment_needed=result[11],
        viewing_notes=result[12],
        source=result[13],
        url=result[14],
        created_at=datetime.fromisoformat(result[15]) if isinstance(result[15], str) else result[15],
        updated_at=datetime.fromisoformat(result[16]) if isinstance(result[16], str) else result[16],
    )


def get_space_events(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_type: str | None = None,
    source: str | None = None,
    limit: int = 100,
) -> list[SpaceEvent]:
    """Get space events, optionally filtered by date range, type, and source."""
    con = get_duckdb_connection()
    query = "SELECT id, name, event_type, date, description, min_latitude, max_latitude, min_longitude, max_longitude, dark_sky_required, min_bortle_class, equipment_needed, viewing_notes, source, url, created_at, updated_at FROM space_events WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date.isoformat())
    if end_date:
        query += " AND date <= ?"
        params.append(end_date.isoformat())
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY date LIMIT ?"
    params.append(limit)
    results = con.execute(query, params).fetchall()
    return [
        SpaceEvent(
            id=row[0],
            name=row[1],
            event_type=row[2],
            date=datetime.fromisoformat(row[3]) if isinstance(row[3], str) else row[3],
            description=row[4],
            min_latitude=row[5],
            max_latitude=row[6],
            min_longitude=row[7],
            max_longitude=row[8],
            dark_sky_required=bool(row[9]),
            min_bortle_class=row[10],
            equipment_needed=row[11],
            viewing_notes=row[12],
            source=row[13],
            url=row[14],
            created_at=datetime.fromisoformat(row[15]) if isinstance(row[15], str) else row[15],
            updated_at=datetime.fromisoformat(row[16]) if isinstance(row[16], str) else row[16],
        )
        for row in results
    ]


def create_space_event(
    name: str,
    event_type: str,
    date: datetime,
    description: str,
    source: str = "Planetary Society",
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    dark_sky_required: bool = False,
    min_bortle_class: int | None = None,
    equipment_needed: str | None = None,
    viewing_notes: str | None = None,
    url: str | None = None,
) -> int:
    """Create a new space event. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO space_events (name, event_type, date, description, min_latitude, max_latitude,
                                 min_longitude, max_longitude, dark_sky_required, min_bortle_class,
                                 equipment_needed, viewing_notes, source, url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            name,
            event_type,
            date.isoformat(),
            description,
            min_latitude,
            max_latitude,
            min_longitude,
            max_longitude,
            dark_sky_required,
            min_bortle_class,
            equipment_needed,
            viewing_notes,
            source,
            url,
            now,
            now,
        ],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_space_event(event_id: int, **kwargs: Any) -> None:
    """Update a space event. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = (
        "name",
        "event_type",
        "date",
        "description",
        "min_latitude",
        "max_latitude",
        "min_longitude",
        "max_longitude",
        "dark_sky_required",
        "min_bortle_class",
        "equipment_needed",
        "viewing_notes",
        "source",
        "url",
    )
    for key, value in kwargs.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(event_id)
    con.execute(f"UPDATE space_events SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_space_event(event_id: int) -> None:
    """Delete a space event."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM space_events WHERE id = ?", [event_id])


def delete_space_events_by_source_and_date_range(source: str, start_date: datetime, end_date: datetime) -> None:
    """Delete space events by source and date range."""
    con = get_duckdb_connection()
    con.execute(
        "DELETE FROM space_events WHERE source = ? AND date >= ? AND date < ?",
        [source, start_date.isoformat(), end_date.isoformat()],
    )


def create_or_update_space_event(
    name: str,
    event_type: str,
    date: datetime,
    description: str,
    source: str = "Planetary Society",
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    dark_sky_required: bool = False,
    min_bortle_class: int | None = None,
    equipment_needed: str | None = None,
    viewing_notes: str | None = None,
    url: str | None = None,
) -> int:
    """Create or update a space event. Returns the ID."""
    con = get_duckdb_connection()
    # Check if exists by name, date, and source
    existing = con.execute(
        "SELECT id FROM space_events WHERE name = ? AND date = ? AND source = ?",
        [name, date.isoformat(), source],
    ).fetchone()

    now = datetime.now(UTC).isoformat()
    if existing:
        # Update
        con.execute(
            """
            UPDATE space_events SET event_type = ?, description = ?, min_latitude = ?,
                                 max_latitude = ?, min_longitude = ?, max_longitude = ?,
                                 dark_sky_required = ?, min_bortle_class = ?, equipment_needed = ?,
                                 viewing_notes = ?, url = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                event_type,
                description,
                min_latitude,
                max_latitude,
                min_longitude,
                max_longitude,
                dark_sky_required,
                min_bortle_class,
                equipment_needed,
                viewing_notes,
                url,
                now,
                existing[0],
            ],
        )
        return existing[0]
    else:
        # Insert - DuckDB doesn't auto-increment INTEGER PRIMARY KEY - calculate next ID
        max_id_result = con.execute("SELECT COALESCE(MAX(id), 0) FROM space_events").fetchone()
        next_id = (max_id_result[0] if max_id_result else 0) + 1

        # Convert numpy.bool to Python bool for DuckDB compatibility
        dark_sky_required_bool = bool(dark_sky_required) if dark_sky_required is not None else False

        con.execute(
            """
            INSERT INTO space_events (id, name, event_type, date, description, min_latitude, max_latitude,
                                     min_longitude, max_longitude, dark_sky_required, min_bortle_class,
                                     equipment_needed, viewing_notes, source, url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                next_id,
                name,
                event_type,
                date.isoformat(),
                description,
                min_latitude,
                max_latitude,
                min_longitude,
                max_longitude,
                dark_sky_required_bool,
                min_bortle_class,
                equipment_needed,
                viewing_notes,
                source,
                url,
                now,
                now,
            ],
        )
        return next_id


# ============================================================================
# Ephemeris Files
# ============================================================================


def get_ephemeris_file(file_key: str) -> EphemerisFile | None:
    """Get an ephemeris file by key."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT file_key, filename, display_name, description, coverage_start, coverage_end, size_mb,
               file_type, url, contents, use_case, created_at, updated_at
        FROM ephemeris_files WHERE file_key = ?
        """,
        [file_key],
    ).fetchone()
    if not result:
        return None
    return EphemerisFile(
        file_key=result[0],
        filename=result[1],
        display_name=result[2],
        description=result[3],
        coverage_start=result[4],
        coverage_end=result[5],
        size_mb=result[6],
        file_type=result[7],
        url=result[8],
        contents=result[9],
        use_case=result[10],
        created_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
        updated_at=datetime.fromisoformat(result[12]) if isinstance(result[12], str) else result[12],
    )


def get_all_ephemeris_files(file_type: str | None = None) -> list[EphemerisFile]:
    """Get all ephemeris files, optionally filtered by type."""
    con = get_duckdb_connection()
    if file_type:
        results = con.execute(
            """
            SELECT file_key, filename, display_name, description, coverage_start, coverage_end, size_mb,
                   file_type, url, contents, use_case, created_at, updated_at
            FROM ephemeris_files WHERE file_type = ? ORDER BY display_name
            """,
            [file_type],
        ).fetchall()
    else:
        results = con.execute(
            """
            SELECT file_key, filename, display_name, description, coverage_start, coverage_end, size_mb,
                   file_type, url, contents, use_case, created_at, updated_at
            FROM ephemeris_files ORDER BY display_name
            """
        ).fetchall()
    return [
        EphemerisFile(
            file_key=row[0],
            filename=row[1],
            display_name=row[2],
            description=row[3],
            coverage_start=row[4],
            coverage_end=row[5],
            size_mb=row[6],
            file_type=row[7],
            url=row[8],
            contents=row[9],
            use_case=row[10],
            created_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
            updated_at=datetime.fromisoformat(row[12]) if isinstance(row[12], str) else row[12],
        )
        for row in results
    ]


def create_or_update_ephemeris_file(
    file_key: str,
    filename: str,
    display_name: str,
    description: str,
    coverage_start: int,
    coverage_end: int,
    size_mb: float,
    file_type: str,
    url: str,
    contents: str,
    use_case: str,
) -> None:
    """Create or update an ephemeris file."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO ephemeris_files (file_key, filename, display_name, description, coverage_start,
                                    coverage_end, size_mb, file_type, url, contents, use_case,
                                    created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (file_key) DO UPDATE SET
            filename = EXCLUDED.filename,
            display_name = EXCLUDED.display_name,
            description = EXCLUDED.description,
            coverage_start = EXCLUDED.coverage_start,
            coverage_end = EXCLUDED.coverage_end,
            size_mb = EXCLUDED.size_mb,
            file_type = EXCLUDED.file_type,
            url = EXCLUDED.url,
            contents = EXCLUDED.contents,
            use_case = EXCLUDED.use_case,
            updated_at = EXCLUDED.updated_at
        """,
        [
            file_key,
            filename,
            display_name,
            description,
            coverage_start,
            coverage_end,
            size_mb,
            file_type,
            url,
            contents,
            use_case,
            now,
            now,
        ],
    )


def delete_ephemeris_file(file_key: str) -> None:
    """Delete an ephemeris file."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM ephemeris_files WHERE file_key = ?", [file_key])


# ============================================================================
# Star Name Mappings
# ============================================================================


def get_star_name_mapping(hr_number: int) -> StarNameMapping | None:
    """Get a star name mapping by HR number."""
    con = get_duckdb_connection()
    result = con.execute(
        "SELECT hr_number, common_name, bayer_designation, created_at, updated_at FROM star_name_mappings WHERE hr_number = ?",
        [hr_number],
    ).fetchone()
    if not result:
        return None
    return StarNameMapping(
        hr_number=result[0],
        common_name=result[1],
        bayer_designation=result[2],
        created_at=datetime.fromisoformat(result[3]) if isinstance(result[3], str) else result[3],
        updated_at=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
    )


def get_star_name_mapping_by_common_name(common_name: str) -> StarNameMapping | None:
    """Get a star name mapping by common name."""
    con = get_duckdb_connection()
    result = con.execute(
        "SELECT hr_number, common_name, bayer_designation, created_at, updated_at FROM star_name_mappings WHERE common_name = ?",
        [common_name],
    ).fetchone()
    if not result:
        return None
    return StarNameMapping(
        hr_number=result[0],
        common_name=result[1],
        bayer_designation=result[2],
        created_at=datetime.fromisoformat(result[3]) if isinstance(result[3], str) else result[3],
        updated_at=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
    )


def create_or_update_star_name_mapping(hr_number: int, common_name: str, bayer_designation: str | None = None) -> None:
    """Create or update a star name mapping."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO star_name_mappings (hr_number, common_name, bayer_designation, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (hr_number) DO UPDATE SET
            common_name = EXCLUDED.common_name,
            bayer_designation = EXCLUDED.bayer_designation,
            updated_at = EXCLUDED.updated_at
        """,
        [hr_number, common_name, bayer_designation, now, now],
    )


def delete_star_name_mapping(hr_number: int) -> None:
    """Delete a star name mapping."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM star_name_mappings WHERE hr_number = ?", [hr_number])


# ============================================================================
# TLE Data
# ============================================================================


def get_tle(norad_id: int) -> TLE | None:
    """Get TLE data by NORAD ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT norad_id, satellite_name, satellite_group, line1, line2, epoch, fetched_at
        FROM tle_data WHERE norad_id = ?
        """,
        [norad_id],
    ).fetchone()
    if not result:
        return None
    return TLE(
        norad_id=result[0],
        satellite_name=result[1],
        satellite_group=result[2],
        line1=result[3],
        line2=result[4],
        epoch=datetime.fromisoformat(result[5]) if result[5] and isinstance(result[5], str) else result[5],
        fetched_at=datetime.fromisoformat(result[6]) if isinstance(result[6], str) else result[6],
    )


def get_tles_by_group(satellite_group: str) -> list[TLE]:
    """Get all TLEs for a satellite group."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT norad_id, satellite_name, satellite_group, line1, line2, epoch, fetched_at
        FROM tle_data WHERE satellite_group = ? ORDER BY satellite_name
        """,
        [satellite_group],
    ).fetchall()
    return [
        TLE(
            norad_id=row[0],
            satellite_name=row[1],
            satellite_group=row[2],
            line1=row[3],
            line2=row[4],
            epoch=datetime.fromisoformat(row[5]) if row[5] and isinstance(row[5], str) else row[5],
            fetched_at=datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
        )
        for row in results
    ]


def create_or_update_tle(
    norad_id: int,
    satellite_name: str,
    line1: str,
    line2: str,
    satellite_group: str | None = None,
    epoch: datetime | None = None,
    fetched_at: datetime | None = None,
) -> None:
    """Create or update TLE data."""
    con = get_duckdb_connection()
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    con.execute(
        """
        INSERT INTO tle_data (norad_id, satellite_name, satellite_group, line1, line2, epoch, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (norad_id) DO UPDATE SET
            satellite_name = EXCLUDED.satellite_name,
            satellite_group = EXCLUDED.satellite_group,
            line1 = EXCLUDED.line1,
            line2 = EXCLUDED.line2,
            epoch = EXCLUDED.epoch,
            fetched_at = EXCLUDED.fetched_at
        """,
        [
            norad_id,
            satellite_name,
            satellite_group,
            line1,
            line2,
            epoch.isoformat() if epoch else None,
            fetched_at.isoformat(),
        ],
    )


def delete_tle(norad_id: int) -> None:
    """Delete TLE data."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM tle_data WHERE norad_id = ?", [norad_id])


# ============================================================================
# Variable Stars
# ============================================================================


def get_variable_star(star_id: int) -> VariableStar | None:
    """Get a variable star by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, designation, variable_type, period_days, magnitude_min, magnitude_max,
               ra_hours, dec_degrees, notes, created_at, updated_at
        FROM variable_stars WHERE id = ?
        """,
        [star_id],
    ).fetchone()
    if not result:
        return None
    return VariableStar(
        id=result[0],
        name=result[1],
        designation=result[2],
        variable_type=result[3],
        period_days=result[4],
        magnitude_min=result[5],
        magnitude_max=result[6],
        ra_hours=result[7],
        dec_degrees=result[8],
        notes=result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_variable_star_by_name(name: str) -> VariableStar | None:
    """Get a variable star by name."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, designation, variable_type, period_days, magnitude_min, magnitude_max,
               ra_hours, dec_degrees, notes, created_at, updated_at
        FROM variable_stars WHERE name = ?
        """,
        [name],
    ).fetchone()
    if not result:
        return None
    return VariableStar(
        id=result[0],
        name=result[1],
        designation=result[2],
        variable_type=result[3],
        period_days=result[4],
        magnitude_min=result[5],
        magnitude_max=result[6],
        ra_hours=result[7],
        dec_degrees=result[8],
        notes=result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_all_variable_stars(variable_type: str | None = None) -> list[VariableStar]:
    """Get all variable stars, optionally filtered by type."""
    con = get_duckdb_connection()
    if variable_type:
        results = con.execute(
            """
            SELECT id, name, designation, variable_type, period_days, magnitude_min, magnitude_max,
                   ra_hours, dec_degrees, notes, created_at, updated_at
            FROM variable_stars WHERE variable_type = ? ORDER BY name
            """,
            [variable_type],
        ).fetchall()
    else:
        results = con.execute(
            """
            SELECT id, name, designation, variable_type, period_days, magnitude_min, magnitude_max,
                   ra_hours, dec_degrees, notes, created_at, updated_at
            FROM variable_stars ORDER BY name
            """
        ).fetchall()
    return [
        VariableStar(
            id=row[0],
            name=row[1],
            designation=row[2],
            variable_type=row[3],
            period_days=row[4],
            magnitude_min=row[5],
            magnitude_max=row[6],
            ra_hours=row[7],
            dec_degrees=row[8],
            notes=row[9],
            created_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
            updated_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
        )
        for row in results
    ]


def create_variable_star(
    name: str,
    designation: str,
    variable_type: str,
    period_days: float,
    magnitude_min: float,
    magnitude_max: float,
    ra_hours: float,
    dec_degrees: float,
    notes: str,
) -> int:
    """Create a new variable star. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO variable_stars (name, designation, variable_type, period_days, magnitude_min,
                                   magnitude_max, ra_hours, dec_degrees, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            name,
            designation,
            variable_type,
            period_days,
            magnitude_min,
            magnitude_max,
            ra_hours,
            dec_degrees,
            notes,
            now,
            now,
        ],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_variable_star(star_id: int, **kwargs: Any) -> None:
    """Update a variable star. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = (
        "name",
        "designation",
        "variable_type",
        "period_days",
        "magnitude_min",
        "magnitude_max",
        "ra_hours",
        "dec_degrees",
        "notes",
    )
    for key, value in kwargs.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(star_id)
    con.execute(f"UPDATE variable_stars SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_variable_star(star_id: int) -> None:
    """Delete a variable star."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM variable_stars WHERE id = ?", [star_id])


# ============================================================================
# Comets
# ============================================================================


def get_comet(comet_id: int) -> Comet | None:
    """Get a comet by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, designation, perihelion_date, perihelion_distance_au, peak_magnitude,
               peak_date, is_periodic, period_years, notes, created_at, updated_at
        FROM comets WHERE id = ?
        """,
        [comet_id],
    ).fetchone()
    if not result:
        return None
    return Comet(
        id=result[0],
        name=result[1],
        designation=result[2],
        perihelion_date=datetime.fromisoformat(result[3]) if isinstance(result[3], str) else result[3],
        perihelion_distance_au=result[4],
        peak_magnitude=result[5],
        peak_date=datetime.fromisoformat(result[6]) if isinstance(result[6], str) else result[6],
        is_periodic=bool(result[7]),
        period_years=result[8],
        notes=result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_comet_by_name(name: str) -> Comet | None:
    """Get a comet by name."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, name, designation, perihelion_date, perihelion_distance_au, peak_magnitude,
               peak_date, is_periodic, period_years, notes, created_at, updated_at
        FROM comets WHERE name = ?
        """,
        [name],
    ).fetchone()
    if not result:
        return None
    return Comet(
        id=result[0],
        name=result[1],
        designation=result[2],
        perihelion_date=datetime.fromisoformat(result[3]) if isinstance(result[3], str) else result[3],
        perihelion_distance_au=result[4],
        peak_magnitude=result[5],
        peak_date=datetime.fromisoformat(result[6]) if isinstance(result[6], str) else result[6],
        is_periodic=bool(result[7]),
        period_years=result[8],
        notes=result[9],
        created_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
        updated_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
    )


def get_all_comets(is_periodic: bool | None = None) -> list[Comet]:
    """Get all comets, optionally filtered by periodic status."""
    con = get_duckdb_connection()
    if is_periodic is not None:
        results = con.execute(
            """
            SELECT id, name, designation, perihelion_date, perihelion_distance_au, peak_magnitude,
                   peak_date, is_periodic, period_years, notes, created_at, updated_at
            FROM comets WHERE is_periodic = ? ORDER BY peak_date
            """,
            [is_periodic],
        ).fetchall()
    else:
        results = con.execute(
            """
            SELECT id, name, designation, perihelion_date, perihelion_distance_au, peak_magnitude,
                   peak_date, is_periodic, period_years, notes, created_at, updated_at
            FROM comets ORDER BY peak_date
            """
        ).fetchall()
    return [
        Comet(
            id=row[0],
            name=row[1],
            designation=row[2],
            perihelion_date=datetime.fromisoformat(row[3]) if isinstance(row[3], str) else row[3],
            perihelion_distance_au=row[4],
            peak_magnitude=row[5],
            peak_date=datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
            is_periodic=bool(row[7]),
            period_years=row[8],
            notes=row[9],
            created_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
            updated_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
        )
        for row in results
    ]


def create_comet(
    name: str,
    designation: str,
    perihelion_date: datetime,
    perihelion_distance_au: float,
    peak_magnitude: float,
    peak_date: datetime,
    is_periodic: bool = False,
    period_years: float | None = None,
    notes: str = "",
) -> int:
    """Create a new comet. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        """
        INSERT INTO comets (name, designation, perihelion_date, perihelion_distance_au, peak_magnitude,
                           peak_date, is_periodic, period_years, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            name,
            designation,
            perihelion_date.isoformat(),
            perihelion_distance_au,
            peak_magnitude,
            peak_date.isoformat(),
            is_periodic,
            period_years,
            notes,
            now,
            now,
        ],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_comet(comet_id: int, **kwargs: Any) -> None:
    """Update a comet. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = (
        "name",
        "designation",
        "perihelion_date",
        "perihelion_distance_au",
        "peak_magnitude",
        "peak_date",
        "is_periodic",
        "period_years",
        "notes",
    )
    for key, value in kwargs.items():
        if key in allowed_fields:
            if key in ("perihelion_date", "peak_date") and isinstance(value, datetime):
                value = value.isoformat()
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(comet_id)
    con.execute(f"UPDATE comets SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_comet(comet_id: int) -> None:
    """Delete a comet."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM comets WHERE id = ?", [comet_id])


# ============================================================================
# Eclipses
# ============================================================================


def get_eclipse(eclipse_id: int) -> Eclipse | None:
    """Get an eclipse by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        "SELECT id, eclipse_type, date, magnitude, created_at, updated_at FROM eclipses WHERE id = ?",
        [eclipse_id],
    ).fetchone()
    if not result:
        return None
    return Eclipse(
        id=result[0],
        eclipse_type=result[1],
        date=datetime.fromisoformat(result[2]) if isinstance(result[2], str) else result[2],
        magnitude=result[3],
        created_at=datetime.fromisoformat(result[4]) if isinstance(result[4], str) else result[4],
        updated_at=datetime.fromisoformat(result[5]) if isinstance(result[5], str) else result[5],
    )


def get_eclipses(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    eclipse_type: str | None = None,
    limit: int = 100,
) -> list[Eclipse]:
    """Get eclipses, optionally filtered by date range and type."""
    con = get_duckdb_connection()
    query = "SELECT id, eclipse_type, date, magnitude, created_at, updated_at FROM eclipses WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date.isoformat())
    if end_date:
        query += " AND date <= ?"
        params.append(end_date.isoformat())
    if eclipse_type:
        query += " AND eclipse_type = ?"
        params.append(eclipse_type)
    query += " ORDER BY date LIMIT ?"
    params.append(limit)
    results = con.execute(query, params).fetchall()
    return [
        Eclipse(
            id=row[0],
            eclipse_type=row[1],
            date=datetime.fromisoformat(row[2]) if isinstance(row[2], str) else row[2],
            magnitude=row[3],
            created_at=datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4],
            updated_at=datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5],
        )
        for row in results
    ]


# Alias for backward compatibility
get_all_eclipses = get_eclipses


def create_eclipse(eclipse_type: str, date: datetime, magnitude: float) -> int:
    """Create a new eclipse. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    con.execute(
        "INSERT INTO eclipses (eclipse_type, date, magnitude, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        [eclipse_type, date.isoformat(), magnitude, now, now],
    )
    result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
    return result[0] if result else 0


def update_eclipse(eclipse_id: int, **kwargs: Any) -> None:
    """Update an eclipse. Pass fields to update as keyword arguments."""
    if not kwargs:
        return
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    set_clauses = []
    values = []
    allowed_fields = ("eclipse_type", "date", "magnitude")
    for key, value in kwargs.items():
        if key in allowed_fields:
            if key == "date" and isinstance(value, datetime):
                value = value.isoformat()
            set_clauses.append(f"{key} = ?")
            values.append(value)
    if not set_clauses:
        return
    set_clauses.append("updated_at = ?")
    values.append(now)
    values.append(eclipse_id)
    con.execute(f"UPDATE eclipses SET {', '.join(set_clauses)} WHERE id = ?", values)


def delete_eclipse(eclipse_id: int) -> None:
    """Delete an eclipse."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM eclipses WHERE id = ?", [eclipse_id])


# ============================================================================
# Bortle Characteristics
# ============================================================================


def get_bortle_characteristics(bortle_class: int) -> BortleCharacteristics | None:
    """Get Bortle characteristics for a class."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT bortle_class, sqm_min, sqm_max, naked_eye_mag, milky_way, airglow, zodiacal_light,
               description, recommendations, created_at, updated_at
        FROM bortle_characteristics WHERE bortle_class = ?
        """,
        [bortle_class],
    ).fetchone()
    if not result:
        return None
    return BortleCharacteristics(
        bortle_class=result[0],
        sqm_min=result[1],
        sqm_max=result[2],
        naked_eye_mag=result[3],
        milky_way=bool(result[4]),
        airglow=bool(result[5]),
        zodiacal_light=bool(result[6]),
        description=result[7],
        recommendations=result[8],
        created_at=datetime.fromisoformat(result[9]) if isinstance(result[9], str) else result[9],
        updated_at=datetime.fromisoformat(result[10]) if isinstance(result[10], str) else result[10],
    )


def get_all_bortle_characteristics() -> list[BortleCharacteristics]:
    """Get all Bortle characteristics."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT bortle_class, sqm_min, sqm_max, naked_eye_mag, milky_way, airglow, zodiacal_light,
               description, recommendations, created_at, updated_at
        FROM bortle_characteristics ORDER BY bortle_class
        """
    ).fetchall()
    return [
        BortleCharacteristics(
            bortle_class=row[0],
            sqm_min=row[1],
            sqm_max=row[2],
            naked_eye_mag=row[3],
            milky_way=bool(row[4]),
            airglow=bool(row[5]),
            zodiacal_light=bool(row[6]),
            description=row[7],
            recommendations=row[8],
            created_at=datetime.fromisoformat(row[9]) if isinstance(row[9], str) else row[9],
            updated_at=datetime.fromisoformat(row[10]) if isinstance(row[10], str) else row[10],
        )
        for row in results
    ]


def create_or_update_bortle_characteristics(
    bortle_class: int,
    sqm_min: float,
    sqm_max: float,
    naked_eye_mag: float,
    milky_way: bool,
    airglow: bool,
    zodiacal_light: bool,
    description: str,
    recommendations: str,
) -> None:
    """Create or update Bortle characteristics."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    # Convert numpy.bool to Python bool for DuckDB compatibility
    milky_way_bool = bool(milky_way) if milky_way is not None else False
    airglow_bool = bool(airglow) if airglow is not None else False
    zodiacal_light_bool = bool(zodiacal_light) if zodiacal_light is not None else False
    con.execute(
        """
        INSERT INTO bortle_characteristics (bortle_class, sqm_min, sqm_max, naked_eye_mag, milky_way,
                                           airglow, zodiacal_light, description, recommendations,
                                           created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (bortle_class) DO UPDATE SET
            sqm_min = EXCLUDED.sqm_min,
            sqm_max = EXCLUDED.sqm_max,
            naked_eye_mag = EXCLUDED.naked_eye_mag,
            milky_way = EXCLUDED.milky_way,
            airglow = EXCLUDED.airglow,
            zodiacal_light = EXCLUDED.zodiacal_light,
            description = EXCLUDED.description,
            recommendations = EXCLUDED.recommendations,
            updated_at = EXCLUDED.updated_at
        """,
        [
            bortle_class,
            sqm_min,
            sqm_max,
            naked_eye_mag,
            milky_way_bool,
            airglow_bool,
            zodiacal_light_bool,
            description,
            recommendations,
            now,
            now,
        ],
    )


# ============================================================================
# RSS Feeds
# ============================================================================


def get_rss_feed(feed_id: int) -> RSSFeed | None:
    """Get an RSS feed article by ID."""
    con = get_duckdb_connection()
    result = con.execute(
        """
        SELECT id, title, link, guid, description, content, published_date, author, categories,
               source, feed_url, created_at, updated_at, fetched_at
        FROM rss_feeds WHERE id = ?
        """,
        [feed_id],
    ).fetchone()
    if not result:
        return None
    return RSSFeed(
        id=result[0],
        title=result[1],
        link=result[2],
        guid=result[3],
        description=result[4],
        content=result[5],
        published_date=datetime.fromisoformat(result[6]) if isinstance(result[6], str) else result[6],
        author=result[7],
        categories=result[8],
        source=result[9],
        feed_url=result[10],
        created_at=datetime.fromisoformat(result[11]) if isinstance(result[11], str) else result[11],
        updated_at=datetime.fromisoformat(result[12]) if isinstance(result[12], str) else result[12],
        fetched_at=datetime.fromisoformat(result[13]) if isinstance(result[13], str) else result[13],
    )


def get_rss_feeds(
    source: str | None = None,
    start_date: datetime | None = None,
    limit: int = 100,
) -> list[RSSFeed]:
    """Get RSS feed articles, optionally filtered by source and date."""
    con = get_duckdb_connection()
    query = """
        SELECT id, title, link, guid, description, content, published_date, author, categories,
               source, feed_url, created_at, updated_at, fetched_at
        FROM rss_feeds WHERE 1=1
    """
    params = []
    if source:
        query += " AND source = ?"
        params.append(source)
    if start_date:
        query += " AND published_date >= ?"
        params.append(start_date.isoformat())
    query += " ORDER BY published_date DESC LIMIT ?"
    params.append(limit)
    results = con.execute(query, params).fetchall()
    return [
        RSSFeed(
            id=row[0],
            title=row[1],
            link=row[2],
            guid=row[3],
            description=row[4],
            content=row[5],
            published_date=datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
            author=row[7],
            categories=row[8],
            source=row[9],
            feed_url=row[10],
            created_at=datetime.fromisoformat(row[11]) if isinstance(row[11], str) else row[11],
            updated_at=datetime.fromisoformat(row[12]) if isinstance(row[12], str) else row[12],
            fetched_at=datetime.fromisoformat(row[13]) if isinstance(row[13], str) else row[13],
        )
        for row in results
    ]


def create_or_update_rss_feed(
    title: str,
    link: str,
    description: str,
    published_date: datetime,
    source: str,
    feed_url: str,
    guid: str | None = None,
    content: str | None = None,
    author: str | None = None,
    categories: str | None = None,
    fetched_at: datetime | None = None,
) -> int:
    """Create or update an RSS feed article. Returns the ID."""
    con = get_duckdb_connection()
    now = datetime.now(UTC).isoformat()
    if fetched_at is None:
        fetched_at = datetime.now(UTC)
    # Check if exists by link
    existing = con.execute("SELECT id FROM rss_feeds WHERE link = ?", [link]).fetchone()
    if existing:
        # Update
        con.execute(
            """
            UPDATE rss_feeds
            SET title = ?, guid = ?, description = ?, content = ?, published_date = ?,
                author = ?, categories = ?, source = ?, feed_url = ?, updated_at = ?, fetched_at = ?
            WHERE id = ?
            """,
            [
                title,
                guid,
                description,
                content,
                published_date.isoformat(),
                author,
                categories,
                source,
                feed_url,
                now,
                fetched_at.isoformat(),
                existing[0],
            ],
        )
        return existing[0]
    else:
        # Insert
        con.execute(
            """
            INSERT INTO rss_feeds (title, link, guid, description, content, published_date, author,
                                  categories, source, feed_url, created_at, updated_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                title,
                link,
                guid,
                description,
                content,
                published_date.isoformat(),
                author,
                categories,
                source,
                feed_url,
                now,
                now,
                fetched_at.isoformat(),
            ],
        )
        result = con.execute("SELECT LAST_INSERT_ROWID()").fetchone()
        return result[0] if result else 0


def delete_rss_feed(feed_id: int) -> None:
    """Delete an RSS feed article."""
    con = get_duckdb_connection()
    con.execute("DELETE FROM rss_feeds WHERE id = ?", [feed_id])


def delete_old_rss_feeds(source: str, before_date: datetime) -> int:
    """Delete RSS feed articles older than the specified date. Returns number of rows deleted."""
    con = get_duckdb_connection()
    result = con.execute(
        "DELETE FROM rss_feeds WHERE source = ? AND fetched_at < ?",
        [source, before_date.isoformat()],
    )
    return result.rowcount if hasattr(result, "rowcount") else 0


# ============================================================================
# Meteor Showers
# ============================================================================


def get_meteor_showers() -> list[MeteorShower]:
    """Get all meteor showers from the database."""
    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT id, name, code, start_month, start_day, end_month, end_day,
               peak_month, peak_day, radiant_ra_hours, radiant_dec_degrees,
               radiant_constellation, zhr_peak, velocity_km_s, parent_comet,
               best_time, notes, created_at, updated_at
        FROM meteor_showers
        ORDER BY peak_month, peak_day
        """
    ).fetchall()

    showers = []
    for row in results:
        showers.append(
            MeteorShower(
                id=row[0],
                name=row[1],
                code=row[2],
                start_month=row[3],
                start_day=row[4],
                end_month=row[5],
                end_day=row[6],
                peak_month=row[7],
                peak_day=row[8],
                radiant_ra_hours=row[9],
                radiant_dec_degrees=row[10],
                radiant_constellation=row[11],
                zhr_peak=row[12],
                velocity_km_s=row[13],
                parent_comet=row[14],
                best_time=row[15],
                notes=row[16],
                created_at=datetime.fromisoformat(row[17]) if row[17] else datetime.now(UTC),
                updated_at=datetime.fromisoformat(row[18]) if row[18] else datetime.now(UTC),
            )
        )
    return showers


# Alias for compatibility
get_all_meteor_showers = get_meteor_showers
