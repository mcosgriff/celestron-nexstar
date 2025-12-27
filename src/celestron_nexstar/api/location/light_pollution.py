"""
Light Pollution Data Integration

Provides Bortle scale and SQM (Sky Quality Meter) values
for assessing sky darkness at observing locations.

Uses async HTTP to fetch data from light pollution APIs with caching.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from celestron_nexstar.api.core.exceptions import DatabaseError


logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path.home() / ".celestron_nexstar" / "cache"
CACHE_FILE = CACHE_DIR / "light_pollution.json"
CACHE_STALE_HOURS = 24  # Consider cache stale after 24 hours
CACHE_MAX_AGE_DAYS = 7  # Maximum age before forcing refresh


class BortleClass(IntEnum):
    """
    Bortle Dark-Sky Scale (1-9).

    Class 1: Excellent dark-sky site
    Class 2: Typical truly dark site
    Class 3: Rural sky
    Class 4: Rural/suburban transition
    Class 5: Suburban sky
    Class 6: Bright suburban sky
    Class 7: Suburban/urban transition
    Class 8: City sky
    Class 9: Inner-city sky
    """

    CLASS_1 = 1  # Excellent (21.99-22.00 mag/arcsec²)
    CLASS_2 = 2  # Typical dark (21.89-21.99)
    CLASS_3 = 3  # Rural (21.69-21.89)
    CLASS_4 = 4  # Rural/suburban (20.49-21.69)
    CLASS_5 = 5  # Suburban (19.50-20.49)
    CLASS_6 = 6  # Bright suburban (18.94-19.50)
    CLASS_7 = 7  # Suburban/urban (18.38-18.94)
    CLASS_8 = 8  # City (below 18.38)
    CLASS_9 = 9  # Inner-city (severely light polluted)


@dataclass(frozen=True)
class LightPollutionData:
    """Light pollution information for a location."""

    bortle_class: BortleClass
    sqm_value: float  # Sky Quality Meter (mag/arcsec²)

    # Impact on observing
    naked_eye_limiting_magnitude: float
    milky_way_visible: bool
    airglow_visible: bool
    zodiacal_light_visible: bool

    # Description
    description: str
    recommendations: tuple[str, ...]

    # Metadata
    source: str | None = None  # API source used
    cached: bool = False  # Whether data came from cache


# NOTE: Bortle class characteristics are now stored in database seed files.
# See _get_bortle_characteristics() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py


def sqm_to_bortle(sqm: float) -> BortleClass:
    """Convert SQM value to Bortle class."""
    if sqm >= 21.99:
        return BortleClass.CLASS_1
    elif sqm >= 21.89:
        return BortleClass.CLASS_2
    elif sqm >= 21.69:
        return BortleClass.CLASS_3
    elif sqm >= 20.49:
        return BortleClass.CLASS_4
    elif sqm >= 19.50:
        return BortleClass.CLASS_5
    elif sqm >= 18.94:
        return BortleClass.CLASS_6
    elif sqm >= 18.38:
        return BortleClass.CLASS_7
    elif sqm >= 17.5:
        return BortleClass.CLASS_8
    else:
        return BortleClass.CLASS_9


def _get_default_bortle_characteristics(bortle_class: BortleClass) -> dict[str, Any]:
    """
    Get default Bortle class characteristics as fallback when database is not seeded.

    These are hardcoded defaults used when the database hasn't been seeded yet.
    For full functionality, seed the database with: nexstar data seed

    Args:
        bortle_class: Bortle class enum value

    Returns:
        Dictionary with basic Bortle characteristics
    """
    # Default characteristics based on Bortle scale definitions
    defaults = {
        BortleClass.CLASS_1: {
            "sqm_range": (21.99, 22.00),
            "naked_eye_mag": 7.6,
            "milky_way": True,
            "airglow": True,
            "zodiacal_light": True,
            "description": "Excellent dark-sky site",
            "recommendations": ["Perfect for all deep-sky objects", "Faintest galaxies and nebulae visible"],
        },
        BortleClass.CLASS_2: {
            "sqm_range": (21.89, 21.99),
            "naked_eye_mag": 7.1,
            "milky_way": True,
            "airglow": True,
            "zodiacal_light": True,
            "description": "Typical truly dark site",
            "recommendations": ["Excellent for deep-sky observing", "Milky Way shows significant detail"],
        },
        BortleClass.CLASS_3: {
            "sqm_range": (21.69, 21.89),
            "naked_eye_mag": 6.6,
            "milky_way": True,
            "airglow": False,
            "zodiacal_light": True,
            "description": "Rural sky",
            "recommendations": ["Good for deep-sky observing", "Some light pollution on horizon"],
        },
        BortleClass.CLASS_4: {
            "sqm_range": (20.49, 21.69),
            "naked_eye_mag": 6.1,
            "milky_way": True,
            "airglow": False,
            "zodiacal_light": False,
            "description": "Rural/suburban transition",
            "recommendations": ["Fair for deep-sky", "Milky Way still visible"],
        },
        BortleClass.CLASS_5: {
            "sqm_range": (19.50, 20.49),
            "naked_eye_mag": 5.6,
            "milky_way": False,
            "airglow": False,
            "zodiacal_light": False,
            "description": "Suburban sky",
            "recommendations": ["Focus on brighter Messier objects", "Planets and Moon are excellent"],
        },
        BortleClass.CLASS_6: {
            "sqm_range": (18.94, 19.50),
            "naked_eye_mag": 5.1,
            "milky_way": False,
            "airglow": False,
            "zodiacal_light": False,
            "description": "Bright suburban sky",
            "recommendations": ["Observe bright objects only", "Planets, Moon, and bright clusters"],
        },
        BortleClass.CLASS_7: {
            "sqm_range": (18.38, 18.94),
            "naked_eye_mag": 4.6,
            "milky_way": False,
            "airglow": False,
            "zodiacal_light": False,
            "description": "Suburban/urban transition",
            "recommendations": ["Very limited deep-sky observing", "Focus on planets and Moon"],
        },
        BortleClass.CLASS_8: {
            "sqm_range": (17.00, 18.38),
            "naked_eye_mag": 4.1,
            "milky_way": False,
            "airglow": False,
            "zodiacal_light": False,
            "description": "City sky",
            "recommendations": ["Observe planets and Moon primarily", "Brightest star clusters possible"],
        },
        BortleClass.CLASS_9: {
            "sqm_range": (13.00, 17.00),
            "naked_eye_mag": 3.0,
            "milky_way": False,
            "airglow": False,
            "zodiacal_light": False,
            "description": "Inner-city sky",
            "recommendations": ["Only Moon and bright planets", "Consider traveling to darker sites"],
        },
    }

    return defaults.get(bortle_class, defaults[BortleClass.CLASS_5])


def _get_bortle_characteristics(db_session: Session, bortle_class: BortleClass) -> dict[str, Any]:
    """
    Get Bortle class characteristics from database, with fallback to defaults.

    First attempts to load from database. If database is not seeded, uses
    hardcoded default characteristics and logs a warning.

    Args:
        db_session: Database session
        bortle_class: Bortle class enum value

    Returns:
        Dictionary with characteristics
    """
    import json

    from sqlalchemy import select

    from celestron_nexstar.api.database.models import BortleCharacteristicsModel

    model = db_session.scalar(
        select(BortleCharacteristicsModel).where(BortleCharacteristicsModel.bortle_class == int(bortle_class.value))
    )

    if model is None:
        logger.warning(
            f"Bortle class {bortle_class.value} characteristics not found in database. "
            "Using default values. For full functionality, seed the database by running: nexstar data seed"
        )
        return _get_default_bortle_characteristics(bortle_class)

    return {
        "sqm_range": (model.sqm_min, model.sqm_max),
        "naked_eye_mag": model.naked_eye_mag,
        "milky_way": model.milky_way,
        "airglow": model.airglow,
        "zodiacal_light": model.zodiacal_light,
        "description": model.description,
        "recommendations": json.loads(model.recommendations),
    }


def _create_light_pollution_data(
    db_session: Session, sqm: float, source: str | None = None, cached: bool = False
) -> LightPollutionData:
    """Create LightPollutionData from SQM value."""
    bortle = sqm_to_bortle(sqm)
    chars = _get_bortle_characteristics(db_session, bortle)

    return LightPollutionData(
        bortle_class=bortle,
        sqm_value=sqm,
        naked_eye_limiting_magnitude=float(chars["naked_eye_mag"]),
        milky_way_visible=bool(chars["milky_way"]),
        airglow_visible=bool(chars["airglow"]),
        zodiacal_light_visible=bool(chars["zodiacal_light"]),
        description=str(chars["description"]),
        recommendations=tuple(str(r) for r in chars["recommendations"]),
        source=source,
        cached=cached,
    )


def _ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_cache() -> dict[str, Any] | None:
    """Load cached light pollution data."""
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache_data: dict[str, Any] = json.load(f)
            return cache_data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load cache: {e}")
        return None


def _save_cache(data: dict[str, Any]) -> None:
    """Save light pollution data to cache."""
    _ensure_cache_dir()
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.warning(f"Failed to save cache: {e}")


def _is_cache_stale(cache_data: dict[str, Any]) -> bool:
    """Check if cache is stale."""
    if "timestamp" not in cache_data:
        return True

    try:
        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        age = datetime.now(UTC) - cache_time.replace(tzinfo=UTC)
        return age > timedelta(hours=CACHE_STALE_HOURS)
    except (ValueError, KeyError):
        return True


def _is_cache_too_old(cache_data: dict[str, Any]) -> bool:
    """Check if cache is too old and should be refreshed."""
    if "timestamp" not in cache_data:
        return True

    try:
        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        age = datetime.now(UTC) - cache_time.replace(tzinfo=UTC)
        return age > timedelta(days=CACHE_MAX_AGE_DAYS)
    except (ValueError, KeyError):
        return True


def _get_cache_key(lat: float, lon: float) -> str:
    """Generate cache key for location."""
    # Round to ~1km precision (0.01 degrees ≈ 1km)
    return f"{round(lat, 2)},{round(lon, 2)}"


def _fetch_from_lightpollutionmap_api(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from lightpollutionmap.info API.

    This is a free API that provides light pollution data.
    """
    try:
        import requests

        url = "https://www.lightpollutionmap.info/QueryRaster"
        params = {
            "ql": "1",  # Query level
            "qt": "point",  # Query type
            "qd": f"{lon},{lat}",  # Query data (lon,lat)
        }

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            # API returns JSON but with text/plain content-type, so parse manually
            data = json.loads(response.text)
            # API returns brightness value, convert to SQM
            # Brightness is in nW/cm²/sr, need to convert to mag/arcsec²
            if "value" in data:
                brightness = float(data["value"])
                # Conversion: SQM = -2.5 * log10(brightness) + 20.0 (approximate)
                # This is a simplified conversion
                if brightness > 0:
                    import math

                    sqm = -2.5 * math.log10(brightness) + 20.0
                    # Clamp to reasonable range
                    return max(17.0, min(22.0, sqm))
        return None
    except ImportError:
        logger.warning("requests not installed, cannot fetch light pollution data")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch from lightpollutionmap.info: {e}")
        return None


