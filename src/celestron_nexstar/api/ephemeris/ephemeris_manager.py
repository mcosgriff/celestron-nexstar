"""
Ephemeris File Management

Manages downloading, verification, and information about JPL ephemeris files
for offline field use. Provides a user-friendly interface to Skyfield's
ephemeris file handling.
"""

from __future__ import annotations

import logging
import re
import ssl
from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import aiohttp


logger = logging.getLogger(__name__)


__all__ = [
    "EPHEMERIS_FILES",
    "EphemerisFileInfo",
    "delete_file",
    "download_file",
    "download_set",
    "get_ephemeris_directory",
    "get_file_size",
    "get_installed_files",
    "get_set_info",
    "get_total_size",
    "is_file_installed",
    "verify_file",
]


@dataclass(frozen=True, slots=True)
class EphemerisFileInfo:
    """Information about an ephemeris file."""

    filename: str
    display_name: str
    description: str
    coverage_start: int  # Year
    coverage_end: int  # Year
    size_mb: float  # Approximate size in MB
    contents: tuple[str, ...]  # What celestial objects are included
    use_case: str  # When to use this file
    url: str  # Download URL


# Base URL for NAIF ephemeris files
NAIF_BASE_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk"
NAIF_PLANETS_SUMMARY = f"{NAIF_BASE_URL}/planets/aa_summaries.txt"
NAIF_SATELLITES_SUMMARY = f"{NAIF_BASE_URL}/satellites/aa_summaries.txt"

# Cache for fetched summaries (to avoid repeated network calls)
_SUMMARIES_CACHE: dict[str, str] = {}
_CACHE_TIMESTAMP: datetime | None = None
_CACHE_TTL_HOURS = 24  # Cache for 24 hours


@dataclass(frozen=True, slots=True)
class ParsedEphemerisSummary:
    """Parsed information from NAIF summaries file."""

    filename: str
    bodies: list[str]
    coverage_start: int | None  # Year, or None if very old
    coverage_end: int | None  # Year, or None if very far future
    file_type: Literal["planets", "satellites"]  # Which directory it's in


