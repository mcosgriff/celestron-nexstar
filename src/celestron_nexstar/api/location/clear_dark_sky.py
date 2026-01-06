"""
Clear Dark Sky Chart Integration.

Provides access to Clear Dark Sky charts (cleardarksky.com) which show
astronomical seeing and transparency forecasts.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import requests


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation

logger = logging.getLogger(__name__)

# In-memory cache for chart keys by location
_chart_key_cache: dict[tuple[float, float], str] = {}

# User-Agent header to identify requests
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}


def find_nearest_chart(location: ObserverLocation) -> str | None:
    """
    Find the nearest Clear Dark Sky chart for the given location.

    Args:
        location: Observer location

    Returns:
        Chart key (e.g., "ArvdCO") or None if not found

    Raises:
        requests.RequestException: If all server attempts fail
    """
    # Check cache (round to 2 decimal places)
    cache_key = (round(location.latitude, 2), round(location.longitude, 2))
    if cache_key in _chart_key_cache:
        logger.debug(f"Using cached chart key for {cache_key}")
        return _chart_key_cache[cache_key]

    # Build request parameters
    params = {
        "type": "llmap",
        "Mn": "photoshop",
        "olat": location.latitude,
        "olong": location.longitude,
        "unit": 1,
    }

    # Try servers 1-5 until one responds
    last_error = None
    for server_num in range(1, 6):
        url = f"https://server{server_num}.cleardarksky.com/cgi-bin/find_chart.py"

        try:
            logger.debug(f"Trying Clear Dark Sky server{server_num}...")

            # Get HTML response from Clear Dark Sky
            response = requests.get(url, params=params, headers=_HEADERS, timeout=10)
            response.raise_for_status()

            # Extract chart key from HTML response
            # The response contains preview images like: <img src=../c/ArvdCOcs0.gif?1>
            html_content = response.text

            # Look for the chart preview image in the HTML
            # Pattern: src=../c/{chart_key}cs0.gif
            match = re.search(r"src=\.\./c/(.+?)cs0\.gif", html_content)

            if not match:
                # Try alternate pattern with full URL
                match = re.search(r'src="?https?://www\.cleardarksky\.com/c/(.+?)cs0\.gif', html_content)

            if match:
                chart_key = match.group(1)
                _chart_key_cache[cache_key] = chart_key
                logger.info(f"Found chart key: {chart_key} for location {location.name or cache_key} (using server{server_num})")
                return chart_key

            logger.warning(f"Could not extract chart key from server{server_num} HTML response (location: {location.name or cache_key})")
            logger.debug(f"HTML response preview: {html_content[:500]}")
            # Continue to next server

        except requests.RequestException as e:
            logger.debug(f"Server{server_num} failed: {e}")
            last_error = e
            # Continue to next server

    # All servers failed
    if last_error:
        logger.error(f"All Clear Dark Sky servers (1-5) failed. Last error: {last_error}")
        raise last_error
    else:
        logger.error(f"All Clear Dark Sky servers returned responses but no chart key was found")
        return None


def get_chart_image_url(chart_key: str) -> str:
    """
    Construct the Clear Dark Sky chart image URL.

    Args:
        chart_key: Chart identifier (e.g., "ArvdCO")

    Returns:
        Full URL to chart image (GIF format)
    """
    # Use HTTP due to SSL certificate issues on the HTTPS site
    return f"http://www.cleardarksky.com/c/{chart_key}csk.gif"


def get_chart_page_url(chart_key: str) -> str:
    """
    Construct the Clear Dark Sky chart page URL.

    Args:
        chart_key: Chart identifier (e.g., "ArvdCO")

    Returns:
        Full URL to chart page (HTML)
    """
    return f"https://www.cleardarksky.com/c/{chart_key}key.html"


def fetch_chart_image(chart_key: str) -> bytes | None:
    """
    Fetch the Clear Dark Sky chart image.

    Args:
        chart_key: Chart identifier

    Returns:
        Image bytes (GIF format) or None if failed
    """
    url = get_chart_image_url(chart_key)

    try:
        # Try HTTPS first
        response = requests.get(url, headers=_HEADERS, timeout=10)
        response.raise_for_status()
        return response.content
    except requests.exceptions.SSLError:
        # SSL certificate issue - try HTTP instead
        logger.warning(f"SSL error with HTTPS, trying HTTP for chart image: {chart_key}")
        try:
            http_url = url.replace("https://", "http://")
            response = requests.get(http_url, headers=_HEADERS, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error(f"Failed to fetch chart image via HTTP: {e}")
            return None
    except requests.RequestException as e:
        logger.error(f"Failed to fetch chart image: {e}")
        return None


def is_north_america(location: ObserverLocation) -> bool:
    """
    Check if the location is roughly in North America.

    Clear Dark Sky charts are primarily available for North American locations.

    Args:
        location: Observer location

    Returns:
        True if location is within North America bounds, False otherwise
    """
    # Rough bounds for North America (including Central America and Caribbean)
    # Latitude: 15°N to 72°N (southern Mexico to northern Canada)
    # Longitude: -170°W to -50°W (Alaska to Newfoundland)
    lat_in_range = 15 <= location.latitude <= 72
    lon_in_range = -170 <= location.longitude <= -50

    return lat_in_range and lon_in_range


def clear_cache() -> None:
    """Clear the chart key cache."""
    _chart_key_cache.clear()
    logger.debug("Cleared Clear Dark Sky chart cache")
