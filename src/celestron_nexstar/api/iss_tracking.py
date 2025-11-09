"""
ISS Pass Prediction and Tracking

Fetches ISS orbital data and calculates visible passes for a given location.
Uses Skyfield for accurate satellite tracking and caches results in database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from skyfield.api import load, wgs84
from skyfield.sgp4lib import EarthSatellite

from .compass import azimuth_to_compass_8point


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

__all__ = [
    "ISSPass",
    "get_iss_passes",
    "get_iss_passes_cached",
]

# TLE data source
CELESTRAK_ISS_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"

# Cache configuration
TLE_CACHE_DIR = Path.home() / ".celestron_nexstar" / "cache"
TLE_CACHE_FILE = TLE_CACHE_DIR / "iss_tle.txt"
TLE_MAX_AGE_HOURS = 24  # Refresh TLE every 24 hours
PASS_CACHE_MAX_AGE_HOURS = 24  # Pass predictions valid for 24 hours


@dataclass(frozen=True)
class ISSPass:
    """ISS pass over a location."""

    rise_time: datetime  # When ISS appears above horizon
    max_time: datetime  # When ISS reaches maximum altitude
    set_time: datetime  # When ISS disappears below horizon

    duration_seconds: int  # Total pass duration
    max_altitude_deg: float  # Peak altitude above horizon

    rise_azimuth_deg: float  # Compass direction where it appears
    max_azimuth_deg: float  # Compass direction at peak
    set_azimuth_deg: float  # Compass direction where it disappears

    magnitude: float | None  # Brightness estimate (if available)
    is_visible: bool  # Whether ISS is sunlit (visible vs in shadow)

    @property
    def rise_direction(self) -> str:
        """Compass direction where ISS rises."""
        return azimuth_to_compass_8point(self.rise_azimuth_deg)

    @property
    def max_direction(self) -> str:
        """Compass direction at maximum altitude."""
        return azimuth_to_compass_8point(self.max_azimuth_deg)

    @property
    def set_direction(self) -> str:
        """Compass direction where ISS sets."""
        return azimuth_to_compass_8point(self.set_azimuth_deg)

    @property
    def is_good_pass(self) -> bool:
        """Whether this is a good quality pass (>30° max altitude)."""
        return self.max_altitude_deg >= 30

    @property
    def quality_rating(self) -> str:
        """Quality rating based on maximum altitude."""
        if self.max_altitude_deg >= 70:
            return "Excellent"
        elif self.max_altitude_deg >= 50:
            return "Very Good"
        elif self.max_altitude_deg >= 30:
            return "Good"
        elif self.max_altitude_deg >= 15:
            return "Fair"
        else:
            return "Poor"


def _ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    TLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cached_tle() -> tuple[str, str, datetime] | None:
    """
    Get cached TLE data if fresh enough.

    Returns:
        Tuple of (line1, line2, fetch_time) or None if cache is stale/missing
    """
    if not TLE_CACHE_FILE.exists():
        return None

    try:
        # Check file age
        file_age = datetime.now(UTC) - datetime.fromtimestamp(TLE_CACHE_FILE.stat().st_mtime, UTC)
        if file_age > timedelta(hours=TLE_MAX_AGE_HOURS):
            logger.info("TLE cache is stale (age: %s)", file_age)
            return None

        # Read TLE
        with TLE_CACHE_FILE.open("r") as f:
            lines = f.readlines()
            if len(lines) >= 3:
                # Format: Name\nLine1\nLine2
                line1 = lines[1].strip()
                line2 = lines[2].strip()
                fetch_time = datetime.fromtimestamp(TLE_CACHE_FILE.stat().st_mtime, UTC)
                logger.debug("Using cached TLE (age: %s)", file_age)
                return (line1, line2, fetch_time)

    except Exception as e:
        logger.warning(f"Error reading TLE cache: {e}")

    return None


def _fetch_tle_from_celestrak() -> tuple[str, str, datetime]:
    """
    Fetch current ISS TLE from CelesTrak.

    Returns:
        Tuple of (line1, line2, fetch_time)

    Raises:
        RuntimeError: If fetch fails
    """
    import urllib.request

    logger.info("Fetching ISS TLE from CelesTrak...")

    try:
        with urllib.request.urlopen(CELESTRAK_ISS_URL, timeout=10) as response:
            data = response.read().decode("utf-8")
            lines = data.strip().split("\n")

            if len(lines) >= 3:
                line1 = lines[1].strip()
                line2 = lines[2].strip()
                fetch_time = datetime.now(UTC)

                # Cache it
                _ensure_cache_dir()
                with TLE_CACHE_FILE.open("w") as f:
                    f.write(data)

                logger.info("ISS TLE fetched and cached successfully")
                return (line1, line2, fetch_time)
            else:
                msg = "Invalid TLE format from CelesTrak"
                raise RuntimeError(msg)

    except Exception as e:
        msg = f"Failed to fetch ISS TLE: {e}"
        raise RuntimeError(msg) from e


def _get_iss_satellite() -> EarthSatellite:
    """
    Get ISS satellite object with current TLE.

    Returns:
        Skyfield EarthSatellite object for ISS

    Raises:
        RuntimeError: If TLE cannot be obtained
    """
    # Try cache first
    cached_tle = _get_cached_tle()

    if cached_tle:
        line1, line2, _fetch_time = cached_tle
    else:
        # Fetch fresh TLE
        line1, line2, _fetch_time = _fetch_tle_from_celestrak()

    # Create satellite object
    ts = load.timescale()
    satellite = EarthSatellite(line1, line2, "ISS (ZARYA)", ts)

    return satellite


def get_iss_passes(
    latitude: float,
    longitude: float,
    start_time: datetime | None = None,
    days: int = 7,
    min_altitude_deg: float = 10.0,
) -> list[ISSPass]:
    """
    Calculate ISS passes for a location.

    Uses Skyfield to compute accurate satellite passes with detailed
    azimuth and altitude information.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        start_time: Start of search window (default: now)
        days: Number of days to search (default: 7)
        min_altitude_deg: Minimum peak altitude for pass (default: 10°)

    Returns:
        List of ISS passes sorted by rise time

    Raises:
        RuntimeError: If satellite data cannot be obtained
    """
    if start_time is None:
        start_time = datetime.now(UTC)
    elif start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    else:
        start_time = start_time.astimezone(UTC)

    end_time = start_time + timedelta(days=days)

    logger.info(f"Calculating ISS passes for lat={latitude}, lon={longitude}, {days} days")

    # Get ISS satellite
    satellite = _get_iss_satellite()

    # Create observer location
    observer = wgs84.latlon(latitude, longitude)

    # Load timescale
    ts = load.timescale()
    t0 = ts.from_datetime(start_time)
    t1 = ts.from_datetime(end_time)

    # Find events: 0=rise, 1=culminate (max alt), 2=set
    t, events = satellite.find_events(observer, t0, t1, altitude_degrees=0.0)

    # Group events into passes (rise -> culminate -> set)
    passes: list[ISSPass] = []
    i = 0
    while i < len(events):
        if events[i] == 0:  # Rise event
            rise_t = t[i]
            rise_time = rise_t.utc_datetime()

            # Look for culmination
            if i + 1 < len(events) and events[i + 1] == 1:
                max_t = t[i + 1]
                max_time = max_t.utc_datetime()

                # Look for set
                if i + 2 < len(events) and events[i + 2] == 2:
                    set_t = t[i + 2]
                    set_time = set_t.utc_datetime()

                    # Calculate positions
                    difference_rise = satellite - observer
                    topocentric_rise = difference_rise.at(rise_t)
                    _alt_rise, az_rise, _distance = topocentric_rise.altaz()

                    difference_max = satellite - observer
                    topocentric_max = difference_max.at(max_t)
                    alt_max, az_max, _distance = topocentric_max.altaz()

                    difference_set = satellite - observer
                    topocentric_set = difference_set.at(set_t)
                    _alt_set, az_set, _distance = topocentric_set.altaz()

                    max_altitude = alt_max.degrees

                    # Filter by minimum altitude
                    if max_altitude >= min_altitude_deg:
                        # Check if sunlit (visible)
                        # ISS is visible when it's in sunlight and observer is in darkness
                        is_sunlit = satellite.at(max_t).is_sunlit(load("de421.bsp"))

                        duration = int((set_time - rise_time).total_seconds())

                        iss_pass = ISSPass(
                            rise_time=rise_time,
                            max_time=max_time,
                            set_time=set_time,
                            duration_seconds=duration,
                            max_altitude_deg=max_altitude,
                            rise_azimuth_deg=az_rise.degrees,
                            max_azimuth_deg=az_max.degrees,
                            set_azimuth_deg=az_set.degrees,
                            magnitude=None,  # TODO: Calculate magnitude if needed
                            is_visible=is_sunlit,
                        )

                        passes.append(iss_pass)

                    i += 3  # Move past rise-culminate-set
                    continue

        i += 1

    logger.info(f"Found {len(passes)} ISS passes")
    return passes


def get_iss_passes_cached(
    latitude: float,
    longitude: float,
    start_time: datetime | None = None,
    days: int = 7,
    min_altitude_deg: float = 10.0,
    db_session: Session | None = None,
) -> list[ISSPass]:
    """
    Get ISS passes with database caching.

    Checks database cache first. If cache is fresh (< 24 hours), returns cached data.
    Otherwise calculates new passes and updates cache.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        start_time: Start of search window (default: now)
        days: Number of days to search (default: 7)
        min_altitude_deg: Minimum peak altitude for pass (default: 10°)
        db_session: SQLAlchemy session (optional, creates new if None)

    Returns:
        List of ISS passes sorted by rise time
    """
    if start_time is None:
        start_time = datetime.now(UTC)

    # Round location to ~1km precision for cache key
    lat_rounded = round(latitude, 2)
    lon_rounded = round(longitude, 2)

    # Try to get from cache
    if db_session is not None:
        from .models import ISSPassModel

        # Check for fresh cached passes
        cache_cutoff = datetime.now(UTC) - timedelta(hours=PASS_CACHE_MAX_AGE_HOURS)

        cached_passes = (
            db_session.query(ISSPassModel)
            .filter(
                ISSPassModel.latitude == lat_rounded,
                ISSPassModel.longitude == lon_rounded,
                ISSPassModel.rise_time >= start_time,
                ISSPassModel.fetched_at >= cache_cutoff,
            )
            .order_by(ISSPassModel.rise_time)
            .all()
        )

        if cached_passes:
            logger.info(f"Using {len(cached_passes)} cached ISS passes")
            return [
                ISSPass(
                    rise_time=p.rise_time,
                    max_time=p.max_time,
                    set_time=p.set_time,
                    duration_seconds=p.duration_seconds,
                    max_altitude_deg=p.max_altitude_deg,
                    rise_azimuth_deg=p.rise_azimuth_deg,
                    max_azimuth_deg=p.max_azimuth_deg,
                    set_azimuth_deg=p.set_azimuth_deg,
                    magnitude=p.magnitude,
                    is_visible=p.is_visible,
                )
                for p in cached_passes
            ]

    # Calculate fresh passes
    passes = get_iss_passes(latitude, longitude, start_time, days, min_altitude_deg)

    # Cache in database
    if db_session is not None and passes:
        from .models import ISSPassModel

        # Delete old cached passes for this location
        db_session.query(ISSPassModel).filter(
            ISSPassModel.latitude == lat_rounded,
            ISSPassModel.longitude == lon_rounded,
        ).delete()

        # Insert new passes
        fetch_time = datetime.now(UTC)
        for iss_pass in passes:
            pass_model = ISSPassModel(
                latitude=lat_rounded,
                longitude=lon_rounded,
                rise_time=iss_pass.rise_time,
                max_time=iss_pass.max_time,
                set_time=iss_pass.set_time,
                duration_seconds=iss_pass.duration_seconds,
                max_altitude_deg=iss_pass.max_altitude_deg,
                rise_azimuth_deg=iss_pass.rise_azimuth_deg,
                max_azimuth_deg=iss_pass.max_azimuth_deg,
                set_azimuth_deg=iss_pass.set_azimuth_deg,
                magnitude=iss_pass.magnitude,
                is_visible=iss_pass.is_visible,
                fetched_at=fetch_time,
            )
            db_session.add(pass_model)

        db_session.commit()
        logger.info(f"Cached {len(passes)} ISS passes in database")

    return passes
