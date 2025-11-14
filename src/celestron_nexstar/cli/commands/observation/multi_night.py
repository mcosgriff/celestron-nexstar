"""
Multi-Night Planning Commands

Compare observing conditions across multiple nights and find the best night for specific objects.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict
from zoneinfo import ZoneInfo

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder
from typer.core import TyperGroup

from celestron_nexstar.api.astronomy.solar_system import get_moon_info, get_sun_info
from celestron_nexstar.api.catalogs.catalogs import CelestialObject, get_object_by_name
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.utils import angular_separation, calculate_lst, ra_dec_to_alt_az
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData, get_light_pollution_data
from celestron_nexstar.api.observation.observation_planner import ObservationPlanner, ObservingConditions
from celestron_nexstar.api.observation.visibility import VisibilityInfo, assess_visibility
from celestron_nexstar.cli.utils.export import FileConsole


if TYPE_CHECKING:
    pass


class NightData(TypedDict):
    """Type definition for night data dictionary."""

    date: datetime
    sunset: datetime
    transit_time: datetime
    altitude: float
    conditions: ObservingConditions
    visibility: VisibilityInfo
    score: float
    moon_separation_deg: float  # Angular separation from moon in degrees


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Multi-night observing planning and comparison", cls=SortedCommandsGroup)
console = Console()
_tz_finder = TimezoneFinder()


def _generate_export_filename(command: str = "week") -> Path:
    """Generate export filename for multi-night commands."""
    from datetime import datetime

    from celestron_nexstar.api.location.observer import get_observer_location
    from celestron_nexstar.api.observation.optics import load_configuration

    location = get_observer_location()

    # Get location name (shortened, sanitized)
    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        # Remove common suffixes and limit length
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]  # Limit length
    else:
        location_short = "unknown"

    # Get date
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Generate filename (multi-night commands use telescope configuration)
    config = load_configuration()
    telescope_name = config.telescope.model.value.replace("nexstar_", "").replace("_", "") if config else "no_telescope"

    filename = f"nexstar_{telescope_name}_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


# ============================================================================
# Configuration Constants
# ============================================================================

# Scoring weights for best-night calculation
SCORING_WEIGHTS = {
    "conditions_quality": 0.35,  # Overall conditions (clouds, transparency, wind)
    "seeing": 0.25,  # Atmospheric steadiness
    "visibility": 0.20,  # Object altitude and observability
    "moon_separation": 0.15,  # Angular distance from moon (NEW)
    "moon_brightness": 0.05,  # Moon illumination (reduced from 0.1)
}

# Day colors for chart visualization
DAY_COLORS = [
    "cyan",
    "magenta",
    "yellow",
    "green",
    "blue",
    "bright_cyan",
    "bright_magenta",
]

# Quality thresholds
QUALITY_EXCELLENT = 0.75
QUALITY_GOOD = 0.60
QUALITY_FAIR = 0.40

# Available conditions for display
AVAILABLE_CONDITIONS = {
    "clouds": ("Cloud Cover", "cloud_cover", "_get_cloud_color"),
    "transparency": ("Transparency", "transparency", "_get_transparency_color_wrapper"),
    "seeing": ("Seeing", "seeing", "_get_seeing_color"),
    "darkness": ("Darkness", "darkness", "_get_darkness_color"),
    "wind": ("Wind", "wind", "_get_wind_color"),
    "humidity": ("Humidity", "humidity", "_get_humidity_color"),
    "temperature": ("Temperature", "temperature", "_get_temp_color"),
}

# Default conditions to show (all)
DEFAULT_CONDITIONS = list(AVAILABLE_CONDITIONS.keys())

# Threshold defaults for highlighting good observing conditions
DEFAULT_THRESHOLDS = {
    "max_clouds": 30.0,  # Highlight if clouds <= 30%
    "min_darkness": 5.0,  # Highlight if darkness >= 5.0 mag
    "min_seeing": 60.0,  # Highlight if seeing >= 60/100
}

# Object-type specific scoring weights
# Different celestial objects have different observing requirements
OBJECT_TYPE_WEIGHTS = {
    CelestialObjectType.PLANET: {
        "seeing": 0.45,  # Planets critically need steady air
        "visibility": 0.25,  # High altitude important for steadiness
        "conditions_quality": 0.20,  # General conditions matter
        "moon_separation": 0.05,  # Planets tolerate moon well (bright targets)
        "moon_brightness": 0.05,  # Moon brightness less critical
        "light_pollution_sensitivity": 0.0,  # Planets unaffected by light pollution
    },
    CelestialObjectType.GALAXY: {
        "moon_separation": 0.30,  # Galaxies very sensitive to moon proximity
        "conditions_quality": 0.25,  # Need dark, transparent skies
        "visibility": 0.25,  # Need good altitude
        "seeing": 0.10,  # Seeing less critical for extended objects
        "moon_brightness": 0.10,  # Also sensitive to moon brightness
        "light_pollution_sensitivity": 0.9,  # Extremely sensitive to light pollution
    },
    CelestialObjectType.NEBULA: {
        "moon_separation": 0.25,  # Nebulae sensitive to moon
        "conditions_quality": 0.30,  # Need transparency and darkness
        "visibility": 0.25,  # Need good altitude
        "seeing": 0.10,  # Seeing less critical
        "moon_brightness": 0.10,  # Moon brightness matters
        "light_pollution_sensitivity": 0.8,  # Very sensitive to light pollution
    },
    CelestialObjectType.CLUSTER: {
        "visibility": 0.30,  # Altitude very important
        "conditions_quality": 0.25,  # General conditions
        "seeing": 0.20,  # Some benefit from steady air
        "moon_separation": 0.15,  # Moderate moon sensitivity
        "moon_brightness": 0.10,  # Less sensitive than galaxies
        "light_pollution_sensitivity": 0.4,  # Moderately sensitive to light pollution
    },
    CelestialObjectType.DOUBLE_STAR: {
        "seeing": 0.50,  # Critical for resolving close pairs
        "visibility": 0.25,  # High altitude for steadiness
        "conditions_quality": 0.15,  # General conditions
        "moon_separation": 0.05,  # Stars tolerate moon well
        "moon_brightness": 0.05,  # Bright targets
        "light_pollution_sensitivity": 0.0,  # Stars unaffected by light pollution
    },
    # Default weights for other types (star, asterism, constellation, moon)
    "default": {
        "conditions_quality": 0.30,
        "seeing": 0.25,
        "visibility": 0.25,
        "moon_separation": 0.15,
        "moon_brightness": 0.05,
        "light_pollution_sensitivity": 0.3,  # Moderate sensitivity
    },
}


# ============================================================================
# Color Mapping Functions
# ============================================================================


def _get_cloud_color(clouds: float) -> tuple[str, str]:
    """Get color for cloud cover - 11-level gradient from dark blue (clear) to white (overcast)."""
    if clouds >= 90:
        return ("white", "Overcast")
    elif clouds >= 80:
        return ("#F0F0F0", "90%")
    elif clouds >= 70:
        return ("#E0E0E0", "80%")
    elif clouds >= 60:
        return ("#D0D0D0", "70%")
    elif clouds >= 50:
        return ("#C0C0C0", "60%")
    elif clouds >= 40:
        return ("#A0A0C0", "50%")
    elif clouds >= 30:
        return ("#8080A0", "40%")
    elif clouds >= 20:
        return ("#606080", "30%")
    elif clouds >= 10:
        return ("#404060", "20%")
    elif clouds >= 5:
        return ("#202040", "10%")
    else:
        return ("#0000FF", "Clear")


def _get_transparency_color(transparency: str) -> tuple[str, str]:
    """Get color for transparency - 6-level gradient from white (too cloudy) to dark blue (transparent)."""
    colors = {
        "too_cloudy": ("white", "Too cloudy to forecast"),
        "poor": ("#808080", "Poor"),
        "below_average": ("#4080A0", "Below Average"),
        "average": ("#0066AA", "Average"),
        "above_average": ("#0033AA", "Above average"),
        "transparent": ("#0000FF", "Transparent"),
    }
    return colors.get(transparency, ("#0066AA", "Average"))


def _get_seeing_color(seeing: float | None) -> tuple[str, str]:
    """Get color for seeing - 6-level gradient from white (too cloudy) to dark blue (excellent)."""
    if seeing is None:
        return ("white", "Too cloudy to forecast")
    elif seeing >= 80:
        return ("#0000FF", "Excellent 5/5")
    elif seeing >= 60:
        return ("#0033AA", "Good 4/5")
    elif seeing >= 40:
        return ("#0066AA", "Average 3/5")
    elif seeing >= 20:
        return ("#4080A0", "Poor 2/5")
    else:
        return ("#808080", "Bad 1/5")


def _get_darkness_color(mag: float | None) -> tuple[str, str]:
    """Get color for darkness/limiting magnitude - 15-level gradient matching Clear Sky Chart."""
    if mag is None:
        return ("white", "Day")
    elif mag >= 6.5:
        return ("#000000", "6.5")
    elif mag >= 6.0:
        return ("#000010", "6.0")
    elif mag >= 5.5:
        return ("#000020", "5.5")
    elif mag >= 5.0:
        return ("#000040", "5.0")
    elif mag >= 4.5:
        return ("#000060", "4.5")
    elif mag >= 4.0:
        return ("#000080", "4.0")
    elif mag >= 3.5:
        return ("#0000A0", "3.5")
    elif mag >= 3.0:
        return ("#0000C0", "3.0")
    elif mag >= 2.0:
        return ("#0080C0", "2.0")
    elif mag >= 1.0:
        return ("#00C0C0", "1.0")
    elif mag >= 0.0:
        return ("#40E0E0", "0")
    elif mag >= -1.0:
        return ("#80E0E0", "-1")
    elif mag >= -2.0:
        return ("#C0E0C0", "-2")
    elif mag >= -3.0:
        return ("#FFFF80", "-3")
    elif mag >= -4.0:
        return ("#FFFFC0", "-4")
    else:
        return ("white", "Day")


def _get_wind_color(wind: float | None) -> tuple[str, str]:
    """Get color for wind speed - 6-level gradient matching Clear Sky Chart colors."""
    if wind is None:
        return ("dim", "-")
    elif wind > 45:
        return ("white", ">45 mph")
    elif wind >= 29:
        return ("#E0E0E0", "29-45 mph")
    elif wind >= 17:
        return ("#80C0E0", "17-28 mph")
    elif wind >= 12:
        return ("#4080C0", "12-16 mph")
    elif wind >= 6:
        return ("#2060A0", "6-11 mph")
    else:
        return ("#004080", "0-5 mph")


def _get_humidity_color(humidity: float | None) -> tuple[str, str]:
    """Get color for humidity - 16-level gradient matching Clear Sky Chart colors."""
    if humidity is None:
        return ("dim", "-")
    elif humidity >= 95:
        return ("#800000", "95-100%")
    elif humidity >= 90:
        return ("#A00000", "90-95%")
    elif humidity >= 85:
        return ("#FF0000", "85-90%")
    elif humidity >= 80:
        return ("#FF4400", "80-85%")
    elif humidity >= 75:
        return ("#FF8800", "75-80%")
    elif humidity >= 70:
        return ("#FFFF00", "70-75%")
    elif humidity >= 65:
        return ("#80FF00", "65-70%")
    elif humidity >= 60:
        return ("#00FF00", "60-65%")
    elif humidity >= 55:
        return ("#00FF80", "55-60%")
    elif humidity >= 50:
        return ("#00FFFF", "50-55%")
    elif humidity >= 45:
        return ("#00AAFF", "45-50%")
    elif humidity >= 40:
        return ("#0080FF", "40-45%")
    elif humidity >= 35:
        return ("#0066FF", "35-40%")
    elif humidity >= 30:
        return ("#0044FF", "30-35%")
    elif humidity >= 25:
        return ("#0022FF", "25-30%")
    else:
        return ("#0000FF", "<25%")


def _get_temp_color(temp: float | None) -> tuple[str, str]:
    """Get color for temperature - 19-level gradient matching Clear Sky Chart colors."""
    if temp is None:
        return ("dim", "-")
    elif temp > 113:
        return ("#808080", ">113°F")
    elif temp >= 104:
        return ("#800000", "104-113°F")
    elif temp >= 95:
        return ("#A00000", "95-104°F")
    elif temp >= 86:
        return ("#FF0000", "86-95°F")
    elif temp >= 77:
        return ("#FF4400", "77-86°F")
    elif temp >= 68:
        return ("#FF8800", "68-77°F")
    elif temp >= 59:
        return ("#FFAA00", "59-68°F")
    elif temp >= 50:
        return ("#FFFF00", "50-59°F")
    elif temp >= 41:
        return ("#80FF00", "41-50°F")
    elif temp >= 32:
        return ("#00FF80", "32-41°F")
    elif temp >= 23:
        return ("white", "23-32°F")
    elif temp >= 14:
        return ("#00FFAA", "14-23°F")
    elif temp >= 5:
        return ("#00FFFF", "5-14°F")
    elif temp >= -3:
        return ("#0080FF", "-3-5°F")
    elif temp >= -12:
        return ("#0066FF", "-12--3°F")
    elif temp >= -21:
        return ("#0044FF", "-21--12°F")
    elif temp >= -30:
        return ("#0022FF", "-30--21°F")
    elif temp >= -40:
        return ("#0000FF", "-40--31°F")
    else:
        return ("#FF00FF", "< -40°F")


def _get_local_timezone(lat: float, lon: float) -> ZoneInfo | None:
    """Get timezone for a given latitude and longitude."""
    try:
        tz_name = _tz_finder.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        pass
    return None


def _calculate_hours_to_show(
    day_data: list[dict[str, object]],
    day_key: str,
    is_first_day: bool,
    tz: ZoneInfo | None,
) -> int:
    """
    Calculate how many hours to show for a given day.

    This ensures that day names fit properly in the header and that
    partial days show at least a minimum number of hours.

    Args:
        day_data: List of hourly data for the day
        day_key: ISO format date string (YYYY-MM-DD)
        is_first_day: Whether this is the first day in the chart
        tz: Timezone for local time conversion

    Returns:
        Number of hours to show for this day
    """
    hours_available = len(day_data)
    is_full_day = hours_available >= 24

    # Determine the starting hour for this day
    day_start_hour: int | None = None
    if day_data:
        first_data = day_data[0]
        if isinstance(first_data.get("timestamp"), datetime):
            first_ts = first_data["timestamp"]
            if isinstance(first_ts, datetime):
                local_first_ts = first_ts.astimezone(tz) if tz else first_ts
                day_start_hour = local_first_ts.hour

    # Parse the day info for formatting
    if tz:
        day_dt = datetime.fromisoformat(day_key).replace(tzinfo=tz)
    else:
        day_dt = datetime.fromisoformat(day_key).replace(tzinfo=UTC)

    day_of_week = day_dt.strftime("%A")
    day_number = day_dt.day

    if is_full_day:
        # Full day - use long form "Saturday, 8"
        day_name = f"{day_of_week}, {day_number}"
        name_length = len(day_name)
        min_hours_needed = (name_length + 1) // 2  # Round up
        hours_to_show = max(hours_available, min_hours_needed, 24)
    elif is_first_day and day_start_hour is not None and day_start_hour <= 10:
        # First day starting on or before 10 AM - use long form
        day_name = f"{day_of_week}, {day_number}"
        name_length = len(day_name)
        min_hours_needed = (name_length + 1) // 2
        hours_to_show = max(hours_available, min_hours_needed)
    else:
        # Partial day starting after 10 AM - use short form "Sat"
        # Ensure minimum 3 hours to prevent overlap
        min_hours_for_short = 3
        hours_to_show = max(hours_available, min_hours_for_short)

    # Don't exceed available data
    return min(hours_to_show, len(day_data))


# ============================================================================
# Legend Data Structure
# ============================================================================

# Define all legend levels in order from worst to best conditions
LEGEND_DATA = {
    "Cloud Cover": [
        ("white", "Overcast"),
        ("#F0F0F0", "90% covered"),
        ("#E0E0E0", "80% covered"),
        ("#D0D0D0", "70% covered"),
        ("#C0C0C0", "60% covered"),
        ("#A0A0C0", "50% covered"),
        ("#8080A0", "40% covered"),
        ("#606080", "30% covered"),
        ("#404060", "20% covered"),
        ("#202040", "10% covered"),
        ("#0000FF", "Clear"),
    ],
    "Transparency": [
        ("white", "Too cloudy to forecast"),
        ("#808080", "Poor"),
        ("#4080A0", "Below Average"),
        ("#0066AA", "Average"),
        ("#0033AA", "Above average"),
        ("#0000FF", "Transparent"),
    ],
    "Seeing": [
        ("white", "Too cloudy to forecast"),
        ("#808080", "Bad"),
        ("#4080A0", "Poor"),
        ("#0066AA", "Average"),
        ("#0033AA", "Good"),
        ("#0000FF", "Excellent"),
    ],
    "Darkness": [
        ("white", "Day"),
        ("#FFFFC0", "-4"),
        ("#FFFF80", "-3"),
        ("#C0E0C0", "-2"),
        ("#80E0E0", "-1"),
        ("#40E0E0", "0"),
        ("#00C0C0", "1.0"),
        ("#0080C0", "2.0"),
        ("#0000C0", "3.0"),
        ("#0000A0", "3.5"),
        ("#000080", "4.0"),
        ("#000060", "4.5"),
        ("#000040", "5.0"),
        ("#000020", "5.5"),
        ("#000010", "6.0"),
        ("#000000", "6.5"),
    ],
    "Wind": [
        ("#004080", "0-5 mph"),
        ("#2060A0", "6-11 mph"),
        ("#4080C0", "12-16 mph"),
        ("#80C0E0", "17-28 mph"),
        ("#E0E0E0", "29-45 mph"),
        ("white", ">45 mph"),
    ],
    "Humidity": [
        ("#0000FF", "<25%"),
        ("#0022FF", "25-30%"),
        ("#0044FF", "30-35%"),
        ("#0066FF", "35-40%"),
        ("#0080FF", "40-45%"),
        ("#00AAFF", "45-50%"),
        ("#00FFFF", "50-55%"),
        ("#00FF80", "55-60%"),
        ("#00FF00", "60-65%"),
        ("#80FF00", "65-70%"),
        ("#FFFF00", "70-75%"),
        ("#FF8800", "75-80%"),
        ("#FF4400", "80-85%"),
        ("#FF0000", "85-90%"),
        ("#A00000", "90-95%"),
        ("#800000", "95-100%"),
    ],
    "Temperature": [
        ("#FF00FF", "< -40°F"),
        ("#0000FF", "-40--31°F"),
        ("#0022FF", "-30--21°F"),
        ("#0044FF", "-21--12°F"),
        ("#0066FF", "-12--3°F"),
        ("#0080FF", "-3-5°F"),
        ("#00FFFF", "5-14°F"),
        ("#00FFAA", "14-23°F"),
        ("white", "23-32°F"),
        ("#00FF80", "32-41°F"),
        ("#80FF00", "41-50°F"),
        ("#FFFF00", "50-59°F"),
        ("#FFAA00", "59-68°F"),
        ("#FF8800", "68-77°F"),
        ("#FF4400", "77-86°F"),
        ("#FF0000", "86-95°F"),
        ("#A00000", "95-104°F"),
        ("#800000", "104-113°F"),
        ("#808080", ">113°F"),
    ],
}


def _render_legend(conditions: list[str] | None = None) -> None:
    """
    Render the legend for chart conditions using the data-driven structure.

    Args:
        conditions: List of condition keys to include in legend. If None, shows all.
    """
    if conditions is None:
        conditions = DEFAULT_CONDITIONS

    # Map condition keys to legend names
    condition_name_map = {
        "clouds": "Cloud Cover",
        "transparency": "Transparency",
        "seeing": "Seeing",
        "darkness": "Darkness",
        "wind": "Wind",
        "humidity": "Humidity",
        "temperature": "Temperature",
    }

    console.print("\n[bold]Legend:[/bold]")

    for cond_key in conditions:
        condition_name = condition_name_map.get(cond_key)
        if condition_name and condition_name in LEGEND_DATA:
            levels = LEGEND_DATA[condition_name]
            legend_parts = [f"[dim]{condition_name}:[/dim]"]
            # Add padding to align with grid (20 chars total for condition name area)
            padding = 18 - len(f"{condition_name}:")
            if padding > 0:
                legend_parts.append(" " * padding)

            for color, label in levels:
                # Automatically choose black or white text based on background luminance
                text_color = _get_text_color_for_background(color)
                legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")

            console.print(" ".join(legend_parts))

    console.print(
        "\n[dim]Note: Each block represents one hour. "
        "Time shown in 24-hour format (tens digit above, ones digit below).[/dim]"
    )


@app.command("week", rich_help_panel="Night Comparison")
def show_week(
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Compare observing conditions for the next 7 nights."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("week")

        file_console = create_file_console()
        _show_week_content(file_console)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_week_content(console)


def _show_week_content(output_console: Console | FileConsole) -> None:
    """Generate and display week comparison content."""
    try:
        planner = ObservationPlanner()

        # Get location
        from celestron_nexstar.api.location.observer import get_observer_location

        location = get_observer_location()
        if location is None:
            output_console.print("[red]No location set. Use 'nexstar location set' command.[/red]")  # type: ignore[unreachable]
            raise typer.Exit(code=1) from None

        assert location is not None
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)

        output_console.print("\n[bold cyan]What's Good This Week?[/bold cyan]")
        output_console.print("[dim]Comparing observing conditions for the next 7 nights...[/dim]\n")

        # Get conditions for each night (starting at sunset each day)
        nights = []
        now = datetime.now(UTC)

        for day_offset in range(7):
            # Calculate date for this night
            night_date = now + timedelta(days=day_offset)
            # Get sunset time for this date
            from celestron_nexstar.api.astronomy.solar_system import get_sun_info

            sun_info = get_sun_info(lat, lon, night_date)
            if sun_info and sun_info.sunset_time:
                sunset = sun_info.sunset_time
                if sunset.tzinfo is None:
                    sunset = sunset.replace(tzinfo=UTC)
                elif sunset.tzinfo != UTC:
                    sunset = sunset.astimezone(UTC)

                # Get conditions for this night (starting at sunset)
                conditions = planner.get_tonight_conditions(lat, lon, start_time=sunset)
                nights.append((night_date, sunset, conditions))

        if not nights:
            output_console.print("[yellow]Could not calculate conditions for any nights.[/yellow]")
            return

        # Create comparison table
        table = Table(title="7-Night Comparison")
        table.add_column("Date", style="cyan")
        table.add_column("Quality")
        table.add_column("Seeing", justify="right")
        table.add_column("Clouds", justify="right")
        table.add_column("Moon")
        table.add_column("Moon %", justify="right")
        table.add_column("Best Window")

        for night_date, _sunset, conditions in nights:
            # Format date
            if tz:
                local_date = night_date.astimezone(tz)
                date_str = local_date.strftime("%a %b %d")
            else:
                date_str = night_date.strftime("%a %b %d")

            # Quality assessment
            quality = conditions.observing_quality_score
            if quality > QUALITY_EXCELLENT:
                quality_text = "[green]Excellent[/green]"
            elif quality > QUALITY_GOOD:
                quality_text = "[yellow]Good[/yellow]"
            elif quality > QUALITY_FAIR:
                quality_text = "[dim]Fair[/dim]"
            else:
                quality_text = "[red]Poor[/red]"

            # Seeing
            seeing = conditions.seeing_score
            seeing_text = f"{seeing:.0f}/100"

            # Clouds
            clouds = conditions.weather.cloud_cover_percent or 100.0
            clouds_text = f"{clouds:.0f}%"

            # Moon phase
            moon_phase = conditions.moon_phase.value if conditions.moon_phase else "Unknown"
            moon_illum = conditions.moon_illumination * 100
            moon_text = f"{moon_illum:.0f}%"

            # Best seeing window
            if conditions.best_seeing_windows:
                best_window = conditions.best_seeing_windows[0]
                window_start, window_end = best_window
                if tz:
                    start_local = window_start.astimezone(tz)
                    end_local = window_end.astimezone(tz)
                    window_str = f"{start_local.strftime('%I:%M %p')} - {end_local.strftime('%I:%M %p')}"
                else:
                    window_str = f"{window_start.strftime('%I:%M %p')} - {window_end.strftime('%I:%M %p')}"
            else:
                window_str = "[dim]-[/dim]"

            table.add_row(
                date_str,
                quality_text,
                seeing_text,
                clouds_text,
                moon_phase,
                moon_text,
                window_str,
            )

        output_console.print(table)

        # Find best nights
        best_quality = max(nights, key=lambda n: n[2].observing_quality_score)
        best_seeing = max(nights, key=lambda n: n[2].seeing_score)
        best_clear = min(nights, key=lambda n: n[2].weather.cloud_cover_percent or 100.0)

        output_console.print("\n[bold]Best Nights:[/bold]")
        if tz:
            best_quality_date = best_quality[0].astimezone(tz).strftime("%A, %B %d")
            best_seeing_date = best_seeing[0].astimezone(tz).strftime("%A, %B %d")
            best_clear_date = best_clear[0].astimezone(tz).strftime("%A, %B %d")
        else:
            best_quality_date = best_quality[0].strftime("%A, %B %d")
            best_seeing_date = best_seeing[0].strftime("%A, %B %d")
            best_clear_date = best_clear[0].strftime("%A, %B %d")

        output_console.print(
            f"  [green]Best Overall:[/green] {best_quality_date} (Quality: {best_quality[2].observing_quality_score * 100:.0f}/100)"
        )
        output_console.print(
            f"  [green]Best Seeing:[/green] {best_seeing_date} (Seeing: {best_seeing[2].seeing_score:.0f}/100)"
        )
        output_console.print(
            f"  [green]Clearest Sky:[/green] {best_clear_date} (Clouds: {best_clear[2].weather.cloud_cover_percent or 0:.0f}%)"
        )

    except Exception as e:
        output_console.print(f"[red]Error comparing nights:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("best-night", rich_help_panel="Object Planning")
def show_best_night(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Jupiter, Vega)"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to check (default: 7)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find the best night to observe a specific object in the next N days."""
    from celestron_nexstar.cli.utils.export import create_file_console, export_to_text

    if export:
        if export_path:
            export_path_obj = Path(export_path)
        else:
            # Generate filename with object name
            from datetime import datetime

            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.optics import load_configuration

            location = get_observer_location()
            if location.name:
                location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
                location_short = location_short.replace("_(default)", "").replace("_observatory", "")
                location_short = location_short[:20]
            else:
                location_short = "unknown"

            date_str = datetime.now().strftime("%Y-%m-%d")
            config = load_configuration()
            if config:
                telescope_name = config.telescope.model.value.replace("nexstar_", "").replace("_", "")
            else:
                telescope_name = "no_telescope"

            # Sanitize object name for filename
            obj_safe = object_name.lower().replace(" ", "_").replace("/", "_")[:15]
            export_path_obj = Path(f"nexstar_{telescope_name}_{location_short}_{date_str}_best-night_{obj_safe}.txt")

        file_console = create_file_console()
        _show_best_night_content(file_console, object_name, days)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_best_night_content(console, object_name, days)


