"""
Pane Content Generators

Functions to generate formatted text content for each pane in the TUI.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText


if TYPE_CHECKING:
    pass


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

    # Observing conditions summary
    lines.append(("", "\n"))
    lines.append(("bold", "Observing Quality:\n"))

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

    lines.append(("yellow", "  Weather: Not available\n"))
    lines.append(("yellow", "  Light Pollution: Not available\n"))

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
        def sort_key(item: tuple) -> tuple:
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
                for line in detail_text:
                    lines.append(line)
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
                lines.append(("dim", f"↑↓=nav Enter=detail s=sort r=reverse f=filter Search: '{state.search_query[:15]}' Esc=cancel"))
            else:
                lines.append(("dim", "↑↓=nav Enter=detail s=sort r=reverse f=filter Search mode (press '/' to enter) Esc=cancel"))
        elif state.show_detail:
            lines.append(("dim", "↑↓=nav Enter/Esc=detail s=sort r=reverse f=filter /=search"))
        else:
            lines.append(("dim", "↑↓=nav Enter=detail s=sort r=reverse f=filter /=search"))
    elif state.focused_pane == "conditions":
        # Unique help for conditions pane
        lines.append(("dim", "q=quit r=refresh u=toggle UTC/Local time 1/2/3=focus"))
    elif state.focused_pane == "dataset":
        # Help for dataset pane
        lines.append(("dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session 1/2/3=focus"))
    else:
        # Default help text
        lines.append(("dim", "q=quit r=refresh t=telescope e=eyepiece c=connect s=session u=time 1/2/3=focus"))

    return FormattedText(lines)
