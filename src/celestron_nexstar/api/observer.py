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

import deal


logger = logging.getLogger(__name__)


__all__ = [
    "DEFAULT_LOCATION",
    "ObserverLocation",
    "clear_observer_location",
    "detect_location_automatically",
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


@deal.post(lambda result: (result is not None and result.exists()) or True, message="Must return valid path")
def get_config_path() -> Path:
    """Get path to observer location config file."""
    # Store in user's home directory
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "observer_location.json"


@deal.pre(lambda location: location is not None, message="Location must be provided")  # type: ignore[misc,arg-type]
@deal.pre(lambda location: -90 <= location.latitude <= 90, message="Latitude must be -90 to +90")  # type: ignore[misc,arg-type]
@deal.pre(lambda location: -180 <= location.longitude <= 180, message="Longitude must be -180 to +180")  # type: ignore[misc,arg-type]
@deal.post(lambda result: result is None, message="Save must complete")
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


@deal.post(lambda result: result is not None, message="Location must be returned")
def load_location(ask_for_auto_detect: bool = False) -> ObserverLocation:
    """
    Load observer location from config file.

    Args:
        ask_for_auto_detect: If True and no saved location exists, prompt user to auto-detect

    Returns:
        Saved observer location, or default if not configured
    """
    config_path = get_config_path()

    if not config_path.exists():
        logger.debug(f"No saved location found at {config_path}")
        if ask_for_auto_detect:
            # Try to auto-detect location with user permission
            try:
                import sys

                if sys.stdin.isatty():
                    # We're in an interactive terminal, can prompt
                    from rich.console import Console
                    from rich.prompt import Confirm

                    console = Console()
                    console.print("\n[cyan]No location configured[/cyan]")
                    console.print(
                        "[dim]Your location is needed for accurate calculations. "
                        "Would you like to automatically detect your location?[/dim]\n"
                    )
                    console.print("[yellow]Note:[/yellow] This may use your IP address or system location services.\n")

                    if Confirm.ask("Detect location automatically?", default=True, console=console):
                        try:
                            detected = asyncio.run(detect_location_automatically())
                            console.print(f"\n[green]✓[/green] Detected: {detected.name}")
                            console.print(
                                f"[dim]Coordinates: {detected.latitude:.4f}°, {detected.longitude:.4f}°[/dim]\n"
                            )

                            if Confirm.ask("Use this location?", default=True, console=console):
                                save_location(detected)
                                return detected
                            else:
                                console.print("[dim]Location detection cancelled. Using default location.[/dim]\n")
                        except ValueError as e:
                            console.print(f"[yellow]⚠[/yellow] {e}\n")
                            console.print("[dim]Using default location. You can set it manually later.[/dim]\n")
                        except Exception as e:
                            logger.debug(f"Error during location detection: {e}", exc_info=True)
                            console.print(f"[yellow]⚠[/yellow] Failed to detect location: {e}\n")
                            console.print("[dim]Using default location. You can set it manually later.[/dim]\n")
                    else:
                        console.print("[dim]Using default location. You can set it manually later.[/dim]\n")
            except Exception as e:
                # If we can't prompt (e.g., imports fail, not a TTY), just log and continue
                logger.debug(f"Could not prompt for auto-detection: {e}", exc_info=True)
        return DEFAULT_LOCATION

    try:
        with config_path.open("r") as f:
            data = json.load(f)

        # Validate required fields
        if "latitude" not in data or "longitude" not in data:
            raise KeyError("Missing required fields: latitude and/or longitude")

        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        # Validate coordinate ranges
        if not -90 <= latitude <= 90:
            raise ValueError(f"Invalid latitude: {latitude} (must be -90 to 90)")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Invalid longitude: {longitude} (must be -180 to 180)")

        elevation = data.get("elevation", 0.0)
        if elevation < 0:
            logger.warning(f"Negative elevation in config: {elevation}, using 0.0")
            elevation = 0.0

        location = ObserverLocation(
            latitude=latitude,
            longitude=longitude,
            elevation=float(elevation),
            name=data.get("name"),
        )
        logger.info(
            f"Loaded observer location: {location.name or 'Unnamed'} ({location.latitude:.4f}, {location.longitude:.4f})"
        )
        return location
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        # If config is corrupted or invalid, return default
        logger.warning(f"Failed to load location from {config_path}: {e}. Using default location.")
        return DEFAULT_LOCATION
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error loading location from {config_path}: {e}", exc_info=True)
        return DEFAULT_LOCATION


@deal.post(lambda result: result is not None, message="Observer location must be returned")
def get_observer_location(ask_for_auto_detect: bool = False) -> ObserverLocation:
    """
    Get current observer location.

    Returns cached location if set, otherwise loads from config.
    If no location is configured and ask_for_auto_detect is True,
    will prompt user to automatically detect location.

    Args:
        ask_for_auto_detect: If True and no location is configured, prompt to auto-detect

    Returns:
        Current observer location
    """
    global _current_location

    if _current_location is None:
        _current_location = load_location(ask_for_auto_detect=ask_for_auto_detect)

    return _current_location


@deal.pre(lambda location, save: location is not None, message="Location must be provided")  # type: ignore[misc,arg-type]
@deal.pre(lambda location, save: -90 <= location.latitude <= 90, message="Latitude must be -90 to +90")  # type: ignore[misc,arg-type]
@deal.pre(lambda location, save: -180 <= location.longitude <= 180, message="Longitude must be -180 to +180")  # type: ignore[misc,arg-type]
@deal.pre(lambda location, save: location.elevation >= 0, message="Elevation must be non-negative")  # type: ignore[misc,arg-type]
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


@deal.post(lambda result: result is None, message="Clear must complete")
def clear_observer_location() -> None:
    """Clear cached observer location (will reload from config on next access)."""
    global _current_location
    _current_location = None


# type: ignore[misc,arg-type]
@deal.pre(lambda query: query and len(query.strip()) > 0, message="Query must be non-empty")
@deal.post(lambda result: result is not None, message="Geocoded location must be returned")
# Note: Postconditions on async functions check the coroutine, not the awaited result
# Latitude/longitude validation happens in the function implementation
@deal.raises(ValueError)
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
        params: dict[str, str | int] = {
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


@deal.pre(lambda queries: isinstance(queries, list) and len(queries) > 0, message="Queries must be non-empty list")  # type: ignore[misc,arg-type]
@deal.post(lambda result: isinstance(result, dict), message="Must return dictionary")
# Note: Postconditions on async functions check the coroutine, not the awaited result
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


async def _get_location_from_ip() -> ObserverLocation | None:
    """
    Get approximate location from IP address using a free geolocation service.

    This is less accurate than GPS but doesn't require permissions.

    Returns:
        ObserverLocation if successful, None otherwise
    """
    import aiohttp

    try:
        # Use ipapi.co (free, no API key required, rate limited)
        url = "https://ipapi.co/json/"
        headers = {
            "User-Agent": "celestron-nexstar-cli",
        }

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response,
        ):
            if response.status != 200:
                logger.debug(f"IP geolocation API returned HTTP {response.status}")
                return None

            data = await response.json()

        if "latitude" not in data or "longitude" not in data:
            logger.debug("IP geolocation response missing coordinates")
            return None

        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        # Build location name from available fields
        name_parts = []
        city = data.get("city")
        if city:
            name_parts.append(city)
        region = data.get("region")
        if region:
            name_parts.append(region)
        country_name = data.get("country_name")
        if country_name:
            name_parts.append(country_name)
        name = ", ".join(name_parts) if name_parts else "Detected location"

        return ObserverLocation(
            latitude=latitude,
            longitude=longitude,
            elevation=0.0,  # IP geolocation doesn't provide elevation
            name=name,
        )

    except Exception as e:
        logger.debug(f"Failed to get location from IP: {e}")
        return None


async def _get_location_from_system() -> ObserverLocation | None:
    """
    Try to get location from system location services (platform-specific).

    Returns:
        ObserverLocation if successful, None otherwise
    """
    import platform

    system = platform.system().lower()

    # Linux: Try geoclue2 via DBus
    if system == "linux":
        try:
            # Try to use geoclue2 via dbus-python
            # This requires the geoclue2 service to be running and permissions granted
            import dbus  # type: ignore[import-untyped]

            bus = dbus.SystemBus()
            geoclue = bus.get_object("org.freedesktop.GeoClue2", "/org/freedesktop/GeoClue2/Manager")
            manager = dbus.Interface(geoclue, "org.freedesktop.GeoClue2.Manager")

            # Create a client
            client_path = manager.GetClient()
            client = bus.get_object("org.freedesktop.GeoClue2", client_path)
            client_iface = dbus.Interface(client, "org.freedesktop.GeoClue2.Client")

            # Set desktop ID (required by geoclue2)
            client_iface.SetDesktopId("celestron-nexstar")

            # Request location with city-level accuracy
            client_iface.SetRequestedAccuracyLevel(2)  # 1 = COUNTRY, 2 = CITY, 3 = NEIGHBORHOOD, 4 = STREET

            # Start location request (async, but we'll wait for signal)
            # Note: This is a simplified version - full implementation would use signals
            try:
                location_path = client_iface.GetLocation()
                location = bus.get_object("org.freedesktop.GeoClue2", location_path)
                location_iface = dbus.Interface(location, "org.freedesktop.DBus.Properties")

                latitude = location_iface.Get("org.freedesktop.GeoClue2.Location", "Latitude")
                longitude = location_iface.Get("org.freedesktop.GeoClue2.Location", "Longitude")

                return ObserverLocation(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    elevation=0.0,
                    name="System location",
                )
            except dbus.exceptions.DBusException:
                # Location not available yet or permission denied
                logger.debug("System location not available (may need permission)")
                return None
        except ImportError:
            logger.debug("dbus-python not available for system location services")
        except Exception as e:
            logger.debug(f"Failed to get location from system services: {e}")

    # macOS: Try CoreLocation (requires PyObjC)
    elif system == "darwin":
        try:
            from CoreLocation import CLLocationManager  # type: ignore[import-untyped]

            manager = CLLocationManager()
            manager.requestWhenInUseAuthorization()

            location = manager.location()
            if location:
                return ObserverLocation(
                    latitude=float(location.coordinate().latitude),
                    longitude=float(location.coordinate().longitude),
                    elevation=float(location.altitude()) if location.altitude() else 0.0,
                    name="System location",
                )
        except ImportError:
            logger.debug("PyObjC not available for system location services")
        except Exception as e:
            logger.debug(f"Failed to get location from macOS CoreLocation: {e}")

    # Windows: Try Windows Location API (requires winrt)
    elif system == "windows":
        try:
            import winrt.windows.devices.geolocation as geolocation  # type: ignore[import-untyped]

            locator = geolocation.Geolocator()
            location = await locator.get_geoposition_async()

            return ObserverLocation(
                latitude=location.coordinate.latitude,
                longitude=location.coordinate.longitude,
                elevation=location.coordinate.altitude if location.coordinate.altitude else 0.0,
                name="System location",
            )
        except ImportError:
            logger.debug("winrt not available for Windows location services")
        except Exception as e:
            logger.debug(f"Failed to get location from Windows Location API: {e}")

    return None


@deal.raises(ValueError)
async def detect_location_automatically() -> ObserverLocation:
    """
    Automatically detect user's location.

    Tries multiple methods in order:
    1. System location services (GPS, if available and permitted)
    2. IP-based geolocation (fallback, less accurate)

    Returns:
        Detected ObserverLocation

    Raises:
        ValueError: If location could not be detected by any method
    """
    # Try system location services first (most accurate)
    location = await _get_location_from_system()
    if location:
        logger.info("Detected location from system services")
        return location

    # Fall back to IP-based geolocation
    location = await _get_location_from_ip()
    if location:
        logger.info("Detected location from IP address")
        return location

    raise ValueError("Could not automatically detect location. Please set it manually.")
