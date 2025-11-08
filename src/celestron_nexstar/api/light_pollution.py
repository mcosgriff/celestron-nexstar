"""
Light Pollution Data Integration

Provides Bortle scale and SQM (Sky Quality Meter) values
for assessing sky darkness at observing locations.

Uses async HTTP to fetch data from light pollution APIs with caching.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass

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


# Bortle class characteristics
BORTLE_CHARACTERISTICS = {
    BortleClass.CLASS_1: {
        "sqm_range": (21.99, 22.00),
        "naked_eye_mag": 7.6,
        "milky_way": True,
        "airglow": True,
        "zodiacal_light": True,
        "description": "Excellent dark-sky site. Zodiacal light, gegenschein, and zodiacal band visible.",
        "recommendations": ("Perfect for all types of observing", "Ideal for deep-sky imaging"),
    },
    BortleClass.CLASS_2: {
        "sqm_range": (21.89, 21.99),
        "naked_eye_mag": 7.1,
        "milky_way": True,
        "airglow": True,
        "zodiacal_light": True,
        "description": "Typical truly dark site. Airglow weakly visible near horizon.",
        "recommendations": ("Excellent for all deep-sky objects", "Good for Milky Way photography"),
    },
    BortleClass.CLASS_3: {
        "sqm_range": (21.69, 21.89),
        "naked_eye_mag": 6.6,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": True,
        "description": "Rural sky. Some light pollution evident at horizon.",
        "recommendations": ("Very good for deep-sky observing", "Milky Way structure visible"),
    },
    BortleClass.CLASS_4: {
        "sqm_range": (20.49, 21.69),
        "naked_eye_mag": 6.1,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Rural/suburban transition. Light domes visible in several directions.",
        "recommendations": ("Good for most deep-sky objects", "Brighter galaxies and nebulae visible"),
    },
    BortleClass.CLASS_5: {
        "sqm_range": (19.50, 20.49),
        "naked_eye_mag": 5.6,
        "milky_way": True,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Suburban sky. Milky Way washed out near horizon.",
        "recommendations": ("Focus on brighter deep-sky objects", "Planets and Moon excellent"),
    },
    BortleClass.CLASS_6: {
        "sqm_range": (18.94, 19.50),
        "naked_eye_mag": 5.1,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Bright suburban sky. Milky Way barely visible.",
        "recommendations": ("Bright objects only", "Excellent for planets and Moon"),
    },
    BortleClass.CLASS_7: {
        "sqm_range": (18.38, 18.94),
        "naked_eye_mag": 4.6,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Suburban/urban transition. Sky grayish white.",
        "recommendations": ("Messier objects still visible", "Focus on planets, Moon, double stars"),
    },
    BortleClass.CLASS_8: {
        "sqm_range": (0, 18.38),
        "naked_eye_mag": 4.1,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "City sky. Bright objects only.",
        "recommendations": ("Planets, Moon, brightest clusters", "Consider narrowband filters"),
    },
    BortleClass.CLASS_9: {
        "sqm_range": (0, 17.5),
        "naked_eye_mag": 4.0,
        "milky_way": False,
        "airglow": False,
        "zodiacal_light": False,
        "description": "Inner-city sky. Severely light polluted.",
        "recommendations": ("Moon and planets only", "Consider remote observing"),
    },
}


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


def _create_light_pollution_data(sqm: float, source: str | None = None, cached: bool = False) -> LightPollutionData:
    """Create LightPollutionData from SQM value."""
    bortle = sqm_to_bortle(sqm)
    chars: dict[str, Any] = BORTLE_CHARACTERISTICS[bortle]

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


async def _fetch_from_lightpollutionmap_api(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from lightpollutionmap.info API.

    This is a free API that provides light pollution data.
    """
    try:
        import aiohttp

        url = "https://www.lightpollutionmap.info/QueryRaster"
        params = {
            "ql": "1",  # Query level
            "qt": "point",  # Query type
            "qd": f"{lon},{lat}",  # Query data (lon,lat)
        }

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response,
        ):
            if response.status == 200:
                data = await response.json()
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
        logger.warning("aiohttp not installed, cannot fetch light pollution data")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch from lightpollutionmap.info: {e}")
        return None


