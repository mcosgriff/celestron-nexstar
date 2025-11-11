"""
Observer Location Management

Manages observer's geographic location for accurate ephemeris calculations.
Includes geocoding support for city/address lookups.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


__all__ = [
    "DEFAULT_LOCATION",
    "ObserverLocation",
    "clear_observer_location",
    "geocode_location",
    "get_observer_location",
    "set_observer_location",
]


@dataclass
class ObserverLocation:
    """Observer's geographic location."""

    latitude: float  # Degrees north (negative for south)
    longitude: float  # Degrees east (negative for west)
    elevation: float = 0.0  # Meters above sea level
    name: str | None = None  # Optional location name


# Default location (Greenwich Observatory)
DEFAULT_LOCATION = ObserverLocation(
    latitude=51.4769,
    longitude=-0.0005,
    elevation=0.0,
    name="Greenwich Observatory (default)",
)

# Global current location
_current_location: ObserverLocation | None = None


def get_config_path() -> Path:
    """Get path to observer location config file."""
    # Store in user's home directory
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "observer_location.json"


def save_location(location: ObserverLocation) -> None:
    """
    Save observer location to config file.

    Args:
        location: Observer location to save
    """
    config_path = get_config_path()
    logger.info(
        f"Saving observer location: {location.name or 'Unnamed'} ({location.latitude:.4f}, {location.longitude:.4f})"
    )

    data = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "elevation": location.elevation,
        "name": location.name,
    }

    with config_path.open("w") as f:
        json.dump(data, f, indent=2)

    logger.debug(f"Location saved to {config_path}")


def load_location() -> ObserverLocation:
    """
    Load observer location from config file.

    Returns:
        Saved observer location, or default if not configured
    """
    config_path = get_config_path()

    if not config_path.exists():
        logger.debug(f"No saved location found at {config_path}, using default")
        return DEFAULT_LOCATION

    try:
        with config_path.open("r") as f:
            data = json.load(f)

        location = ObserverLocation(
            latitude=data["latitude"],
            longitude=data["longitude"],
            elevation=data.get("elevation", 0.0),
            name=data.get("name"),
        )
        logger.info(
            f"Loaded observer location: {location.name or 'Unnamed'} ({location.latitude:.4f}, {location.longitude:.4f})"
        )
        return location
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # If config is corrupted, return default
        logger.warning(f"Failed to load location from {config_path}: {e}. Using default location.")
        return DEFAULT_LOCATION


def get_observer_location() -> ObserverLocation:
    """
    Get current observer location.

    Returns cached location if set, otherwise loads from config.

    Returns:
        Current observer location
    """
    global _current_location

    if _current_location is None:
        _current_location = load_location()

    return _current_location


def set_observer_location(location: ObserverLocation, save: bool = True) -> None:
    """
    Set current observer location.

    Args:
        location: New observer location
        save: Whether to save to config file (default: True)
    """
    global _current_location
    _current_location = location

    if save:
        save_location(location)


def clear_observer_location() -> None:
    """Clear cached observer location (will reload from config on next access)."""
    global _current_location
    _current_location = None


async def geocode_location(query: str) -> ObserverLocation:
    """
    Geocode a location from city name, address, or ZIP code.

    Uses OpenStreetMap's Nominatim service via aiohttp.

    Args:
        query: Location query (e.g., "New York, NY", "90210", "London, UK")

    Returns:
        Observer location with coordinates from geocoding

    Raises:
        ValueError: If location could not be found or geocoding failed
    """
    import aiohttp

    try:
        # Use Nominatim API directly
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": "celestron-nexstar-cli",
        }

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response,
        ):
            if response.status != 200:
                raise ValueError(f"Geocoding API returned HTTP {response.status}")

            data = await response.json()

        if not data or len(data) == 0:
            raise ValueError(f"Could not find location: '{query}'") from None

        result = data[0]
        latitude = float(result["lat"])
        longitude = float(result["lon"])
        address = result.get("display_name", query)

        # Try to get elevation from addressdetails if available
        elevation = 0.0
        if "addressdetails" in result:
            # Elevation not typically in Nominatim response, but we can try
            pass

        return ObserverLocation(
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            name=address,
        )

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Failed to geocode location: {e}") from None


async def geocode_location_batch(queries: list[str]) -> dict[str, ObserverLocation]:
    """
    Geocode multiple locations concurrently.

    Args:
        queries: List of location queries

    Returns:
        Dictionary mapping queries to ObserverLocation (failed queries excluded)
    """
    tasks = [geocode_location(query) for query in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    data_map: dict[str, ObserverLocation] = {}
    for query, result in zip(queries, results, strict=False):
        if isinstance(result, Exception):
            logger.warning(f"Error geocoding '{query}': {result}")
        elif isinstance(result, ObserverLocation):
            data_map[query] = result

    return data_map