def _show_best_night_content(output_console: Console | FileConsole, object_name: str, days: int) -> None:
    """Generate and display best night content."""
    try:
        # Find the object
        import asyncio

        matches = asyncio.run(get_object_by_name(object_name))
        if not matches:
            output_console.print(f"[red]No objects found matching '{object_name}'[/red]")
            raise typer.Exit(code=1) from None

        # If multiple matches, use the first one (could add selection UI later)
        obj = matches[0]
        if len(matches) > 1:
            output_console.print(f"[yellow]Multiple matches found. Using: {obj.name}[/yellow]")
            if obj.common_name:
                output_console.print(f"[dim]Common name: {obj.common_name}[/dim]")

        planner = ObservationPlanner()

        # Get location
        from celestron_nexstar.api.location.observer import get_observer_location

        location = get_observer_location()
        if location is None:
            output_console.print("[red]No location set. Use 'nexstar location set' command.[/red]")  # type: ignore[unreachable]
            raise typer.Exit(code=1) from None

        assert location is not None
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)

        output_console.print(f"\n[bold cyan]Best Night for {obj.name}[/bold cyan]")
        if obj.common_name:
            output_console.print(f"[dim]{obj.common_name}[/dim]")
        output_console.print(f"[dim]Type: {obj.object_type.value.title()}[/dim]")
        output_console.print(
            f"[dim]Checking next {days} nights with {obj.object_type.value}-optimized scoring...[/dim]\n"
        )

        # Get light pollution data for observer location
        async def _get_light_data() -> Any:
            from celestron_nexstar.api.database.models import get_db_session

            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, lat, lon)

        light_pollution_data = asyncio.run(_get_light_data())
        output_console.print(
            f"[dim]Location light pollution: Bortle {light_pollution_data.bortle_class.value} - {light_pollution_data.description}[/dim]\n"
        )

        # Check each night
        nights_data: list[NightData] = []
        now = datetime.now(UTC)

        for day_offset in range(days):
            # Calculate date for this night
            night_date = now + timedelta(days=day_offset)
            # Get sunset time for this date
            from celestron_nexstar.api.astronomy.solar_system import get_sun_info

            sun_info = get_sun_info(lat, lon, night_date)
            if not sun_info or not sun_info.sunset_time:
                continue

            sunset = sun_info.sunset_time
            if sunset.tzinfo is None:
                sunset = sunset.replace(tzinfo=UTC)
            elif sunset.tzinfo != UTC:
                sunset = sunset.astimezone(UTC)

            # Get conditions for this night
            conditions = planner.get_tonight_conditions(lat, lon, start_time=sunset)

            # Check object visibility at transit (highest point)
            # Calculate transit time
            lst_hours = calculate_lst(lon, sunset)
            obj_ra = obj.ra_hours
            ha_hours = lst_hours - obj_ra

            # Normalize hour angle to -12 to +12
            while ha_hours > 12:
                ha_hours -= 24
            while ha_hours < -12:
                ha_hours += 24

            # Calculate time to transit
            time_diff_hours = -ha_hours
            transit_time = sunset + timedelta(hours=time_diff_hours)

            # Check if transit is during observing window (after sunset, before sunrise)
            sunrise = sun_info.sunrise_time
            if sunrise:
                if sunrise.tzinfo is None:
                    sunrise = sunrise.replace(tzinfo=UTC)
                elif sunrise.tzinfo != UTC:
                    sunrise = sunrise.astimezone(UTC)
                if sunrise < sunset:
                    sunrise = sunrise + timedelta(days=1)

                # Determine observation time
                observation_time = transit_time

                if not (sunset <= transit_time <= sunrise):
                    # Transit is outside observing window
                    # Check if object is circumpolar (always above horizon)
                    # Use midnight (middle of observing window) instead
                    midnight = sunset + (sunrise - sunset) / 2
                    alt_at_midnight, _az = ra_dec_to_alt_az(obj.ra_hours, obj.dec_degrees, lat, lon, midnight)

                    if alt_at_midnight > 0:
                        # Object is visible at midnight - likely circumpolar or visible during night
                        observation_time = midnight
                    else:
                        # Object is not visible during this night
                        continue

                # Calculate altitude at observation time
                alt, _az = ra_dec_to_alt_az(obj.ra_hours, obj.dec_degrees, lat, lon, observation_time)

                # Skip if object is below horizon
                if alt <= 0:
                    continue

                # Assess visibility
                visibility = assess_visibility(
                    obj,
                    observer_lat=lat,
                    observer_lon=lon,
                    dt=observation_time,
                )

                # Get moon position at observation time
                moon_info = get_moon_info(lat, lon, observation_time)
                moon_separation_deg = 0.0
                moon_separation_score = 1.0  # Default: no interference

                if moon_info:
                    # Calculate moon-object separation and scoring
                    moon_separation_score, moon_separation_deg = _calculate_moon_separation_score(
                        obj.ra_hours,
                        obj.dec_degrees,
                        moon_info.ra_hours,
                        moon_info.dec_degrees,
                        conditions.moon_illumination,
                    )

                # Calculate object-type specific score (with light pollution)
                total_score = _calculate_object_type_score(
                    obj,
                    conditions,
                    visibility,
                    moon_separation_score,
                    light_pollution_data,
                )

                nights_data.append(
                    {
                        "date": night_date,
                        "sunset": sunset,
                        "transit_time": observation_time,
                        "altitude": alt,
                        "conditions": conditions,
                        "visibility": visibility,
                        "score": total_score,
                        "moon_separation_deg": moon_separation_deg,
                    }
                )

        if not nights_data:
            output_console.print(
                f"[yellow]Object is not visible during observing hours in the next {days} nights.[/yellow]"
            )
            return

        # Sort by score (best first)
        nights_data.sort(key=lambda n: float(n["score"]), reverse=True)

        # Create table
        table = Table(title=f"Best Nights for {obj.name}")
        table.add_column("Date", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Quality")
        table.add_column("Seeing", justify="right")
        table.add_column("Clouds", justify="right")
        table.add_column("Transit")
        table.add_column("Altitude", justify="right")
        table.add_column("Moon")
        table.add_column("Moon Sep", justify="right")

        for night in nights_data:
            date: datetime = night["date"]
            if tz:
                local_date = date.astimezone(tz)
                date_str = local_date.strftime("%a %b %d")
            else:
                date_str = date.strftime("%a %b %d")

            score = float(night["score"]) * 100
            night_conditions: ObservingConditions = night["conditions"]

            # Quality
            quality = night_conditions.observing_quality_score
            if quality > QUALITY_EXCELLENT:
                quality_text = "[green]Excellent[/green]"
            elif quality > QUALITY_GOOD:
                quality_text = "[yellow]Good[/yellow]"
            elif quality > QUALITY_FAIR:
                quality_text = "[dim]Fair[/dim]"
            else:
                quality_text = "[red]Poor[/red]"

            seeing = f"{night_conditions.seeing_score:.0f}/100"
            clouds = f"{night_conditions.weather.cloud_cover_percent or 100.0:.0f}%"

            # Transit time
            transit: datetime = night["transit_time"]
            if tz:
                transit_local = transit.astimezone(tz)
                transit_str = transit_local.strftime("%I:%M %p")
            else:
                transit_str = transit.strftime("%I:%M %p")

            altitude_val: float = night["altitude"]
            altitude = f"{altitude_val:.0f}°"
            moon = f"{night_conditions.moon_illumination * 100:.0f}%"
            moon_sep: float = night["moon_separation_deg"]
            moon_sep_str = f"{moon_sep:.0f}°"

            table.add_row(
                date_str,
                f"{score:.0f}",
                quality_text,
                seeing,
                clouds,
                transit_str,
                altitude,
                moon,
                moon_sep_str,
            )

        output_console.print(table)

        # Show best night details
        best: NightData = nights_data[0]
        best_date: datetime = best["date"]
        if tz:
            best_local = best_date.astimezone(tz)
            best_date_str = best_local.strftime("%A, %B %d, %Y")
        else:
            best_date_str = best_date.strftime("%A, %B %d, %Y")

        # Format transit time for summary
        best_transit: datetime = best["transit_time"]
        if tz:
            best_transit_local = best_transit.astimezone(tz)
            best_transit_str = best_transit_local.strftime("%I:%M %p")
        else:
            best_transit_str = best_transit.strftime("%I:%M %p")

        best_conditions: ObservingConditions = best["conditions"]
        best_visibility: VisibilityInfo = best["visibility"]
        best_altitude: float = best["altitude"]
        best_score: float = best["score"]

        output_console.print(f"\n[bold green]Best Night:[/bold green] {best_date_str}")
        output_console.print(f"  Score: {best_score * 100:.0f}/100")
        output_console.print(f"  Transit: {best_transit_str} at {best_altitude:.0f}° altitude")
        output_console.print(f"  Seeing: {best_conditions.seeing_score:.0f}/100")
        output_console.print(f"  Cloud Cover: {best_conditions.weather.cloud_cover_percent or 100.0:.0f}%")
        output_console.print(f"  Moon: {best_conditions.moon_illumination * 100:.0f}% illuminated")

        # Show moon separation
        best_moon_sep: float = best["moon_separation_deg"]
        output_console.print(f"  Moon Separation: {best_moon_sep:.0f}°")

        # Add object-type specific note with light pollution context
        if obj.object_type == CelestialObjectType.PLANET:
            output_console.print("  [dim]Note: Planets benefit most from excellent seeing and high altitude[/dim]")
            output_console.print("  [dim]      Light pollution has minimal impact on planetary observing[/dim]")
        elif obj.object_type == CelestialObjectType.GALAXY:
            output_console.print("  [dim]Note: Galaxies need dark skies and distance from the moon[/dim]")
            if light_pollution_data.bortle_class >= BortleClass.CLASS_6:
                output_console.print(
                    f"  [yellow]      ⚠ Light pollution (Bortle {light_pollution_data.bortle_class.value}) significantly reduces galaxy visibility[/yellow]"
                )
            else:
                output_console.print(
                    f"  [dim]      Your Bortle {light_pollution_data.bortle_class.value} location is suitable for galaxy observation[/dim]"
                )
        elif obj.object_type == CelestialObjectType.NEBULA:
            output_console.print("  [dim]Note: Nebulae need transparency, darkness, and distance from moon[/dim]")
            if light_pollution_data.bortle_class >= BortleClass.CLASS_6:
                output_console.print(
                    f"  [yellow]      ⚠ Light pollution (Bortle {light_pollution_data.bortle_class.value}) reduces nebula contrast and detail[/yellow]"
                )
            else:
                output_console.print(
                    f"  [dim]      Your Bortle {light_pollution_data.bortle_class.value} location is suitable for nebula observation[/dim]"
                )
        elif obj.object_type == CelestialObjectType.DOUBLE_STAR:
            output_console.print("  [dim]Note: Double stars need excellent seeing to resolve close pairs[/dim]")
            output_console.print("  [dim]      Light pollution has minimal impact on double star observing[/dim]")
        elif obj.object_type == CelestialObjectType.CLUSTER:
            output_console.print("  [dim]Note: Clusters benefit most from good altitude and moderate darkness[/dim]")
            if light_pollution_data.bortle_class >= BortleClass.CLASS_7:
                output_console.print(
                    f"  [yellow]      ⚠ Light pollution (Bortle {light_pollution_data.bortle_class.value}) may wash out fainter cluster members[/yellow]"
                )
            else:
                output_console.print(
                    f"  [dim]      Your Bortle {light_pollution_data.bortle_class.value} location is acceptable for cluster observation[/dim]"
                )

        if best_visibility.is_visible:
            output_console.print("  [green]✓ Object will be visible[/green]")
        else:
            output_console.print(f"  [red]✗ Object may not be visible: {', '.join(best_visibility.reasons)}[/red]")

    except Exception as e:
        output_console.print(f"[red]Error finding best night:[/red] {e}")
        import traceback

        output_console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("clear-sky", rich_help_panel="Forecast Visualization")
def show_clear_sky_chart(
    days: int = typer.Option(4, "--days", "-d", help="Number of days to show (default: 4, max: 7)"),
    nighttime_only: bool = typer.Option(
        False, "--nighttime-only", "-n", help="Only show nighttime hours (after sunset, before sunrise)"
    ),
    conditions: str = typer.Option(
        ",".join(DEFAULT_CONDITIONS),
        "--conditions",
        "-c",
        help=f"Comma-separated list of conditions to display. Available: {', '.join(AVAILABLE_CONDITIONS.keys())}",
    ),
    highlight_good: bool = typer.Option(
        False,
        "--highlight-good",
        help="Highlight hours with good observing conditions (low clouds, high darkness, good seeing)",
    ),
    max_clouds: float = typer.Option(
        DEFAULT_THRESHOLDS["max_clouds"],
        "--max-clouds",
        help="Maximum cloud cover %% for highlighting (used with --highlight-good)",
    ),
    min_darkness: float = typer.Option(
        DEFAULT_THRESHOLDS["min_darkness"],
        "--min-darkness",
        help="Minimum darkness (limiting magnitude) for highlighting (used with --highlight-good)",
    ),
    min_seeing: float = typer.Option(
        DEFAULT_THRESHOLDS["min_seeing"],
        "--min-seeing",
        help="Minimum seeing score (0-100) for highlighting (used with --highlight-good)",
    ),
    export: str | None = typer.Option(
        None,
        "--export",
        "-e",
        help="Export chart data to file. Supported formats: .csv, .json",
    ),
) -> None:
    """Display a Clear Sky Chart-style forecast grid showing conditions over multiple days."""
    try:
        from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
        from celestron_nexstar.api.location.observer import get_observer_location
        from celestron_nexstar.api.location.weather import fetch_hourly_weather_forecast

        # Parse and validate conditions
        requested_conditions = [c.strip() for c in conditions.split(",")]
        invalid_conditions = [c for c in requested_conditions if c not in AVAILABLE_CONDITIONS]
        if invalid_conditions:
            console.print(f"[red]Invalid conditions: {', '.join(invalid_conditions)}[/red]")
            console.print(f"[yellow]Available conditions: {', '.join(AVAILABLE_CONDITIONS.keys())}[/yellow]")
            raise typer.Exit(code=1) from None

        location = get_observer_location()
        if location is None:
            console.print("[red]No location set. Use 'nexstar location set' command.[/red]")  # type: ignore[unreachable]
            raise typer.Exit(code=1) from None

        assert location is not None
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)
        location_name = location.name or "Current Location"

        # Limit to 7 days max
        days = min(max(1, days), 7)
        hours = days * 24

        console.print(f"\n[bold cyan]Clear Sky Chart for {location_name}[/bold cyan]")
        # Display current time in local timezone
        now_utc = datetime.now(UTC)
        now_local = now_utc.astimezone(tz) if tz else now_utc
        console.print(f"[dim]Last updated {now_local.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        console.print(f"[dim]Forecast for next {days} days...[/dim]\n")

        # Fetch hourly forecast
        hourly_forecast = asyncio.run(fetch_hourly_weather_forecast(location, hours=hours))
        if not hourly_forecast:
            console.print("[yellow]Hourly forecast data not available.[/yellow]")
            return

        # Get light pollution for darkness calculation
        async def _get_light_data() -> Any:
            from celestron_nexstar.api.database.models import get_db_session

            async with get_db_session() as db_session:
                return await get_light_pollution_data(db_session, lat, lon)

        lp_data = asyncio.run(_get_light_data())

        # Calculate transparency and darkness for each hour
        chart_data = []

        for forecast in hourly_forecast:
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            # Calculate transparency from humidity/dew point
            transparency = "average"  # Default
            if forecast.cloud_cover_percent is not None and forecast.cloud_cover_percent > 30:
                transparency = "too_cloudy"
            elif forecast.humidity_percent is not None:
                # Lower humidity = better transparency
                if forecast.humidity_percent < 30:
                    transparency = "transparent"
                elif forecast.humidity_percent < 50:
                    transparency = "above_average"
                elif forecast.humidity_percent < 70:
                    transparency = "average"
                elif forecast.humidity_percent < 85:
                    transparency = "below_average"
                else:
                    transparency = "poor"

            # Calculate darkness (limiting magnitude at zenith)
            # Based on sun altitude, moon phase, and moon altitude
            sun_info = get_sun_info(lat, lon, forecast_ts)
            moon_info = get_moon_info(lat, lon, forecast_ts)

            darkness_mag = None
            base_mag = lp_data.naked_eye_limiting_magnitude
            if sun_info:
                sun_alt = sun_info.altitude_deg
                if sun_alt < -18:  # Astronomical twilight
                    # Dark sky - calculate limiting magnitude
                    if moon_info:
                        # Moon brightens the sky
                        moon_illum = moon_info.illumination
                        moon_alt = moon_info.altitude_deg
                        if moon_alt > 0:
                            # Moon is up - reduce limiting magnitude
                            # Full moon reduces by ~3-4 mag, new moon has no effect
                            moon_reduction = moon_illum * 3.5 * (moon_alt / 90.0)  # Scale by altitude
                            darkness_mag = base_mag - moon_reduction
                        else:
                            darkness_mag = base_mag
                    else:
                        darkness_mag = base_mag
                elif sun_alt < -12:  # Astronomical twilight
                    darkness_mag = base_mag - 0.5 if moon_info is None else base_mag - 1.0
                elif sun_alt < -6:  # Nautical twilight
                    darkness_mag = 3.0
                elif sun_alt < 0:  # Civil twilight
                    darkness_mag = 2.0
                else:  # Daytime
                    darkness_mag = 0.0

            # Determine if seeing is "too cloudy to forecast" (>80% cloud cover)
            seeing_value: float | None = forecast.seeing_score
            if forecast.cloud_cover_percent is not None and forecast.cloud_cover_percent > 80:
                seeing_value = None  # Mark as too cloudy

            chart_data.append(
                {
                    "timestamp": forecast_ts,
                    "cloud_cover": forecast.cloud_cover_percent or 100.0,
                    "transparency": transparency,
                    "seeing": seeing_value,
                    "darkness": darkness_mag,
                    "wind": forecast.wind_speed_mph,
                    "humidity": forecast.humidity_percent,
                    "temperature": forecast.temperature_f,
                }
            )

        if not chart_data:
            console.print("[yellow]No forecast data available.[/yellow]")
            return

        # Get current time in UTC, rounded down to the nearest hour
        now_utc = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        now_local = now_utc.astimezone(tz) if tz else now_utc
        current_hour = now_local.hour

        # Determine start time for filtering
        # If current hour is 22 (10pm) or 23 (11pm), include previous hour(s) to show at least 3 hours
        if current_hour >= 22:
            # Show 9pm, 10pm, 11pm (hours 21, 22, 23)
            hours_back = current_hour - 21  # 1 hour back for 22, 2 hours back for 23
            start_time_utc = now_utc - timedelta(hours=hours_back)
        else:
            # Start at current hour
            start_time_utc = now_utc

        # Filter chart_data to include data from start_time forward
        filtered_chart_data = [
            data
            for data in chart_data
            if isinstance(data["timestamp"], datetime) and data["timestamp"] >= start_time_utc
        ]

        # Apply nighttime-only filter if requested
        if nighttime_only:
            filtered_chart_data = [
                data
                for data in filtered_chart_data
                if isinstance(data["timestamp"], datetime) and _is_nighttime(data["timestamp"], lat, lon)
            ]

        if not filtered_chart_data:
            if nighttime_only:
                console.print(
                    "[yellow]No nighttime forecast data available. Try without --nighttime-only flag.[/yellow]"
                )
            else:
                console.print("[yellow]No forecast data available from current time forward.[/yellow]")
            return

        # Export data if requested
        if export:
            _export_chart_data(filtered_chart_data, export, tz)
            console.print(f"[green]Data exported to {export}[/green]")

        # Prepare threshold dict for highlighting
        thresholds = None
        if highlight_good:
            thresholds = {
                "max_clouds": max_clouds,
                "min_darkness": min_darkness,
                "min_seeing": min_seeing,
            }

        # Group data by day and create grid
        # Create a grid display similar to Clear Sky Chart
        _display_clear_sky_chart(
            filtered_chart_data,
            lat,
            lon,
            tz,
            days,
            start_hour=start_time_utc,
            conditions=requested_conditions,
            thresholds=thresholds,
        )

    except Exception as e:
        console.print(f"[red]Error generating chart:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


def _export_chart_data(chart_data: list[dict[str, object]], export_path: str, tz: ZoneInfo | None) -> None:
    """
    Export chart data to CSV or JSON format.

    Args:
        chart_data: List of hourly forecast data
        export_path: File path to export to (.csv or .json)
        tz: Timezone for local time conversion

    Raises:
        ValueError: If export format is not supported
    """
    import csv
    import json
    from pathlib import Path

    export_file = Path(export_path)
    extension = export_file.suffix.lower()

    if extension == ".csv":
        # Export to CSV
        with export_file.open("w", newline="") as f:
            if not chart_data:
                return

            # Get all possible fields from first data point
            fieldnames = ["timestamp_utc", "timestamp_local"]
            # Add all data fields
            for key in chart_data[0]:
                if key != "timestamp":
                    fieldnames.append(key)

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for data in chart_data:
                row: dict[str, object] = {}
                ts = data.get("timestamp")
                if isinstance(ts, datetime):
                    row["timestamp_utc"] = ts.isoformat()
                    local_ts = ts.astimezone(tz) if tz else ts
                    row["timestamp_local"] = local_ts.isoformat()

                # Add all other fields
                for key, value in data.items():
                    if key != "timestamp":
                        row[key] = value

                writer.writerow(row)

    elif extension == ".json":
        # Export to JSON
        export_data = []
        for data in chart_data:
            json_row: dict[str, object] = {}
            ts = data.get("timestamp")
            if isinstance(ts, datetime):
                json_row["timestamp_utc"] = ts.isoformat()
                local_ts = ts.astimezone(tz) if tz else ts
                json_row["timestamp_local"] = local_ts.isoformat()

            # Add all other fields
            for key, value in data.items():
                if key != "timestamp":
                    json_row[key] = value

            export_data.append(json_row)

        with export_file.open("w") as f:
            json.dump(export_data, f, indent=2)

    else:
        msg = f"Unsupported export format: {extension}. Use .csv or .json"
        raise ValueError(msg)


@lru_cache(maxsize=256)
def _is_nighttime_cached(timestamp_iso: str, lat: float, lon: float) -> bool:
    """
    Cached version of nighttime check to avoid redundant sun calculations.

    Args:
        timestamp_iso: ISO format timestamp string (for hashability)
        lat: Observer latitude
        lon: Observer longitude

    Returns:
        True if the sun is below the horizon, False otherwise
    """
    timestamp = datetime.fromisoformat(timestamp_iso)
    sun_info = get_sun_info(lat, lon, timestamp)
    if sun_info:
        return sun_info.altitude_deg < 0
    return False


def _is_nighttime(timestamp: datetime, lat: float, lon: float) -> bool:
    """
    Check if a given timestamp is during nighttime (sun below horizon).

    Args:
        timestamp: The time to check
        lat: Observer latitude
        lon: Observer longitude

    Returns:
        True if the sun is below the horizon, False otherwise
    """
    return _is_nighttime_cached(timestamp.isoformat(), lat, lon)


def _calculate_light_pollution_score(bortle_class: BortleClass) -> float:
    """
    Calculate light pollution quality score from Bortle class.

    Args:
        bortle_class: Bortle dark-sky scale class (1-9)

    Returns:
        Score from 0.0 (worst light pollution) to 1.0 (best darkness)
    """
    # Map Bortle class to quality score
    bortle_scores = {
        BortleClass.CLASS_1: 1.0,  # Excellent dark-sky site
        BortleClass.CLASS_2: 0.95,  # Typical truly dark site
        BortleClass.CLASS_3: 0.85,  # Rural sky
        BortleClass.CLASS_4: 0.70,  # Rural/suburban transition
        BortleClass.CLASS_5: 0.50,  # Suburban sky
        BortleClass.CLASS_6: 0.30,  # Bright suburban sky
        BortleClass.CLASS_7: 0.15,  # Suburban/urban transition
        BortleClass.CLASS_8: 0.05,  # City sky
        BortleClass.CLASS_9: 0.0,  # Inner-city sky
    }
    return bortle_scores.get(bortle_class, 0.5)  # Default to suburban


def _calculate_object_type_score(
    obj: CelestialObject,
    conditions: ObservingConditions,
    visibility: VisibilityInfo,
    moon_separation_score: float,
    light_pollution_data: LightPollutionData | None = None,
) -> float:
    """
    Calculate observation quality score tailored to the object's type.

    Different objects have different observing requirements:
    - Planets: Need excellent seeing, less affected by moon or light pollution
    - Galaxies: Need dark skies, distance from moon, and minimal light pollution
    - Nebulae: Need darkness, transparency, and low light pollution
    - Clusters: Need good altitude and moderate darkness
    - Double stars: Need excellent seeing to resolve

    Args:
        obj: Celestial object being observed
        conditions: Observing conditions for the night
        visibility: Visibility assessment for the object
        moon_separation_score: Pre-calculated moon-object separation score
        light_pollution_data: Light pollution information for observer location

    Returns:
        Total score (0.0-1.0) weighted for object type and adjusted for light pollution
    """
    # Get weights for this object type, fall back to default
    weights = OBJECT_TYPE_WEIGHTS.get(obj.object_type, OBJECT_TYPE_WEIGHTS["default"])

    # Calculate component scores
    conditions_score = conditions.observing_quality_score * weights["conditions_quality"]
    seeing_score = (conditions.seeing_score / 100.0) * weights["seeing"]
    visibility_score = visibility.observability_score * weights["visibility"]
    moon_sep_score = moon_separation_score * weights["moon_separation"]
    moon_brightness_score = (1.0 - conditions.moon_illumination) * weights["moon_brightness"]

    # Calculate base score (before light pollution penalty)
    base_score = conditions_score + seeing_score + visibility_score + moon_sep_score + moon_brightness_score

    # Apply light pollution penalty based on object sensitivity
    if light_pollution_data:
        light_pollution_quality = _calculate_light_pollution_score(light_pollution_data.bortle_class)
        sensitivity = weights["light_pollution_sensitivity"]

        # Penalty formula: objects with higher sensitivity get more penalty in poor conditions
        # - Sensitivity 0.0 (planets, double stars): no penalty
        # - Sensitivity 0.9 (galaxies) in Bortle 5 (0.5 quality): 45% penalty (score reduced to 55%)
        # - Sensitivity 0.8 (nebulae) in Bortle 7 (0.15 quality): 68% penalty (score reduced to 32%)
        light_pollution_penalty = 1.0 - (sensitivity * (1.0 - light_pollution_quality))
        final_score = base_score * light_pollution_penalty
    else:
        # No light pollution data available, use base score
        final_score = base_score

    return final_score


def _calculate_moon_separation_score(
    object_ra_hours: float,
    object_dec_degrees: float,
    moon_ra_hours: float,
    moon_dec_degrees: float,
    moon_illumination: float,
) -> tuple[float, float]:
    """
    Calculate moon interference score based on separation and illumination.

    Args:
        object_ra_hours: Object's RA in hours
        object_dec_degrees: Object's declination in degrees
        moon_ra_hours: Moon's RA in hours
        moon_dec_degrees: Moon's declination in degrees
        moon_illumination: Moon illumination fraction (0.0-1.0)

    Returns:
        Tuple of (score, separation_degrees)
        - score: 0.0 (worst interference) to 1.0 (no interference)
        - separation_degrees: Angular separation in degrees
    """
    # Calculate angular separation between object and moon
    separation_deg = angular_separation(
        object_ra_hours,
        object_dec_degrees,
        moon_ra_hours,
        moon_dec_degrees,
    )

    # Moon interference is combination of:
    # 1. Angular separation (closer = worse)
    # 2. Moon brightness (brighter = worse)

    # Separation scoring:
    # - <15°: Very bad (moon glare ruins observation)
    # - 15-30°: Poor (significant interference)
    # - 30-60°: Fair (moderate interference)
    # - 60-90°: Good (minimal interference)
    # - >90°: Excellent (opposite sides of sky)

    if separation_deg >= 90:
        separation_score = 1.0
    elif separation_deg >= 60:
        separation_score = 0.8 + 0.2 * ((separation_deg - 60) / 30)
    elif separation_deg >= 30:
        separation_score = 0.5 + 0.3 * ((separation_deg - 30) / 30)
    elif separation_deg >= 15:
        separation_score = 0.2 + 0.3 * ((separation_deg - 15) / 15)
    else:
        separation_score = 0.2 * (separation_deg / 15)

    # Brightness factor: brighter moon = more interference
    # New moon (0% illumination) = no penalty
    # Full moon (100% illumination) = maximum penalty
    brightness_factor = 1.0 - (moon_illumination * 0.5)  # Max 50% reduction

    # Combined score
    final_score = separation_score * brightness_factor

    return final_score, separation_deg


def _meets_thresholds(data: dict[str, object], thresholds: dict[str, float]) -> bool:
    """
    Check if an hour's data meets the good observing thresholds.

    Args:
        data: Hour data dictionary with condition values
        thresholds: Dict with max_clouds, min_darkness, min_seeing

    Returns:
        True if all thresholds are met
    """
    cloud_cover = data.get("cloud_cover")
    darkness = data.get("darkness")
    seeing = data.get("seeing")

    # Check cloud cover threshold
    if isinstance(cloud_cover, (int, float)) and cloud_cover > thresholds["max_clouds"]:
        return False

    # Check darkness threshold
    if isinstance(darkness, (int, float)) and darkness < thresholds["min_darkness"]:
        return False

    # Check seeing threshold - return the negated condition directly
    return not (isinstance(seeing, (int, float)) and seeing < thresholds["min_seeing"])


def _get_transparency_color_wrapper(value: object) -> tuple[str, str]:
    """Wrapper to handle transparency color lookup with type checking."""
    if isinstance(value, str):
        return _get_transparency_color(value)
    return ("dim", "-")


def _render_day_header(
    day_labels: list[str],
    days_data: dict[str, list[dict[str, object]]],
    tz: ZoneInfo | None,
) -> None:
    """Render the day name header row."""
    from rich.text import Text

    day_header = Text()
    day_header.append(" " * 20)  # Space for condition labels

    for day_idx, day_key in enumerate(day_labels):
        day_color = DAY_COLORS[day_idx % len(DAY_COLORS)]
        day_data = days_data[day_key]

        if tz:
            day_dt = datetime.fromisoformat(day_key).replace(tzinfo=tz)
        else:
            day_dt = datetime.fromisoformat(day_key).replace(tzinfo=UTC)

        # Calculate hours to show for this day
        is_first_day = day_idx == 0
        hours_to_show = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)
        is_full_day = hours_to_show >= 24

        # Format day name
        day_number = day_dt.day
        day_of_week = day_dt.strftime("%A")
        day_name = f"{day_of_week}, {day_number}" if is_full_day else day_dt.strftime("%a")

        # Display day name
        day_header.append(day_name, style=f"bold {day_color}")

        # Fill remaining space to match time row width
        name_length = len(day_name)
        total_width = hours_to_show * 2 - 1
        remaining_chars = max(0, total_width - name_length)
        day_header.append(" " * remaining_chars, style="dim")

        # Add spacing between days
        if day_idx < len(day_labels) - 1:
            day_header.append("  ", style="dim")

    console.print(day_header)


def _render_time_header(
    day_labels: list[str],
    days_data: dict[str, list[dict[str, object]]],
    tz: ZoneInfo | None,
    thresholds: dict[str, float] | None = None,
) -> None:
    """Render the time header rows (tens and ones digits), with optional highlighting."""
    from rich.text import Text

    # Tens digit row
    tens_row = Text()
    tens_row.append(" " * 20)

    for day_idx, day_key in enumerate(day_labels):
        day_color = DAY_COLORS[day_idx % len(DAY_COLORS)]
        day_data = days_data[day_key]

        is_first_day = day_idx == 0
        hours_to_show = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)

        for i, data in enumerate(day_data[:hours_to_show]):
            ts_value = data["timestamp"]
            if not isinstance(ts_value, datetime):
                continue
            local_ts = ts_value.astimezone(tz) if tz else ts_value
            hour = local_ts.hour
            tens_digit = hour // 10
            tens_row.append(f"{tens_digit}", style=f"bold {day_color}")
            if i < hours_to_show - 1:
                tens_row.append(" ", style="dim")

        if day_idx < len(day_labels) - 1:
            tens_row.append("  ", style="dim")

    console.print(tens_row)

    # Ones digit row
    ones_row = Text()
    ones_row.append(" " * 20)

    for day_idx, day_key in enumerate(day_labels):
        day_color = DAY_COLORS[day_idx % len(DAY_COLORS)]
        day_data = days_data[day_key]

        is_first_day = day_idx == 0
        hours_to_show = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)

        for i, data in enumerate(day_data[:hours_to_show]):
            ts_value = data["timestamp"]
            if not isinstance(ts_value, datetime):
                continue
            local_ts = ts_value.astimezone(tz) if tz else ts_value
            hour = local_ts.hour
            ones_digit = hour % 10
            ones_row.append(f"{ones_digit}", style=f"bold {day_color}")
            if i < hours_to_show - 1:
                ones_row.append(" ", style="dim")

        if day_idx < len(day_labels) - 1:
            ones_row.append("  ", style="dim")

    console.print(ones_row)

    # Highlight row (if thresholds provided)
    if thresholds:
        highlight_row = Text()
        highlight_row.append(" " * 20)

        for day_idx, day_key in enumerate(day_labels):
            day_data = days_data[day_key]
            is_first_day = day_idx == 0
            hours_to_show = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)

            for i, data in enumerate(day_data[:hours_to_show]):
                if _meets_thresholds(data, thresholds):
                    highlight_row.append("★", style="bold green")
                else:
                    highlight_row.append(" ", style="dim")

                if i < hours_to_show - 1:
                    highlight_row.append(" ", style="dim")

            if day_idx < len(day_labels) - 1:
                highlight_row.append("  ", style="dim")

        console.print(highlight_row)


