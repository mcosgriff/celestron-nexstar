"""
Observer Location Management

Manages observer's geographic location for accurate ephemeris calculations.
Includes geocoding support for city/address lookups.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import deal
from sqlalchemy import select, update

from celestron_nexstar.api.core.exceptions import (
    GeocodingError,
    LocationNotFoundError,
    LocationNotSetError,
)
from celestron_nexstar.api.database.models import ObserverLocationModel, get_db_session


logger = logging.getLogger(__name__)


__all__ = [
    "DEFAULT_LOCATION",
    "FEET_TO_METERS",
    "METERS_TO_FEET",
    "ObserverLocation",
    "ObserverLocationEntry",
    "add_observer_location",
    "clear_observer_location",
    "detect_location_automatically",
    "enrich_location_with_elevation_feet",
    "enrich_location_with_radar_site",
    "geocode_location",
    "geocode_location_batch",
    "get_active_observer_location_id",
    "get_observer_location",
    "lookup_radar_site_code",
    "list_observer_locations",
    "set_active_observer_location",
    "set_observer_location",
    "update_observer_location",
]

METERS_TO_FEET = 3.28084
FEET_TO_METERS = 1.0 / METERS_TO_FEET


@dataclass(frozen=True)
class ObserverLocation:
    """Observer's geographic location."""

    latitude: float  # Degrees north (negative for south)
    longitude: float  # Degrees east (negative for west)
    elevation: float = 0.0  # Elevation above sea level (unitless, stored as-is)
    name: str | None = None  # Optional location name
    radar_site_code: str | None = None  # Optional NEXRAD radar site code


@dataclass(frozen=True)
class ObserverLocationEntry:
    """Saved observer location entry."""

    id: str
    location: ObserverLocation


# Default location (Greenwich Observatory)
DEFAULT_LOCATION = ObserverLocation(
    latitude=51.4769,
    longitude=-0.0005,
    elevation=0.0,
    name="Greenwich Observatory (default)",
)

# Global current location
_current_location: ObserverLocation | None = None
_current_location_id: str | None = None


def _model_to_entry(model: ObserverLocationModel) -> ObserverLocationEntry:
    location = ObserverLocation(
        latitude=model.latitude,
        longitude=model.longitude,
        elevation=model.elevation,
        name=model.name,
        radar_site_code=model.radar_site_code,
    )
    return ObserverLocationEntry(id=model.id, location=location)


def _get_active_location_model(session) -> ObserverLocationModel | None:
    active_locations = list(
        session.execute(
            select(ObserverLocationModel)
            .where(ObserverLocationModel.is_active.is_(True))
            .order_by(ObserverLocationModel.created_at)
        ).scalars()
    )
    if active_locations:
        active = active_locations[0]
        if len(active_locations) > 1:
            extra_ids = [entry.id for entry in active_locations[1:]]
            session.execute(
                update(ObserverLocationModel).where(ObserverLocationModel.id.in_(extra_ids)).values(is_active=False)
            )
            session.commit()
        return active

    first = session.execute(select(ObserverLocationModel).order_by(ObserverLocationModel.created_at)).scalars().first()
    if first:
        first.is_active = True
        session.commit()
        return first
    return None


@deal.pre(lambda location: location is not None, message="Location must be provided")  # type: ignore[misc,arg-type]
@deal.pre(lambda location: -90 <= location.latitude <= 90, message="Latitude must be -90 to +90")  # type: ignore[misc,arg-type]
@deal.pre(lambda location: -180 <= location.longitude <= 180, message="Longitude must be -180 to +180")  # type: ignore[misc,arg-type]
@deal.post(lambda result: result is None, message="Save must complete")
def save_location(location: ObserverLocation) -> None:
    """
    Save observer location to database.

    Args:
        location: Observer location to save
    """
    logger.info(
        f"Saving observer location: {location.name or 'Unnamed'} ({location.latitude:.4f}, {location.longitude:.4f})"
    )

    with get_db_session() as session:
        active = _get_active_location_model(session)
        if active:
            active.name = location.name
            active.latitude = location.latitude
            active.longitude = location.longitude
            active.elevation = location.elevation
            active.radar_site_code = location.radar_site_code
            session.commit()
        else:
            active = ObserverLocationModel(
                name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                elevation=location.elevation,
                radar_site_code=location.radar_site_code,
                is_active=True,
            )
            session.add(active)
            session.commit()

        global _current_location_id
        _current_location_id = active.id
    logger.debug("Observer location saved to database")