async def _fetch_summaries(url: str) -> str:
    """Fetch summaries file from NAIF server."""
    try:
        # Create SSL context that uses system certificates
        # This is necessary on macOS where Python may not have access to system certs
        # Try to use certifi if available (common on macOS), otherwise use default context
        try:
            import certifi

            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            # Fallback to system certificates
            ssl_context = ssl.create_default_context()

        # Create connector with SSL context
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with (
            aiohttp.ClientSession(connector=connector) as session,
            session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            text = await response.text()
            return str(text)
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        raise


def _parse_summaries(content: str, file_type: Literal["planets", "satellites"]) -> list[ParsedEphemerisSummary]:
    """Parse NAIF summaries file content."""
    summaries: list[ParsedEphemerisSummary] = []
    current_file: str | None = None
    current_bodies: list[str] = []
    current_start: int | None = None
    current_end: int | None = None

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for "Summary for: filename.bsp"
        if match := re.match(r"Summary for:\s+(.+)\.bsp", line):
            # Save previous file if exists
            if current_file:
                summaries.append(
                    ParsedEphemerisSummary(
                        filename=f"{current_file}.bsp",
                        bodies=current_bodies.copy(),
                        coverage_start=current_start,
                        coverage_end=current_end,
                        file_type=file_type,
                    )
                )

            # Start new file
            current_file = match.group(1)
            current_bodies = []
            current_start = None
            current_end = None

        # Check for body lines (format: "BODY_NAME (ID) w.r.t. REFERENCE (REF_ID)")
        elif current_file and re.match(r"^[A-Z0-9_/]+ \(\d+\)", line):
            # Extract body name (before the parenthesis)
            body_match = re.match(r"^([A-Z0-9_/]+)", line)
            if body_match:
                body_name = body_match.group(1)
                # Skip system barycenters and Earth (we want specific objects)
                if body_name not in ("EARTH BARYCENTER", "SOLAR SYSTEM BARYCENTER", "EARTH"):
                    # Map NAIF body names to common names
                    body_mapped = _map_naif_body_name(body_name)
                    if body_mapped and body_mapped not in current_bodies:
                        current_bodies.append(body_mapped)

        # Check for time coverage
        elif current_file and "Start of Interval (ET)" in line:
            # Look for date range in next few lines
            for j in range(i + 1, min(i + 5, len(lines))):
                date_line = lines[j].strip()
                # Format: "1900 JAN 01 00:00:00.000      2100 JAN 24 00:00:00.000"
                date_match = re.search(r"(\d{4})\s+[A-Z]{3}\s+\d+", date_line)
                if date_match:
                    year = int(date_match.group(1))
                    if current_start is None:
                        current_start = year
                    # Find end date (second date in line)
                    dates = re.findall(r"(\d{4})\s+[A-Z]{3}\s+\d+", date_line)
                    if len(dates) >= 2:
                        current_end = int(dates[1])
                    elif len(dates) == 1 and current_start is not None:
                        # Only one date, assume it's the start, look for end in next line
                        for k in range(j + 1, min(j + 3, len(lines))):
                            end_match = re.search(r"(\d{4})\s+[A-Z]{3}\s+\d+", lines[k])
                            if end_match:
                                current_end = int(end_match.group(1))
                                break
                    break

        i += 1

    # Don't forget the last file
    if current_file:
        summaries.append(
            ParsedEphemerisSummary(
                filename=f"{current_file}.bsp",
                bodies=current_bodies.copy(),
                coverage_start=current_start,
                coverage_end=current_end,
                file_type=file_type,
            )
        )

    return summaries


def _map_naif_body_name(naif_name: str) -> str | None:
    """Map NAIF body names to common astronomical names."""
    # NAIF body name mappings
    mappings = {
        # Planets
        "MERCURY": "Mercury",
        "VENUS": "Venus",
        "MARS": "Mars",
        "JUPITER": "Jupiter",
        "SATURN": "Saturn",
        "URANUS": "Uranus",
        "NEPTUNE": "Neptune",
        "PLUTO": "Pluto",
        "SUN": "Sun",
        "MOON": "Moon",
        # Jupiter moons
        "IO": "Io",
        "EUROPA": "Europa",
        "GANYMEDE": "Ganymede",
        "CALLISTO": "Callisto",
        "AMALTHEA": "Amalthea",
        "HIMALIA": "Himalia",
        "ELARA": "Elara",
        "PASIPHAE": "Pasiphae",
        "SINOPE": "Sinope",
        "LYSITHEA": "Lysithea",
        "CARME": "Carme",
        "ANANKE": "Ananke",
        "LEDA": "Leda",
        # Saturn moons
        "TITAN": "Titan",
        "RHEA": "Rhea",
        "IAPETUS": "Iapetus",
        "DIONE": "Dione",
        "TETHYS": "Tethys",
        "ENCELADUS": "Enceladus",
        "MIMAS": "Mimas",
        "HYPERION": "Hyperion",
        # Uranus moons
        "ARIEL": "Ariel",
        "UMBRIEL": "Umbriel",
        "TITANIA": "Titania",
        "OBERON": "Oberon",
        "MIRANDA": "Miranda",
        # Neptune moons
        "TRITON": "Triton",
        # Mars moons
        "PHOBOS": "Phobos",
        "DEIMOS": "Deimos",
    }
    return mappings.get(naif_name, naif_name.replace("_", " ").title() if "_" in naif_name else None)


def _generate_file_info(parsed: ParsedEphemerisSummary) -> EphemerisFileInfo:
    """Generate EphemerisFileInfo from parsed summary."""
    filename_base = parsed.filename.replace(".bsp", "")
    base_url = f"{NAIF_BASE_URL}/{parsed.file_type}"

    # Generate display name based on filename
    if parsed.file_type == "planets":
        if "de" in filename_base.lower():
            # DE files (Development Ephemeris)
            version = filename_base.upper()
            if "s" in version:
                display_name = f"{version} - Modern Planetary (no Moon)"
            else:
                display_name = f"{version} - Full Precision Planetary"
        else:
            display_name = filename_base.replace("_", " ").title()
    else:
        # Satellite files
        if "jup" in filename_base.lower():
            display_name = "Jupiter Moons"
        elif "sat" in filename_base.lower():
            display_name = "Saturn Moons"
        elif "ura" in filename_base.lower():
            display_name = "Uranus Moons"
        elif "nep" in filename_base.lower():
            display_name = "Neptune Moons"
        elif "mar" in filename_base.lower():
            display_name = "Mars Moons"
        else:
            display_name = filename_base.replace("_", " ").title()

    # Generate description
    if parsed.bodies:
        if len(parsed.bodies) <= 5:
            description = f"{', '.join(parsed.bodies)}"
        else:
            description = f"{', '.join(parsed.bodies[:5])}, +{len(parsed.bodies) - 5} more"
    else:
        description = f"{parsed.file_type.title()} ephemeris file"

    # Estimate size (rough approximation based on file type and coverage)
    if parsed.file_type == "planets":
        if "de440" in filename_base.lower():
            size_mb = 115.0
        elif "de421" in filename_base.lower():
            size_mb = 16.0
        else:
            size_mb = 50.0  # Default for planetary files
    else:
        # Satellite files are typically larger
        if "jup" in filename_base.lower():
            size_mb = 1083.9
        elif "sat" in filename_base.lower():
            size_mb = 630.9
        elif "ura" in filename_base.lower():
            size_mb = 1967.0
        elif "nep" in filename_base.lower():
            size_mb = 100.4
        elif "mar" in filename_base.lower():
            size_mb = 64.5
        else:
            size_mb = 500.0  # Default for satellite files

    # Generate use case
    if parsed.file_type == "planets":
        use_case = "Planetary positions and orbits"
    else:
        use_case = f"Required for {display_name.lower()} positions"

    return EphemerisFileInfo(
        filename=parsed.filename,
        display_name=display_name,
        description=description,
        coverage_start=parsed.coverage_start or 1900,
        coverage_end=parsed.coverage_end or 2100,
        size_mb=size_mb,
        contents=tuple(parsed.bodies) if parsed.bodies else ("Various objects",),
        use_case=use_case,
        url=f"{base_url}/{parsed.filename}",
    )


async def _load_ephemeris_files_from_naif() -> dict[str, EphemerisFileInfo]:
    """Load ephemeris file information from NAIF summaries."""
    global _SUMMARIES_CACHE, _CACHE_TIMESTAMP

    # Check cache
    if _CACHE_TIMESTAMP and (datetime.now() - _CACHE_TIMESTAMP).total_seconds() < _CACHE_TTL_HOURS * 3600:
        if "planets" in _SUMMARIES_CACHE and "satellites" in _SUMMARIES_CACHE:
            logger.debug("Using cached NAIF summaries")
            planets_content = _SUMMARIES_CACHE["planets"]
            satellites_content = _SUMMARIES_CACHE["satellites"]
        else:
            planets_content = None
            satellites_content = None
    else:
        planets_content = None
        satellites_content = None

    # Fetch if not cached
    if not planets_content:
        try:
            planets_content = await _fetch_summaries(NAIF_PLANETS_SUMMARY)
            _SUMMARIES_CACHE["planets"] = planets_content
        except Exception as e:
            logger.warning(f"Failed to fetch planets summary: {e}")
            planets_content = ""

    if not satellites_content:
        try:
            satellites_content = await _fetch_summaries(NAIF_SATELLITES_SUMMARY)
            _SUMMARIES_CACHE["satellites"] = satellites_content
        except Exception as e:
            logger.warning(f"Failed to fetch satellites summary: {e}")
            satellites_content = ""

    _CACHE_TIMESTAMP = datetime.now()

    # Parse summaries
    all_summaries: list[ParsedEphemerisSummary] = []
    if planets_content:
        all_summaries.extend(_parse_summaries(planets_content, "planets"))
    if satellites_content:
        all_summaries.extend(_parse_summaries(satellites_content, "satellites"))

    # Convert to EphemerisFileInfo
    files: dict[str, EphemerisFileInfo] = {}
    for summary in all_summaries:
        key = summary.filename.replace(".bsp", "")
        files[key] = _generate_file_info(summary)

    return files


def _get_ephemeris_files() -> dict[str, EphemerisFileInfo]:
    """Get ephemeris files from database, with fallback to hardcoded data."""
    try:
        import asyncio

        from celestron_nexstar.api.database.database import get_ephemeris_files

        # Try to get from database first
        db_files = asyncio.run(get_ephemeris_files())
        if db_files:
            logger.info(f"Loaded {len(db_files)} ephemeris files from database")
            # Convert dict to EphemerisFileInfo objects
            result: dict[str, EphemerisFileInfo] = {}
            for key, file_data in db_files.items():
                result[key] = EphemerisFileInfo(
                    filename=file_data["filename"],
                    display_name=file_data["display_name"],
                    description=file_data["description"],
                    coverage_start=file_data["coverage_start"],
                    coverage_end=file_data["coverage_end"],
                    size_mb=file_data["size_mb"],
                    contents=file_data["contents"],
                    use_case=file_data["use_case"],
                    url=file_data["url"],
                )
            # Merge with hardcoded files (hardcoded take precedence for known files)
            result.update(_HARDCODED_EPHEMERIS_FILES)
            return result
    except Exception as e:
        logger.warning(f"Failed to load ephemeris files from database: {e}, trying NAIF fetch")

    # Fallback: try to load from NAIF
    try:
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        files = asyncio.run(_load_ephemeris_files_from_naif())
        if files:
            logger.info(f"Loaded {len(files)} ephemeris files from NAIF summaries")
            # Merge with hardcoded files (hardcoded take precedence for known files)
            files.update(_HARDCODED_EPHEMERIS_FILES)
            return files
    except Exception as e:
        logger.warning(f"Failed to load ephemeris files from NAIF: {e}, using hardcoded fallback")

    # Final fallback to hardcoded files
    return _HARDCODED_EPHEMERIS_FILES.copy()


# Lazy-loaded ephemeris files (loaded on first access)
_EPHEMERIS_FILES_CACHE: dict[str, EphemerisFileInfo] | None = None


def _get_ephemeris_files_dict() -> dict[str, EphemerisFileInfo]:
    """Get ephemeris files dictionary (lazy-loaded, cached)."""
    global _EPHEMERIS_FILES_CACHE
    if _EPHEMERIS_FILES_CACHE is None:
        _EPHEMERIS_FILES_CACHE = _get_ephemeris_files()
    return _EPHEMERIS_FILES_CACHE


# Public API: EPHEMERIS_FILES is a property that returns the cached dict
# This allows it to be used like a dict but loads lazily
class _EphemerisFilesDict:
    """Wrapper to make EPHEMERIS_FILES work like a dict but load lazily."""

    def __getitem__(self, key: str) -> EphemerisFileInfo:
        return _get_ephemeris_files_dict()[key]

    def __contains__(self, key: str) -> bool:
        return key in _get_ephemeris_files_dict()

    def keys(self) -> KeysView[str]:
        return _get_ephemeris_files_dict().keys()

    def items(self) -> ItemsView[str, EphemerisFileInfo]:
        return _get_ephemeris_files_dict().items()

    def values(self) -> ValuesView[EphemerisFileInfo]:
        return _get_ephemeris_files_dict().values()

    def get(self, key: str, default: EphemerisFileInfo | None = None) -> EphemerisFileInfo | None:
        return _get_ephemeris_files_dict().get(key, default)

    def __iter__(self) -> Iterator[str]:
        return iter(_get_ephemeris_files_dict())

    def __len__(self) -> int:
        return len(_get_ephemeris_files_dict())


EPHEMERIS_FILES = _EphemerisFilesDict()


# Hardcoded fallback ephemeris files (used if NAIF fetch fails or for known important files)
_HARDCODED_EPHEMERIS_FILES: dict[str, EphemerisFileInfo] = {
    "de421": EphemerisFileInfo(
        filename="de421.bsp",
        display_name="DE421 - Compact Planetary",
        description="Compact planetary ephemeris including Moon",
        coverage_start=1900,
        coverage_end=2050,
        size_mb=16.0,
        contents=(
            "Sun",
            "Moon",
            "Mercury",
            "Venus",
            "Mars",
            "Jupiter barycenter",
            "Saturn barycenter",
            "Uranus barycenter",
            "Neptune barycenter",
            "Pluto barycenter",
        ),
        use_case="Good general-purpose file for planets and Moon with reasonable size",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de421.bsp",
    ),
    "de440s": EphemerisFileInfo(
        filename="de440s.bsp",
        display_name="DE440s - Modern Planetary",
        description="Modern high-accuracy planetary ephemeris (planets only, no Moon)",
        coverage_start=1849,
        coverage_end=2150,
        size_mb=115,
        contents=(
            "Sun",
            "Mercury",
            "Venus",
            "Earth",
            "Mars",
            "Jupiter barycenter",
            "Saturn barycenter",
            "Uranus barycenter",
            "Neptune barycenter",
            "Pluto barycenter",
        ),
        use_case="Best for planetary positions (current default), but lacks Moon",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp",
    ),
    "de440": EphemerisFileInfo(
        filename="de440.bsp",
        display_name="DE440 - Full Precision Planetary",
        description="Full precision planetary and lunar ephemeris",
        coverage_start=1550,
        coverage_end=2650,
        size_mb=114.2,
        contents=(
            "Sun",
            "Moon",
            "Mercury",
            "Venus",
            "Mars",
            "Jupiter barycenter",
            "Saturn barycenter",
            "Uranus barycenter",
            "Neptune barycenter",
            "Pluto barycenter",
        ),
        use_case="Maximum accuracy for planets and Moon, large file size",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp",
    ),
    "jup365": EphemerisFileInfo(
        filename="jup365.bsp",
        display_name="Jupiter Moons",
        description="Jupiter's Galilean moons",
        coverage_start=1900,
        coverage_end=2100,
        size_mb=1083.9,
        contents=("Io", "Europa", "Ganymede", "Callisto"),
        use_case="Required for Jupiter moon positions",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/jup365.bsp",
    ),
    "sat441": EphemerisFileInfo(
        filename="sat441.bsp",
        display_name="Saturn Moons",
        description="Saturn's major moons",
        coverage_start=1900,
        coverage_end=2100,
        size_mb=630.9,
        contents=(
            "Titan",
            "Rhea",
            "Iapetus",
            "Dione",
            "Tethys",
            "Enceladus",
            "Mimas",
            "Hyperion",
        ),
        use_case="Required for Saturn moon positions",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/sat441.bsp",
    ),
    "ura184_part-1": EphemerisFileInfo(
        filename="ura184_part-1.bsp",
        display_name="Uranus Moons",
        description="Uranus's major moons",
        coverage_start=1900,
        coverage_end=2100,
        size_mb=1967,
        contents=("Ariel", "Umbriel", "Titania", "Oberon", "Miranda"),
        use_case="Required for Uranus moon positions",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/ura184_part-1.bsp",
    ),
    "nep097": EphemerisFileInfo(
        filename="nep097.bsp",
        display_name="Neptune Moons",
        description="Neptune's major moon",
        coverage_start=1600,
        coverage_end=2399,
        size_mb=100.4,
        contents=("Triton",),
        use_case="Required for Neptune's moon Triton",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/nep097.bsp",
    ),
    "mar099s": EphemerisFileInfo(
        filename="mar099s.bsp",
        display_name="Mars Moons",
        description="Mars's two small moons",
        coverage_start=1995,
        coverage_end=2050,
        size_mb=64.5,
        contents=("Phobos", "Deimos"),
        use_case="Required for Mars moons (very challenging to observe)",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/mar099s.bsp",
    ),
}

# Predefined file sets for different use cases
# "recommended" matches Skyfield's default recommendation (DE421 + Jupiter moons)
EPHEMERIS_SETS: dict[str, list[str]] = {
    "recommended": ["de421", "jup365"],  # Skyfield's default recommendation
    "minimal": ["de421", "jup365"],  # Same as recommended (alias for backwards compatibility)
    "standard": ["de440s", "jup365", "sat441"],
    "complete": ["de440s", "jup365", "sat441", "ura184_part-1", "nep097"],
    "full": ["de440", "jup365", "sat441", "ura184_part-1", "nep097", "mar099s"],
}


def get_ephemeris_directory() -> Path:
    """
    Get the directory where ephemeris files are stored.

    Uses the standard Skyfield cache location: ~/.skyfield/ (or SKYFIELD_DIR env var).

    Returns:
        Path to ephemeris directory
    """
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_directory

    return get_skyfield_directory()


def get_installed_files() -> list[tuple[str, EphemerisFileInfo, Path]]:
    """
    Get list of installed ephemeris files.

    Returns:
        List of (file_key, file_info, file_path) tuples for installed files
    """
    ephemeris_dir = get_ephemeris_directory()
    installed = []

    for key, info in EPHEMERIS_FILES.items():
        file_path = ephemeris_dir / info.filename
        if file_path.exists():
            installed.append((key, info, file_path))

    return installed


def is_file_installed(file_key: str) -> bool:
    """
    Check if an ephemeris file is installed.

    Args:
        file_key: File identifier (e.g., 'de440s', 'jup365')

    Returns:
        True if file is installed
    """
    if file_key not in EPHEMERIS_FILES:
        return False

    info = EPHEMERIS_FILES[file_key]
    file_path = get_ephemeris_directory() / info.filename
    return file_path.exists()


def get_file_size(file_key: str) -> int | None:
    """
    Get actual size of installed file in bytes.

    Args:
        file_key: File identifier

    Returns:
        File size in bytes, or None if not installed
    """
    if not is_file_installed(file_key):
        return None

    info = EPHEMERIS_FILES[file_key]
    file_path = get_ephemeris_directory() / info.filename
    return file_path.stat().st_size


def download_file(file_key: str, force: bool = False) -> Path:
    """
    Download an ephemeris file.

    Uses Skyfield's built-in download mechanism which handles
    caching and verification.

    Args:
        file_key: File identifier (e.g., 'de440s', 'jup365')
        force: Force re-download even if file exists

    Returns:
        Path to downloaded file

    Raises:
        ValueError: If file_key is not recognized
        Exception: If download fails
    """
    if file_key not in EPHEMERIS_FILES:
        raise ValueError(f"Unknown ephemeris file: {file_key}")

    info = EPHEMERIS_FILES[file_key]
    ephemeris_dir = get_ephemeris_directory()

    # Use centralized Skyfield loader (respects SKYFIELD_DIR env var)
    from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

    loader = get_skyfield_loader()

    # Check if file exists and force is False
    # Use the actual directory from the loader, not ephemeris_dir
    file_path = ephemeris_dir / info.filename
    if file_path.exists() and not force:
        return file_path

    # Download file using explicit URL from our configuration
    # This ensures we use the correct NAIF URLs instead of Skyfield's defaults
    loader.download(info.url, filename=info.filename)

    return file_path


def download_set(
    set_name: Literal["recommended", "minimal", "standard", "complete", "full"],
    force: bool = False,
) -> list[Path]:
    """
    Download a predefined set of ephemeris files.

    Args:
        set_name: Name of the file set
        force: Force re-download even if files exist

    Returns:
        List of paths to downloaded files
    """
    if set_name not in EPHEMERIS_SETS:
        raise ValueError(f"Unknown ephemeris set: {set_name}")

    file_keys = EPHEMERIS_SETS[set_name]
    downloaded = []

    for file_key in file_keys:
        file_path = download_file(file_key, force=force)
        downloaded.append(file_path)

    return downloaded


def verify_file(file_key: str) -> tuple[bool, str]:
    """
    Verify an ephemeris file's integrity.

    Checks if the file exists and can be loaded by Skyfield.

    Args:
        file_key: File identifier

    Returns:
        Tuple of (is_valid, message)
    """
    if file_key not in EPHEMERIS_FILES:
        return False, f"Unknown ephemeris file: {file_key}"

    if not is_file_installed(file_key):
        return False, "File not installed"

    info = EPHEMERIS_FILES[file_key]
    get_ephemeris_directory()

    try:
        # Try to load the file with Skyfield
        from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader

        loader = get_skyfield_loader()
        eph = loader(info.filename)

        # Basic validation - check if we can access it as an SPK file
        if hasattr(eph, "__getitem__"):
            return True, "File is valid and loadable"
        else:
            return False, "File loaded but format appears incorrect"

    except Exception as e:
        return False, f"File verification failed: {e!s}"


def get_total_size(file_keys: list[str] | None = None) -> float:
    """
    Calculate total size in MB for given files or all files.

    Args:
        file_keys: List of file identifiers, or None for all files

    Returns:
        Total size in megabytes
    """
    if file_keys is None:
        file_keys = list(EPHEMERIS_FILES.keys())

    total_mb = 0.0
    for key in file_keys:
        if key in EPHEMERIS_FILES:
            total_mb += EPHEMERIS_FILES[key].size_mb

    return total_mb


def get_set_info(set_name: str) -> dict[str, str | int | float | list[EphemerisFileInfo]]:
    """
    Get information about a file set.

    Args:
        set_name: Name of the file set

    Returns:
        Dictionary with set information
    """
    if set_name not in EPHEMERIS_SETS:
        raise ValueError(f"Unknown ephemeris set: {set_name}")

    file_keys = EPHEMERIS_SETS[set_name]
    files = [EPHEMERIS_FILES[key] for key in file_keys]
    total_size = sum(f.size_mb for f in files)

    # Check how many are installed
    installed_count = sum(1 for key in file_keys if is_file_installed(key))

    return {
        "name": set_name,
        "file_count": len(file_keys),
        "files": files,
        "total_size_mb": total_size,
        "installed_count": installed_count,
    }


def delete_file(file_key: str) -> bool:
    """
    Delete an installed ephemeris file.

    Args:
        file_key: File identifier

    Returns:
        True if file was deleted, False if not installed
    """
    if not is_file_installed(file_key):
        return False

    info = EPHEMERIS_FILES[file_key]
    file_path = get_ephemeris_directory() / info.filename

    try:
        file_path.unlink()
        return True
    except Exception:
        return False
