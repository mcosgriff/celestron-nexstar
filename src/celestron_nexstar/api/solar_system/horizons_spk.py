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
    "download_comet_spk",
    "get_spk_cache_dir",
    "get_spk_file_path",
    "list_cached_spks",
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

    Uses ~/.skyfield/spk/ by default, respecting SKYFIELD_DIR env var.

    Returns:
        Path to SPK cache directory
    """
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_directory

    spk_dir = get_skyfield_directory() / "spk"
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
    # Strip any parenthetical name for cleaner lookup
    clean_des = re.sub(r"\s*\([^)]*\)", "", designation).strip()

    return {
        "format": "json",
        "COMMAND": f"DES={clean_des}",
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


def compute_position_from_spk(
    designation: str,
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> tuple[float, float, float, float, float, float] | None:
    """
    Compute comet position from SPK file using Skyfield.

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
