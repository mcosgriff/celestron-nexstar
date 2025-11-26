"""
Constellation Image Utilities

Functions to download and cache constellation SVG images from Wikimedia Commons.
"""

import logging
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Wikimedia Commons base URL for constellation SVGs
# Format: https://commons.wikimedia.org/wiki/File:Constellation_{name}.svg
WIKIMEDIA_BASE_URL = "https://upload.wikimedia.org/wikipedia/commons"
# Alternative: use a direct SVG repository if available
# For now, we'll use a mapping approach with Wikimedia Commons

# Constellation name mappings (some constellations have different names in Wikimedia)
CONSTELLATION_NAME_MAPPINGS: dict[str, str] = {
    # Map our constellation names to Wikimedia file names
    # Most are the same, but some need adjustments
    "Canis Major": "Canis_Major",
    "Canis Minor": "Canis_Minor",
    "Ursa Major": "Ursa_Major",
    "Ursa Minor": "Ursa_Minor",
    "Corona Borealis": "Corona_Borealis",
    "Corona Australis": "Corona_Australis",
    # Add more mappings as needed
}


def get_constellation_image_cache_dir() -> Path:
    """
    Get the cache directory for constellation images.

    Returns:
        Path to ~/.cache/celestron-nexstar/constellation-images/
    """
    cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "constellation-images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_constellation_svg_path(constellation_name: str) -> Path:
    """
    Get the path to a cached constellation SVG file.

    Args:
        constellation_name: Name of the constellation (e.g., "Orion")

    Returns:
        Path to the SVG file (may not exist)
    """
    cache_dir = get_constellation_image_cache_dir()
    # Normalize constellation name for filename
    safe_name = constellation_name.replace(" ", "_").replace("/", "_")
    return cache_dir / f"{safe_name}.svg"


def download_constellation_svg(constellation_name: str, force: bool = False) -> Path | None:
    """
    Download a constellation SVG from Wikimedia Commons and cache it.

    Args:
        constellation_name: Name of the constellation (e.g., "Orion")
        force: Force re-download even if cached

    Returns:
        Path to the cached SVG file, or None if download failed
    """
    svg_path = get_constellation_svg_path(constellation_name)

    # Return cached file if it exists and we're not forcing
    if svg_path.exists() and not force:
        logger.debug(f"Using cached SVG for {constellation_name}: {svg_path}")
        return svg_path

    # Map constellation name to Wikimedia file name
    wiki_name = CONSTELLATION_NAME_MAPPINGS.get(constellation_name, constellation_name.replace(" ", "_"))

    # Try multiple URL patterns for Wikimedia Commons
    # Wikimedia Commons uses Special:FilePath for direct file access
    urls = [
        # Direct file path (most reliable)
        f"https://commons.wikimedia.org/wiki/Special:FilePath/Constellation_{wiki_name}.svg",
        # Alternative patterns
        f"{WIKIMEDIA_BASE_URL}/0/0a/Constellation_{wiki_name}.svg",
        f"https://upload.wikimedia.org/wikipedia/commons/0/0a/Constellation_{wiki_name}.svg",
    ]

    # Also try with different capitalization
    wiki_name_cap = wiki_name.capitalize()
    urls.extend(
        [
            f"https://commons.wikimedia.org/wiki/Special:FilePath/Constellation_{wiki_name_cap}.svg",
            f"{WIKIMEDIA_BASE_URL}/0/0a/Constellation_{wiki_name_cap}.svg",
        ]
    )

    for url in urls:
        try:
            logger.info(f"Attempting to download constellation SVG from {url}")
            # Create a request with proper headers
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "celestron-nexstar/1.0 (astronomy application)")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                # Basic validation: check if it looks like SVG
                # Check first 2KB for SVG markers
                if b"<svg" in data[:2048] or (b"<?xml" in data[:2048] and b"svg" in data[:2048].lower()):
                    svg_path.write_bytes(data)
                    logger.info(f"Downloaded {len(data):,} bytes to {svg_path}")
                    return svg_path
                else:
                    # Check if it's HTML (redirect page)
                    if b"<html" in data[:2048] or b"<!DOCTYPE" in data[:2048]:
                        logger.debug(f"Received HTML instead of SVG from {url} (likely redirect)")
                    else:
                        logger.warning(f"Downloaded file doesn't appear to be SVG: {url}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            logger.debug(f"Failed to download from {url}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Unexpected error downloading from {url}: {e}")
            continue

    logger.warning(f"Could not download SVG for constellation '{constellation_name}' from any source")
    return None


def get_constellation_svg(constellation_name: str) -> Path | None:
    """
    Get the path to a constellation SVG, downloading if necessary.

    Args:
        constellation_name: Name of the constellation

    Returns:
        Path to the SVG file, or None if not available
    """
    svg_path = get_constellation_svg_path(constellation_name)

    # Return if already cached
    if svg_path.exists():
        return svg_path

    # Try to download
    return download_constellation_svg(constellation_name, force=False)