def _render_condition_row(
    condition_name: str,
    field: str,
    color_func: object,
    day_labels: list[str],
    days_data: dict[str, list[dict[str, object]]],
    tz: ZoneInfo | None,
) -> None:
    """Render a single condition row in the chart."""
    from rich.text import Text

    condition_row = Text()
    condition_row.append(f"{condition_name:<20}", style="bold")

    for day_idx, day_key in enumerate(day_labels):
        day_data = days_data[day_key]

        is_first_day = day_idx == 0
        hours_to_show = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)

        for i, data in enumerate(day_data[:hours_to_show]):
            value = data.get(field)

            # Get color based on field type and value
            if field == "seeing":
                if value is None:
                    color, _label = _get_seeing_color(None)
                elif isinstance(value, (int, float)):
                    color, _label = _get_seeing_color(float(value))
                else:
                    color, _label = ("dim", "-")
            elif field == "cloud_cover" and isinstance(value, (int, float)):
                color, _label = _get_cloud_color(float(value))
            elif field == "darkness":
                if isinstance(value, (int, float)):
                    color, _label = _get_darkness_color(float(value))
                else:
                    color, _label = _get_darkness_color(None)
            elif field == "wind":
                if isinstance(value, (int, float)):
                    color, _label = _get_wind_color(float(value))
                else:
                    color, _label = _get_wind_color(None)
            elif field == "humidity":
                if isinstance(value, (int, float)):
                    color, _label = _get_humidity_color(float(value))
                else:
                    color, _label = _get_humidity_color(None)
            elif field == "temperature":
                if isinstance(value, (int, float)):
                    color, _label = _get_temp_color(float(value))
                else:
                    color, _label = _get_temp_color(None)
            elif field == "transparency" and isinstance(value, str):
                color, _label = _get_transparency_color_wrapper(value)
            else:
                color, _label = ("dim", "-")

            # Render the cell
            condition_row.append("█", style=color)

            if i < hours_to_show - 1:
                condition_row.append(" ", style="dim")

        # Add spacing between days
        if day_idx < len(day_labels) - 1:
            condition_row.append("  ", style="dim")

    console.print(condition_row)


