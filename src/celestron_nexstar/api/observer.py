"""
Observer Location Management

Manages observer's geographic location for accurate ephemeris calculations.
Includes geocoding support for city/address lookups.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from geopy.exc import GeopyError
from geopy.geocoders import Nominatim


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
    data = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "elevation": location.elevation,
        "name": location.name,
    }

    with config_path.open("w") as f:
        json.dump(data, f, indent=2)


def load_location() -> ObserverLocation:
    """
    Load observer location from config file.

    Returns:
        Saved observer location, or default if not configured
    """
    config_path = get_config_path()

    if not config_path.exists():
        return DEFAULT_LOCATION

    try:
        with config_path.open("r") as f:
            data = json.load(f)

        return ObserverLocation(
            latitude=data["latitude"],
            longitude=data["longitude"],
            elevation=data.get("elevation", 0.0),
            name=data.get("name"),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # If config is corrupted, return default
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


def geocode_location(query: str) -> ObserverLocation:
    """
    Geocode a location from city name, address, or ZIP code.

    Uses OpenStreetMap's Nominatim service for geocoding.

    Args:
        query: Location query (e.g., "New York, NY", "90210", "London, UK")

    Returns:
        Observer location with coordinates from geocoding

    Raises:
        ValueError: If location could not be found or geocoding failed
    """
    try:
        # Create geocoder with a user agent
        geolocator = Nominatim(user_agent="celestron-nexstar-cli")

        # Geocode the query
        location = geolocator.geocode(query, timeout=10)

        if location is None:
            raise ValueError(f"Could not find location: '{query}'") from None

        return ObserverLocation(
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=location.altitude if hasattr(location, "altitude") and location.altitude else 0.0,
            name=location.address,
        )

    except GeopyError as e:
        raise ValueError(f"Geocoding error: {e}") from None
    except Exception as e:
        raise ValueError(f"Failed to geocode location: {e}") from None
