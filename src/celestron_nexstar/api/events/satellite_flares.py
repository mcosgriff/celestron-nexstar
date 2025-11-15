"""
Satellite Flares and Bright Passes

Tracks bright satellite passes including Starlink trains and other bright satellites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

# skyfield is a required dependency
from skyfield.api import wgs84
from skyfield.sgp4lib import EarthSatellite

from celestron_nexstar.api.core.exceptions import TLEFetchError


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "SatellitePass",
    "get_bright_satellite_passes",
    "get_starlink_passes",
    "get_stations_passes",
    "get_visual_passes",
]


@dataclass
class SatellitePass:
    """Bright satellite pass information."""

    name: str  # Satellite name
    rise_time: datetime  # When satellite appears
    max_time: datetime  # Maximum altitude time
    set_time: datetime  # When satellite disappears
    max_altitude_deg: float  # Peak altitude
    magnitude: float  # Peak brightness (lower = brighter)
    is_visible: bool  # Whether pass is visible
    notes: str  # Additional information


# Known bright satellites (NORAD IDs)
# CelesTrak provides TLE data for these
BRIGHT_SATELLITES = {
    "HST": (20580, "Hubble Space Telescope", -2.0),  # Very bright
    "TIANGONG": (48274, "Tiangong Space Station", -1.0),  # Very bright
    "CHINA-STATION": (48274, "China Space Station", -1.0),
    "BLUEWALKER-3": (54218, "BlueWalker 3", 0.4),  # Very bright satellite
    "TERRA": (25994, "Terra", 2.5),  # Earth observation satellite
    "AQUA": (27424, "Aqua", 2.5),  # Earth observation satellite
    "LACROSSE-5": (26908, "Lacrosse 5", 1.5),  # Reconnaissance satellite
}

# CelesTrak URLs
CELESTRAK_STARLINK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=TLE"
CELESTRAK_STATIONS_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=TLE"
CELESTRAK_VISUAL_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=TLE"

# TLE cache configuration
TLE_MAX_AGE_HOURS = 24  # Refresh TLE every 24 hours
STARLINK_MAX_SATELLITES = 100  # Limit number of Starlink satellites to track (for performance)
STATIONS_MAX_SATELLITES = 50  # Limit number of space station satellites to track
VISUAL_MAX_SATELLITES = 200  # Limit number of visual satellites to track (for performance)


def _fetch_tle_from_celestrak(norad_id: int) -> tuple[str, str] | None:
    """
    Fetch TLE data from CelesTrak for a satellite.

    Args:
        norad_id: NORAD catalog number

    Returns:
        Tuple of (line1, line2) or None if fetch fails
    """
    import urllib.request

    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = response.read().decode("utf-8")
            lines = data.strip().split("\n")

            if len(lines) >= 3:
                return (lines[1].strip(), lines[2].strip())
    except Exception as e:
        logger.debug(f"Failed to fetch TLE for NORAD {norad_id}: {e}")

    return None


def get_bright_satellite_passes(
    location: ObserverLocation,
    days: int = 7,
    min_magnitude: float = 3.0,
) -> list[SatellitePass]:
    """
    Get bright satellite passes for a location.

    Args:
        location: Observer location
        days: Number of days to search (default: 7)
        min_magnitude: Maximum magnitude to include (default: 3.0, brighter)

    Returns:
        List of SatellitePass objects, sorted by rise time
    """

    passes = []
    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(days=days)

    # Create observer and load timescale once (reused for all satellites)
    observer = wgs84.latlon(location.latitude, location.longitude)
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

    loader = get_skyfield_loader()
    ts = loader.timescale()
    t0 = ts.from_datetime(start_time)
    t1 = ts.from_datetime(end_time)

    # For each bright satellite, get passes
    for _sat_key, (norad_id, name, magnitude) in BRIGHT_SATELLITES.items():
        if magnitude > min_magnitude:
            continue

        try:
            tle_data = _fetch_tle_from_celestrak(norad_id)
            if not tle_data:
                continue

            line1, line2 = tle_data
            satellite = EarthSatellite(line1, line2, name, ts)

            t, events = satellite.find_events(observer, t0, t1, altitude_degrees=0.0)

            # Group into passes
            i = 0
            while i < len(events):
                if events[i] == 0:  # Rise
                    if i + 2 < len(events) and events[i + 1] == 1 and events[i + 2] == 2:
                        rise_time = t[i].utc_datetime()
                        max_time = t[i + 1].utc_datetime()
                        set_time = t[i + 2].utc_datetime()

                        # Get max altitude
                        t_max = ts.from_datetime(max_time)
                        difference = satellite - observer
                        topocentric = difference.at(t_max)
                        alt, _az, _distance = topocentric.altaz()
                        max_alt = alt.degrees

                        if max_alt >= 10.0:  # Only include passes above 10°
                            passes.append(
                                SatellitePass(
                                    name=name,
                                    rise_time=rise_time,
                                    max_time=max_time,
                                    set_time=set_time,
                                    max_altitude_deg=max_alt,
                                    magnitude=magnitude,
                                    is_visible=True,
                                    notes="Bright satellite pass - visible to naked eye",
                                )
                            )
                        i += 3
                    else:
                        i += 1
                else:
                    i += 1
        except Exception as e:
            logger.debug(f"Error calculating passes for {name}: {e}")
            continue

    # Sort by rise time
    passes.sort(key=lambda p: p.rise_time)
    return passes


def _parse_tle_epoch(line1: str) -> datetime | None:
    """
    Parse epoch from TLE line 1.

    Args:
        line1: First line of TLE

    Returns:
        Epoch datetime or None if parsing fails
    """
    try:
        # TLE epoch format: YYDDD.DDDDDDDD (year, day of year, fractional day)
        # Extract epoch from line1 (characters 18-32)
        epoch_str = line1[18:32].strip()
        if not epoch_str:
            return None

        year_2digit = int(epoch_str[:2])
        day_of_year = float(epoch_str[2:])

        # Convert 2-digit year to 4-digit (assume 2000-2099)
        year = 2000 + year_2digit if year_2digit < 50 else 1900 + year_2digit

        # Calculate date from day of year
        base_date = datetime(year, 1, 1, tzinfo=UTC)
        days = int(day_of_year)
        fractional_day = day_of_year - days
        hours = int(fractional_day * 24)
        minutes = int((fractional_day * 24 - hours) * 60)
        seconds = int(((fractional_day * 24 - hours) * 60 - minutes) * 60)

        epoch = base_date + timedelta(days=days - 1, hours=hours, minutes=minutes, seconds=seconds)
        return epoch
    except Exception:
        return None


def _extract_norad_id(line1: str) -> int | None:
    """
    Extract NORAD ID from TLE line 1.

    Args:
        line1: First line of TLE

    Returns:
        NORAD ID or None if extraction fails
    """
    try:
        # NORAD ID is in characters 2-7 of line1
        norad_str = line1[2:7].strip()
        return int(norad_str)
    except Exception:
        return None


async def _fetch_group_tle_from_celestrak(
    url: str, group_name: str, max_satellites: int
) -> list[tuple[int, str, str, str]]:
    """
    Fetch TLE data from CelesTrak for a satellite group (async).

    Args:
        url: CelesTrak URL for the group
        group_name: Name of the satellite group (for logging)
        max_satellites: Maximum number of satellites to fetch

    Returns:
        List of tuples: (norad_id, satellite_name, line1, line2)

    Raises:
        RuntimeError: If fetch fails
    """
    import aiohttp

    try:
        logger.info(f"Fetching {group_name} TLE data from CelesTrak...")

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                msg = f"Failed to fetch {group_name} TLE: HTTP {response.status}"
                raise TLEFetchError(msg) from None

            data = await response.text()
            lines = data.strip().split("\n")

            # Parse TLE data (format: Name\nLine1\nLine2\nName\nLine1\nLine2...)
            tle_list = []
            i = 0
            while i < len(lines) - 2:
                name = lines[i].strip()
                line1 = lines[i + 1].strip()
                line2 = lines[i + 2].strip()

                # Validate TLE format
                if line1.startswith("1 ") and line2.startswith("2 "):
                    norad_id = _extract_norad_id(line1)
                    if norad_id:
                        tle_list.append((norad_id, name, line1, line2))
                        if len(tle_list) >= max_satellites:
                            logger.info(f"Limiting to first {max_satellites} {group_name} satellites")
                            break

                i += 3

            logger.info(f"Fetched {len(tle_list)} {group_name} TLE records")
            return tle_list

    except Exception as e:
        if isinstance(e, TLEFetchError):
            raise
        msg = f"Failed to fetch {group_name} TLE: {e}"
        raise TLEFetchError(msg) from e


async def _fetch_starlink_tle_from_celestrak() -> list[tuple[int, str, str, str]]:
    """
    Fetch Starlink TLE data from CelesTrak (async).

    Returns:
        List of tuples: (norad_id, satellite_name, line1, line2)

    Raises:
        RuntimeError: If fetch fails
    """
    return await _fetch_group_tle_from_celestrak(CELESTRAK_STARLINK_URL, "Starlink", STARLINK_MAX_SATELLITES)


def _get_cached_group_tle(
    group_name: str, max_satellites: int, db_session: Session | None = None
) -> list[tuple[int, str, str, str, datetime]] | None:
    """
    Get cached TLE data for a satellite group if fresh enough.

    Args:
        group_name: Name of the satellite group (e.g., "starlink", "stations", "visual")
        max_satellites: Maximum number of satellites to return
        db_session: Database session (optional)

    Returns:
        List of tuples: (norad_id, satellite_name, line1, line2, fetched_at) or None if cache is stale/missing
    """
    if db_session is None:
        return None

    try:
        from celestron_nexstar.api.database.models import TLEModel

        # Check for fresh TLE data (less than 24 hours old)
        cache_cutoff = datetime.now(UTC) - timedelta(hours=TLE_MAX_AGE_HOURS)

        cached_tles = (
            db_session.query(TLEModel)
            .filter(
                TLEModel.satellite_group == group_name,
                TLEModel.fetched_at >= cache_cutoff,
            )
            .limit(max_satellites)
            .all()
        )

        if cached_tles:
            logger.info(f"Using {len(cached_tles)} cached {group_name} TLE records")
            return [(tle.norad_id, tle.satellite_name, tle.line1, tle.line2, tle.fetched_at) for tle in cached_tles]

    except Exception as e:
        logger.debug(f"Error reading cached TLE: {e}")

    return None


def _get_cached_starlink_tle(db_session: Session | None = None) -> list[tuple[int, str, str, str, datetime]] | None:
    """
    Get cached Starlink TLE data if fresh enough.

    Args:
        db_session: Database session (optional)

    Returns:
        List of tuples: (norad_id, satellite_name, line1, line2, fetched_at) or None if cache is stale/missing
    """
    return _get_cached_group_tle("starlink", STARLINK_MAX_SATELLITES, db_session)


async def _store_group_tle(
    tle_list: list[tuple[int, str, str, str]],
    group_name: str,
    db_session: Session | None = None,
) -> None:
    """
    Store TLE data for a satellite group in database.

    Args:
        tle_list: List of tuples: (norad_id, satellite_name, line1, line2)
        group_name: Name of the satellite group (e.g., "starlink", "stations", "visual")
        db_session: Database session (optional)
    """
    if db_session is None:
        return

    try:
        from celestron_nexstar.api.database.models import TLEModel

        fetch_time = datetime.now(UTC)

        # Delete old TLE data for this group
        db_session.query(TLEModel).filter(TLEModel.satellite_group == group_name).delete()

        # Insert new TLE data
        for norad_id, name, line1, line2 in tle_list:
            epoch = _parse_tle_epoch(line1)
            tle_model = TLEModel(
                norad_id=norad_id,
                satellite_name=name,
                satellite_group=group_name,
                line1=line1,
                line2=line2,
                epoch=epoch,
                fetched_at=fetch_time,
            )
            db_session.add(tle_model)

        db_session.commit()
        logger.info(f"Stored {len(tle_list)} {group_name} TLE records in database")

    except Exception as e:
        logger.warning(f"Error storing TLE data: {e}")
        db_session.rollback()


async def _store_starlink_tle(
    tle_list: list[tuple[int, str, str, str]],
    db_session: Session | None = None,
) -> None:
    """
    Store Starlink TLE data in database.

    Args:
        tle_list: List of tuples: (norad_id, satellite_name, line1, line2)
        db_session: Database session (optional)
    """
    await _store_group_tle(tle_list, "starlink", db_session)


async def _get_group_satellites(
    url: str,
    group_name: str,
    max_satellites: int,
    db_session: Session | None = None,
) -> list[EarthSatellite]:
    """
    Get satellite objects with current TLE for a satellite group.

    Args:
        url: CelesTrak URL for the group
        group_name: Name of the satellite group (e.g., "starlink", "stations", "visual")
        max_satellites: Maximum number of satellites to track
        db_session: Database session (optional)

    Returns:
        List of Skyfield EarthSatellite objects

    Raises:
        RuntimeError: If TLE cannot be obtained
    """

    # Try cache first
    cached_tles = _get_cached_group_tle(group_name, max_satellites, db_session)

    if cached_tles:
        tle_list = [(norad_id, name, line1, line2) for norad_id, name, line1, line2, _ in cached_tles]
    else:
        # Fetch fresh TLE
        tle_list = await _fetch_group_tle_from_celestrak(url, group_name, max_satellites)
        # Store in database
        await _store_group_tle(tle_list, group_name, db_session)

    # Create satellite objects
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

    loader = get_skyfield_loader()
    ts = loader.timescale()
    satellites = []

    for norad_id, name, line1, line2 in tle_list:
        try:
            satellite = EarthSatellite(line1, line2, name, ts)
            satellites.append(satellite)
        except Exception as e:
            logger.debug(f"Error creating satellite object for {name} (NORAD {norad_id}): {e}")
            continue

    logger.info(f"Created {len(satellites)} {group_name} satellite objects")
    return satellites


async def _get_starlink_satellites(
    db_session: Session | None = None,
) -> list[EarthSatellite]:
    """Get Starlink satellite objects with current TLE."""
    return await _get_group_satellites(CELESTRAK_STARLINK_URL, "starlink", STARLINK_MAX_SATELLITES, db_session)


def get_starlink_passes(
    location: ObserverLocation,
    days: int = 7,
    min_altitude_deg: float = 10.0,
    max_passes: int = 50,
    db_session: Session | None = None,
) -> list[SatellitePass]:
    """
    Get Starlink train passes for a location.

    Fetches TLE data from CelesTrak (or uses cached data), stores it in the database,
    and calculates visible passes for Starlink satellites.

    Args:
        location: Observer location
        days: Number of days to search (default: 7)
        min_altitude_deg: Minimum peak altitude for pass (default: 10°)
        max_passes: Maximum number of passes to return (default: 50)
        db_session: Database session (optional, for caching)

    Returns:
        List of SatellitePass objects, sorted by rise time
    """

    import asyncio

    try:
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        satellites = asyncio.run(_get_starlink_satellites(db_session))
    except Exception as e:
        logger.error(f"Failed to get Starlink satellites: {e}")
        return []

    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(days=days)

    return _calculate_passes_for_satellites(
        satellites, location, start_time, end_time, min_altitude_deg, max_passes, "Starlink"
    )


async def _get_stations_satellites(
    db_session: Session | None = None,
) -> list[EarthSatellite]:
    """Get space station satellite objects with current TLE."""
    return await _get_group_satellites(CELESTRAK_STATIONS_URL, "stations", STATIONS_MAX_SATELLITES, db_session)


async def _get_visual_satellites(
    db_session: Session | None = None,
) -> list[EarthSatellite]:
    """Get visually observable satellite objects with current TLE."""
    return await _get_group_satellites(CELESTRAK_VISUAL_URL, "visual", VISUAL_MAX_SATELLITES, db_session)


def _calculate_passes_for_satellites(
    satellites: list[EarthSatellite],
    location: ObserverLocation,
    start_time: datetime,
    end_time: datetime,
    min_altitude_deg: float,
    max_passes: int,
    group_name: str = "satellite",
) -> list[SatellitePass]:
    """
    Calculate passes for a list of satellites.

    Args:
        satellites: List of EarthSatellite objects
        location: Observer location
        start_time: Start of search window
        end_time: End of search window
        min_altitude_deg: Minimum peak altitude for pass
        max_passes: Maximum number of passes to return
        group_name: Name of satellite group (for notes)

    Returns:
        List of SatellitePass objects
    """
    if not satellites:
        logger.warning(f"No {group_name} satellites available")
        return []

    passes: list[SatellitePass] = []
    observer = wgs84.latlon(location.latitude, location.longitude)

    # Load timescale and ephemeris
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

    loader = get_skyfield_loader()
    ts = loader.timescale()
    t0 = ts.from_datetime(start_time)
    t1 = ts.from_datetime(end_time)

    # Load ephemeris for sun visibility check
    eph = loader("de421.bsp")

    # Calculate passes for each satellite
    for satellite in satellites:
        try:
            # Find events: 0=rise, 1=culminate (max alt), 2=set
            t, events = satellite.find_events(observer, t0, t1, altitude_degrees=0.0)

            # Group events into passes (rise -> culminate -> set)
            i = 0
            while i < len(events) and len(passes) < max_passes:
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

                            # Calculate max altitude
                            difference_max = satellite - observer
                            topocentric_max = difference_max.at(max_t)
                            alt_max, _az_max, _distance = topocentric_max.altaz()
                            max_altitude = alt_max.degrees

                            # Filter by minimum altitude
                            if max_altitude >= min_altitude_deg:
                                # Check if sunlit (visible)
                                is_sunlit = satellite.at(max_t).is_sunlit(eph)

                                # Estimate magnitude (rough estimate based on altitude)
                                magnitude = 3.0 + (90 - max_altitude) / 30.0
                                if not is_sunlit:
                                    magnitude = 10.0  # Not visible if in shadow

                                # Get satellite name from TLE
                                satellite_name = str(satellite.name) if hasattr(satellite, "name") else group_name

                                passes.append(
                                    SatellitePass(
                                        name=satellite_name,
                                        rise_time=rise_time,
                                        max_time=max_time,
                                        set_time=set_time,
                                        max_altitude_deg=max_altitude,
                                        magnitude=magnitude,
                                        is_visible=is_sunlit,
                                        notes=f"{group_name.title()} satellite pass",
                                    )
                                )

                            i += 3  # Move past rise-culminate-set
                            continue

                i += 1

        except Exception as e:
            logger.debug(f"Error calculating passes for satellite: {e}")
            continue

    # Sort by rise time
    passes.sort(key=lambda p: p.rise_time)

    logger.info(f"Found {len(passes)} {group_name} passes")
    return passes[:max_passes]


def get_stations_passes(
    location: ObserverLocation,
    days: int = 7,
    min_altitude_deg: float = 10.0,
    max_passes: int = 50,
    db_session: Session | None = None,
) -> list[SatellitePass]:
    """
    Get space station passes for a location.

    Fetches TLE data from CelesTrak (or uses cached data), stores it in the database,
    and calculates visible passes for space stations (ISS, Tiangong, etc.).

    Args:
        location: Observer location
        days: Number of days to search (default: 7)
        min_altitude_deg: Minimum peak altitude for pass (default: 10°)
        max_passes: Maximum number of passes to return (default: 50)
        db_session: Database session (optional, for caching)

    Returns:
        List of SatellitePass objects, sorted by rise time
    """

    import asyncio

    try:
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        satellites = asyncio.run(_get_stations_satellites(db_session))
    except Exception as e:
        logger.error(f"Failed to get space station satellites: {e}")
        return []

    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(days=days)

    return _calculate_passes_for_satellites(
        satellites, location, start_time, end_time, min_altitude_deg, max_passes, "space station"
    )


def get_visual_passes(
    location: ObserverLocation,
    days: int = 7,
    min_altitude_deg: float = 10.0,
    max_passes: int = 100,
    db_session: Session | None = None,
) -> list[SatellitePass]:
    """
    Get visually observable satellite passes for a location.

    Fetches TLE data from CelesTrak (or uses cached data), stores it in the database,
    and calculates visible passes for visually observable satellites.

    Args:
        location: Observer location
        days: Number of days to search (default: 7)
        min_altitude_deg: Minimum peak altitude for pass (default: 10°)
        max_passes: Maximum number of passes to return (default: 100)
        db_session: Database session (optional, for caching)

    Returns:
        List of SatellitePass objects, sorted by rise time
    """

    import asyncio

    try:
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        satellites = asyncio.run(_get_visual_satellites(db_session))
    except Exception as e:
        logger.error(f"Failed to get visual satellites: {e}")
        return []

    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(days=days)

    return _calculate_passes_for_satellites(
        satellites, location, start_time, end_time, min_altitude_deg, max_passes, "visual"
    )