def _get_text_color_for_background(bg_color: str) -> str:
    """
    Determine whether to use black or white text based on background color luminance.

    Uses WCAG relative luminance formula to ensure good contrast.
    Returns 'black' for light backgrounds, 'white' for dark backgrounds.
    """
    # Handle named colors
    named_colors = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "cyan": (0, 255, 255),
        "yellow": (255, 255, 0),
        "magenta": (255, 0, 255),
    }

    if bg_color in named_colors:
        r, g, b = named_colors[bg_color]
    elif bg_color.startswith("#"):
        # Parse hex color
        hex_color = bg_color.lstrip("#")
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
        else:
            # Fallback for invalid hex
            return "white"
    else:
        # Fallback for unknown colors
        return "white"

    # Convert sRGB to linear RGB (gamma correction)
    def srgb_to_linear(channel: int) -> float:
        """Convert sRGB channel (0-255) to linear RGB (0-1)."""
        normalized = channel / 255.0
        if normalized <= 0.04045:
            return float(normalized / 12.92)
        else:
            return float(((normalized + 0.055) / 1.055) ** 2.4)

    r_linear = srgb_to_linear(r)
    g_linear = srgb_to_linear(g)
    b_linear = srgb_to_linear(b)

    # Calculate relative luminance (WCAG formula)
    # L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    luminance = 0.2126 * r_linear + 0.7152 * g_linear + 0.0722 * b_linear

    # Use black text on light backgrounds (luminance > 0.5), white on dark
    return "black" if luminance > 0.5 else "white"