@deal.post(lambda result: result is not None, message="Location must be returned")
def load_location(ask_for_auto_detect: bool = False) -> ObserverLocation:
    """
    Load observer location from database.

    Args:
        ask_for_auto_detect: If True and no saved location exists, prompt user to auto-detect

    Returns:
        Saved observer location, or default if not configured
    """
    try:
        with get_db_session() as session:
            active = _get_active_location_model(session)
            if active:
                location = ObserverLocation(
                    latitude=active.latitude,
                    longitude=active.longitude,
                    elevation=active.elevation,
                    name=active.name,
                    radar_site_code=active.radar_site_code,
                )
                global _current_location_id
                _current_location_id = active.id
                logger.info(
                    "Loaded observer location: "
                    f"{location.name or 'Unnamed'} ({location.latitude:.4f}, {location.longitude:.4f})"
                )
                return location

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
                            detected = detect_location_automatically()
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
                        except (
                            RuntimeError,
                            AttributeError,
                            TypeError,
                            KeyError,
                            IndexError,
                            OSError,
                            TimeoutError,
                        ) as e:
                            # RuntimeError: async/await errors, event loop errors
                            # AttributeError: missing attributes
                            # TypeError: wrong data types
                            # KeyError: missing keys in response data
                            # IndexError: missing array indices
                            # OSError: network/system errors
                            # TimeoutError: request timeout
                            logger.debug(f"Error during location detection: {e}", exc_info=True)
                            console.print(f"[yellow]⚠[/yellow] Failed to detect location: {e}\n")
                            console.print("[dim]Using default location. You can set it manually later.[/dim]\n")
                    else:
                        console.print("[dim]Using default location. You can set it manually later.[/dim]\n")
            except (OSError, RuntimeError, AttributeError, ImportError, TypeError) as e:
                # OSError: I/O errors (stdin/stdout), not a TTY
                # RuntimeError: console/prompt errors
                # AttributeError: missing console attributes
                # ImportError: missing rich imports
                # TypeError: wrong argument types
                # If we can't prompt (e.g., imports fail, not a TTY), just log and continue
                logger.debug(f"Could not prompt for auto-detection: {e}", exc_info=True)
        return DEFAULT_LOCATION
    except Exception as e:
        logger.warning(f"Failed to load observer location from database: {e}. Using default location.")
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
        save: Whether to save to database (default: True)
    """
    global _current_location, _current_location_id
    _current_location = location

    if save:
        save_location(location)
    else:
        _current_location_id = None


def list_observer_locations() -> list[ObserverLocationEntry]:
    """Return all saved observer locations."""
    with get_db_session() as session:
        models = session.execute(select(ObserverLocationModel).order_by(ObserverLocationModel.created_at)).scalars()
        return [_model_to_entry(model) for model in models]


def get_active_observer_location_id() -> str | None:
    """Return the active observer location id, if any."""
    global _current_location_id
    if _current_location_id is not None:
        return _current_location_id

    with get_db_session() as session:
        active = _get_active_location_model(session)
        if active:
            _current_location_id = active.id
            return active.id
    return None


def set_active_observer_location(location_id: str, save: bool = True) -> ObserverLocation:
    """Set the active observer location by id."""
    with get_db_session() as session:
        location = session.get(ObserverLocationModel, location_id)
        if not location:
            raise LocationNotFoundError(f"Saved location not found: {location_id}")

        if save:
            session.execute(update(ObserverLocationModel).values(is_active=False))
            location.is_active = True
            session.commit()

        active_location = ObserverLocation(
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=location.elevation,
            name=location.name,
            radar_site_code=location.radar_site_code,
        )
        global _current_location, _current_location_id
        _current_location = active_location
        _current_location_id = location.id
        return active_location


def add_observer_location(location: ObserverLocation, set_active: bool = True) -> ObserverLocationEntry:
    """Add a new observer location entry."""
    with get_db_session() as session:
        if set_active:
            session.execute(update(ObserverLocationModel).values(is_active=False))
        model = ObserverLocationModel(
            name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=location.elevation,
            radar_site_code=location.radar_site_code,
            is_active=set_active,
        )
        session.add(model)
        session.commit()

        entry = _model_to_entry(model)
        if set_active:
            global _current_location, _current_location_id
            _current_location = entry.location
            _current_location_id = entry.id
        return entry


def update_observer_location(
    location_id: str,
    location: ObserverLocation,
    set_active: bool = True,
) -> ObserverLocationEntry:
    """Update an existing observer location entry."""
    with get_db_session() as session:
        model = session.get(ObserverLocationModel, location_id)
        if not model:
            raise LocationNotFoundError(f"Saved location not found: {location_id}")

        model.name = location.name
        model.latitude = location.latitude
        model.longitude = location.longitude
        model.elevation = location.elevation
        model.radar_site_code = location.radar_site_code
        if set_active:
            session.execute(update(ObserverLocationModel).values(is_active=False))
            model.is_active = True
        session.commit()

        entry = _model_to_entry(model)
        if set_active:
            global _current_location, _current_location_id
            _current_location = entry.location
            _current_location_id = entry.id
        return entry


@deal.post(lambda result: result is None, message="Clear must complete")
def clear_observer_location() -> None:
    """Clear cached observer location (will reload from config on next access)."""
    global _current_location, _current_location_id
    _current_location = None
    _current_location_id = None


@deal.pre(lambda query: query and len(query.strip()) > 0, message="Query must be non-empty")
@deal.post(lambda result: result is not None, message="Geocoded location must be returned")
# Latitude/longitude validation happens in the function implementation
@deal.raises(GeocodingError, LocationNotFoundError)
def geocode_location(query: str) -> ObserverLocation:
    """
    Geocode a location from city name, address, or ZIP code.

    Uses OpenStreetMap's Nominatim service via requests.

    Args:
        query: Location query (e.g., "New York, NY", "90210", "London, UK")

    Returns:
        Observer location with coordinates from geocoding

    Raises:
        ValueError: If location could not be found or geocoding failed
    """
    try:
        import requests

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

        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            raise GeocodingError(f"Geocoding API returned HTTP {response.status_code}")
        data = response.json()

        if not data or len(data) == 0:
            raise LocationNotFoundError(f"Could not find location: '{query}'") from None

        result = data[0]
        latitude = float(result["lat"])
        longitude = float(result["lon"])
        address = result.get("display_name", query)

        return ObserverLocation(
            latitude=latitude,
            longitude=longitude,
            elevation=0.0,  # Elevation can be enriched via Open-Elevation
            name=address,
            radar_site_code=None,
        )

    except (GeocodingError, LocationNotFoundError):
        raise
    except (requests.RequestException, TimeoutError, ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
        # requests.RequestException: HTTP/network errors
        # TimeoutError: request timeout
        # ValueError: invalid coordinates or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # AttributeError: missing attributes in response
        raise GeocodingError(f"Failed to geocode location: {e}") from None


@deal.pre(lambda queries: isinstance(queries, list) and len(queries) > 0, message="Queries must be non-empty list")  # type: ignore[misc,arg-type]
@deal.post(lambda result: isinstance(result, dict), message="Must return dictionary")
def geocode_location_batch(queries: list[str]) -> dict[str, ObserverLocation]:
    """
    Geocode multiple locations sequentially.

    Args:
        queries: List of location queries

    Returns:
        Dictionary mapping queries to ObserverLocation (failed queries excluded)
    """
    data_map: dict[str, ObserverLocation] = {}
    for query in queries:
        try:
            result = geocode_location(query)
            data_map[query] = result
        except Exception as e:
            logger.warning(f"Error geocoding '{query}': {e}")

    return data_map


def _get_location_from_ip() -> ObserverLocation | None:
    """
    Get approximate location from IP address using a free geolocation service.

    This is less accurate than GPS but doesn't require permissions.

    Returns:
        ObserverLocation if successful, None otherwise
    """
    try:
        import requests

        # Use ipapi.co (free, no API key required, rate limited)
        url = "https://ipapi.co/json/"
        headers = {
            "User-Agent": "celestron-nexstar-cli",
        }

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.debug(f"IP geolocation API returned HTTP {response.status_code}")
            return None

        data = response.json()

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
            radar_site_code=None,
        )

    except (
        requests.RequestException,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
    ) as e:
        # requests.RequestException: HTTP/network errors
        # TimeoutError: request timeout
        # ValueError: invalid coordinates or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # AttributeError: missing attributes in response
        logger.debug(f"Failed to get location from IP: {e}")
        return None


def _get_location_from_system() -> ObserverLocation | None:
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
                    radar_site_code=None,
                )
            except dbus.exceptions.DBusException:
                # Location not available yet or permission denied
                logger.debug("System location not available (may need permission)")
                return None
        except ImportError:
            logger.debug("dbus-python not available for system location services")
        except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as e:
            # AttributeError: missing dbus attributes
            # RuntimeError: dbus service errors
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in dbus response
            # IndexError: missing array indices
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
                    radar_site_code=None,
                )
        except ImportError:
            logger.debug("PyObjC not available for system location services")
        except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError, OSError) as e:
            # AttributeError: missing CoreLocation attributes
            # RuntimeError: CoreLocation service errors
            # ValueError: invalid coordinates or data format
            # TypeError: wrong data types
            # KeyError: missing keys in response
            # IndexError: missing array indices
            # OSError: system/permission errors
            logger.debug(f"Failed to get location from macOS CoreLocation: {e}")

    # Windows: Try Windows Location API (requires winrt)
    elif system == "windows":
        try:
            import winrt.windows.devices.geolocation as geolocation  # type: ignore[import-untyped]

            locator = geolocation.Geolocator()
            # Windows Runtime async methods need to be run in an event loop
            location = locator.get_geoposition_async()

            return ObserverLocation(
                latitude=location.coordinate.latitude,
                longitude=location.coordinate.longitude,
                elevation=location.coordinate.altitude if location.coordinate.altitude else 0.0,
                name="System location",
                radar_site_code=None,
            )
        except ImportError:
            logger.debug("winrt not available for Windows location services")
        except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError, OSError, TimeoutError) as e:
            # AttributeError: missing winrt attributes
            # RuntimeError: async/await errors, Location API errors
            # ValueError: invalid coordinates or data format
            # TypeError: wrong data types
            # KeyError: missing keys in response
            # IndexError: missing array indices
            # OSError: system/permission errors
            # TimeoutError: location request timeout
            logger.debug(f"Failed to get location from Windows Location API: {e}")

    return None


@deal.raises(LocationNotSetError)
def detect_location_automatically() -> ObserverLocation:
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
    location = _get_location_from_system()
    if location:
        logger.info("Detected location from system services")
        return enrich_location_with_radar_site(location)

    # Fall back to IP-based geolocation
    location = _get_location_from_ip()
    if location:
        logger.info("Detected location from IP address")
        return enrich_location_with_radar_site(location)

    raise LocationNotSetError("Could not automatically detect location. Please set it manually.")


def _lookup_elevation_meters(lat: float, lon: float) -> float | None:
    """
    Lookup elevation in meters using Open-Elevation.

    Endpoint format:
      https://api.open-elevation.com/api/v1/lookup?locations=LAT,LON
    """
    import requests

    try:
        url = "https://api.open-elevation.com/api/v1/lookup"
        params = {"locations": f"{lat:.6f},{lon:.6f}"}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        elev = results[0].get("elevation")
        if elev is None:
            return None
        return float(elev)
    except Exception:
        return None


def enrich_location_with_elevation_feet(location: ObserverLocation) -> ObserverLocation:
    """
    Return a copy of `location` with elevation set (feet above sea level) using Open-Elevation.

    If the elevation lookup fails, returns the original location unchanged.
    """
    try:
        elev_m = _lookup_elevation_meters(location.latitude, location.longitude)
        if elev_m is None:
            return location
        elev_ft = max(0.0, float(elev_m) * METERS_TO_FEET)
        return ObserverLocation(
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=elev_ft,
            name=location.name,
            radar_site_code=location.radar_site_code,
        )
    except Exception:
        return location


def lookup_radar_site_code(latitude: float, longitude: float) -> str | None:
    """
    Look up the nearest NEXRAD radar site code for a location using the NWS points API.

    Returns a radar site code like "KFTG", or None if unavailable.
    """
    try:
        import requests

        url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
        headers = {
            "User-Agent": "celestron-nexstar-cli",
            "Accept": "application/geo+json",
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.debug(f"NWS points API returned HTTP {response.status_code}")
            return None
        data = response.json()
        properties = data.get("properties", {})
        radar_site = properties.get("radarStation")
        if isinstance(radar_site, str) and radar_site.strip():
            return radar_site.strip().upper()
        return None
    except Exception as e:
        logger.debug(f"Failed to lookup radar site code: {e}")
        return None


def enrich_location_with_radar_site(location: ObserverLocation) -> ObserverLocation:
    """
    Return a copy of `location` with radar_site_code populated when available.

    If lookup fails, returns the original location unchanged.
    """
    radar_site = lookup_radar_site_code(location.latitude, location.longitude)
    if not radar_site:
        return location
    return ObserverLocation(
        latitude=location.latitude,
        longitude=location.longitude,
        elevation=location.elevation,
        name=location.name,
        radar_site_code=radar_site,
    )
