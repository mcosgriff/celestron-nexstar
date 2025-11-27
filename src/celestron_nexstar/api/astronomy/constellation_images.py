"""
Constellation Image Utilities

Functions to download and cache constellation SVG images from Wikimedia Commons.

License: Wikimedia Commons images are typically available under Creative Commons
Attribution-ShareAlike (CC BY-SA) license. Users should verify the specific license
for each image and provide appropriate attribution when using these images.
"""

import logging
import sys
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Also print to stderr for debugging (will show in console)
def _debug_print(*args: Any, **kwargs: Any) -> None:
    """Print to stderr for debugging."""
    print(*args, file=sys.stderr, **kwargs)


# Wikimedia Commons base URL for constellation SVGs
# Format: https://commons.wikimedia.org/wiki/File:{name}_IAU.svg
# The IAU constellation images follow the pattern: {Constellation}_IAU.svg
# Example: Andromeda_IAU.svg, Ursa_Major_IAU.svg
WIKIMEDIA_BASE_URL = "https://upload.wikimedia.org/wikipedia/commons"

# Constellation name mappings (some constellations have different names in Wikimedia)
# Maps constellation names to Wikimedia Commons file names for SVG downloads
CONSTELLATION_NAME_MAPPINGS: dict[str, str] = {
    # Northern Hemisphere constellations
    "Andromeda": "Andromeda",
    "Aquila": "Aquila",
    "Aries": "Aries",
    "Auriga": "Auriga",
    "Boötes": "Boötes",
    "Camelopardalis": "Camelopardalis",
    "Cancer": "Cancer",
    "Canes Venatici": "Canes_Venatici",
    "Canis Minor": "Canis_Minor",
    "Cassiopeia": "Cassiopeia",
    "Cepheus": "Cepheus",
    "Coma Berenices": "Coma_Berenices",
    "Corona Borealis": "Corona_Borealis",
    "Cygnus": "Cygnus",
    "Delphinus": "Delphinus",
    "Draco": "Draco",
    "Equuleus": "Equuleus",
    "Gemini": "Gemini",
    "Hercules": "Hercules",
    "Lacerta": "Lacerta",
    "Leo": "Leo",
    "Leo Minor": "Leo_Minor",
    "Lynx": "Lynx",
    "Lyra": "Lyra",
    "Pegasus": "Pegasus",
    "Perseus": "Perseus",
    "Pisces": "Pisces",
    "Sagitta": "Sagitta",
    "Serpens": "Serpens",
    "Taurus": "Taurus",
    "Triangulum": "Triangulum",
    "Ursa Major": "Ursa_Major",
    "Ursa Minor": "Ursa_Minor",
    "Vulpecula": "Vulpecula",
    # Equatorial constellations (visible from Northern Hemisphere)
    "Virgo": "Virgo",
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


async def download_constellation_svg(constellation_name: str, force: bool = False) -> Path | None:
    """
    Download a constellation SVG from Wikimedia Commons and cache it (async).

    Args:
        constellation_name: Name of the constellation (e.g., "Orion")
        force: Force re-download even if cached

    Returns:
        Path to the cached SVG file, or None if download failed
    """
    import aiohttp

    svg_path = get_constellation_svg_path(constellation_name)

    # Return cached file if it exists and we're not forcing
    if svg_path.exists() and not force:
        _debug_print(f"[constellation_images] Using cached SVG for {constellation_name}: {svg_path}")
        logger.info(f"Using cached SVG for {constellation_name}: {svg_path}")
        return svg_path
    elif svg_path.exists() and force:
        _debug_print(
            f"[constellation_images] Force re-download requested for {constellation_name}, will overwrite cache"
        )
        logger.info(f"Force re-download requested for {constellation_name}, will overwrite cache")

    # Map constellation name to Wikimedia file name
    # IAU constellation images use the pattern: {Constellation}_IAU.svg
    # Example: Andromeda_IAU.svg, Ursa_Major_IAU.svg
    wiki_name = CONSTELLATION_NAME_MAPPINGS.get(constellation_name, constellation_name.replace(" ", "_"))

    # Construct the IAU filename pattern
    iau_filename = f"{wiki_name}_IAU.svg"

    # URL-encode the filename to handle special characters (e.g., 'ö' in Boötes)
    # Use quote with safe='/' to preserve forward slashes in paths
    iau_filename_encoded = urllib.parse.quote(iau_filename, safe="/")

    # Try multiple URL patterns for Wikimedia Commons
    # Wikimedia Commons uses Special:FilePath for direct file access
    # The Special:FilePath URL automatically handles the hash-based directory structure
    urls = [
        # Direct file path using IAU pattern (most reliable - handles hash automatically)
        f"https://commons.wikimedia.org/wiki/Special:FilePath/{iau_filename_encoded}",
    ]

    # Also try with different capitalization (first letter capitalized)
    wiki_name_cap = wiki_name.capitalize()
    iau_filename_cap = f"{wiki_name_cap}_IAU.svg"
    iau_filename_cap_encoded = urllib.parse.quote(iau_filename_cap, safe="/")
    urls.append(f"https://commons.wikimedia.org/wiki/Special:FilePath/{iau_filename_cap_encoded}")

    # Log the URLs being tried for debugging
    _debug_print(
        f"[constellation_images] Building URLs for constellation '{constellation_name}' (filename: {iau_filename}):"
    )
    logger.info(f"Building URLs for constellation '{constellation_name}' (filename: {iau_filename}):")
    for i, url in enumerate(urls, 1):
        _debug_print(f"[constellation_images]   URL {i}: {url}")
        logger.info(f"  URL {i}: {url}")

    headers = {"User-Agent": "celestron-nexstar/1.0 (astronomy application)"}

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                _debug_print(f"[constellation_images] Attempting to download constellation SVG from {url}")
                logger.info(f"Attempting to download constellation SVG from {url}")
                # Allow redirects - Special:FilePath may redirect to the actual file
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                ) as response:
                    # Log the final URL after redirects
                    final_url = str(response.url)
                    if final_url != url:
                        _debug_print(f"[constellation_images] Redirected from {url} to {final_url}")
                        logger.info(f"Redirected from {url} to {final_url}")

                    # Check if we got redirected to a thumbnail (PNG) instead of SVG
                    if "/thumb/" in final_url or final_url.endswith(".png"):
                        _debug_print(
                            f"[constellation_images] WARNING: Redirected to thumbnail PNG instead of SVG: {final_url}, skipping"
                        )
                        logger.warning(f"Redirected to thumbnail PNG instead of SVG: {final_url}, skipping")
                        continue

                    if response.status != 200:
                        _debug_print(f"[constellation_images] Failed to download from {url}: HTTP {response.status}")
                        logger.info(f"Failed to download from {url}: HTTP {response.status}")
                        continue

                    # Check content type
                    content_type = response.headers.get("Content-Type", "").lower()
                    _debug_print(f"[constellation_images] Content-Type: {content_type}, URL: {final_url}")
                    logger.info(f"Content-Type: {content_type}, URL: {final_url}")
                    data = await response.read()
                    _debug_print(f"[constellation_images] Downloaded {len(data)} bytes from {final_url}")
                    logger.info(f"Downloaded {len(data)} bytes from {final_url}")

                    if "image/svg" not in content_type and "text/html" in content_type:
                        # Got HTML, might be a redirect page - try to extract the actual file URL
                        _debug_print(
                            f"[constellation_images] Received HTML instead of SVG from {final_url}, checking for redirect"
                        )
                        logger.info(f"Received HTML instead of SVG from {final_url}, checking for redirect")
                        # Look for the actual file URL in the HTML
                        import re

                        # Try multiple patterns to find the SVG file URL
                        patterns = [
                            rb'href="(https://upload\.wikimedia\.org[^"]+\.svg)"',  # Standard href
                            rb'src="(https://upload\.wikimedia\.org[^"]+\.svg)"',  # img src
                            rb'"(https://upload\.wikimedia\.org/wikipedia/commons/[^"]+\.svg)"',  # Any quoted URL
                        ]
                        direct_url = None
                        for pattern in patterns:
                            match = re.search(pattern, data)
                            if match:
                                candidate = match.group(1).decode("utf-8")
                                # Make sure it's not a thumbnail (no /thumb/ in path)
                                if "/thumb/" not in candidate and candidate.endswith(".svg"):
                                    direct_url = candidate
                                    break

                        if direct_url:
                            _debug_print(f"[constellation_images] Found direct file URL in HTML: {direct_url}")
                            logger.info(f"Found direct file URL in HTML: {direct_url}")
                            # Try the direct URL
                            async with session.get(
                                direct_url,
                                headers=headers,
                                timeout=aiohttp.ClientTimeout(total=10),
                            ) as direct_response:
                                if direct_response.status == 200:
                                    data = await direct_response.read()
                                    _debug_print(
                                        f"[constellation_images] Downloaded {len(data)} bytes from direct URL: {direct_url}"
                                    )
                                    logger.info(f"Downloaded {len(data)} bytes from direct URL: {direct_url}")
                                else:
                                    _debug_print(
                                        f"[constellation_images] Failed to download from direct URL: HTTP {direct_response.status}"
                                    )
                                    logger.info(f"Failed to download from direct URL: HTTP {direct_response.status}")
                                    continue
                        else:
                            _debug_print(
                                f"[constellation_images] WARNING: Could not find SVG URL in HTML response from {final_url}"
                            )
                            logger.warning(f"Could not find SVG URL in HTML response from {final_url}")
                            continue

                    # Basic validation: check if it looks like SVG
                    # Check first 2KB for SVG markers
                    if b"<svg" in data[:2048] or (b"<?xml" in data[:2048] and b"svg" in data[:2048].lower()):
                        svg_path.write_bytes(data)
                        _debug_print(f"[constellation_images] SUCCESS: Downloaded {len(data):,} bytes to {svg_path}")
                        logger.info(f"Downloaded {len(data):,} bytes to {svg_path}")
                        return svg_path
                    else:
                        # Check if it's HTML (redirect page)
                        if b"<html" in data[:2048] or b"<!DOCTYPE" in data[:2048]:
                            logger.debug(f"Received HTML instead of SVG from {url} (likely redirect)")
                        else:
                            logger.warning(f"Downloaded file doesn't appear to be SVG: {url}")
            except (aiohttp.ClientError, TimeoutError) as e:
                _debug_print(f"[constellation_images] Failed to download from {url}: {e}")
                logger.debug(f"Failed to download from {url}: {e}")
                continue
            except Exception as e:
                _debug_print(f"[constellation_images] Unexpected error downloading from {url}: {e}")
                logger.warning(f"Unexpected error downloading from {url}: {e}")
                continue

    _debug_print(
        f"[constellation_images] WARNING: Could not download SVG for constellation '{constellation_name}' from any source"
    )
    logger.warning(f"Could not download SVG for constellation '{constellation_name}' from any source")
    return None


async def get_constellation_svg(constellation_name: str) -> Path | None:
    """
    Get the path to a constellation SVG, downloading if necessary (async).

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
    return await download_constellation_svg(constellation_name, force=False)