def _display_clear_sky_chart(
    chart_data: list[dict[str, object]],
    lat: float,
    lon: float,
    tz: ZoneInfo | None,
    days: int,
    start_hour: datetime | None = None,
    conditions: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
) -> None:
    """Display a Clear Sky Chart-style grid visualization."""
    if conditions is None:
        conditions = DEFAULT_CONDITIONS

    # Group data by day
    days_data: dict[str, list[dict[str, object]]] = {}
    for data in chart_data:
        ts_value = data["timestamp"]
        if not isinstance(ts_value, datetime):
            continue
        local_ts = ts_value.astimezone(tz) if tz else ts_value

        day_key = local_ts.strftime("%Y-%m-%d")
        if day_key not in days_data:
            days_data[day_key] = []
        days_data[day_key].append(data)

    # Sort data within each day by timestamp
    for day_key in days_data:
        days_data[day_key].sort(
            key=lambda x: x["timestamp"] if isinstance(x["timestamp"], datetime) else datetime.min.replace(tzinfo=UTC)
        )

    # Get sorted day labels
    day_labels = sorted(days_data.keys())[:days]

    # Filter first day if start_hour is specified
    if start_hour and tz:
        start_hour_local_ts = start_hour.astimezone(tz)
        start_hour_local = start_hour_local_ts.hour
        first_day_key = start_hour_local_ts.strftime("%Y-%m-%d")

        if first_day_key in days_data:
            min_hour = 21 if start_hour_local >= 22 else start_hour_local
            days_data[first_day_key] = [
                data
                for data in days_data[first_day_key]
                if isinstance(data["timestamp"], datetime) and data["timestamp"].astimezone(tz).hour >= min_hour
            ]

    # Pre-calculate hours to show for each day (performance optimization)
    hours_to_show_cache: dict[str, int] = {}
    for day_idx, day_key in enumerate(day_labels):
        is_first_day = day_idx == 0
        day_data = days_data[day_key]
        hours_to_show_cache[day_key] = _calculate_hours_to_show(day_data, day_key, is_first_day, tz)

    # Build the chart
    console.print("[bold]Clear Sky Chart[/bold]\n")

    # Render headers
    _render_day_header(day_labels, days_data, tz)
    _render_time_header(day_labels, days_data, tz, thresholds)

    # Build condition rows based on requested conditions
    condition_rows = []
    for cond_key in conditions:
        if cond_key in AVAILABLE_CONDITIONS:
            name, field, func_name = AVAILABLE_CONDITIONS[cond_key]
            # Get the actual function from globals
            color_func = globals()[func_name]
            condition_rows.append((name, field, color_func))

    # Render condition rows
    for condition_name, field, color_func in condition_rows:
        _render_condition_row(condition_name, field, color_func, day_labels, days_data, tz)

    # Render legend (only for requested conditions)
    _render_legend(conditions)
