"""
JPL Horizons SPK File Management

Downloads and manages SPK (SPICE kernel) files from JPL Horizons
for high-accuracy comet and asteroid ephemeris calculations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


__all__ = [
    "SPKFileInfo",
    "compute_asteroid_position_from_elements",
    "compute_comet_position_from_elements",
    "compute_position_from_spk",
    "download_asteroid_spk",
    "download_asteroid_spk_sync",
    "download_comet_spk",
    "get_asteroid_spk_file_path",
    "get_spk_cache_dir",
    "get_spk_file_path",
    "list_cached_spks",
    "load_asteroid_spk",
    "load_comet_spk",
]


# Horizons API endpoint for SPK file generation
HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"


@dataclass
class SPKFileInfo:
    """Information about a cached SPK file."""

    designation: str  # Comet designation (e.g., "C/2023 A3")
    filename: str  # SPK filename
    file_path: Path  # Full path to file
    size_bytes: int  # File size
    downloaded_at: datetime  # When file was downloaded
    coverage_start: datetime  # Start of ephemeris coverage
    coverage_end: datetime  # End of ephemeris coverage


def get_spk_cache_dir() -> Path:
    """
    Get the SPK cache directory.

    Returns:
        Path to ~/.cache/celestron-nexstar/spk/
    """
    spk_dir = Path.home() / ".cache" / "celestron-nexstar" / "spk"
    spk_dir.mkdir(parents=True, exist_ok=True)
    return spk_dir


def _sanitize_designation(designation: str) -> str:
    """
    Sanitize a comet designation for use as a filename.

    Args:
        designation: Comet designation (e.g., "C/2023 A3 (Tsuchinshan-ATLAS)")

    Returns:
        Sanitized string safe for filenames
    """
    # Remove parenthetical names
    clean = re.sub(r"\s*\([^)]*\)", "", designation)
    # Replace special chars with underscores
    clean = re.sub(r"[/\\:\s]+", "_", clean)
    # Remove leading/trailing underscores
    clean = clean.strip("_")
    return clean


def get_spk_file_path(designation: str) -> Path:
    """
    Get the expected path for a comet's SPK file.

    Args:
        designation: Comet designation

    Returns:
        Path where SPK file would be stored
    """
    filename = f"{_sanitize_designation(designation)}.bsp"
    return get_spk_cache_dir() / filename


def _build_horizons_request_params(
    designation: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, str]:
    """
    Build Horizons API request parameters for SPK generation.

    Args:
        designation: Comet designation (e.g., "C/2023 A3")
        start_date: Start of ephemeris coverage
        end_date: End of ephemeris coverage

    Returns:
        Dict of request parameters
    """
    # Format dates for Horizons API (YYYY-MM-DD)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Build command - for comets use DES= prefix
    # Strip any parenthetical name and source suffixes (MPEC, MPC, etc.) for cleaner lookup
    clean_des = re.sub(r"\s*\([^)]*\)", "", designation).strip()
    # Remove trailing source designators like MPEC, MPC, JPL, etc.
    clean_des = re.sub(r"\s+(MPEC|MPC|JPL|IAU)$", "", clean_des, flags=re.IGNORECASE).strip()

    return {
        "format": "json",
        "COMMAND": f"'{clean_des};'",  # Quote and semicolon required for comet designations
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "SPK",
        "CENTER": "@sun",  # Heliocentric
        "START_TIME": start_str,
        "STOP_TIME": end_str,
        "STEP_SIZE": "1d",  # Daily steps for SPK
    }


async def _fetch_spk_async(
    designation: str,
    start_date: datetime,
    end_date: datetime,
) -> bytes | None:
    """
    Fetch SPK data from Horizons API asynchronously.

    Args:
        designation: Comet designation
        start_date: Start of coverage
        end_date: End of coverage

    Returns:
        SPK file content as bytes, or None if failed
    """
    import aiohttp
    from aiohttp import ClientTimeout

    params = _build_horizons_request_params(designation, start_date, end_date)
    timeout = ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(HORIZONS_API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Horizons API returned status {resp.status} for {designation}")
                    return None

                data = await resp.json()

                # Check for errors in response
                if "error" in data:
                    logger.error(f"Horizons API error for {designation}: {data['error']}")
                    return None

                # Get SPK URL from response
                spk_url = data.get("spk_file_id") or data.get("spk")
                if not spk_url:
                    # Check if we got a result with ephemeris URL
                    result = data.get("result", "")
                    if "$$SOE" in result:
                        logger.warning(f"Got ephemeris text instead of SPK for {designation}")
                    else:
                        logger.error(f"No SPK URL in Horizons response for {designation}")
                    return None

                # Download the actual SPK file (using session timeout)
                download_timeout = ClientTimeout(total=120)
                async with aiohttp.ClientSession(timeout=download_timeout) as dl_session:
                    async with dl_session.get(spk_url) as spk_resp:
                        if spk_resp.status != 200:
                            logger.error(f"Failed to download SPK file for {designation}: {spk_resp.status}")
                            return None
                        return await spk_resp.read()

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching SPK for {designation}: {e}")
        return None
    except TimeoutError:
        logger.error(f"Timeout fetching SPK for {designation}")
        return None


def download_comet_spk(
    designation: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    force: bool = False,
) -> SPKFileInfo | None:
    """
    Download SPK file for a comet from JPL Horizons.

    Args:
        designation: Comet designation (e.g., "C/2023 A3")
        start_date: Start of ephemeris coverage (default: 1 year ago)
        end_date: End of ephemeris coverage (default: 2 years from now)
        force: Force re-download even if file exists

    Returns:
        SPKFileInfo if successful, None if failed
    """
    import asyncio

    # Default date range: 1 year back, 2 years forward
    now = datetime.now(UTC)
    if start_date is None:
        start_date = now - timedelta(days=365)
    if end_date is None:
        end_date = now + timedelta(days=730)

    # Check for existing file
    file_path = get_spk_file_path(designation)
    if file_path.exists() and not force:
        # Load existing file info
        stat = file_path.stat()
        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=stat.st_size,
            downloaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    # Download SPK
    try:
        # Run async download
        loop = asyncio.new_event_loop()
        try:
            spk_data = loop.run_until_complete(_fetch_spk_async(designation, start_date, end_date))
        finally:
            loop.close()

        if spk_data is None:
            return None

        # Write to cache
        file_path.write_bytes(spk_data)
        logger.info(f"Downloaded SPK for {designation} ({len(spk_data)} bytes)")

        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=len(spk_data),
            downloaded_at=datetime.now(UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    except Exception as e:
        logger.error(f"Error downloading SPK for {designation}: {e}")
        return None


def download_comet_spk_sync(
    designation: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    force: bool = False,
) -> SPKFileInfo | None:
    """
    Synchronous version of SPK download using requests.

    For use in contexts where asyncio is not available.
    """
    import requests

    # Default date range
    now = datetime.now(UTC)
    if start_date is None:
        start_date = now - timedelta(days=365)
    if end_date is None:
        end_date = now + timedelta(days=730)

    # Check for existing file
    file_path = get_spk_file_path(designation)
    if file_path.exists() and not force:
        stat = file_path.stat()
        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=stat.st_size,
            downloaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    params = _build_horizons_request_params(designation, start_date, end_date)

    try:
        # Request SPK from Horizons
        resp = requests.get(HORIZONS_API_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            logger.error(f"Horizons API error for {designation}: {data['error']}")
            return None

        # Get SPK URL
        spk_url = data.get("spk_file_id") or data.get("spk")
        if not spk_url:
            logger.error(f"No SPK URL in Horizons response for {designation}")
            return None

        # Download SPK file
        spk_resp = requests.get(spk_url, timeout=120)
        spk_resp.raise_for_status()
        spk_data = spk_resp.content

        # Write to cache
        file_path.write_bytes(spk_data)
        logger.info(f"Downloaded SPK for {designation} ({len(spk_data)} bytes)")

        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=len(spk_data),
            downloaded_at=datetime.now(UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    except requests.RequestException as e:
        logger.error(f"Network error downloading SPK for {designation}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading SPK for {designation}: {e}")
        return None


def list_cached_spks() -> list[SPKFileInfo]:
    """
    List all cached SPK files.

    Returns:
        List of SPKFileInfo for all cached files
    """
    spk_dir = get_spk_cache_dir()
    results = []

    for file_path in spk_dir.glob("*.bsp"):
        stat = file_path.stat()
        # Extract designation from filename (reverse of sanitization)
        designation = file_path.stem.replace("_", "/", 1).replace("_", " ")

        results.append(
            SPKFileInfo(
                designation=designation,
                filename=file_path.name,
                file_path=file_path,
                size_bytes=stat.st_size,
                downloaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                coverage_start=datetime.now(UTC) - timedelta(days=365),  # Approximate
                coverage_end=datetime.now(UTC) + timedelta(days=730),  # Approximate
            )
        )

    return results


def load_comet_spk(designation: str) -> tuple[bool, Path | None]:
    """
    Check if SPK exists for comet and return path if available.

    Args:
        designation: Comet designation

    Returns:
        Tuple of (is_available, file_path)
    """
    file_path = get_spk_file_path(designation)
    if file_path.exists():
        return True, file_path
    return False, None


# =============================================================================
# ASTEROID SPK FUNCTIONS
# =============================================================================


def _sanitize_asteroid_designation(designation: str) -> str:
    """
    Sanitize an asteroid designation for use as a filename.

    Args:
        designation: Asteroid designation (e.g., "1", "4 Vesta", "99942 Apophis")

    Returns:
        Sanitized string safe for filenames
    """
    # Remove parenthetical names
    clean = re.sub(r"\s*\([^)]*\)", "", designation)
    # Replace special chars with underscores
    clean = re.sub(r"[/\\:\s]+", "_", clean)
    # Remove leading/trailing underscores
    clean = clean.strip("_")
    return f"asteroid_{clean}"


def get_asteroid_spk_file_path(designation: str) -> Path:
    """
    Get the expected path for an asteroid's SPK file.

    Args:
        designation: Asteroid designation (e.g., "1", "4")

    Returns:
        Path where SPK file would be stored
    """
    filename = f"{_sanitize_asteroid_designation(designation)}.bsp"
    return get_spk_cache_dir() / filename


def _build_asteroid_horizons_params(
    designation: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, str]:
    """
    Build Horizons API request parameters for asteroid SPK generation.

    Args:
        designation: Asteroid number or name (e.g., "1", "Ceres", "4 Vesta")
        start_date: Start of ephemeris coverage
        end_date: End of ephemeris coverage

    Returns:
        Dict of request parameters
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # For asteroids, use the number directly or search by name
    # Numbers are simplest
    clean_des = designation.split()[0] if " " in designation else designation

    return {
        "format": "json",
        "COMMAND": clean_des,  # Just the number for asteroids
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "SPK",
        "CENTER": "@sun",
        "START_TIME": start_str,
        "STOP_TIME": end_str,
        "STEP_SIZE": "1d",
    }


