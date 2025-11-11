"""
Satellite Flares and Bright Passes

Tracks bright satellite passes including Starlink trains and other bright satellites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING


try:
    from skyfield.api import load, wgs84
    from skyfield.sgp4lib import EarthSatellite

    SKYFIELD_AVAILABLE = True
except ImportError:
    SKYFIELD_AVAILABLE = False

if TYPE_CHECKING:
    from .observer import ObserverLocation

logger = logging.getLogger(__name__)

__all__ = [
    "SatellitePass",
    "get_bright_satellite_passes",
    "get_starlink_passes",
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
}


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
    if not SKYFIELD_AVAILABLE:
        logger.warning("Skyfield not available, cannot calculate satellite passes")
        return []

    passes = []
    start_time = datetime.now(UTC)
    end_time = start_time + timedelta(days=days)

    # For each bright satellite, get passes
    for _sat_key, (norad_id, name, magnitude) in BRIGHT_SATELLITES.items():
        if magnitude > min_magnitude:
            continue

        try:
            tle_data = _fetch_tle_from_celestrak(norad_id)
            if not tle_data:
                continue

            line1, line2 = tle_data
            satellite = EarthSatellite(line1, line2, name, load.timescale())

            # Create observer
            observer = wgs84.latlon(location.latitude, location.longitude)

            # Find events
            ts = load.timescale()
            t0 = ts.from_datetime(start_time)
            t1 = ts.from_datetime(end_time)

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


def get_starlink_passes(
    location: ObserverLocation,
    days: int = 7,
) -> list[SatellitePass]:
    """
    Get Starlink train passes (simplified).

    Note: Full Starlink tracking requires fetching TLE for many satellites.
    This is a simplified version that provides general guidance.

    Args:
        location: Observer location
        days: Number of days to search (default: 7)

    Returns:
        List of SatellitePass objects (simplified)
    """
    # Starlink tracking is complex - would need to fetch TLE for many satellites
    # For now, return empty list with note
    logger.info("Starlink tracking requires fetching TLE for many satellites - not yet fully implemented")
    return []
