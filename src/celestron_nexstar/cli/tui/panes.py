"""
Pane Content Generators

Functions to generate formatted text content for each pane in the TUI.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    pass


def _get_indicator_color(score: float) -> str:
    """
    Get color for condition indicator based on score (0-100).

    Args:
        score: Condition score from 0-100

    Returns:
        Color name for prompt_toolkit styling
    """
    if score >= 90:
        return "ansigreen"  # Great conditions (green)
    elif score >= 80:
        return "ansicyan"  # Good conditions (light green/cyan)
    elif score >= 50:
        return "ansiyellow"  # Marginal conditions (yellow)
    else:
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
    if 5.0 <= wind_mph <= 10.0:
        return 100.0
    elif wind_mph < 5.0:
        # Below 5 mph: score reduces linearly
        return wind_mph * 20.0  # 0-100 points
    elif wind_mph <= 15.0:
        # 10-15 mph: score reduces gradually
        return 100.0 - (wind_mph - 10.0) * 10.0  # 100-50 points
    elif wind_mph <= 20.0:
        # 15-20 mph: score reduces more sharply
        return 50.0 - (wind_mph - 15.0) * 10.0  # 50-0 points
    else:
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


def get_dataset_info() -> FormattedText:
    """
    Generate formatted text for the dataset information pane.

    Returns:
        Formatted text showing database statistics and catalog information
    """
    try:
        from ...api.database import get_database

        db = get_database()
        stats = db.get_stats()

        from .state import get_state

        state = get_state()
        is_focused = state.focused_pane == "dataset"

        lines: list[tuple[str, str]] = []
        if is_focused:
            lines.append(("bold yellow", "▶ Database Statistics\n"))
        else:
            lines.append(("bold", "Database Statistics\n"))
        lines.append(("", "─" * 30 + "\n"))
        lines.append(("", f"Total Objects: {stats.total_objects:,}\n"))
        lines.append(("", f"Catalogs: {len(stats.objects_by_catalog)}\n"))
        lines.append(("", f"Types: {len(stats.objects_by_type)}\n"))
        lines.append(("", "\n"))

        # Magnitude range
        if stats.magnitude_range[0] is not None and stats.magnitude_range[1] is not None:
            lines.append(("", "Magnitude Range:\n"))
            lines.append(("cyan", f"  {stats.magnitude_range[0]:.1f} to {stats.magnitude_range[1]:.1f}\n"))
            lines.append(("", "\n"))

        # Top catalogs
        lines.append(("bold", "Top Catalogs:\n"))
        sorted_catalogs = sorted(stats.objects_by_catalog.items(), key=lambda x: x[1], reverse=True)[:5]
        for catalog, count in sorted_catalogs:
            lines.append(("", f"  {catalog:15s} "))
            lines.append(("cyan", f"{count:6,}\n"))

        lines.append(("", "\n"))

        # Top object types
        lines.append(("bold", "Object Types:\n"))
        sorted_types = sorted(stats.objects_by_type.items(), key=lambda x: x[1], reverse=True)[:5]
        for obj_type, count in sorted_types:
            lines.append(("", f"  {obj_type:15s} "))
            lines.append(("yellow", f"{count:6,}\n"))

        lines.append(("", "\n"))
        lines.append(("", "─" * 30 + "\n"))
        lines.append(("bold", "Telescope Configuration\n"))
        lines.append(("", "\n"))

        # Get optical configuration
        try:
            from ...api.optics import get_current_configuration

            config = get_current_configuration()
            lines.append(("", "Telescope:\n"))
            lines.append(("cyan", f"  {config.telescope.display_name}\n"))
            lines.append(
                ("", f'  Aperture: {config.telescope.aperture_mm:.0f}mm ({config.telescope.aperture_inches:.1f}")\n')
            )
            lines.append(("", f"  Focal Length: {config.telescope.focal_length_mm:.0f}mm\n"))
            lines.append(("", f"  f-ratio: f/{config.telescope.focal_ratio:.1f}\n"))
            lines.append(("", "\n"))

            lines.append(("", "Eyepiece:\n"))
            eyepiece_name = config.eyepiece.name or f"{config.eyepiece.focal_length_mm:.0f}mm"
            lines.append(("cyan", f"  {eyepiece_name}\n"))
            lines.append(("", f"  Focal Length: {config.eyepiece.focal_length_mm:.0f}mm\n"))
            lines.append(("", f"  Apparent FOV: {config.eyepiece.apparent_fov_deg:.0f}°\n"))
            lines.append(("", "\n"))

            lines.append(("", "Configuration:\n"))
            lines.append(("", f"  Magnification: {config.magnification:.0f}x\n"))
            lines.append(("", f"  Exit Pupil: {config.exit_pupil_mm:.2f}mm\n"))
            lines.append(("", f"  True FOV: {config.true_fov_arcmin:.1f}' ({config.true_fov_deg:.2f}°)\n"))
            lines.append(("", "\n"))

            # Limiting magnitude
            from ...api.enums import SkyBrightness
            from ...api.optics import calculate_limiting_magnitude

            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
            lines.append(("", "Limiting Mag: "))
            lines.append(("yellow", f"{limiting_mag:.1f}\n"))
            lines.append(("", "\n"))

        except Exception as e:
            lines.append(("yellow", f"Config: Error ({e})\n"))

        # Telescope Status (if connected)
        lines.append(("", "─" * 30 + "\n"))
        lines.append(("bold", "Telescope Status\n"))
        lines.append(("", "\n"))

        try:
            from ..utils.state import get_telescope

            telescope = get_telescope()
            if telescope and telescope.protocol and telescope.protocol.is_open():
                # Connection status
                lines.append(("green", "  Connected\n"))
                lines.append(("", "\n"))

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

                    lines.append(("", "Position (RA/Dec):\n"))
                    lines.append(("cyan", f"  RA:  {ra_h:02d}h {ra_m:02d}m {ra_s:02d}s\n"))
                    lines.append(("cyan", f"  Dec: {abs(dec_d):02d}° {dec_m:02d}' {dec_s:02d}\" {dec_dir}\n"))
                    lines.append(("", "\n"))

                    lines.append(("", "Position (Alt/Az):\n"))
                    lines.append(("cyan", f"  Alt: {alt_az.altitude:5.1f}°\n"))
                    lines.append(("cyan", f"  Az:  {alt_az.azimuth:5.1f}°\n"))
                    lines.append(("", "\n"))

                except Exception:
                    lines.append(("yellow", "  Position: Unavailable\n"))
                    lines.append(("", "\n"))

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
                    lines.append(("", "Tracking: "))
                    lines.append(("cyan", f"{tracking_name}\n"))
                except Exception:
                    lines.append(("yellow", "  Tracking: Unknown\n"))

            else:
                lines.append(("dim", "  Not connected\n"))
                lines.append(("dim", "  Press 'c' to connect\n"))

        except Exception as e:
            lines.append(("yellow", f"Status: Error ({str(e)[:30]})\n"))

        # Session Information
        lines.append(("", "\n"))
        lines.append(("", "─" * 30 + "\n"))
        lines.append(("bold", "Session\n"))
        lines.append(("", "\n"))

        try:
            from .state import get_state

            state = get_state()
            if state.session_start_time is None:
                lines.append(("dim", "  Not started\n"))
                lines.append(("dim", "  Press 's' to start\n"))
            else:
                duration = state.get_session_duration()
                if duration is not None:
                    hours = int(duration)
                    minutes = int((duration - hours) * 60)
                    lines.append(("", f"  Duration: {hours}h {minutes}m\n"))
                lines.append(("", f"  Observed: {len(state.observed_objects)}\n"))
                if state.observed_objects:
                    # Show last 3 observed objects
                    for obj_name in state.observed_objects[-3:]:
                        lines.append(("dim", f"    • {obj_name[:25]}\n"))

        except Exception:
            lines.append(("yellow", "  Session: Error\n"))

        lines.append(("", "\n"))
        lines.append(("dim", "Press 't'=telescope 'e'=eyepiece\n"))

        return FormattedText(lines)

    except Exception as e:
        return FormattedText(
            [
                ("bold red", "Database Error\n"),
                ("", f"Cannot load database: {e}\n"),
            ]
        )


def get_conditions_info() -> FormattedText:
    """
    Generate formatted text for the current conditions pane.

    Returns:
        Formatted text showing weather, sky conditions, and time information
    """
    from .state import get_state

    state = get_state()
    is_focused = state.focused_pane == "conditions"

    lines: list[tuple[str, str]] = []
    if is_focused:
        lines.append(("bold yellow", "▶ Observing Conditions\n"))
    else:
        lines.append(("bold", "Observing Conditions\n"))
    lines.append(("", "─" * 30 + "\n"))

    # Location
    try:
        from ...api.observer import get_observer_location
        from ..utils.state import get_telescope

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
                    lines.append(("", "Location:\n"))
                    lines.append(("cyan", f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n"))
                    lines.append(("dim", "  (from telescope GPS)\n"))
            except Exception:
                # Fall back to observer location
                location = get_observer_location()
                if location:
                    lat = location.latitude
                    lon = location.longitude
                    lat_dir = "N" if lat >= 0 else "S"
                    lon_dir = "E" if lon >= 0 else "W"
                    lines.append(("", "Location:\n"))
                    if location.name:
                        lines.append(("cyan", f"  {location.name}\n"))
                    lines.append(("", f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n"))
                else:
                    lines.append(("yellow", "Location: Not set\n"))
        else:
            # No telescope, use observer location
            location = get_observer_location()
            if location:
                lat = location.latitude
                lon = location.longitude
                lat_dir = "N" if lat >= 0 else "S"
                lon_dir = "E" if lon >= 0 else "W"
                lines.append(("", "Location:\n"))
                if location.name:
                    lines.append(("cyan", f"  {location.name}\n"))
                lines.append(("", f"  {abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}\n"))
            else:
                lines.append(("yellow", "Location: Not set\n"))
    except Exception as e:
        lines.append(("yellow", f"Location: Error ({e})\n"))

    lines.append(("", "\n"))

    # Time information
    from datetime import UTC

    from .state import get_state

    state = get_state()
    if state.time_display_mode == "utc":
        now = datetime.now(UTC)
        time_label = "UTC"
    else:
        now = datetime.now()
        time_label = "Local"

    lines.append(("", "Time:\n"))
    lines.append(("cyan", f"  {time_label}: {now.strftime('%H:%M:%S')}\n"))
    lines.append(("cyan", f"  Date:  {now.strftime('%Y-%m-%d')}\n"))
    lines.append(("dim", "  Press 'u' to toggle UTC/Local\n"))
    lines.append(("", "\n"))

    # Sky conditions
    lines.append(("bold", "Sky Conditions:\n"))

    # Get observer location for moon/sun calculations
    moon_observer_lat = None
    moon_observer_lon = None
    try:
        from ...api.observer import get_observer_location
        from ..utils.state import get_telescope

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
            from ...api.solar_system import get_moon_info

            moon_info = get_moon_info(moon_observer_lat, moon_observer_lon, now)
            if moon_info:
                lines.append(("", "Moon:\n"))
                lines.append(("cyan", f"  Phase: {moon_info.phase_name}\n"))
                lines.append(("", f"  Illumination: {moon_info.illumination * 100:.0f}%\n"))
                if moon_info.altitude_deg > 0:
                    lines.append(("", f"  Alt: {moon_info.altitude_deg:5.1f}° "))
                    lines.append(("", f"Az: {moon_info.azimuth_deg:5.1f}°\n"))
                else:
                    lines.append(("dim", "  Below horizon\n"))
            else:
                lines.append(("yellow", "  Moon: Calculation unavailable\n"))
        except Exception as e:
            # Truncate error message to prevent scrolling
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            lines.append(("yellow", f"  Moon: {error_msg}\n"))
    else:
        lines.append(("yellow", "  Moon: Location not set\n"))

    lines.append(("", "\n"))

    # Sun information
    if moon_observer_lat is not None and moon_observer_lon is not None:
        try:
            from ...api.solar_system import get_sun_info

            sun_info = get_sun_info(moon_observer_lat, moon_observer_lon, now)
            if sun_info:
                lines.append(("", "Sun:\n"))
                if sun_info.is_daytime:
                    lines.append(("green", "  Above horizon\n"))
                    lines.append(("", f"  Alt: {sun_info.altitude_deg:5.1f}° "))
                    lines.append(("", f"Az: {sun_info.azimuth_deg:5.1f}°\n"))
                    if sun_info.sunset_time:
                        # Convert to local time if needed
                        sunset_local = sun_info.sunset_time
                        if state.time_display_mode == "local":
                            sunset_local = sun_info.sunset_time.replace(tzinfo=UTC).astimezone()
                        lines.append(("", f"  Sunset: {sunset_local.strftime('%H:%M')}\n"))
                else:
                    lines.append(("dim", "  Below horizon\n"))
                    if sun_info.sunrise_time:
                        # Convert to local time if needed
                        sunrise_local = sun_info.sunrise_time
                        if state.time_display_mode == "local":
                            sunrise_local = sun_info.sunrise_time.replace(tzinfo=UTC).astimezone()
                        lines.append(("", f"  Sunrise: {sunrise_local.strftime('%H:%M')}\n"))
            else:
                lines.append(("yellow", "  Sun: Calculation unavailable\n"))
        except Exception as e:
            # Truncate error message to prevent scrolling
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            lines.append(("yellow", f"  Sun: {error_msg}\n"))
    else:
        lines.append(("yellow", "  Sun: Location not set\n"))

    lines.append(("", "\n"))

    # Weather information
    lines.append(("bold", "Weather:\n"))
    weather_data = None
    weather_status = None
    weather_warning = None
    try:
        import asyncio

        from ...api.observer import get_observer_location
        from ...api.weather import assess_observing_conditions, fetch_weather

        # Get location for weather
        weather_location = None
        try:
            from ..utils.state import get_telescope

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
                        from ...api.observer import ObserverLocation

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
            weather_data = asyncio.run(fetch_weather(weather_location))
            weather_status, weather_warning = assess_observing_conditions(weather_data)

            if weather_data.error:
                lines.append(("yellow", f"  {weather_data.error}\n"))
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

                lines.append((status_color, f"  {status_icon} {weather_status.title()}\n"))
                lines.append(("", f"  {weather_warning}\n"))

                # Weather details
                if weather_data.temperature_c is not None:
                    lines.append(("", f"  Temp: {weather_data.temperature_c:.1f}°C\n"))
                if weather_data.cloud_cover_percent is not None:
                    lines.append(("", f"  Clouds: {weather_data.cloud_cover_percent:.0f}%\n"))
                if weather_data.humidity_percent is not None:
                    lines.append(("", f"  Humidity: {weather_data.humidity_percent:.0f}%\n"))
                if weather_data.wind_speed_ms is not None:
                    wind_kmh = weather_data.wind_speed_ms * 3.6
                    lines.append(("", f"  Wind: {wind_kmh:.0f} km/h\n"))
                if weather_data.visibility_km is not None:
                    lines.append(("", f"  Visibility: {weather_data.visibility_km:.1f} km\n"))
        else:
            lines.append(("yellow", "  Location not set\n"))
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception("Error fetching weather")
        lines.append(("yellow", "  Weather unavailable\n"))

    lines.append(("", "\n"))

    # Observing conditions summary with color-coded indicators
    lines.append(("", "\n"))
    lines.append(("bold", "Observing Quality:\n"))

    # Get seeing score from observation planner
    seeing_score: float | None = None
    try:
        from ...api.observation_planner import ObservationPlanner

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
            lines.append(("", "  Cloud Cover: "))
            lines.append((cloud_color, f"● {weather_data.cloud_cover_percent:.0f}%\n"))

        # Seeing indicator
        if seeing_score is not None:
            seeing_color = _get_indicator_color(seeing_score)
            lines.append(("", "  Seeing: "))
            lines.append((seeing_color, f"● {seeing_score:.0f}/100\n"))

        # Wind indicator
        if weather_data.wind_speed_ms is not None:
            wind_mph = weather_data.wind_speed_ms  # Already in mph when units=imperial
            wind_score = _calculate_wind_score(wind_mph)
            wind_color = _get_indicator_color(wind_score)
            lines.append(("", "  Wind: "))
            lines.append((wind_color, f"● {wind_mph:.1f} mph\n"))

        # Humidity indicator
        if weather_data.humidity_percent is not None:
            humidity_score = _calculate_humidity_score(weather_data.humidity_percent)
            humidity_color = _get_indicator_color(humidity_score)
            lines.append(("", "  Humidity: "))
            lines.append((humidity_color, f"● {weather_data.humidity_percent:.0f}%\n"))
    else:
        lines.append(("yellow", "  Conditions: Unavailable\n"))

    # Additional info
    try:
        from ...api.enums import SkyBrightness
        from ...api.optics import calculate_limiting_magnitude, get_current_configuration

        config = get_current_configuration()
        if config:
            limiting_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
            lines.append(("", f"  Limiting Mag: {limiting_mag:.1f}\n"))

            # Calculate dark sky hours remaining (if sun is below horizon)
            if sun_info and not sun_info.is_daytime and sun_info.sunrise_time:
                now_utc = datetime.now(UTC)
                if sun_info.sunrise_time > now_utc:
                    delta = sun_info.sunrise_time - now_utc
                    hours = delta.total_seconds() / 3600.0
                    lines.append(("", f"  Dark Hours: {hours:.1f}h\n"))
    except Exception:
        pass

    # Light pollution information
    lines.append(("", "  Light Pollution: "))
    try:
        from ...api.light_pollution import BortleClass, get_light_pollution_data

        # Get location for light pollution (same logic as weather)
        lp_location = None
        try:
            from ..utils.state import get_telescope

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
                lp_data = asyncio.run(get_light_pollution_data(lp_location[0], lp_location[1]))

                # Display Bortle class with color coding
                bortle = lp_data.bortle_class
                if bortle <= BortleClass.CLASS_2:
                    bortle_color = "green"
                elif bortle <= BortleClass.CLASS_4:
                    bortle_color = "cyan"
                elif bortle <= BortleClass.CLASS_6:
                    bortle_color = "yellow"
                else:
                    bortle_color = "red"

                lines.append((bortle_color, f"Bortle {bortle.value}\n"))
                lines.append(("", f"    SQM: {lp_data.sqm_value:.2f} mag/arcsec²\n"))
                lines.append(("", f"    Naked Eye Limit: {lp_data.naked_eye_limiting_magnitude:.1f} mag\n"))

                # Show visibility indicators
                visibility_parts = []
                if lp_data.milky_way_visible:
                    visibility_parts.append("Milky Way")
                if lp_data.airglow_visible:
                    visibility_parts.append("Airglow")
                if lp_data.zodiacal_light_visible:
                    visibility_parts.append("Zodiacal Light")

                if visibility_parts:
                    lines.append(("dim", f"    Visible: {', '.join(visibility_parts)}\n"))

                # Show source (cached or API)
                if lp_data.cached:
                    lines.append(("dim", "    (cached)\n"))
                elif lp_data.source:
                    lines.append(("dim", f"    (source: {lp_data.source})\n"))
            except Exception as e:
                logger.exception("Error fetching light pollution data")
                lines.append(("yellow", f"Error: {str(e)[:30]}...\n"))
        else:
            lines.append(("yellow", "Location not set\n"))
    except Exception:
        logger.exception("Error in light pollution display")
        lines.append(("yellow", "Unavailable\n"))

    return FormattedText(lines)


def get_visible_objects_info() -> FormattedText:
    """
    Generate formatted text for the visible objects pane.

    Returns:
        Formatted text showing currently visible celestial objects
    """
    from .state import get_state

    state = get_state()
    is_focused = state.focused_pane == "visible"

    lines: list[tuple[str, str]] = []
    if is_focused:
        lines.append(("bold yellow", "▶ Currently Visible Objects\n"))
    else:
        lines.append(("bold", "Currently Visible Objects\n"))
    lines.append(("", "─" * 40 + "\n"))

    try:
        from ...api.database import get_database
        from ...api.observer import get_observer_location
        from ...api.optics import get_current_configuration
        from ...api.visibility import filter_visible_objects

        # Get configuration
        config = get_current_configuration()

        # Get location (prefer telescope GPS, fall back to observer location)
        observer_lat = None
        observer_lon = None

        try:
            from ..utils.state import get_telescope

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
                lines.append(("yellow", "Location not set.\n"))
                lines.append(("", "Use 'location set' to configure.\n"))
                state.set_visible_objects([])
                return FormattedText(lines)

        # Get objects from database
        db = get_database()
        from ...api.enums import SkyBrightness
        from ...api.optics import calculate_limiting_magnitude

        if config:
            max_mag = calculate_limiting_magnitude(
                config.telescope.effective_aperture_mm,
                sky_brightness=SkyBrightness.GOOD,
                exit_pupil_mm=config.exit_pupil_mm,
            )
        else:
            max_mag = 15.0

        all_objects = db.filter_objects(max_magnitude=max_mag, limit=1000)

        # Filter visible objects (returns list of (object, visibility_info) tuples)
        visible = filter_visible_objects(
            all_objects,
            config=config,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            min_altitude_deg=20.0,  # Above 20 degrees
        )

        if not visible:
            lines.append(("yellow", "No visible objects found.\n"))
            lines.append(("", "Check location and time settings.\n"))
            state.set_visible_objects([])
            return FormattedText(lines)

        # Apply search filter if active
        if state.search_query:
            search_lower = state.search_query.lower()
            visible = [
                (obj, vis_info)
                for obj, vis_info in visible
                if search_lower in obj.name.lower() or (obj.common_name and search_lower in obj.common_name.lower())
            ]

        # Apply type filter if active
        if state.filter_type:
            visible = [(obj, vis_info) for obj, vis_info in visible if obj.object_type.value == state.filter_type]

        # Apply magnitude filter if active
        if state.filter_mag_min is not None:
            visible = [
                (obj, vis_info)
                for obj, vis_info in visible
                if obj.magnitude is not None and obj.magnitude >= state.filter_mag_min
            ]
        if state.filter_mag_max is not None:
            visible = [
                (obj, vis_info)
                for obj, vis_info in visible
                if obj.magnitude is not None and obj.magnitude <= state.filter_mag_max
            ]

        # Apply sorting
        from ...api.catalogs import CelestialObject
        from ...api.visibility import VisibilityInfo

        def sort_key(item: tuple[CelestialObject, VisibilityInfo]) -> tuple[float | str, ...]:
            obj, vis_info = item
            if state.sort_by == "altitude":
                return (vis_info.altitude_deg or -999,)
            elif state.sort_by == "magnitude":
                mag = obj.magnitude if obj.magnitude is not None else 999
                return (mag,)
            elif state.sort_by == "name":
                return (obj.name.lower(),)
            elif state.sort_by == "type":
                return (obj.object_type.value, obj.name.lower())
            return (0,)

        visible_sorted = sorted(visible, key=sort_key, reverse=state.sort_reverse)

        # Store in state
        state.set_visible_objects(visible_sorted[:50])

        # Show sorting/filtering info
        lines.append(("dim", f"Sort: {state.sort_by} "))
        if state.sort_reverse:
            lines.append(("dim", "↓ "))
        else:
            lines.append(("dim", "↑ "))
        if state.search_mode:
            if state.search_query:
                lines.append(("yellow", f"| Search: '{state.search_query[:15]}'"))
            else:
                lines.append(("yellow", "| Search: (press '/' again to enter text)"))
            lines.append(("dim", " Esc to cancel\n"))
        elif state.search_query:
            lines.append(("dim", f"| Search: '{state.search_query[:15]}' "))
        if state.filter_type:
            lines.append(("dim", f"| Type: {state.filter_type} "))
        lines.append(("dim", "\n"))
        lines.append(("", "\n"))

        # Show detail view at top if active
        if state.show_detail and state.focused_pane == "visible":
            selected = state.get_selected_object()
            if selected:
                from .detail import get_object_detail_text

                detail_text = get_object_detail_text(selected[0], selected[1])
                # Add detail lines to output
                # FormattedText is a list of tuples, convert to list of lines
                detail_lines_list = list(detail_text)
                for line in detail_lines_list:
                    # Ensure line is a tuple[str, str] (ignore mouse handlers if present)
                    if isinstance(line, tuple) and len(line) >= 2:
                        lines.append((line[0], line[1]))
                lines.append(("", "\n"))

        # Display top 30 objects
        lines.append(("", f"Showing {min(30, len(visible_sorted))} of {len(visible_sorted)} objects\n"))
        if not state.show_detail:
            lines.append(("dim", "Press '3' to focus, ↑↓ to navigate, Enter for details\n"))
        lines.append(("", "\n"))

        for idx, (obj, visibility_info) in enumerate(visible_sorted[:30]):
            # Highlight selected item
            is_selected = idx == state.selected_index and state.focused_pane == "visible"
            if is_selected:
                lines.append(("bg:#444444", "> "))  # Selection marker
            else:
                lines.append(("", "  "))

            # Object name
            name = obj.name[:18]
            if is_selected:
                lines.append(("bold underline", f"{name:18s} "))
            else:
                lines.append(("bold", f"{name:18s} "))

            # Altitude
            if visibility_info.altitude_deg is not None:
                alt_str = f"Alt:{visibility_info.altitude_deg:5.1f}°"
                if visibility_info.altitude_deg > 60:
                    color = "green"
                elif visibility_info.altitude_deg > 30:
                    color = "yellow"
                else:
                    color = "red"
                lines.append((color, alt_str))
            else:
                lines.append(("dim", "Alt: N/A"))

            lines.append(("", " "))

            # Magnitude
            if visibility_info.magnitude is not None:
                lines.append(("cyan", f"Mag:{visibility_info.magnitude:5.1f}"))
            else:
                lines.append(("dim", "Mag: N/A"))

            lines.append(("", "\n"))

    except Exception as e:
        lines.append(("bold red", "Error\n"))
        lines.append(("", f"Cannot load visible objects: {e}\n"))
        state.set_visible_objects([])

    return FormattedText(lines)


def get_header_info() -> FormattedText:
    """
    Generate formatted text for the header bar.

    Returns:
        Formatted text for header showing connection status and title
    """
    lines: list[tuple[str, str]] = []

    # Title
    lines.append(("bold cyan", "NexStar Telescope Dashboard"))
    lines.append(("", " " * 20))

    # Connection status
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            lines.append(("bold green", "● Connected"))
        else:
            lines.append(("bold red", "○ Disconnected"))
    except Exception:
        lines.append(("bold yellow", "○ Unknown"))

    # Time
    from datetime import UTC

    from .state import get_state

    state = get_state()
    if state.time_display_mode == "utc":
        now = datetime.now(UTC)
        time_label = "UTC"
    else:
        now = datetime.now()
        time_label = "Local"

    lines.append(("", " " * 5))
    lines.append(("dim", f"{time_label} "))
    lines.append(("", now.strftime("%H:%M:%S")))

    return FormattedText(lines)


def get_status_info() -> FormattedText:
    """
    Generate formatted text for the status bar.

    Returns:
        Formatted text for status bar showing position, tracking info, and help
    """
    from .state import get_state

    state = get_state()
    lines: list[tuple[str, str]] = []

    # Telescope position if connected
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            try:
                ra_dec = telescope.get_position_ra_dec()
                alt_az = telescope.get_position_alt_az()
                lines.append(("cyan", f"RA:{ra_dec.ra_hours:6.2f}h "))
                lines.append(("cyan", f"Dec:{ra_dec.dec_degrees:6.2f}° "))
                lines.append(("cyan", f"Alt:{alt_az.altitude:5.1f}° "))
                lines.append(("cyan", f"Az:{alt_az.azimuth:5.1f}° "))
                lines.append(("", " | "))
            except Exception:
                pass
    except Exception:
        pass

    # Help text - context sensitive, single line
    if state.focused_pane == "visible":
        if state.search_mode:
            # Show search mode indicator
            if state.search_query:
                lines.append(
                    (
                        "dim",
                        f"↑↓=nav Enter=detail s=sort r=reverse f=filter Search: '{state.search_query[:15]}' Esc=cancel",
                    )
                )
            else:
                lines.append(
                    ("dim", "↑↓=nav Enter=detail s=sort r=reverse f=filter Search mode (press '/' to enter) Esc=cancel")
                )
        elif state.show_detail:
            lines.append(("dim", "↑↓=nav Enter/Esc=detail s=sort r=reverse f=filter /=search"))
        else:
            lines.append(("dim", "↑↓=nav Enter=detail s=sort r=reverse f=filter /=search"))
    elif state.focused_pane == "conditions":
        # Unique help for conditions pane
        lines.append(("dim", "q=quit r=refresh u=toggle UTC/Local l=location 1/2/3=focus"))
    elif state.focused_pane == "dataset":
        # Help for dataset pane
        lines.append(("dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session 1/2/3=focus"))
    else:
        # Default help text
        lines.append(("dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session u=time 1/2/3=focus"))

    return FormattedText(lines)