def download_asteroid_spk(
    designation: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    force: bool = False,
) -> SPKFileInfo | None:
    """
    Download SPK file for an asteroid from JPL Horizons.

    Args:
        designation: Asteroid designation (number like "1", "4", "99942")
        start_date: Start of ephemeris coverage (default: 1 year ago)
        end_date: End of ephemeris coverage (default: 2 years from now)
        force: Force re-download even if file exists

    Returns:
        SPKFileInfo if successful, None if failed
    """
    import asyncio

    now = datetime.now(UTC)
    if start_date is None:
        start_date = now - timedelta(days=365)
    if end_date is None:
        end_date = now + timedelta(days=730)

    file_path = get_asteroid_spk_file_path(designation)
    if file_path.exists() and not force:
        stat = file_path.stat()
        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=stat.st_size,
            downloaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    try:
        loop = asyncio.new_event_loop()
        try:
            spk_data = loop.run_until_complete(_fetch_asteroid_spk_async(designation, start_date, end_date))
        finally:
            loop.close()

        if spk_data is None:
            return None

        file_path.write_bytes(spk_data)
        logger.info(f"Downloaded SPK for asteroid {designation} ({len(spk_data)} bytes)")

        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=len(spk_data),
            downloaded_at=datetime.now(UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    except Exception as e:
        logger.error(f"Error downloading SPK for asteroid {designation}: {e}")
        return None


async def _fetch_asteroid_spk_async(
    designation: str,
    start_date: datetime,
    end_date: datetime,
) -> bytes | None:
    """Fetch asteroid SPK data from Horizons API asynchronously."""
    import aiohttp
    from aiohttp import ClientTimeout

    params = _build_asteroid_horizons_params(designation, start_date, end_date)
    timeout = ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(HORIZONS_API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Horizons API returned status {resp.status} for asteroid {designation}")
                    return None

                data = await resp.json()

                if "error" in data:
                    logger.error(f"Horizons API error for asteroid {designation}: {data['error']}")
                    return None

                spk_url = data.get("spk_file_id") or data.get("spk")
                if not spk_url:
                    logger.error(f"No SPK URL in Horizons response for asteroid {designation}")
                    return None

                download_timeout = ClientTimeout(total=120)
                async with aiohttp.ClientSession(timeout=download_timeout) as dl_session:
                    async with dl_session.get(spk_url) as spk_resp:
                        if spk_resp.status != 200:
                            logger.error(f"Failed to download SPK for asteroid {designation}: {spk_resp.status}")
                            return None
                        return await spk_resp.read()

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching SPK for asteroid {designation}: {e}")
        return None
    except TimeoutError:
        logger.error(f"Timeout fetching SPK for asteroid {designation}")
        return None


def download_asteroid_spk_sync(
    designation: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    force: bool = False,
) -> SPKFileInfo | None:
    """
    Synchronous version of asteroid SPK download using requests.
    """
    import requests

    now = datetime.now(UTC)
    if start_date is None:
        start_date = now - timedelta(days=365)
    if end_date is None:
        end_date = now + timedelta(days=730)

    file_path = get_asteroid_spk_file_path(designation)
    if file_path.exists() and not force:
        stat = file_path.stat()
        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=stat.st_size,
            downloaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    params = _build_asteroid_horizons_params(designation, start_date, end_date)

    logger.info(f"Requesting SPK for asteroid {designation} with params: {params}")

    try:
        resp = requests.get(HORIZONS_API_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        logger.debug(f"Horizons response for {designation}: {data}")

        if "error" in data:
            error_msg = data['error']
            logger.error(f"Horizons API error for asteroid {designation}: {error_msg}")
            # Return None with more detailed error
            return None

        # Check for result field which contains the actual response
        result = data.get("result", "")
        if "SPK file" in result or "binary" in result.lower():
            # Response contains SPK information
            logger.debug(f"Horizons result contains SPK reference: {result[:200]}")

        spk_url = data.get("spk_file_id") or data.get("spk")
        if not spk_url:
            logger.error(f"No SPK URL in Horizons response for asteroid {designation}. Response keys: {list(data.keys())}")
            logger.error(f"Full response: {data}")
            return None

        # Check if this is actually a URL or just a SPICE ID
        # Horizons sometimes returns SPICE IDs (like "20000015") instead of downloadable URLs
        # This means the asteroid doesn't have a downloadable SPK file
        if not spk_url.startswith(("http://", "https://", "ftp://")):
            logger.warning(
                f"Horizons returned SPICE ID '{spk_url}' instead of SPK URL for asteroid {designation}. "
                f"This asteroid does not have a downloadable SPK file. "
                f"Use compute_asteroid_position_from_elements() instead."
            )
            return None

        logger.info(f"Downloading SPK from: {spk_url}")
        spk_resp = requests.get(spk_url, timeout=120)
        spk_resp.raise_for_status()
        spk_data = spk_resp.content

        file_path.write_bytes(spk_data)
        logger.info(f"Downloaded SPK for asteroid {designation} ({len(spk_data)} bytes)")

        return SPKFileInfo(
            designation=designation,
            filename=file_path.name,
            file_path=file_path,
            size_bytes=len(spk_data),
            downloaded_at=datetime.now(UTC),
            coverage_start=start_date,
            coverage_end=end_date,
        )

    except requests.RequestException as e:
        logger.error(f"Network error downloading SPK for asteroid {designation}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error downloading SPK for asteroid {designation}: {e}", exc_info=True)
        return None


def load_asteroid_spk(designation: str) -> tuple[bool, Path | None]:
    """
    Check if SPK exists for asteroid and return path if available.

    Args:
        designation: Asteroid designation

    Returns:
        Tuple of (is_available, file_path)
    """
    file_path = get_asteroid_spk_file_path(designation)
    if file_path.exists():
        return True, file_path
    return False, None


def compute_position_from_spk(
    designation: str,
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[float, float, float, float, float, float] | None:
    """
    Compute comet position from SPK file using Skyfield.

    Note: SPK files are only available for a small number of comets.
    For most comets, use compute_comet_position_from_elements() instead,
    which computes positions from orbital elements.

    Args:
        designation: Comet designation
        observer_lat: Observer latitude
        observer_lon: Observer longitude
        dt: Datetime for calculation (default: now)

    Returns:
        Tuple of (ra_hours, dec_degrees, alt_deg, az_deg, helio_dist_au, geo_dist_au)
        or None if SPK not available or calculation fails
    """

    from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
    from celestron_nexstar.api.ephemeris.skyfield_utils import (
        get_skyfield_ephemeris,
        get_skyfield_loader,
        get_skyfield_timescale,
    )

    # Check if SPK exists
    spk_available, spk_path = load_comet_spk(designation)
    if not spk_available or spk_path is None:
        logger.debug(f"No SPK file available for {designation}, use compute_comet_position_from_elements() instead")
        return None

    try:
        ts = get_skyfield_timescale()
        loader = get_skyfield_loader()

        # Load main ephemeris for Earth/Sun
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        # Load comet SPK
        comet_eph = loader.open(str(spk_path))

        # Handle datetime
        if dt is None:
            dt = datetime.now(UTC)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        t = ts.from_datetime(dt)

        # Get bodies
        earth = eph["earth"]
        sun = eph["sun"]

        # Try to find comet in SPK - usually has SPICE ID or name
        comet = None
        for segment in comet_eph.segments:
            # Get target name/ID
            target = segment.target
            if isinstance(target, int):
                try:
                    comet = comet_eph[target]
                    break
                except KeyError:
                    continue
            elif isinstance(target, str) and designation.lower() in target.lower():
                comet = comet_eph[target]
                break

        if comet is None:
            # Try first segment
            if comet_eph.segments:
                target = comet_eph.segments[0].target
                comet = comet_eph[target]
            else:
                logger.error(f"No segments found in SPK for {designation}")
                return None

        # Get comet position from Earth
        comet_astrometric = earth.at(t).observe(comet)
        ra, dec, distance = comet_astrometric.radec()

        # Get heliocentric distance
        comet_from_sun = sun.at(t).observe(comet)
        helio_dist = comet_from_sun.distance().au

        # Convert to alt/az
        azimuth, altitude = ra_dec_to_alt_az(ra.hours, dec.degrees, observer_lat, observer_lon, dt)

        return (
            ra.hours,
            dec.degrees,
            altitude,
            azimuth,
            float(helio_dist),
            float(distance.au),
        )

    except Exception as e:
        logger.error(f"Error computing position from SPK for {designation}: {e}")
        return None


def compute_comet_position_from_elements(
    perihelion_distance_au: float,
    eccentricity: float,
    inclination_deg: float,
    arg_perihelion_deg: float,
    ascending_node_deg: float,
    perihelion_time: datetime,
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[float, float, float, float, float, float] | None:
    """
    Compute comet position from orbital elements using Skyfield.

    This is the recommended method for most comets, as SPK files are not
    available from JPL Horizons for most comets.

    Args:
        perihelion_distance_au: Perihelion distance in AU
        eccentricity: Orbital eccentricity
        inclination_deg: Orbital inclination in degrees
        arg_perihelion_deg: Argument of perihelion in degrees
        ascending_node_deg: Longitude of ascending node in degrees
        perihelion_time: Time of perihelion passage
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime for calculation (default: now)

    Returns:
        Tuple of (ra_hours, dec_degrees, alt_deg, az_deg, helio_dist_au, geo_dist_au)
        or None if calculation fails
    """
    try:
        from skyfield.api import load
        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
        from skyfield.data import mpc
        from skyfield.elementslib import OsculatingElements

        from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        ts = get_skyfield_timescale()

        # Load planetary ephemeris for Earth/Sun
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        earth = eph["earth"]
        sun = eph["sun"]

        # Handle datetime
        if dt is None:
            dt = datetime.now(UTC)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        t = ts.from_datetime(dt)

        # Convert perihelion time to Skyfield time
        if perihelion_time.tzinfo is None:
            perihelion_time = perihelion_time.replace(tzinfo=UTC)
        else:
            perihelion_time = perihelion_time.astimezone(UTC)
        t_perihelion = ts.from_datetime(perihelion_time)

        # Create comet from orbital elements
        # Skyfield uses OsculatingElements for computing positions from elements
        # We need to create a position/velocity vector at perihelion and let Skyfield propagate
        from skyfield.positionlib import Barycentric
        from skyfield.vectorlib import VectorSum

        # Compute semi-major axis from perihelion distance and eccentricity
        # q = a(1-e), so a = q/(1-e)
        if eccentricity < 1.0:
            semi_major_axis_au = perihelion_distance_au / (1.0 - eccentricity)
        else:
            # Parabolic or hyperbolic orbit
            semi_major_axis_au = None

        # Use Skyfield's mpc.comet_orbit to create orbital elements
        # This returns a function that can compute positions
        from skyfield.api import Distance, Angle
        from skyfield.units import Angle as AngleUnit

        # Create the comet using orbital elements
        # Skyfield's comet_orbit expects: (semi_major_axis_au, eccentricity, inclination_deg,
        #                                   longitude_of_ascending_node_deg, argument_of_perihelion_deg,
        #                                   mean_anomaly_at_epoch_deg, epoch, GM)

        # For a comet at perihelion, mean anomaly = 0
        # But we need to adjust for the current time
        import math

        if semi_major_axis_au and eccentricity < 1.0:
            # Elliptical orbit - compute mean motion
            # n = sqrt(GM / a^3) in radians/day
            # Period T = 2*pi / n
            period_days = 2 * math.pi * math.sqrt((semi_major_axis_au ** 3) / (GM_SUN / (149597870.7 ** 3 * 86400 ** 2)))

            # Days since perihelion
            days_since_perihelion = (t.tt - t_perihelion.tt)

            # Mean anomaly at observation time
            mean_anomaly_deg = (360.0 * days_since_perihelion / period_days) % 360.0
        else:
            # Parabolic or hyperbolic - use different approach
            # For now, use a simpler calculation
            mean_anomaly_deg = 0.0

        # Use mpc.comet_orbit from Skyfield
        comet = mpc.comet_orbit(eph,
                                q_au=perihelion_distance_au,
                                e=eccentricity,
                                i_degrees=inclination_deg,
                                omega_degrees=arg_perihelion_deg,
                                Omega_degrees=ascending_node_deg,
                                perihelion_time=t_perihelion)

        # Compute comet position from Earth at observation time
        comet_astrometric = earth.at(t).observe(comet)
        ra, dec, distance = comet_astrometric.radec()

        # Compute heliocentric distance
        comet_from_sun = sun.at(t).observe(comet)
        helio_dist = comet_from_sun.distance().au

        # Convert to alt/az
        azimuth, altitude = ra_dec_to_alt_az(ra.hours, dec.degrees, observer_lat, observer_lon, dt)

        return (
            float(ra.hours),
            float(dec.degrees),
            float(altitude),
            float(azimuth),
            float(helio_dist),
            float(distance.au),
        )

    except Exception as e:
        logger.error(f"Error computing comet position from orbital elements: {e}", exc_info=True)
        return None


def compute_asteroid_position_from_elements(
    semi_major_axis_au: float,
    eccentricity: float,
    inclination_deg: float,
    arg_perihelion_deg: float,
    ascending_node_deg: float,
    mean_anomaly_deg: float,
    epoch: datetime,
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[float, float, float, float, float, float] | None:
    """
    Compute asteroid position from orbital elements using Skyfield.

    This is the recommended method for most asteroids, as SPK files are not
    available from JPL Horizons for most asteroids (especially dwarf planets,
    TNOs, centaurs, etc.).

    Args:
        semi_major_axis_au: Semi-major axis in AU
        eccentricity: Orbital eccentricity
        inclination_deg: Orbital inclination in degrees
        arg_perihelion_deg: Argument of perihelion in degrees
        ascending_node_deg: Longitude of ascending node in degrees
        mean_anomaly_deg: Mean anomaly at epoch in degrees
        epoch: Epoch time for orbital elements
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime for calculation (default: now)

    Returns:
        Tuple of (ra_hours, dec_degrees, alt_deg, az_deg, helio_dist_au, geo_dist_au)
        or None if calculation fails
    """
    try:
        from skyfield.api import load
        from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
        from skyfield.elementslib import OsculatingElements

        from celestron_nexstar.api.core.utils import ra_dec_to_alt_az
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        ts = get_skyfield_timescale()

        # Load planetary ephemeris for Earth/Sun
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        earth = eph["earth"]
        sun = eph["sun"]

        # Handle datetime
        if dt is None:
            dt = datetime.now(UTC)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        t = ts.from_datetime(dt)

        # Convert epoch to Skyfield time
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=UTC)
        else:
            epoch = epoch.astimezone(UTC)
        t_epoch = ts.from_datetime(epoch)

        # Use OsculatingElements to create asteroid from elements
        # OsculatingElements expects Angle objects for angles
        from skyfield.units import Angle

        # Create osculating elements
        # Note: Skyfield's OsculatingElements uses radians internally
        elements = OsculatingElements(
            semi_major_axis_au,
            eccentricity,
            Angle(degrees=inclination_deg),
            Angle(degrees=ascending_node_deg),
            Angle(degrees=arg_perihelion_deg),
            Angle(degrees=mean_anomaly_deg),
            t_epoch,
            GM_SUN,
        )

        # Get position at observation time relative to Sun
        # OsculatingElements.at() gives position relative to the reference body (Sun)
        asteroid_sun_pos = elements.at(t)

        # Convert to position from Earth
        # asteroid_from_earth = earth_from_sun + sun_from_asteroid
        # = earth_from_sun - asteroid_from_sun
        sun_pos = sun.at(t)
        earth_pos = earth.at(t)

        # Compute asteroid position from Earth
        # We need to add the sun-to-asteroid vector to Earth's heliocentric position
        asteroid_pos = sun_pos + asteroid_sun_pos

        # Observe from Earth
        asteroid_astrometric = earth_pos.observe(asteroid_pos)
        ra, dec, distance = asteroid_astrometric.radec()

        # Compute heliocentric distance (distance from asteroid to sun)
        helio_dist = asteroid_sun_pos.distance().au

        # Convert to alt/az
        azimuth, altitude = ra_dec_to_alt_az(ra.hours, dec.degrees, observer_lat, observer_lon, dt)

        return (
            float(ra.hours),
            float(dec.degrees),
            float(altitude),
            float(azimuth),
            float(helio_dist),
            float(distance.au),
        )

    except Exception as e:
        logger.error(f"Error computing asteroid position from orbital elements: {e}", exc_info=True)
        return None
