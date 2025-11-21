"""
Pane Content Generators

Functions to generate formatted text content for each pane in the TUI.
Now using Textual widgets with Rich markup.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.widgets import Static  # type: ignore[import-not-found]


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    pass


def _add_rich_line(result: list[str], style: str, text: str) -> None:
    """
    Add a line with Rich markup to the result list.

    Args:
        result: List to append to
        style: Style name (Rich markup compatible)
        text: Text content
    """
    if style:
        # Convert style names to Rich markup
        style_map = {
            "bold": "bold",
            "dim": "dim",
            "cyan": "cyan",
            "yellow": "yellow",
            "green": "green",
            "red": "red",
            "bold yellow": "bold yellow",
            "bold cyan": "bold cyan",
            "bold green": "bold green",
            "bold red": "bold red",
            "ansigreen": "green",
            "ansicyan": "cyan",
            "ansiyellow": "yellow",
            "ansired": "red",
            "bg:#444444": "on #444444",
        }
        rich_style = style_map.get(style, style)
        result.append(f"[{rich_style}]{text}[/]")
    else:
        result.append(text)


def _get_indicator_color(score: float) -> str:
    """
    Get color for condition indicator based on score (0-100).

    Args:
        score: Condition score from 0-100

    Returns:
        Color name for Rich markup styling
    """
    match score:
        case s if s >= 90:
            return "ansigreen"  # Great conditions (green)
        case s if s >= 80:
            return "ansicyan"  # Good conditions (light green/cyan)
        case s if s >= 50:
            return "ansiyellow"  # Marginal conditions (yellow)
        case _:
            return "ansired"  # Poor conditions (red)


def _calculate_cloud_cover_score(cloud_cover_percent: float) -> float:
    """
    Calculate cloud cover score (0-100, higher is better).

    Args:
        cloud_cover_percent: Cloud cover percentage (0-100)

    Returns:
        Score from 0-100
    """
    # Lower cloud cover = better (0% = 100, 100% = 0)
    return max(0.0, 100.0 - cloud_cover_percent)


def _calculate_wind_score(wind_mph: float) -> float:
    """
    Calculate wind speed score (0-100, higher is better).

    Args:
        wind_mph: Wind speed in mph

    Returns:
        Score from 0-100
    """
    # Optimal: 5-10 mph = 100
    # Below 5 mph: insufficient mixing (reduced score)
    # Above 10 mph: turbulence increases (reduced score)
    match wind_mph:
        case w if 5.0 <= w <= 10.0:
            return 100.0
        case w if w < 5.0:
            # Below 5 mph: score reduces linearly
            return w * 20.0  # 0-100 points
        case w if w <= 15.0:
            # 10-15 mph: score reduces gradually
            return 100.0 - (w - 10.0) * 10.0  # 100-50 points
        case w if w <= 20.0:
            # 15-20 mph: score reduces more sharply
            return 50.0 - (w - 15.0) * 10.0  # 50-0 points
        case _:
            return 0.0


def _calculate_humidity_score(humidity_percent: float) -> float:
    """
    Calculate humidity score (0-100, higher is better).

    Args:
        humidity_percent: Relative humidity percentage (0-100)

    Returns:
        Score from 0-100
    """
    # Lower humidity = better (0% = 100, 100% = 0)
    return max(0.0, 100.0 - humidity_percent)


async def _get_dataset_info_async() -> str:
    """
    Generate formatted text for the dataset information pane (async version).

    Returns:
        Formatted text showing database statistics and catalog information
    """
    try:
        from celestron_nexstar.api.database.database import get_database

        db = get_database()
        stats = await db.get_stats()

        from celestron_nexstar.cli.tui.state import get_state

        state = get_state()
        is_focused = state.focused_pane == "dataset"

        lines: list[str] = []
        if is_focused:
            _add_rich_line(lines, "bold yellow", "▶ Database Statistics\n")
        else:
            _add_rich_line(lines, "bold", "Database Statistics\n")
        lines.append("─" * 30 + "\n")
        lines.append(f"Total Objects: {stats.total_objects:,}\n")
        lines.append(f"Catalogs: {len(stats.objects_by_catalog)}\n")
        lines.append(f"Types: {len(stats.objects_by_type)}\n")
        lines.append("\n")

        # Magnitude range
        if stats.magnitude_range[0] is not None and stats.magnitude_range[1] is not None:
            lines.append("Magnitude Range:\n")
            _add_rich_line(lines, "cyan", f"  {stats.magnitude_range[0]:.2f} to {stats.magnitude_range[1]:.2f}\n")
            lines.append("\n")

        # Top catalogs
        _add_rich_line(lines, "bold", "Top Catalogs:\n")
        sorted_catalogs = sorted(stats.objects_by_catalog.items(), key=lambda x: x[1], reverse=True)[:5]
        for catalog, count in sorted_catalogs:
            lines.append(f"  {catalog:15s} ")
            _add_rich_line(lines, "cyan", f"{count:6,}\n")

        lines.append("\n")

        # Top object types
        _add_rich_line(lines, "bold", "Object Types:\n")
        sorted_types = sorted(stats.objects_by_type.items(), key=lambda x: x[1], reverse=True)[:5]
        for obj_type, count in sorted_types:
            lines.append(f"  {obj_type:15s} ")
            _add_rich_line(lines, "yellow", f"{count:6,}\n")

        lines.append("\n")
        lines.append("─" * 30 + "\n")
        _add_rich_line(lines, "bold", "Telescope Configuration\n")
        lines.append("\n")

        # Get optical configuration
        try:
            from celestron_nexstar.api.observation.optics import get_current_configuration

            config = get_current_configuration()
            lines.append("Telescope:\n")
            _add_rich_line(lines, "cyan", f"  {config.telescope.display_name}\n")
            lines.append(
                f'  Aperture: {config.telescope.aperture_mm:.0f}mm ({config.telescope.aperture_inches:.1f}")\n'
            )
            lines.append(f"  Focal Length: {config.telescope.focal_length_mm:.0f}mm\n")
            lines.append(f"  f-ratio: f/{config.telescope.focal_ratio:.1f}\n")
            lines.append("\n")

            lines.append("Eyepiece:\n")
            eyepiece_name = config.eyepiece.name or f"{config.eyepiece.focal_length_mm:.0f}mm"
            _add_rich_line(lines, "cyan", f"  {eyepiece_name}\n")
            lines.append(f"  Focal Length: {config.eyepiece.focal_length_mm:.0f}mm\n")
            lines.append(f"  Apparent FOV: {config.eyepiece.apparent_fov_deg:.0f}°\n")
            lines.append("\n")

            lines.append("Configuration:\n")
            lines.append(f"  Magnification: {config.magnification:.0f}x\n")
            lines.append(f"  Exit Pupil: {config.exit_pupil_mm:.2f}mm\n")
            lines.append(f"  True FOV: {config.true_fov_arcmin:.1f}' ({config.true_fov_deg:.2f}°)\n")
            lines.append("\n")

            # Limiting magnitude
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.observation.optics import calculate_limiting_magnitude

            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
            lines.append("Limiting Mag: ")
            _add_rich_line(lines, "yellow", f"{limiting_mag:.2f}\n")
            lines.append("\n")

        except Exception as e:
            _add_rich_line(lines, "yellow", f"Config: Error ({e})\n")

        # Telescope Status (if connected)
        lines.append("─" * 30 + "\n")
        _add_rich_line(lines, "bold", "Telescope Status\n")
        lines.append("\n")

        try:
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                # Connection status
                _add_rich_line(lines, "green", "  Connected\n")
                lines.append("\n")

                # Get position
                try:
                    ra_dec = telescope.get_position_ra_dec()
                    alt_az = telescope.get_position_alt_az()

                    # Format RA
                    ra_h = int(ra_dec.ra_hours)
                    ra_m = int((ra_dec.ra_hours - ra_h) * 60)
                    ra_s = int(((ra_dec.ra_hours - ra_h) * 60 - ra_m) * 60)

                    # Format Dec
                    dec_d = int(ra_dec.dec_degrees)
                    dec_m = int((abs(ra_dec.dec_degrees) - abs(dec_d)) * 60)
                    dec_s = int(((abs(ra_dec.dec_degrees) - abs(dec_d)) * 60 - dec_m) * 60)
                    dec_dir = "N" if ra_dec.dec_degrees >= 0 else "S"

                    lines.append("Position (RA/Dec):\n")
                    _add_rich_line(lines, "cyan", f"  RA:  {ra_h:02d}h {ra_m:02d}m {ra_s:02d}s\n")
                    _add_rich_line(lines, "cyan", f"  Dec: {abs(dec_d):02d}° {dec_m:02d}' {dec_s:02d}\" {dec_dir}\n")
                    lines.append("\n")

                    lines.append("Position (Alt/Az):\n")
                    _add_rich_line(lines, "cyan", f"  Alt: {alt_az.altitude:5.1f}°\n")
                    _add_rich_line(lines, "cyan", f"  Az:  {alt_az.azimuth:5.1f}°\n")
                    lines.append("\n")

                except Exception:
                    _add_rich_line(lines, "yellow", "  Position: Unavailable\n")
                    lines.append("\n")

                # Get tracking mode
                try:
                    tracking_mode_num = telescope.protocol.get_tracking_mode()
                    tracking_modes = {
                        0: "Off",
                        1: "Alt-Az",
                        2: "EQ North",
                        3: "EQ South",
                    }
                    tracking_name = tracking_modes.get(tracking_mode_num, f"Unknown ({tracking_mode_num})")
                    lines.append("Tracking: ")
                    _add_rich_line(lines, "cyan", f"{tracking_name}\n")
                except Exception:
                    _add_rich_line(lines, "yellow", "  Tracking: Unknown\n")

            else:
                _add_rich_line(lines, "dim", "  Not connected\n")
                _add_rich_line(lines, "dim", "  Press 'c' to connect\n")

        except Exception as e:
            _add_rich_line(lines, "yellow", f"Status: Error ({str(e)[:30]})\n")

        # Session Information
        lines.append("\n")
        lines.append("─" * 30 + "\n")
        _add_rich_line(lines, "bold", "Session\n")
        lines.append("\n")

        try:
            from celestron_nexstar.cli.tui.state import get_state

            state = get_state()
            if state.session_start_time is None:
                _add_rich_line(lines, "dim", "  Not started\n")
                _add_rich_line(lines, "dim", "  Press 's' to start\n")
            else:
                duration = state.get_session_duration()
                if duration is not None:
                    hours = int(duration)
                    minutes = int((duration - hours) * 60)
                    lines.append(f"  Duration: {hours}h {minutes}m\n")
                lines.append(f"  Observed: {len(state.observed_objects)}\n")
                if state.observed_objects:
                    # Show last 3 observed objects
                    for obj_name in state.observed_objects[-3:]:
                        _add_rich_line(lines, "dim", f"    • {obj_name[:25]}\n")

        except Exception:
            _add_rich_line(lines, "yellow", "  Session: Error\n")

        lines.append("\n")
        _add_rich_line(lines, "dim", "Press 't'=telescope 'e'=eyepiece\n")

        return "".join(lines)

    except Exception as e:
        return f"[bold red]Database Error\n[/][red]Cannot load database: {e}\n[/]"


def get_dataset_info() -> str:
    """
    Generate formatted text for the dataset information pane (sync wrapper).

    Returns:
        Formatted text showing database statistics and catalog information
    """
    try:
        import asyncio

        # Try to get the current event loop
        try:
            asyncio.get_running_loop()
            # If we're in an event loop, we can't use asyncio.run()
            # Return a placeholder and let the async version handle it
            return "[yellow]Loading...[/yellow]"
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(_get_dataset_info_async())
    except Exception as e:
        return f"[bold red]Database Error\n[/][red]Cannot load database: {e}\n[/]"


def get_conditions_info() -> str:
    """
    Generate formatted text for the current conditions pane.

    Returns:
        Formatted text showing weather, sky conditions, and time information
    """
    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    is_focused = state.focused_pane == "conditions"

    lines: list[str] = []
    if is_focused:
        _add_rich_line(lines, "bold yellow", "▶ Observing Conditions\n")
    else:
        _add_rich_line(lines, "bold", "Observing Conditions\n")
    lines.append("─" * 30 + "\n")

    # Location
    try:
        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.cli.utils.state import get_telescope

        # Check if telescope has location
        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            try:
                telescope_location = telescope.get_location()
                if telescope_location and telescope_location.latitude != 0.0 and telescope_location.longitude != 0.0:
                    # Use telescope location
                    lat = telescope_location.latitude
                    lon = telescope_location.longitude
                    lat_dir = "N" if lat >= 0 else "S"
                    lon_dir = "E" if lon >= 0 else "W"
                    lines.append("Location:\n")
                    _add_rich_line(lines, "cyan", f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n")
                    _add_rich_line(lines, "dim", "  (from telescope GPS)\n")
            except Exception:
                # Fall back to observer location
                location = get_observer_location()
                if location:
                    lat = location.latitude
                    lon = location.longitude
                    lat_dir = "N" if lat >= 0 else "S"
                    lon_dir = "E" if lon >= 0 else "W"
                    lines.append("Location:\n")
                    if location.name:
                        _add_rich_line(lines, "cyan", f"  {location.name}\n")
                    lines.append(f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n")
                else:
                    _add_rich_line(lines, "yellow", "Location: Not set\n")
        else:
            # No telescope, use observer location
            location = get_observer_location()
            if location:
                lat = location.latitude
                lon = location.longitude
                lat_dir = "N" if lat >= 0 else "S"
                lon_dir = "E" if lon >= 0 else "W"
                lines.append("Location:\n")
                if location.name:
                    _add_rich_line(lines, "cyan", f"  {location.name}\n")
                lines.append(f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n")
            else:
                _add_rich_line(lines, "yellow", "Location: Not set\n")
    except Exception as e:
        _add_rich_line(lines, "yellow", f"Location: Error ({e})\n")

    lines.append("\n")

    # Time information
    from datetime import UTC

    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    if state.time_display_mode == "utc":
        now = datetime.now(UTC)
        time_label = "UTC"
    else:
        now = datetime.now()
        time_label = "Local"

    lines.append("Time:\n")
    _add_rich_line(lines, "cyan", f"  {time_label}: {now.strftime('%H:%M:%S')}\n")
    _add_rich_line(lines, "cyan", f"  Date:  {now.strftime('%Y-%m-%d')}\n")
    _add_rich_line(lines, "dim", "  Press 'u' to toggle UTC/Local\n")
    lines.append("\n")

    # Sky conditions
    _add_rich_line(lines, "bold", "Sky Conditions:\n")

    # Get observer location for moon/sun calculations
    moon_observer_lat = None
    moon_observer_lon = None
    try:
        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.cli.utils.state import get_telescope

        # Try telescope GPS first
        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            try:
                telescope_location = telescope.get_location()
                if telescope_location and telescope_location.latitude != 0.0 and telescope_location.longitude != 0.0:
                    moon_observer_lat = telescope_location.latitude
                    moon_observer_lon = telescope_location.longitude
            except Exception:
                pass

        # Fall back to observer location
        if moon_observer_lat is None or moon_observer_lon is None:
            location = get_observer_location()
            if location:
                moon_observer_lat = location.latitude
                moon_observer_lon = location.longitude
    except Exception:
        pass

    # Moon information
    if moon_observer_lat is not None and moon_observer_lon is not None:
        try:
            from celestron_nexstar.api.astronomy.solar_system import get_moon_info

            moon_info = get_moon_info(moon_observer_lat, moon_observer_lon, now)
            if moon_info:
                lines.append("Moon:\n")
                _add_rich_line(lines, "cyan", f"  Phase: {moon_info.phase_name}\n")
                lines.append(f"  Illumination: {moon_info.illumination * 100:.0f}%\n")
                if moon_info.altitude_deg > 0:
                    lines.append(f"  Alt: {moon_info.altitude_deg:5.1f}° ")
                    lines.append(f"Az: {moon_info.azimuth_deg:5.1f}°\n")
                else:
                    _add_rich_line(lines, "dim", "  Below horizon\n")
            else:
                _add_rich_line(lines, "yellow", "  Moon: Calculation unavailable\n")
        except Exception as e:
            # Truncate error message to prevent scrolling
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            _add_rich_line(lines, "yellow", f"  Moon: {error_msg}\n")
    else:
        _add_rich_line(lines, "yellow", "  Moon: Location not set\n")

    lines.append("\n")

    # Sun information
    if moon_observer_lat is not None and moon_observer_lon is not None:
        try:
            from celestron_nexstar.api.astronomy.solar_system import get_sun_info

            sun_info = get_sun_info(moon_observer_lat, moon_observer_lon, now)
            if sun_info:
                lines.append("Sun:\n")
                if sun_info.is_daytime:
                    _add_rich_line(lines, "green", "  Above horizon\n")
                    lines.append(f"  Alt: {sun_info.altitude_deg:5.1f}° ")
                    lines.append(f"Az: {sun_info.azimuth_deg:5.1f}°\n")
                    if sun_info.sunset_time:
                        # Convert to local time if needed
                        sunset_local = sun_info.sunset_time
                        if state.time_display_mode == "local":
                            sunset_local = sun_info.sunset_time.replace(tzinfo=UTC).astimezone()
                        lines.append(f"  Sunset: {sunset_local.strftime('%H:%M')}\n")
                else:
                    _add_rich_line(lines, "dim", "  Below horizon\n")
                    if sun_info.sunrise_time:
                        # Convert to local time if needed
                        sunrise_local = sun_info.sunrise_time
                        if state.time_display_mode == "local":
                            sunrise_local = sun_info.sunrise_time.replace(tzinfo=UTC).astimezone()
                        lines.append(f"  Sunrise: {sunrise_local.strftime('%H:%M')}\n")
            else:
                _add_rich_line(lines, "yellow", "  Sun: Calculation unavailable\n")
        except Exception as e:
            # Truncate error message to prevent scrolling
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            _add_rich_line(lines, "yellow", f"  Sun: {error_msg}\n")
    else:
        _add_rich_line(lines, "yellow", "  Sun: Location not set\n")

    lines.append("\n")

    # Weather information
    _add_rich_line(lines, "bold", "Weather:\n")
    weather_data = None
    weather_status = None
    weather_warning = None
    try:
        import asyncio

        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.api.location.weather import assess_observing_conditions, fetch_weather

        # Get location for weather
        weather_location = None
        try:
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                try:
                    telescope_location = telescope.get_location()
                    if (
                        telescope_location
                        and telescope_location.latitude != 0.0
                        and telescope_location.longitude != 0.0
                    ):
                        # Create ObserverLocation from telescope location
                        from celestron_nexstar.api.location.observer import ObserverLocation

                        weather_location = ObserverLocation(
                            latitude=telescope_location.latitude,
                            longitude=telescope_location.longitude,
                            elevation=0.0,  # GeographicLocation doesn't have elevation
                        )
                except Exception:
                    pass

            if weather_location is None:
                weather_location = get_observer_location()
        except Exception:
            weather_location = None

        if weather_location:
            # Try to get the current event loop
            try:
                _ = asyncio.get_running_loop()
                # If we're in an event loop, we can't use asyncio.run()
                # Return placeholder and let async version handle it
                _add_rich_line(lines, "yellow", "  Weather: Loading...\n")
                weather_data = None
            except RuntimeError:
                # No event loop running, safe to use asyncio.run()
                weather_data = asyncio.run(fetch_weather(weather_location))
                if weather_data:
                    weather_status, weather_warning = assess_observing_conditions(weather_data)
                else:
                    weather_status = None
                    weather_warning = None

            if weather_data:
                if weather_data.error:
                    _add_rich_line(lines, "yellow", f"  {weather_data.error}\n")
                else:
                    # Status indicator
                    if weather_status == "excellent":
                        status_color = "green"
                        status_icon = "✓"
                    elif weather_status == "good":
                        status_color = "cyan"
                        status_icon = "○"
                    elif weather_status == "fair":
                        status_color = "yellow"
                        status_icon = "⚠"
                    elif weather_status == "poor":
                        status_color = "red"
                        status_icon = "✗"
                    else:
                        status_color = "dim"
                        status_icon = "?"

                    if weather_status:
                        _add_rich_line(lines, status_color, f"  {status_icon} {weather_status.title()}\n")
                    if weather_warning:
                        lines.append(f"  {weather_warning}\n")

                    # Weather details
                    if weather_data.temperature_c is not None:
                        lines.append(f"  Temp: {weather_data.temperature_c:.1f}°C\n")
                    if weather_data.cloud_cover_percent is not None:
                        lines.append(f"  Clouds: {weather_data.cloud_cover_percent:.0f}%\n")
                    if weather_data.humidity_percent is not None:
                        lines.append(f"  Humidity: {weather_data.humidity_percent:.0f}%\n")
                    if weather_data.wind_speed_ms is not None:
                        wind_kmh = weather_data.wind_speed_ms * 3.6
                        lines.append(f"  Wind: {wind_kmh:.0f} km/h\n")
                    if weather_data.visibility_km is not None:
                        lines.append(f"  Visibility: {weather_data.visibility_km:.1f} km\n")
        else:
            _add_rich_line(lines, "yellow", "  Location not set\n")
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception("Error fetching weather")
        _add_rich_line(lines, "yellow", "  Weather unavailable\n")

    lines.append("\n")

    # Observing conditions summary with color-coded indicators
    lines.append("\n")
    _add_rich_line(lines, "bold", "Observing Quality:\n")

    # Get seeing score from observation planner
    seeing_score: float | None = None
    try:
        from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

        planner = ObservationPlanner()
        conditions = planner.get_tonight_conditions()
        seeing_score = conditions.seeing_score
    except Exception:
        pass

    # Display color-coded indicators
    if weather_data and not weather_data.error:
        # Cloud Cover indicator
        if weather_data.cloud_cover_percent is not None:
            cloud_score = _calculate_cloud_cover_score(weather_data.cloud_cover_percent)
            cloud_color = _get_indicator_color(cloud_score)
            lines.append("  Cloud Cover: ")
            _add_rich_line(lines, cloud_color, f"● {weather_data.cloud_cover_percent:.0f}%\n")

        # Seeing indicator
        if seeing_score is not None:
            seeing_color = _get_indicator_color(seeing_score)
            lines.append("  Seeing: ")
            _add_rich_line(lines, seeing_color, f"● {seeing_score:.0f}/100\n")

        # Wind indicator
        if weather_data.wind_speed_ms is not None:
            wind_mph = weather_data.wind_speed_ms  # Already in mph when units=imperial
            wind_score = _calculate_wind_score(wind_mph)
            wind_color = _get_indicator_color(wind_score)
            lines.append("  Wind: ")
            _add_rich_line(lines, wind_color, f"● {wind_mph:.1f} mph\n")

        # Humidity indicator
        if weather_data.humidity_percent is not None:
            humidity_score = _calculate_humidity_score(weather_data.humidity_percent)
            humidity_color = _get_indicator_color(humidity_score)
            lines.append("  Humidity: ")
            _add_rich_line(lines, humidity_color, f"● {weather_data.humidity_percent:.0f}%\n")
    else:
        _add_rich_line(lines, "yellow", "  Conditions: Unavailable\n")

    # Additional info
    try:
        from celestron_nexstar.api.core.enums import SkyBrightness
        from celestron_nexstar.api.observation.optics import calculate_limiting_magnitude, get_current_configuration

        config = get_current_configuration()
        if config:
            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
            lines.append(f"  Limiting Mag: {limiting_mag:.2f}\n")

            # Calculate dark sky hours remaining (if sun is below horizon)
            if sun_info and not sun_info.is_daytime and sun_info.sunrise_time:
                now_utc = datetime.now(UTC)
                if sun_info.sunrise_time > now_utc:
                    delta = sun_info.sunrise_time - now_utc
                    hours = delta.total_seconds() / 3600.0
                    lines.append(f"  Dark Hours: {hours:.1f}h\n")
    except Exception:
        pass

    # Light pollution information
    lines.append("  Light Pollution: ")
    try:
        from celestron_nexstar.api.location.light_pollution import BortleClass, get_light_pollution_data

        # Get location for light pollution (same logic as weather)
        lp_location = None
        try:
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                try:
                    telescope_location = telescope.get_location()
                    if (
                        telescope_location
                        and telescope_location.latitude != 0.0
                        and telescope_location.longitude != 0.0
                    ):
                        lp_location = (telescope_location.latitude, telescope_location.longitude)
                except Exception:
                    pass

            if lp_location is None:
                location = get_observer_location()
                if location:
                    lp_location = (location.latitude, location.longitude)
        except Exception:
            lp_location = None

        if lp_location:
            try:

                async def _get_light_data() -> Any:
                    from celestron_nexstar.api.database.models import get_db_session

                    async with get_db_session() as db_session:
                        return await get_light_pollution_data(db_session, lp_location[0], lp_location[1])

                # Try to get the current event loop
                try:
                    asyncio.get_running_loop()
                    # If we're in an event loop, we can't use asyncio.run()
                    # Skip light pollution data for now
                    lp_data = None
                except RuntimeError:
                    # No event loop running, safe to use asyncio.run()
                    lp_data = asyncio.run(_get_light_data())

                # Display Bortle class with color coding
                if lp_data is None:
                    _add_rich_line(lines, "yellow", "Loading...\n")
                else:
                    bortle = lp_data.bortle_class
                    if bortle <= BortleClass.CLASS_2:
                        bortle_color = "green"
                    elif bortle <= BortleClass.CLASS_4:
                        bortle_color = "cyan"
                    elif bortle <= BortleClass.CLASS_6:
                        bortle_color = "yellow"
                    else:
                        bortle_color = "red"

                    _add_rich_line(lines, bortle_color, f"Bortle {bortle.value}\n")
                    lines.append(f"    SQM: {lp_data.sqm_value:.2f} mag/arcsec²\n")
                    lines.append(f"    Naked Eye Limit: {lp_data.naked_eye_limiting_magnitude:.2f} mag\n")

                    # Show visibility indicators
                    visibility_parts = []
                    if lp_data.milky_way_visible:
                        visibility_parts.append("Milky Way")
                    if lp_data.airglow_visible:
                        visibility_parts.append("Airglow")
                    if lp_data.zodiacal_light_visible:
                        visibility_parts.append("Zodiacal Light")

                    if visibility_parts:
                        _add_rich_line(lines, "dim", f"    Visible: {', '.join(visibility_parts)}\n")

                    # Show source (cached or API)
                    if lp_data.cached:
                        _add_rich_line(lines, "dim", "    (cached)\n")
                    elif lp_data.source:
                        _add_rich_line(lines, "dim", f"    (source: {lp_data.source})\n")
            except Exception as e:
                logger.exception("Error fetching light pollution data")
                _add_rich_line(lines, "yellow", f"Error: {str(e)[:30]}...\n")
        else:
            _add_rich_line(lines, "yellow", "Location not set\n")
    except Exception:
        logger.exception("Error in light pollution display")
        _add_rich_line(lines, "yellow", "Unavailable\n")

    return "".join(lines)


def get_visible_objects_info() -> str:
    """
    Generate formatted text for the visible objects pane.

    Returns:
        Formatted text showing currently visible celestial objects
    """
    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    is_focused = state.focused_pane == "visible"

    lines: list[str] = []
    if is_focused:
        _add_rich_line(lines, "bold yellow", "▶ Currently Visible Objects\n")
    else:
        _add_rich_line(lines, "bold", "Currently Visible Objects\n")
    lines.append("─" * 40 + "\n")

    try:
        from celestron_nexstar.api.database.database import get_database
        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.api.observation.optics import get_current_configuration
        from celestron_nexstar.api.observation.visibility import filter_visible_objects

        # Get configuration
        config = get_current_configuration()

        # Get location (prefer telescope GPS, fall back to observer location)
        observer_lat = None
        observer_lon = None

        try:
            from celestron_nexstar.cli.utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                try:
                    telescope_location = telescope.get_location()
                    if (
                        telescope_location
                        and telescope_location.latitude != 0.0
                        and telescope_location.longitude != 0.0
                    ):
                        observer_lat = telescope_location.latitude
                        observer_lon = telescope_location.longitude
                except Exception:
                    pass
        except Exception:
            pass

        # Fall back to observer location if telescope doesn't have it
        if observer_lat is None or observer_lon is None:
            location = get_observer_location()
            if location:
                observer_lat = location.latitude
                observer_lon = location.longitude
            else:
                _add_rich_line(lines, "yellow", "Location not set.\n")
                lines.append("Use 'location set' to configure.\n")
                state.set_visible_objects([])
                return "".join(lines)

        # Get objects from database
        db = get_database()
        from celestron_nexstar.api.core.enums import SkyBrightness
        from celestron_nexstar.api.observation.optics import calculate_limiting_magnitude

        if config:
            max_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
        else:
            max_mag = 15.0

        import asyncio

        # Try to get the current event loop
        try:
            asyncio.get_running_loop()
            # If we're in an event loop, we can't use asyncio.run()
            # Return placeholder
            _add_rich_line(lines, "yellow", "Loading objects...\n")
            all_objects = []
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            all_objects = asyncio.run(db.filter_objects(max_magnitude=max_mag, limit=1000))

        # Filter visible objects (returns list of (object, visibility_info) tuples)
        visible = filter_visible_objects(
            all_objects,
            config=config,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            min_altitude_deg=20.0,  # Above 20 degrees
        )

        if not visible:
            _add_rich_line(lines, "yellow", "No visible objects found.\n")
            lines.append("Check location and time settings.\n")
            state.set_visible_objects([])
            return "".join(lines)

        # Apply filtering and sorting using API functions
        from celestron_nexstar.api.observation.filtering import filter_and_sort_objects

        visible_sorted = filter_and_sort_objects(
            visible,
            search_query=state.search_query,
            object_type=state.filter_type,
            magnitude_min=state.filter_mag_min,
            magnitude_max=state.filter_mag_max,
            constellation=state.filter_constellation,
            sort_by=state.sort_by,
            sort_reverse=state.sort_reverse,
            limit=50,
        )

        # Store in state
        state.set_visible_objects(visible_sorted[:50])

        # Show sorting/filtering info
        _add_rich_line(lines, "dim", f"Sort: {state.sort_by} ")
        if state.sort_reverse:
            _add_rich_line(lines, "dim", "↓ ")
        else:
            _add_rich_line(lines, "dim", "↑ ")
        if state.search_mode:
            if state.search_query:
                _add_rich_line(lines, "yellow", f"| Search: '{state.search_query[:15]}'")
            else:
                _add_rich_line(lines, "yellow", "| Search: (press '/' again to enter text)")
            _add_rich_line(lines, "dim", " Esc to cancel\n")
        elif state.search_query:
            _add_rich_line(lines, "dim", f"| Search: '{state.search_query[:15]}' ")
        if state.filter_type:
            _add_rich_line(lines, "dim", f"| Type: {state.filter_type} ")
        _add_rich_line(lines, "dim", "\n")
        lines.append("\n")

        # Show detail view at top if active
        if state.show_detail and state.focused_pane == "visible":
            selected = state.get_selected_object()
            if selected:
                from celestron_nexstar.cli.tui.detail import get_object_detail_text

                detail_text = get_object_detail_text(selected[0], selected[1])
                # Add detail text (already Rich markup string)
                lines.append(detail_text)
                lines.append("\n")

        # Display top 30 objects
        lines.append(f"Showing {min(30, len(visible_sorted))} of {len(visible_sorted)} objects\n")
        if not state.show_detail:
            _add_rich_line(lines, "dim", "Press '3' to focus, ↑↓ to navigate, Enter for details\n")
        lines.append("\n")

        for idx, (obj, visibility_info) in enumerate(visible_sorted[:30]):
            # Highlight selected item
            is_selected = idx == state.selected_index and state.focused_pane == "visible"
            if is_selected:
                _add_rich_line(lines, "bg:#444444", "> ")  # Selection marker
            else:
                lines.append("  ")

            # Object name
            name = obj.name[:18]
            if is_selected:
                _add_rich_line(lines, "bold underline", f"{name:18s} ")
            else:
                _add_rich_line(lines, "bold", f"{name:18s} ")

            # Altitude
            if visibility_info.altitude_deg is not None:
                alt_str = f"Alt:{visibility_info.altitude_deg:5.1f}°"
                if visibility_info.altitude_deg > 60:
                    color = "green"
                elif visibility_info.altitude_deg > 30:
                    color = "yellow"
                else:
                    color = "red"
                _add_rich_line(lines, color, alt_str)
            else:
                _add_rich_line(lines, "dim", "Alt: N/A")

            lines.append(" ")

            # Magnitude
            if visibility_info.magnitude is not None:
                _add_rich_line(lines, "cyan", f"Mag:{visibility_info.magnitude:5.2f}")
            else:
                _add_rich_line(lines, "dim", "Mag: N/A")

            lines.append("\n")

    except Exception as e:
        _add_rich_line(lines, "bold red", "Error\n")
        lines.append(f"Cannot load visible objects: {e}\n")
        state.set_visible_objects([])

    return "".join(lines)


def get_header_info() -> str:
    """
    Generate formatted text for the header bar.

    Returns:
        Formatted text for header showing connection status and title
    """
    lines: list[str] = []

    # Title
    _add_rich_line(lines, "bold cyan", "NexStar Telescope Dashboard")
    lines.append(" " * 20)

    # Connection status
    try:
        from celestron_nexstar.cli.utils.state import get_telescope

        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            _add_rich_line(lines, "bold green", "● Connected")
        else:
            _add_rich_line(lines, "bold red", "○ Disconnected")
    except Exception:
        _add_rich_line(lines, "bold yellow", "○ Unknown")

    # Time
    from datetime import UTC

    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    if state.time_display_mode == "utc":
        now = datetime.now(UTC)
        time_label = "UTC"
    else:
        now = datetime.now()
        time_label = "Local"

    lines.append(" " * 5)
    _add_rich_line(lines, "dim", f"{time_label} ")
    lines.append(now.strftime("%H:%M:%S"))

    return "".join(lines)


def get_status_info() -> str:
    """
    Generate formatted text for the status bar.

    Returns:
        Formatted text for status bar showing time, weather, GPS, and telescope position
    """
    import asyncio
    from datetime import datetime

    from celestron_nexstar.cli.tui.state import get_state

    state = get_state()
    lines: list[str] = []

    # Current time
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    _add_rich_line(lines, "bold cyan", f"Time: {time_str}")
    lines.append(" | ")

    # Weather (temperature and cloud cover)
    try:
        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.api.location.weather import fetch_weather

        location = get_observer_location()
        # Try to get the current event loop
        try:
            asyncio.get_running_loop()
            # If we're in an event loop, we can't use asyncio.run()
            # Skip weather for now
            weather = None
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            weather = asyncio.run(fetch_weather(location))

        if weather and weather.temperature_c is not None:
            # WeatherData.temperature_c is actually in Fahrenheit when units=imperial
            temp_str = f"{weather.temperature_c:.1f}°F"
            _add_rich_line(lines, "yellow", f"Temp: {temp_str}")
            lines.append(" | ")

        if weather and weather.cloud_cover_percent is not None:
            cloud_str = f"{weather.cloud_cover_percent:.0f}%"
            _add_rich_line(lines, "yellow", f"Clouds: {cloud_str}")
            lines.append(" | ")
    except Exception:
        pass  # Silently fail if weather unavailable

    # GPS coordinates
    try:
        from celestron_nexstar.api.location.observer import get_observer_location

        location = get_observer_location()
        gps_str = f"{location.latitude:.4f}, {location.longitude:.4f}"
        _add_rich_line(lines, "green", f"GPS: {gps_str}")
        lines.append(" | ")
    except Exception:
        pass  # Silently fail if location unavailable

    # Telescope position if connected
    try:
        from celestron_nexstar.cli.utils.state import get_telescope

        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            try:
                ra_dec = telescope.get_position_ra_dec()
                alt_az = telescope.get_position_alt_az()
                _add_rich_line(lines, "cyan", f"RA:{ra_dec.ra_hours:6.2f}h ")
                _add_rich_line(lines, "cyan", f"Dec:{ra_dec.dec_degrees:6.2f}° ")
                _add_rich_line(lines, "cyan", f"Alt:{alt_az.altitude:5.1f}° ")
                _add_rich_line(lines, "cyan", f"Az:{alt_az.azimuth:5.1f}° ")
                lines.append(" | ")
            except Exception:
                _add_rich_line(lines, "cyan", "Scope: Connected")
                lines.append(" | ")
    except Exception:
        pass  # Silently fail if telescope unavailable

    # Help text - context sensitive, single line
    if state.focused_pane == "visible":
        if state.search_mode:
            # Show search mode indicator
            if state.search_query:
                _add_rich_line(
                    lines,
                    "dim",
                    f"↑↓=nav Enter=detail s=sort r=reverse f=filter Search: '{state.search_query[:15]}' Esc=cancel",
                )
            else:
                _add_rich_line(
                    lines,
                    "dim",
                    "↑↓=nav Enter=detail s=sort r=reverse f=filter Search mode (press '/' to enter) Esc=cancel",
                )
        elif state.show_detail:
            _add_rich_line(lines, "dim", "↑↓=nav Enter/Esc=detail s=sort r=reverse f=filter /=search")
        else:
            _add_rich_line(lines, "dim", "↑↓=nav Enter=detail s=sort r=reverse f=filter /=search")
    elif state.focused_pane == "conditions":
        # Unique help for conditions pane
        _add_rich_line(lines, "dim", "q=quit r=refresh u=toggle UTC/Local l=location 1/2/3=focus")
    elif state.focused_pane == "dataset":
        # Help for dataset pane
        _add_rich_line(lines, "dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session 1/2/3=focus")
    else:
        # Default help text
        _add_rich_line(lines, "dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session u=time 1/2/3=focus")

    return "".join(lines)


# Textual Widget Classes


class HeaderBar(Static):
    """Header bar widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the header bar widget."""
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        """Start updating header."""
        self.set_interval(1.0, self.update_content)

    def update_content(self) -> None:
        """Update header content."""
        rich_markup = get_header_info()
        self.update(rich_markup)


class DatasetPane(Static):
    """Dataset information pane widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the dataset pane widget."""
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        """Start updating pane."""
        self.set_interval(2.0, self.update_content)
        self.update_content()

    def update_content(self) -> None:
        """Update pane content."""

        async def _update() -> None:
            rich_markup = await _get_dataset_info_async()
            self.update(rich_markup)

        self.run_worker(_update())


class ConditionsPane(Static):
    """Conditions information pane widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the conditions pane widget."""
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        """Start updating pane."""
        self.set_interval(2.0, self.update_content)
        self.update_content()

    def update_content(self) -> None:
        """Update pane content."""
        rich_markup = get_conditions_info()
        self.update(rich_markup)


class VisibleObjectsPane(Static):
    """Visible objects pane widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the visible objects pane widget."""
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        """Start updating pane."""
        self.set_interval(2.0, self.update_content)
        self.update_content()

    def update_content(self) -> None:
        """Update pane content."""
        rich_markup = get_visible_objects_info()
        self.update(rich_markup)


class StatusBar(Static):
    """Status bar widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the status bar widget."""
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        """Start updating status bar."""
        self.set_interval(1.0, self.update_content)

    def update_content(self) -> None:
        """Update status bar content."""
        rich_markup = get_status_info()
        self.update(rich_markup)