def _fetch_from_darksky_api(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from Dark Sky Finder or similar API.

    This is a fallback API if the primary one fails.
    """
    # Placeholder for alternative API
    # Many light pollution APIs require API keys or have rate limits
    return None


def _fetch_sqm(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from database (offline only).

    Only uses database - no external API calls. Designed to work offline.
    """
    # Try database only (offline, fast, preferred)
    try:
        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.database.light_pollution_db import get_sqm_from_database

        db = get_database()
        sqm = get_sqm_from_database(lat, lon, db)
        if sqm is not None:
            logger.info(f"Found SQM {sqm:.2f} in database for {lat},{lon}")
            return sqm
        else:
            logger.debug(f"No SQM data in database for {lat},{lon}")
    except Exception as e:
        logger.debug(f"Database lookup failed: {e}")
        import traceback

        logger.debug(traceback.format_exc())

    # No API fallback - database only for offline operation
    logger.debug("No SQM data available in database")
    return None


def get_light_pollution_data(
    db_session: Session, lat: float, lon: float, force_refresh: bool = False
) -> LightPollutionData | None:
    """
    Get light pollution data for a location.

    Uses database only (offline). Requires light pollution data to be loaded into database.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        force_refresh: Force refresh even if cache is valid

    Returns:
        Light pollution data, or None if no data found in database

    Note:
        To load light pollution data into the database, run:
          nexstar data download-light-pollution
    """
    cache_key = _get_cache_key(lat, lon)

    # Check cache first (unless forcing refresh)
    if not force_refresh:
        cache_data = _load_cache()
        if cache_data and "data" in cache_data:
            location_data = cache_data["data"].get(cache_key)
            if location_data and "timestamp" in location_data:
                try:
                    cache_time = datetime.fromisoformat(location_data["timestamp"])
                    age = datetime.now(UTC) - cache_time.replace(tzinfo=UTC)
                    if age < timedelta(hours=CACHE_STALE_HOURS):
                        logger.debug(f"Using cached light pollution data for {lat},{lon}")
                        return _create_light_pollution_data(
                            db_session, location_data["sqm"], location_data.get("source"), cached=True
                        )
                except (ValueError, KeyError):
                    pass

    # Need to fetch new data from database
    logger.info(f"Fetching light pollution data for {lat},{lon}")
    sqm = _fetch_sqm(lat, lon)

    if sqm is None:
        # No data in database - log warning and return None
        logger.warning(
            f"No light pollution data found in database for location ({lat:.4f}, {lon:.4f}). "
            "To load light pollution data, run: nexstar data download-light-pollution"
        )
        return None

    # Data came from database (offline source)
    source = "database"

    # Save to cache
    cache_data = _load_cache() or {"data": {}, "timestamp": datetime.now(UTC).isoformat()}
    if "data" not in cache_data:
        cache_data["data"] = {}

    cache_data["data"][cache_key] = {
        "sqm": sqm,
        "source": source,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    cache_data["timestamp"] = datetime.now(UTC).isoformat()
    _save_cache(cache_data)

    return _create_light_pollution_data(db_session, sqm, source, cached=False)


def get_light_pollution_data_batch(
    db_session: Session, locations: list[tuple[float, float]], force_refresh: bool = False
) -> dict[tuple[float, float], LightPollutionData]:
    """
    Get light pollution data for multiple locations.

    Fetches data for multiple locations for a full night of viewing.
    Uses caching to avoid redundant database lookups.

    Args:
        db_session: Database session
        locations: List of (lat, lon) tuples
        force_refresh: Force refresh even if cache is valid

    Returns:
        Dictionary mapping (lat, lon) to LightPollutionData
        Only includes locations that have data in the database.
    """
    data_map: dict[tuple[float, float], LightPollutionData] = {}
    for lat, lon in locations:
        try:
            result = get_light_pollution_data(db_session, lat, lon, force_refresh)
            data_map[(lat, lon)] = result
        except Exception as e:
            logger.error(f"Error fetching data for {lat},{lon}: {e}")
            # Skip locations without data - don't use fallback estimation
            continue

    return data_map