async def _fetch_from_darksky_api(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from Dark Sky Finder or similar API.

    This is a fallback API if the primary one fails.
    """
    # Placeholder for alternative API
    # Many light pollution APIs require API keys or have rate limits
    return None


async def _fetch_sqm_async(lat: float, lon: float) -> float | None:
    """
    Fetch SQM value from available sources (async).

    Tries database first, then APIs.
    """
    # Try database first (offline, fast)
    try:
        from .database import get_database
        from .light_pollution_db import get_sqm_from_database

        db = get_database()
        sqm = get_sqm_from_database(lat, lon, db)
        if sqm is not None:
            logger.info(f"Found SQM {sqm:.2f} in database for {lat},{lon}")
            return sqm
        else:
            logger.debug(f"No SQM data in database for {lat},{lon}")
    except Exception as e:
        logger.warning(f"Database lookup failed: {e}")
        import traceback

        logger.debug(traceback.format_exc())

    # Try primary API
    sqm = await _fetch_from_lightpollutionmap_api(lat, lon)
    if sqm is not None:
        return sqm

    # Try fallback API
    sqm = await _fetch_from_darksky_api(lat, lon)
    if sqm is not None:
        return sqm

    return None


def _estimate_sqm_from_location(lat: float, lon: float) -> float:
    """
    Estimate SQM value without API data (fallback).

    Uses simple heuristic based on latitude and rough estimates.
    This is a last resort when APIs are unavailable.
    """
    # Very rough estimation: assume suburban (Bortle 5) as default
    # In a real implementation, you might use population density data
    logger.warning("Using estimated SQM value (API unavailable)")
    return 20.0


async def get_light_pollution_data_async(
    lat: float, lon: float, force_refresh: bool = False
) -> LightPollutionData:
    """
    Get light pollution data for a location (async).

    Uses async HTTP to fetch data from APIs with intelligent caching.
    Only fetches new data if cache is stale or force_refresh is True.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        force_refresh: Force refresh even if cache is valid

    Returns:
        Light pollution data
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
                            location_data["sqm"], location_data.get("source"), cached=True
                        )
                except (ValueError, KeyError):
                    pass

    # Need to fetch new data
    logger.info(f"Fetching light pollution data for {lat},{lon}")
    sqm = await _fetch_sqm_async(lat, lon)

    if sqm is None:
        # Fallback to estimation
        sqm = _estimate_sqm_from_location(lat, lon)
        source = "estimated"
    else:
        source = "lightpollutionmap.info"

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

    return _create_light_pollution_data(sqm, source, cached=False)


def get_light_pollution_data(lat: float, lon: float, force_refresh: bool = False) -> LightPollutionData:
    """
    Get light pollution data for a location (synchronous wrapper).

    This is a convenience wrapper that runs the async function.
    When called from within an async context, it will use cached data if available,
    or return estimated data to avoid event loop conflicts.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        force_refresh: Force refresh even if cache is valid

    Returns:
        Light pollution data
    """
    cache_key = _get_cache_key(lat, lon)

    # Always check database first (synchronous, fast, offline)
    try:
        from .database import get_database
        from .light_pollution_db import get_sqm_from_database

        db = get_database()
        sqm = get_sqm_from_database(lat, lon, db)
        if sqm is not None:
            logger.info(f"Found SQM {sqm:.2f} in database for {lat},{lon}")
            return _create_light_pollution_data(sqm, "database", cached=False)
    except Exception as e:
        logger.debug(f"Database lookup failed: {e}")

    # Check cache second - this is synchronous and safe
    cache_data = _load_cache()
    if not force_refresh and cache_data and "data" in cache_data:
        location_data = cache_data["data"].get(cache_key)
        if location_data and "timestamp" in location_data:
            try:
                cache_time = datetime.fromisoformat(location_data["timestamp"])
                age = datetime.now(UTC) - cache_time.replace(tzinfo=UTC)
                if age < timedelta(hours=CACHE_STALE_HOURS):
                    # Use cached data
                    return _create_light_pollution_data(
                        location_data["sqm"], location_data.get("source"), cached=True
                    )
            except (ValueError, KeyError):
                pass

    # If we need fresh data, check if we're in an async context
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context - can't block, so use cache or estimate
        if cache_data and "data" in cache_data:
            location_data = cache_data["data"].get(cache_key)
            if location_data:
                # Use stale cache rather than blocking
                return _create_light_pollution_data(
                    location_data["sqm"], location_data.get("source"), cached=True
                )
        # No cache available, use estimation
        sqm = _estimate_sqm_from_location(lat, lon)
        return _create_light_pollution_data(sqm, "estimated", cached=False)
    except RuntimeError:
        # No running event loop - safe to run async code
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # This shouldn't happen, but handle it
                sqm = _estimate_sqm_from_location(lat, lon)
                return _create_light_pollution_data(sqm, "estimated", cached=False)
            else:
                return loop.run_until_complete(get_light_pollution_data_async(lat, lon, force_refresh))
        except RuntimeError:
            # No event loop at all, create a new one
            return asyncio.run(get_light_pollution_data_async(lat, lon, force_refresh))


async def get_light_pollution_data_batch_async(
    locations: list[tuple[float, float]], force_refresh: bool = False
) -> dict[tuple[float, float], LightPollutionData]:
    """
    Get light pollution data for multiple locations (async batch).

    Fetches data for multiple locations concurrently for a full night of viewing.
    Uses caching to avoid redundant API calls.

    Args:
        locations: List of (lat, lon) tuples
        force_refresh: Force refresh even if cache is valid

    Returns:
        Dictionary mapping (lat, lon) to LightPollutionData
    """
    tasks = [get_light_pollution_data_async(lat, lon, force_refresh) for lat, lon in locations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    data_map: dict[tuple[float, float], LightPollutionData] = {}
    for (lat, lon), result in zip(locations, results, strict=False):
        if isinstance(result, Exception):
            logger.error(f"Error fetching data for {lat},{lon}: {result}")
            # Use fallback estimation
            sqm = _estimate_sqm_from_location(lat, lon)
            data_map[(lat, lon)] = _create_light_pollution_data(sqm, "estimated", cached=False)
        elif isinstance(result, LightPollutionData):
            data_map[(lat, lon)] = result
        else:
            # Unexpected type, use fallback
            logger.warning(f"Unexpected result type for {lat},{lon}: {type(result)}")
            sqm = _estimate_sqm_from_location(lat, lon)
            data_map[(lat, lon)] = _create_light_pollution_data(sqm, "estimated", cached=False)

    return data_map

