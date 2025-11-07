"""
Pane Content Generators

Functions to generate formatted text content for each pane in the TUI.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText

if TYPE_CHECKING:
    from collections.abc import Callable


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

        lines: list[tuple[str, str]] = [
            ("bold", "Database Statistics\n"),
            ("", "─" * 30 + "\n"),
            ("", f"Total Objects: {stats.total_objects:,}\n"),
            ("", f"Catalogs: {len(stats.objects_by_catalog)}\n"),
            ("", f"Types: {len(stats.objects_by_type)}\n"),
            ("", "\n"),
        ]

        # Magnitude range
        if stats.magnitude_range[0] is not None and stats.magnitude_range[1] is not None:
            lines.append(("", f"Magnitude Range:\n"))
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

        return FormattedText(lines)

    except Exception as e:
        return FormattedText([
            ("bold red", "Database Error\n"),
            ("", f"Cannot load database: {e}\n"),
        ])


def get_conditions_info() -> FormattedText:
    """
    Generate formatted text for the current conditions pane.

    Returns:
        Formatted text showing weather, sky conditions, and time information
    """
    lines: list[tuple[str, str]] = [
        ("bold", "Observing Conditions\n"),
        ("", "─" * 30 + "\n"),
    ]

    # Location
    try:
        from ...api.observer import get_observer_location

        location = get_observer_location()
        if location:
            lines.append(("", f"Location:\n"))
            lines.append(("cyan", f"  {location.name or 'Unnamed'}\n"))
            lines.append(("", f"  {location.latitude_deg:.4f}°N, {abs(location.longitude_deg):.4f}°W\n"))
        else:
            lines.append(("yellow", "Location: Not set\n"))
    except Exception:
        lines.append(("yellow", "Location: Not set\n"))

    lines.append(("", "\n"))

    # Time information
    now = datetime.now()
    lines.append(("", "Time:\n"))
    lines.append(("cyan", f"  Local: {now.strftime('%H:%M:%S')}\n"))
    lines.append(("cyan", f"  Date:  {now.strftime('%Y-%m-%d')}\n"))
    lines.append(("", "\n"))

    # Sky conditions (placeholder for now)
    lines.append(("bold", "Sky Conditions:\n"))
    lines.append(("yellow", "  Weather: Not available\n"))
    lines.append(("yellow", "  Light Pollution: Not available\n"))
    lines.append(("yellow", "  Moon Phase: Not available\n"))

    return FormattedText(lines)


def get_visible_objects_info() -> FormattedText:
    """
    Generate formatted text for the visible objects pane.

    Returns:
        Formatted text showing currently visible celestial objects
    """
    lines: list[tuple[str, str]] = [
        ("bold", "Currently Visible Objects\n"),
        ("", "─" * 40 + "\n"),
    ]

    try:
        from ...api.database import get_database
        from ...api.observer import get_observer_location
        from ...api.optics import get_current_configuration
        from ...api.visibility import filter_visible_objects

        # Get configuration
        location = get_observer_location()
        config = get_current_configuration()

        if not location:
            lines.append(("yellow", "Location not set.\n"))
            lines.append(("", "Use 'location set' to configure.\n"))
            return FormattedText(lines)

        # Get objects from database
        db = get_database()
        if config:
            max_mag = config.limiting_magnitude if hasattr(config, "limiting_magnitude") else 15.0
        else:
            max_mag = 15.0

        all_objects = db.filter_objects(max_magnitude=max_mag, limit=1000)

        # Filter visible objects (returns list of (object, visibility_info) tuples)
        visible = filter_visible_objects(
            all_objects,
            config=config,
            observer_lat=location.latitude_deg,
            observer_lon=location.longitude_deg,
            min_altitude_deg=20.0,  # Above 20 degrees
        )

        if not visible:
            lines.append(("yellow", "No visible objects found.\n"))
            lines.append(("", "Check location and time settings.\n"))
            return FormattedText(lines)

        # Already sorted by observability score, but we can sort by altitude for display
        visible_sorted = sorted(visible, key=lambda x: x[1].altitude_deg or 0, reverse=True)

        # Display top 30 objects
        lines.append(("", f"Showing {min(30, len(visible_sorted))} of {len(visible_sorted)} objects\n"))
        lines.append(("", "\n"))

        for obj, visibility_info in visible_sorted[:30]:
            # Object name
            name = obj.name[:18]
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
    now = datetime.now()
    lines.append(("", " " * 5))
    lines.append(("", now.strftime("%H:%M:%S")))

    return FormattedText(lines)


def get_status_info() -> FormattedText:
    """
    Generate formatted text for the status bar.

    Returns:
        Formatted text for status bar showing position and tracking info
    """
    lines: list[tuple[str, str]] = []

    # Position (if available)
    try:
        from ..utils.state import get_telescope

        telescope = get_telescope()
        if telescope and telescope.protocol and telescope.protocol.is_open():
            pos = telescope.get_position_ra_dec()
            if pos:
                ra_h = int(pos.ra_hours)
                ra_m = int((pos.ra_hours - ra_h) * 60)
                dec_d = int(pos.dec_degrees)
                dec_m = int((abs(pos.dec_degrees) - abs(dec_d)) * 60)
                lines.append(("", f"RA: {ra_h:02d}h{ra_m:02d}m "))
                lines.append(("", f"Dec: {dec_d:+03d}°{dec_m:02d}' "))
    except Exception:
        pass

    # Help text
    lines.append(("dim", "Press 'q' to quit, 'r' to refresh, '1/2/3' to focus panes"))

    return FormattedText(lines)

