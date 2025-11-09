"""
Multi-Night Planning Commands

Compare observing conditions across multiple nights and find the best night for specific objects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TypedDict
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.catalogs import get_object_by_name
from ...api.observation_planner import ObservationPlanner, ObservingConditions
from ...api.solar_system import get_moon_info, get_sun_info
from ...api.utils import calculate_lst, ra_dec_to_alt_az
from ...api.visibility import VisibilityInfo, assess_visibility


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


app = typer.Typer(help="Multi-night observing planning and comparison")
console = Console()
_tz_finder = TimezoneFinder()


def _get_local_timezone(lat: float, lon: float) -> ZoneInfo | None:
    """Get timezone for a given latitude and longitude."""
    try:
        tz_name = _tz_finder.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        pass
    return None


@app.command("week", rich_help_panel="Night Comparison")
def show_week() -> None:
    """Compare observing conditions for the next 7 nights."""
    try:
        planner = ObservationPlanner()

        # Get location
        from ...api.observer import get_observer_location
        location = get_observer_location()
        if location is None:
            console.print("[red]No location set. Use 'nexstar location set' command.[/red]")  # type: ignore[unreachable]
            raise typer.Exit(code=1) from None

        assert location is not None
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)

        console.print("\n[bold cyan]What's Good This Week?[/bold cyan]")
        console.print("[dim]Comparing observing conditions for the next 7 nights...[/dim]\n")

        # Get conditions for each night (starting at sunset each day)
        nights = []
        now = datetime.now(UTC)

        for day_offset in range(7):
            # Calculate date for this night
            night_date = now + timedelta(days=day_offset)
            # Get sunset time for this date
            from ...api.solar_system import get_sun_info
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
            console.print("[yellow]Could not calculate conditions for any nights.[/yellow]")
            return

        # Create comparison table
        table = Table(title="7-Night Comparison")
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Quality", width=12)
        table.add_column("Seeing", justify="right", width=10)
        table.add_column("Clouds", justify="right", width=10)
        table.add_column("Moon", width=15)
        table.add_column("Moon %", justify="right", width=10)
        table.add_column("Best Window", width=20)

        for night_date, _sunset, conditions in nights:
            # Format date
            if tz:
                local_date = night_date.astimezone(tz)
                date_str = local_date.strftime("%a %b %d")
            else:
                date_str = night_date.strftime("%a %b %d")

            # Quality assessment
            quality = conditions.observing_quality_score
            if quality > 0.75:
                quality_text = "[green]Excellent[/green]"
            elif quality > 0.60:
                quality_text = "[yellow]Good[/yellow]"
            elif quality > 0.40:
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

        console.print(table)

        # Find best nights
        best_quality = max(nights, key=lambda n: n[2].observing_quality_score)
        best_seeing = max(nights, key=lambda n: n[2].seeing_score)
        best_clear = min(nights, key=lambda n: n[2].weather.cloud_cover_percent or 100.0)

        console.print("\n[bold]Best Nights:[/bold]")
        if tz:
            best_quality_date = best_quality[0].astimezone(tz).strftime("%A, %B %d")
            best_seeing_date = best_seeing[0].astimezone(tz).strftime("%A, %B %d")
            best_clear_date = best_clear[0].astimezone(tz).strftime("%A, %B %d")
        else:
            best_quality_date = best_quality[0].strftime("%A, %B %d")
            best_seeing_date = best_seeing[0].strftime("%A, %B %d")
            best_clear_date = best_clear[0].strftime("%A, %B %d")

        console.print(f"  [green]Best Overall:[/green] {best_quality_date} (Quality: {best_quality[2].observing_quality_score*100:.0f}/100)")
        console.print(f"  [green]Best Seeing:[/green] {best_seeing_date} (Seeing: {best_seeing[2].seeing_score:.0f}/100)")
        console.print(f"  [green]Clearest Sky:[/green] {best_clear_date} (Clouds: {best_clear[2].weather.cloud_cover_percent:.0f}%)")

    except Exception as e:
        console.print(f"[red]Error comparing nights:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("best-night", rich_help_panel="Object Planning")
def show_best_night(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Jupiter, Vega)"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to check (default: 7)"),
) -> None:
    """Find the best night to observe a specific object in the next N days."""
    try:
        # Find the object
        matches = get_object_by_name(object_name)
        if not matches:
            console.print(f"[red]No objects found matching '{object_name}'[/red]")
            raise typer.Exit(code=1) from None

        # If multiple matches, use the first one (could add selection UI later)
        obj = matches[0]
        if len(matches) > 1:
            console.print(f"[yellow]Multiple matches found. Using: {obj.name}[/yellow]")
            if obj.common_name:
                console.print(f"[dim]Common name: {obj.common_name}[/dim]")

        planner = ObservationPlanner()

        # Get location
        from ...api.observer import get_observer_location
        location = get_observer_location()
        if location is None:
            console.print("[red]No location set. Use 'nexstar location set' command.[/red]")  # type: ignore[unreachable]
            raise typer.Exit(code=1) from None

        assert location is not None
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)

        console.print(f"\n[bold cyan]Best Night for {obj.name}[/bold cyan]")
        if obj.common_name:
            console.print(f"[dim]{obj.common_name}[/dim]")
        console.print(f"[dim]Checking next {days} nights...[/dim]\n")

        # Check each night
        nights_data: list[NightData] = []
        now = datetime.now(UTC)

        for day_offset in range(days):
            # Calculate date for this night
            night_date = now + timedelta(days=day_offset)
            # Get sunset time for this date
            from ...api.solar_system import get_sun_info
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

                if sunset <= transit_time <= sunrise:
                    # Object transits during observing window
                    # Calculate altitude at transit
                    alt, _az = ra_dec_to_alt_az(obj.ra_hours, obj.dec_degrees, lat, lon, transit_time)

                    # Assess visibility
                    visibility = assess_visibility(
                        obj,
                        observer_lat=lat,
                        observer_lon=lon,
                        dt=transit_time,
                    )

                    # Calculate score combining conditions and visibility
                    # Weight: 40% conditions quality, 30% seeing, 20% visibility, 10% moon interference
                    conditions_score = conditions.observing_quality_score * 0.4
                    seeing_score = (conditions.seeing_score / 100.0) * 0.3
                    visibility_score = visibility.observability_score * 0.2
                    moon_score = (1.0 - conditions.moon_illumination) * 0.1  # Less moon = better

                    total_score = conditions_score + seeing_score + visibility_score + moon_score

                    nights_data.append({
                        "date": night_date,
                        "sunset": sunset,
                        "transit_time": transit_time,
                        "altitude": alt,
                        "conditions": conditions,
                        "visibility": visibility,
                        "score": total_score,
                    })

        if not nights_data:
            console.print(f"[yellow]Object does not transit during observing hours in the next {days} nights.[/yellow]")
            return

        # Sort by score (best first)
        nights_data.sort(key=lambda n: float(n["score"]), reverse=True)

        # Create table
        table = Table(title=f"Best Nights for {obj.name}")
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Quality", width=12)
        table.add_column("Seeing", justify="right", width=10)
        table.add_column("Clouds", justify="right", width=10)
        table.add_column("Transit", width=12)
        table.add_column("Altitude", justify="right", width=10)
        table.add_column("Moon", width=10)

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
            if quality > 0.75:
                quality_text = "[green]Excellent[/green]"
            elif quality > 0.60:
                quality_text = "[yellow]Good[/yellow]"
            elif quality > 0.40:
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

            table.add_row(
                date_str,
                f"{score:.0f}",
                quality_text,
                seeing,
                clouds,
                transit_str,
                altitude,
                moon,
            )

        console.print(table)

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

        console.print(f"\n[bold green]Best Night:[/bold green] {best_date_str}")
        console.print(f"  Score: {best_score*100:.0f}/100")
        console.print(f"  Transit: {best_transit_str} at {best_altitude:.0f}° altitude")
        console.print(f"  Seeing: {best_conditions.seeing_score:.0f}/100")
        console.print(f"  Cloud Cover: {best_conditions.weather.cloud_cover_percent or 100.0:.0f}%")
        console.print(f"  Moon: {best_conditions.moon_illumination*100:.0f}% illuminated")

        if best_visibility.is_visible:
            console.print("  [green]✓ Object will be visible[/green]")
        else:
            console.print(f"  [red]✗ Object may not be visible: {', '.join(best_visibility.reasons)}[/red]")

    except Exception as e:
        console.print(f"[red]Error finding best night:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("clear-sky", rich_help_panel="Forecast Visualization")
def show_clear_sky_chart(
    days: int = typer.Option(4, "--days", "-d", help="Number of days to show (default: 4, max: 7)"),
) -> None:
    """Display a Clear Sky Chart-style forecast grid showing conditions over multiple days."""
    try:
        from ...api.light_pollution import get_light_pollution_data
        from ...api.observer import get_observer_location
        from ...api.weather import fetch_hourly_weather_forecast

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
        hourly_forecast = fetch_hourly_weather_forecast(location, hours=hours)
        if not hourly_forecast:
            console.print("[yellow]Hourly forecast data not available.[/yellow]")
            return

        # Get light pollution for darkness calculation
        lp_data = get_light_pollution_data(lat, lon)

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

            chart_data.append({
                "timestamp": forecast_ts,
                "cloud_cover": forecast.cloud_cover_percent or 100.0,
                "transparency": transparency,
                "seeing": seeing_value,
                "darkness": darkness_mag,
                "wind": forecast.wind_speed_mph,
                "humidity": forecast.humidity_percent,
                "temperature": forecast.temperature_f,
            })

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
            data for data in chart_data
            if isinstance(data["timestamp"], datetime) and data["timestamp"] >= start_time_utc
        ]

        if not filtered_chart_data:
            console.print("[yellow]No forecast data available from current time forward.[/yellow]")
            return

        # Group data by day and create grid
        # Create a grid display similar to Clear Sky Chart
        _display_clear_sky_chart(filtered_chart_data, lat, lon, tz, days, start_hour=start_time_utc)

    except Exception as e:
        console.print(f"[red]Error generating chart:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


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
) -> None:
    """Display a Clear Sky Chart-style grid visualization."""
    from rich.text import Text

    # Assign distinct colors to each day for better visual separation
    day_colors = [
        "cyan",
        "magenta",
        "yellow",
        "green",
        "blue",
        "bright_cyan",
        "bright_magenta",
    ]

    # Color mappings for each condition type
    def get_cloud_color(clouds: float) -> tuple[str, str]:
        """Get color for cloud cover - 11-level gradient from dark blue (clear) to white (overcast)."""
        # Gradient: Dark blue (clear) -> lighter blues -> white (overcast)
        # Colors represent what the sky is likely to be, matching Clear Sky Chart
        # Clear, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, Overcast
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

    def get_transparency_color(transparency: str) -> tuple[str, str]:
        """Get color for transparency - 6-level gradient from white (too cloudy) to dark blue (transparent)."""
        # Gradient: White (too cloudy) -> gray -> light blue -> medium blue -> dark blue (transparent)
        colors = {
            "too_cloudy": ("white", "Too cloudy to forecast"),  # White
            "poor": ("#808080", "Poor"),  # Gray
            "below_average": ("#4080A0", "Below Average"),  # Gray-blue
            "average": ("#0066AA", "Average"),  # Medium blue
            "above_average": ("#0033AA", "Above average"),  # Darker blue
            "transparent": ("#0000FF", "Transparent"),  # Dark blue
        }
        return colors.get(transparency, ("#0066AA", "Average"))

    def get_seeing_color(seeing: float | None) -> tuple[str, str]:
        """Get color for seeing - 6-level gradient from white (too cloudy) to dark blue (excellent)."""
        # Too cloudy to forecast (cloud cover > 80%)
        if seeing is None:
            return ("white", "Too cloudy to forecast")
        # Excellent 5/5
        elif seeing >= 80:
            return ("#0000FF", "Excellent 5/5")  # Dark blue
        # Good 4/5
        elif seeing >= 60:
            return ("#0033AA", "Good 4/5")  # Darker blue
        # Average 3/5
        elif seeing >= 40:
            return ("#0066AA", "Average 3/5")  # Medium blue
        # Poor 2/5
        elif seeing >= 20:
            return ("#4080A0", "Poor 2/5")  # Gray-blue
        # Bad 1/5
        else:
            return ("#808080", "Bad 1/5")  # Gray

    def get_darkness_color(mag: float | None) -> tuple[str, str]:
        """Get color for darkness/limiting magnitude - 15-level gradient matching Clear Sky Chart."""
        # Gradient: White (daylight) -> Yellow (dusk) -> Turquoise (twilight) -> Light blue (full moon) -> Deep blue (partial moon) -> Black (dark)
        if mag is None:
            return ("white", "Day")
        elif mag >= 6.5:
            return ("#000000", "6.5")  # Black - Dark sky
        elif mag >= 6.0:
            return ("#000010", "6.0")  # Very dark blue
        elif mag >= 5.5:
            return ("#000020", "5.5")  # Dark blue
        elif mag >= 5.0:
            return ("#000040", "5.0")  # Medium-dark blue
        elif mag >= 4.5:
            return ("#000060", "4.5")  # Medium blue
        elif mag >= 4.0:
            return ("#000080", "4.0")  # Blue
        elif mag >= 3.5:
            return ("#0000A0", "3.5")  # Light blue
        elif mag >= 3.0:
            return ("#0000C0", "3.0")  # Lighter blue
        elif mag >= 2.0:
            return ("#0080C0", "2.0")  # Deep blue (partial moon)
        elif mag >= 1.0:
            return ("#00C0C0", "1.0")  # Light blue (full moon)
        elif mag >= 0.0:
            return ("#40E0E0", "0")  # Turquoise (twilight)
        elif mag >= -1.0:
            return ("#80E0E0", "-1")  # Light turquoise
        elif mag >= -2.0:
            return ("#C0E0C0", "-2")  # Yellow-turquoise transition
        elif mag >= -3.0:
            return ("#FFFF80", "-3")  # Yellow (dusk)
        elif mag >= -4.0:
            return ("#FFFFC0", "-4")  # Light yellow
        else:
            return ("white", "Day")  # White (daylight)

    def get_wind_color(wind: float | None) -> tuple[str, str]:
        """Get color for wind speed - 6-level gradient matching Clear Sky Chart colors."""
        # Gradient: White/light grey (high wind) -> light blue -> medium blue -> dark blue (calm)
        if wind is None:
            return ("dim", "-")
        elif wind > 45:
            return ("white", ">45 mph")  # White or very light grey
        elif wind >= 29:
            return ("#E0E0E0", "29-45 mph")  # Light grey
        elif wind >= 17:
            return ("#80C0E0", "17-28 mph")  # Light blue or teal
        elif wind >= 12:
            return ("#4080C0", "12-16 mph")  # Medium blue
        elif wind >= 6:
            return ("#2060A0", "6-11 mph")  # Darker blue
        else:
            return ("#004080", "0-5 mph")  # Darkest blue - Calm

    def get_humidity_color(humidity: float | None) -> tuple[str, str]:
        """Get color for humidity - 16-level gradient matching Clear Sky Chart colors."""
        # Gradient: Dark blue (low) -> Blues -> Cyan -> Green -> Yellow -> Orange -> Red (high)
        if humidity is None:
            return ("dim", "-")
        elif humidity >= 95:
            return ("#800000", "95-100%")  # Deep rich red
        elif humidity >= 90:
            return ("#A00000", "90-95%")  # Slightly darker red
        elif humidity >= 85:
            return ("#FF0000", "85-90%")  # Pure red
        elif humidity >= 80:
            return ("#FF4400", "80-85%")  # Bright red-orange
        elif humidity >= 75:
            return ("#FF8800", "75-80%")  # Orange
        elif humidity >= 70:
            return ("#FFFF00", "70-75%")  # Bright yellow
        elif humidity >= 65:
            return ("#80FF00", "65-70%")  # Yellow-green
        elif humidity >= 60:
            return ("#00FF00", "60-65%")  # Vibrant green
        elif humidity >= 55:
            return ("#00FF80", "55-60%")  # Light mint green
        elif humidity >= 50:
            return ("#00FFFF", "50-55%")  # Bright cyan/turquoise
        elif humidity >= 45:
            return ("#00AAFF", "45-50%")  # Light teal/greenish-blue
        elif humidity >= 40:
            return ("#0080FF", "40-45%")  # Light blue
        elif humidity >= 35:
            return ("#0066FF", "35-40%")  # Lighter medium blue
        elif humidity >= 30:
            return ("#0044FF", "30-35%")  # Medium blue
        elif humidity >= 25:
            return ("#0022FF", "25-30%")  # Medium-dark blue
        else:
            return ("#0000FF", "<25%")  # Very dark blue

    def get_temp_color(temp: float | None) -> tuple[str, str]:
        """Get color for temperature - 19-level gradient matching Clear Sky Chart colors."""
        # Gradient: Magenta/Blue (cold) -> Cyan -> Green -> Yellow -> Orange -> Red -> Maroon -> Grey (hot)
        if temp is None:
            return ("dim", "-")
        elif temp > 113:
            return ("#808080", ">113°F")  # Grey
        elif temp >= 104:
            return ("#800000", "104-113°F")  # Maroon
        elif temp >= 95:
            return ("#A00000", "95-104°F")  # Dark Red
        elif temp >= 86:
            return ("#FF0000", "86-95°F")  # Bright Red
        elif temp >= 77:
            return ("#FF4400", "77-86°F")  # Red-Orange
        elif temp >= 68:
            return ("#FF8800", "68-77°F")  # Orange
        elif temp >= 59:
            return ("#FFAA00", "59-68°F")  # Orange-Yellow
        elif temp >= 50:
            return ("#FFFF00", "50-59°F")  # Yellow
        elif temp >= 41:
            return ("#80FF00", "41-50°F")  # Lime Green
        elif temp >= 32:
            return ("#00FF80", "32-41°F")  # Medium Green
        elif temp >= 23:
            return ("white", "23-32°F")  # White
        elif temp >= 14:
            return ("#00FFAA", "14-23°F")  # Light Teal
        elif temp >= 5:
            return ("#00FFFF", "5-14°F")  # Cyan
        elif temp >= -3:
            return ("#0080FF", "-3-5°F")  # Light Blue
        elif temp >= -12:
            return ("#0066FF", "-12--3°F")  # Royal Blue
        elif temp >= -21:
            return ("#0044FF", "-21--12°F")  # Medium Blue
        elif temp >= -30:
            return ("#0022FF", "-30--21°F")  # Deep Blue
        elif temp >= -40:
            return ("#0000FF", "-40--31°F")  # Dark Blue
        else:
            return ("#FF00FF", "< -40°F")  # Magenta

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
        days_data[day_key].sort(key=lambda x: x["timestamp"] if isinstance(x["timestamp"], datetime) else datetime.min.replace(tzinfo=UTC))

    # Create header with day labels and hour markers
    day_labels = sorted(days_data.keys())[:days]

    # Determine start hour in local time for filtering first day
    start_hour_local: int | None = None
    if start_hour and tz:
        start_hour_local_ts = start_hour.astimezone(tz)
        start_hour_local = start_hour_local_ts.hour
        first_day_key = start_hour_local_ts.strftime("%Y-%m-%d")

        # Filter first day to only show hours >= start_hour
        # If start_hour is 22 (10pm) or 23 (11pm), we want to show from 21 (9pm) to ensure 3 hours
        if first_day_key in days_data:
            min_hour = 21 if start_hour_local >= 22 else start_hour_local
            days_data[first_day_key] = [
                data for data in days_data[first_day_key]
                if isinstance(data["timestamp"], datetime) and data["timestamp"].astimezone(tz).hour >= min_hour
            ]

    # Build the chart
    console.print("[bold]Clear Sky Chart[/bold]\n")

    # Day name header row (above time)
    day_header = Text()
    day_header.append(" " * 20)  # Space for condition labels

    for day_idx, day_key in enumerate(day_labels):
        day_color = day_colors[day_idx % len(day_colors)]
        day_data = days_data[day_key]

        if tz:
            day_dt = datetime.fromisoformat(day_key).replace(tzinfo=tz)
        else:
            day_dt = datetime.fromisoformat(day_key).replace(tzinfo=UTC)

        # Format: "Sat" or "Saturday, 8"
        day_number = day_dt.day
        day_of_week = day_dt.strftime("%A")
        hours_to_show = len(day_data)
        is_full_day = hours_to_show >= 24

        # Determine format:
        # - Full days (24 hours): long form "Saturday, 8"
        # - Partial days: short form "Sat"
        if is_full_day:
            # Long form: "Saturday, 8"
            day_name = f"{day_of_week}, {day_number}"
            # Calculate minimum hours needed for the name
            name_length = len(day_name)
            min_hours_needed = (name_length + 1) // 2  # Round up
            hours_to_show = max(hours_to_show, min_hours_needed, 24)
            hours_to_show = min(hours_to_show, len(day_data))
        else:
            # Short form: "Sat" (no day number)
            day_name = day_dt.strftime("%a")
            # Ensure minimum 3 hours to prevent overlap
            min_hours_for_short = 3
            hours_to_show = max(hours_to_show, min_hours_for_short)
            hours_to_show = min(hours_to_show, len(day_data))

        # Always start at the beginning of the day (no padding)
        day_header.append(day_name, style=f"bold {day_color}")
        # Fill remaining space to match time row width
        # Time row: hours_to_show digits + (hours_to_show - 1) spaces = hours_to_show * 2 - 1 total
        name_length = len(day_name)
        total_width = hours_to_show * 2 - 1
        remaining_chars = max(0, total_width - name_length)
        day_header.append(" " * remaining_chars, style="dim")

        # Add spacing between days (constant 2 spaces)
        if day_idx < len(day_labels) - 1:
            day_header.append("  ", style="dim")

    console.print(day_header)

    # Create time header rows (tens and ones digits)
    # First row: tens digits
    tens_row = Text()
    tens_row.append(" " * 20)  # Space for condition labels

    for day_idx, day_key in enumerate(day_labels):
        day_color = day_colors[day_idx % len(day_colors)]
        day_data = days_data[day_key]

        # Determine how many hours to show (same logic as date header)
        day_start_hour_for_display: int | None = None
        if day_data:
            first_data = day_data[0]
            if isinstance(first_data["timestamp"], datetime):
                first_ts = first_data["timestamp"]
                local_first_ts = first_ts.astimezone(tz) if tz else first_ts
                day_start_hour_for_display = local_first_ts.hour

        is_first_day_tens = day_idx == 0
        hours_to_show = len(day_data)
        is_full_day = hours_to_show >= 24

        # Same logic as date header
        if is_full_day:
            # Full day - ensure minimum hours for long form
            if tz:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=tz)
            else:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
            day_of_week_for_calc = day_dt_for_calc.strftime("%A")
            day_number_for_calc = day_dt_for_calc.day
            day_name_for_calc = f"{day_of_week_for_calc}, {day_number_for_calc}"
            name_length = len(day_name_for_calc)
            min_hours_needed = (name_length + 1) // 2
            hours_to_show = max(hours_to_show, min_hours_needed, 24)
            hours_to_show = min(hours_to_show, len(day_data))
        elif is_first_day_tens and day_start_hour_for_display is not None and day_start_hour_for_display <= 10:
            # First day starting on or before 10 AM - ensure minimum hours for long form
            if tz:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=tz)
            else:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
            day_of_week_for_calc = day_dt_for_calc.strftime("%A")
            day_number_for_calc = day_dt_for_calc.day
            day_name_for_calc = f"{day_of_week_for_calc}, {day_number_for_calc}"
            name_length = len(day_name_for_calc)
            min_hours_needed = (name_length + 1) // 2
            hours_to_show = max(hours_to_show, min_hours_needed)
            hours_to_show = min(hours_to_show, len(day_data))
        else:
            # Day starting after 10 AM - ensure minimum 3 hours for short form
            min_hours_for_short = 3
            hours_to_show = max(hours_to_show, min_hours_for_short)
            hours_to_show = min(hours_to_show, len(day_data))

        # Tens digit row for this day
        for i, data in enumerate(day_data[:hours_to_show]):
            ts_value = data["timestamp"]
            if not isinstance(ts_value, datetime):
                continue
            local_ts = ts_value.astimezone(tz) if tz else ts_value
            hour = local_ts.hour
            tens_digit = hour // 10
            tens_row.append(f"{tens_digit}", style=f"bold {day_color}")
            if i < hours_to_show - 1:  # Add spacing between hours
                tens_row.append(" ", style="dim")

        # Add spacing between days
        if day_idx < len(day_labels) - 1:
            tens_row.append("  ", style="dim")

    console.print(tens_row)

    # Second row: ones digits
    ones_row = Text()
    ones_row.append(" " * 20)

    for day_idx, day_key in enumerate(day_labels):
        day_color = day_colors[day_idx % len(day_colors)]
        day_data = days_data[day_key]

        # Determine how many hours to show (same logic as date header)
        day_start_hour_for_ones: int | None = None
        if day_data:
            first_data = day_data[0]
            if isinstance(first_data["timestamp"], datetime):
                first_ts = first_data["timestamp"]
                local_first_ts = first_ts.astimezone(tz) if tz else first_ts
                day_start_hour_for_ones = local_first_ts.hour

        is_first_day_ones = day_idx == 0
        hours_to_show = len(day_data)
        is_full_day = hours_to_show >= 24

        # Same logic as date header
        if is_full_day:
            # Full day - ensure minimum hours for long form
            if tz:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=tz)
            else:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
            day_of_week_for_calc = day_dt_for_calc.strftime("%A")
            day_number_for_calc = day_dt_for_calc.day
            day_name_for_calc = f"{day_of_week_for_calc}, {day_number_for_calc}"
            name_length = len(day_name_for_calc)
            min_hours_needed = (name_length + 1) // 2
            hours_to_show = max(hours_to_show, min_hours_needed, 24)
            hours_to_show = min(hours_to_show, len(day_data))
        elif is_first_day_ones and day_start_hour_for_ones is not None and day_start_hour_for_ones <= 10:
            # First day starting on or before 10 AM - ensure minimum hours for long form
            if tz:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=tz)
            else:
                day_dt_for_calc = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
            day_of_week_for_calc = day_dt_for_calc.strftime("%A")
            day_number_for_calc = day_dt_for_calc.day
            day_name_for_calc = f"{day_of_week_for_calc}, {day_number_for_calc}"
            name_length = len(day_name_for_calc)
            min_hours_needed = (name_length + 1) // 2
            hours_to_show = max(hours_to_show, min_hours_needed)
            hours_to_show = min(hours_to_show, len(day_data))
        else:
            # Day starting after 10 AM - ensure minimum 3 hours for short form
            min_hours_for_short = 3
            hours_to_show = max(hours_to_show, min_hours_for_short)
            hours_to_show = min(hours_to_show, len(day_data))

        # Ones digit row for this day
        for i, data in enumerate(day_data[:hours_to_show]):
            ts_value = data["timestamp"]
            if not isinstance(ts_value, datetime):
                continue
            local_ts = ts_value.astimezone(tz) if tz else ts_value
            hour = local_ts.hour
            ones_digit = hour % 10
            ones_row.append(f"{ones_digit}", style=f"bold {day_color}")
            if i < hours_to_show - 1:  # Add spacing between hours
                ones_row.append(" ", style="dim")

        # Add spacing between days
        if day_idx < len(day_labels) - 1:
            ones_row.append("  ", style="dim")

    console.print(ones_row)

    # Helper function for transparency color
    def get_transparency_color_wrapper(value: object) -> tuple[str, str]:
        """Wrapper to handle transparency color lookup."""
        if isinstance(value, str):
            return get_transparency_color(value)
        return ("dim", "-")

    # Condition rows - each cell is uniform size with time visible
    conditions = [
        ("Cloud Cover", "cloud_cover", get_cloud_color),
        ("Transparency", "transparency", get_transparency_color_wrapper),
        ("Seeing", "seeing", get_seeing_color),
        ("Darkness", "darkness", get_darkness_color),
        ("Wind", "wind", get_wind_color),
        ("Humidity", "humidity", get_humidity_color),
        ("Temperature", "temperature", get_temp_color),
    ]

    for condition_name, field, color_func in conditions:
        # Create two rows per condition: one for the condition color, one for spacing
        condition_row = Text()
        # Match time header padding: 20 characters total (condition name + padding)
        # Left-align the condition name and pad to 20 chars total (including trailing space)
        condition_row.append(f"{condition_name:<20}", style="bold")  # Left-aligned, padded to exactly 20 chars

        for day_idx, day_key in enumerate(day_labels):
            day_data = days_data[day_key]
            day_color = day_colors[day_idx % len(day_colors)]

            # Determine how many hours to show (same logic as date/time headers)
            day_start_hour_for_grid: int | None = None
            if day_data:
                first_data = day_data[0]
                if isinstance(first_data["timestamp"], datetime):
                    first_ts = first_data["timestamp"]
                    local_first_ts = first_ts.astimezone(tz) if tz else first_ts
                    day_start_hour_for_grid = local_first_ts.hour

            is_first_day_grid = day_idx == 0
            hours_to_show_grid = len(day_data)
            is_full_day_grid = hours_to_show_grid >= 24

            if is_full_day_grid:
                # Full day - ensure minimum hours for long form
                if tz:
                    day_dt_for_grid = datetime.fromisoformat(day_key).replace(tzinfo=tz)
                else:
                    day_dt_for_grid = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
                day_of_week_for_grid = day_dt_for_grid.strftime("%A")
                day_number_for_grid = day_dt_for_grid.day
                day_name_for_grid = f"{day_of_week_for_grid}, {day_number_for_grid}"
                name_length_grid = len(day_name_for_grid)
                min_hours_needed_grid = (name_length_grid + 1) // 2
                hours_to_show_grid = max(hours_to_show_grid, min_hours_needed_grid, 24)
                hours_to_show_grid = min(hours_to_show_grid, len(day_data))
            elif is_first_day_grid and day_start_hour_for_grid is not None and day_start_hour_for_grid <= 10:
                # First day starting on or before 10 AM - ensure minimum hours for long form
                if tz:
                    day_dt_for_grid = datetime.fromisoformat(day_key).replace(tzinfo=tz)
                else:
                    day_dt_for_grid = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
                day_of_week_for_grid = day_dt_for_grid.strftime("%A")
                day_number_for_grid = day_dt_for_grid.day
                day_name_for_grid = f"{day_of_week_for_grid}, {day_number_for_grid}"
                name_length_grid = len(day_name_for_grid)
                min_hours_needed_grid = (name_length_grid + 1) // 2
                hours_to_show_grid = max(hours_to_show_grid, min_hours_needed_grid)
                hours_to_show_grid = min(hours_to_show_grid, len(day_data))
            else:
                # Day starting after 10 AM - ensure minimum 3 hours for short form
                min_hours_for_short = 3
                hours_to_show_grid = max(hours_to_show_grid, min_hours_for_short)
                hours_to_show_grid = min(hours_to_show_grid, len(day_data))

            # Grid cells should align with time digits
            # The time header shows tens and ones digits on separate rows
            # Cells should align with the ones digit row (bottom row)

            for i, data in enumerate(day_data[:hours_to_show_grid]):
                value = data.get(field)
                # Handle seeing separately since it can be None (too cloudy)
                if field == "seeing":
                    if value is None:
                        color, _label = get_seeing_color(None)
                    elif isinstance(value, (int, float)):
                        color, _label = color_func(float(value))
                    else:
                        color, _label = ("dim", "-")
                elif value is not None:
                    if field == "cloud_cover" and isinstance(value, (int, float)):
                        color, _label = color_func(float(value))
                    elif field == "darkness":
                        if value is None:
                            # get_darkness_color accepts None
                            color, _label = get_darkness_color(None)
                        elif isinstance(value, (int, float)):
                            color, _label = color_func(float(value))
                        else:
                            color, _label = ("dim", "-")
                    elif field in ("wind", "humidity", "temperature"):
                        if value is None:
                            # These functions accept None
                            if field == "wind":
                                color, _label = get_wind_color(None)
                            elif field == "humidity":
                                color, _label = get_humidity_color(None)
                            else:  # temperature
                                color, _label = get_temp_color(None)
                        elif isinstance(value, (int, float)):
                            color, _label = color_func(float(value))
                        else:
                            color, _label = ("dim", "-")
                    else:
                        # For transparency, value should be a string
                        if field == "transparency" and isinstance(value, str):
                            color, _label = get_transparency_color_wrapper(value)
                        else:
                            color, _label = ("dim", "-")
                else:
                    color, _label = ("dim", "-")

                # Create a uniform cell: use full block with background color
                # Each cell is 1 character wide, we'll use █ with the condition color
                condition_row.append("█", style=color)

                if i < hours_to_show_grid - 1:  # Add spacing between hours (match time header spacing)
                    condition_row.append(" ", style="dim")

            # Add spacing between days
            if day_idx < len(day_labels) - 1:
                condition_row.append("  ", style="dim")

        console.print(condition_row)

    # Legend with colored text
    console.print("\n[bold]Legend:[/bold]")

    # Cloud Cover legend with all 11 levels - background colors with white text
    # Add 20 chars padding to align with grid cells (matching condition name area)
    cloud_legend_parts = ["[dim]Cloud Cover:[/dim]", " " * (18 - len("Cloud Cover:"))]
    # Order: Overcast, 90%, 80%, 70%, 60%, 50%, 40%, 30%, 20%, 10%, Clear
    cloud_levels = [
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
    ]
    for color, label in cloud_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        cloud_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(cloud_legend_parts))

    # Transparency legend with all 6 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    transparency_legend_parts = ["[dim]Transparency:[/dim]", " " * (18 - len("Transparency:"))]
    # Order: Too cloudy, Poor, Below Average, Average, Above average, Transparent
    transparency_levels = [
        ("white", "Too cloudy to forecast"),
        ("#808080", "Poor"),
        ("#4080A0", "Below Average"),
        ("#0066AA", "Average"),
        ("#0033AA", "Above average"),
        ("#0000FF", "Transparent"),
    ]
    for color, label in transparency_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        transparency_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(transparency_legend_parts))
    # Seeing legend with all 6 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    seeing_legend_parts = ["[dim]Seeing:[/dim]", " " * (18 - len("Seeing:"))]
    # Order: Too cloudy, Bad, Poor, Average, Good, Excellent
    seeing_levels = [
        ("white", "Too cloudy to forecast"),
        ("#808080", "Bad"),
        ("#4080A0", "Poor"),
        ("#0066AA", "Average"),
        ("#0033AA", "Good"),
        ("#0000FF", "Excellent"),
    ]
    for color, label in seeing_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        seeing_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(seeing_legend_parts))
    # Darkness legend with all 15 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    darkness_legend_parts = ["[dim]Darkness:[/dim]", " " * (18 - len("Darkness:"))]
    # Order: -4, -3, -2, -1, 0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5
    darkness_levels = [
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
    ]
    for color, label in darkness_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        darkness_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(darkness_legend_parts))
    # Wind legend with all 6 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    wind_legend_parts = ["[dim]Wind:[/dim]", " " * (18 - len("Wind:"))]
    # Order: 0-5 mph, 6-11 mph, 12-16 mph, 17-28 mph, 29-45 mph, >45 mph
    wind_levels = [
        ("#004080", "0-5 mph"),  # Darkest blue - Calm
        ("#2060A0", "6-11 mph"),  # Darker blue
        ("#4080C0", "12-16 mph"),  # Medium blue
        ("#80C0E0", "17-28 mph"),  # Light blue or teal
        ("#E0E0E0", "29-45 mph"),  # Light grey
        ("white", ">45 mph"),  # White or very light grey
    ]
    for color, label in wind_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        wind_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(wind_legend_parts))
    # Humidity legend with all 16 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    humidity_legend_parts = ["[dim]Humidity:[/dim]", " " * (18 - len("Humidity:"))]
    # Order: <25%, 25-30%, 30-35%, 35-40%, 40-45%, 45-50%, 50-55%, 55-60%, 60-65%, 65-70%, 70-75%, 75-80%, 80-85%, 85-90%, 90-95%, 95-100%
    humidity_levels = [
        ("#0000FF", "<25%"),  # Very dark blue
        ("#0022FF", "25-30%"),  # Medium-dark blue
        ("#0044FF", "30-35%"),  # Medium blue
        ("#0066FF", "35-40%"),  # Lighter medium blue
        ("#0080FF", "40-45%"),  # Light blue
        ("#00AAFF", "45-50%"),  # Light teal/greenish-blue
        ("#00FFFF", "50-55%"),  # Bright cyan/turquoise
        ("#00FF80", "55-60%"),  # Light mint green
        ("#00FF00", "60-65%"),  # Vibrant green
        ("#80FF00", "65-70%"),  # Yellow-green
        ("#FFFF00", "70-75%"),  # Bright yellow
        ("#FF8800", "75-80%"),  # Orange
        ("#FF4400", "80-85%"),  # Bright red-orange
        ("#FF0000", "85-90%"),  # Pure red
        ("#A00000", "90-95%"),  # Slightly darker red
        ("#800000", "95-100%"),  # Deep rich red
    ]
    for color, label in humidity_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        humidity_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(humidity_legend_parts))
    # Temperature legend with all 19 levels - background colors with appropriate text colors
    # Add 20 chars padding to align with grid cells (matching condition name area)
    temp_legend_parts = ["[dim]Temperature:[/dim]", " " * (18 - len("Temperature:"))]
    # Order: < -40F, -40F to -31F, -30F to -21F, -21F to -12F, -12F to -3F, -3F to 5F, 5F to 14F, 14F to 23F, 23F to 32F, 32F to 41F, 41F to 50F, 50F to 59F, 59F to 68F, 68F to 77F, 77F to 86F, 86F to 95F, 95F to 104F, 104F to 113F, >113F
    temp_levels = [
        ("#FF00FF", "< -40°F"),  # Magenta
        ("#0000FF", "-40--31°F"),  # Dark Blue
        ("#0022FF", "-30--21°F"),  # Deep Blue
        ("#0044FF", "-21--12°F"),  # Medium Blue
        ("#0066FF", "-12--3°F"),  # Royal Blue
        ("#0080FF", "-3-5°F"),  # Light Blue
        ("#00FFFF", "5-14°F"),  # Cyan
        ("#00FFAA", "14-23°F"),  # Light Teal
        ("white", "23-32°F"),  # White
        ("#00FF80", "32-41°F"),  # Medium Green
        ("#80FF00", "41-50°F"),  # Lime Green
        ("#FFFF00", "50-59°F"),  # Yellow
        ("#FFAA00", "59-68°F"),  # Orange-Yellow
        ("#FF8800", "68-77°F"),  # Orange
        ("#FF4400", "77-86°F"),  # Red-Orange
        ("#FF0000", "86-95°F"),  # Bright Red
        ("#A00000", "95-104°F"),  # Dark Red
        ("#800000", "104-113°F"),  # Maroon
        ("#808080", ">113°F"),  # Grey
    ]
    for color, label in temp_levels:
        # Automatically choose black or white text based on background luminance
        text_color = _get_text_color_for_background(color)
        temp_legend_parts.append(f"[{text_color} on {color}]{label}[/{text_color} on {color}]")
    console.print(" ".join(temp_legend_parts))
    console.print("\n[dim]Note: Each block represents one hour. Time shown in 24-hour format (tens digit above, ones digit below).[/dim]")

