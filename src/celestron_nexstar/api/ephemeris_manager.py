"""
Ephemeris File Management

Manages downloading, verification, and information about JPL ephemeris files
for offline field use. Provides a user-friendly interface to Skyfield's
ephemeris file handling.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skyfield.api import Loader


@dataclass
class EphemerisFileInfo:
    """Information about an ephemeris file."""

    filename: str
    display_name: str
    description: str
    coverage_start: int  # Year
    coverage_end: int  # Year
    size_mb: float  # Approximate size in MB
    contents: list[str]  # What celestial objects are included
    use_case: str  # When to use this file
    url: str  # Download URL


# Comprehensive ephemeris file database
EPHEMERIS_FILES: dict[str, EphemerisFileInfo] = {
    "de421": EphemerisFileInfo(
        filename="de421.bsp",
        display_name="DE421 - Compact Planetary",
        description="Compact planetary ephemeris including Moon",
        coverage_start=1900,
        coverage_end=2050,
        size_mb=16.0,
        contents=[
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
        ],
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
        contents=[
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
        ],
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
        contents=[
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
        ],
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
        contents=["Io", "Europa", "Ganymede", "Callisto"],
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
        contents=[
            "Titan",
            "Rhea",
            "Iapetus",
            "Dione",
            "Tethys",
            "Enceladus",
            "Mimas",
            "Hyperion",
        ],
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
        contents=["Ariel", "Umbriel", "Titania", "Oberon", "Miranda"],
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
        contents=["Triton"],
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
        contents=["Phobos", "Deimos"],
        use_case="Required for Mars moons (very challenging to observe)",
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/satellites/mar099s.bsp",
    ),
}

# Predefined file sets for different use cases
EPHEMERIS_SETS: dict[str, list[str]] = {
    "minimal": ["de421", "jup365"],
    "standard": ["de440s", "jup365", "sat441"],
    "complete": ["de440s", "jup365", "sat441", "ura184_part-1", "nep097"],
    "full": ["de440", "jup365", "sat441", "ura184_part-1", "nep097", "mar099s"],
}


def get_ephemeris_directory() -> Path:
    """
    Get the directory where ephemeris files are stored.

    Uses the standard Skyfield cache location: ~/.skyfield/

    Returns:
        Path to ephemeris directory
    """
    cache_dir = Path.home() / ".skyfield"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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

    # Configure Skyfield loader with our cache directory
    loader = Loader(str(ephemeris_dir))

    # Check if file exists and force is False
    file_path = ephemeris_dir / info.filename
    if file_path.exists() and not force:
        return file_path

    # Download file using explicit URL from our configuration
    # This ensures we use the correct NAIF URLs instead of Skyfield's defaults
    loader.download(info.url, filename=info.filename)

    return file_path


def download_set(
    set_name: Literal["minimal", "standard", "complete", "full"],
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
    ephemeris_dir = get_ephemeris_directory()

    try:
        # Try to load the file with Skyfield
        loader = Loader(str(ephemeris_dir))
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


def get_set_info(set_name: str) -> dict:
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
