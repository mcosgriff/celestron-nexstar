"""
Weather Commands

Display current weather conditions for the observer location.
"""

import asyncio
import logging
from datetime import UTC

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.api.location.weather import (
    WeatherData,
    assess_observing_conditions,
    calculate_seeing_conditions,
    fetch_historical_weather_climatology,
    fetch_hourly_weather_forecast,
    fetch_weather,
)
from celestron_nexstar.cli.utils.output import print_error


logger = logging.getLogger(__name__)


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Weather information commands", cls=SortedCommandsGroup)
console = Console()


def _get_current_weather_with_cache(location: ObserverLocation) -> WeatherData:
    """
    Get current weather data, using cache if available, otherwise fetching from API.

    This is a convenience wrapper around fetch_weather() which now handles
    database caching internally using current location and current time.

    Args:
        location: Observer location

    Returns:
        WeatherData with current conditions
    """
    # fetch_weather() now handles database checking and storage internally
    return asyncio.run(fetch_weather(location))


@app.command("current", rich_help_panel="Weather Information")
def show_current_weather(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Display current weather conditions for the observer location.

    Uses cached data if available (within the last hour), otherwise fetches
    from the Open-Meteo API and stores the result in the database.

    Examples:
        nexstar weather current
        nexstar weather current --json
    """
    try:
        location = get_observer_location()
        weather = _get_current_weather_with_cache(location)

        if json_output:
            import json

            output = {
                "location": {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "name": location.name,
                },
                "weather": {
                    "temperature_f": weather.temperature_c,  # Field name is misleading, value is in Fahrenheit
                    "dew_point_f": weather.dew_point_f,
                    "humidity_percent": weather.humidity_percent,
                    "cloud_cover_percent": weather.cloud_cover_percent,
                    "wind_speed_mph": weather.wind_speed_ms,  # Field name is misleading, value is in mph
                    "visibility_km": weather.visibility_km,
                    "condition": weather.condition,
                    "last_updated": weather.last_updated,
                    "error": weather.error,
                },
            }

            # Add seeing conditions
            if not weather.error:
                seeing_score = calculate_seeing_conditions(weather)
                status, warning = assess_observing_conditions(weather)
                output["weather"]["seeing_score"] = seeing_score
                output["weather"]["observing_status"] = status
                output["weather"]["observing_warning"] = warning

            console.print(json.dumps(output, indent=2))
            return

        # Display formatted output
        location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
        console.print(f"\n[bold cyan]Current Weather: {location_name}[/bold cyan]\n")

        if weather.error:
            print_error(f"Weather data unavailable: {weather.error}")
            raise typer.Exit(code=1) from None

        # Create weather table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Parameter", style="cyan", width=20)
        table.add_column("Value", style="green")

        # Temperature
        if weather.temperature_c is not None:
            table.add_row("Temperature", f"{weather.temperature_c:.1f}°F")

        # Dew Point
        if weather.dew_point_f is not None:
            table.add_row("Dew Point", f"{weather.dew_point_f:.1f}°F")

        # Humidity
        if weather.humidity_percent is not None:
            table.add_row("Humidity", f"{weather.humidity_percent:.0f}%")

        # Cloud Cover
        if weather.cloud_cover_percent is not None:
            cloud_cover = weather.cloud_cover_percent
            match cloud_cover:
                case c if c < 20:
                    cloud_str = f"[green]{c:.0f}%[/green] (Clear)"
                case c if c < 50:
                    cloud_str = f"[yellow]{c:.0f}%[/yellow] (Partly Cloudy)"
                case c if c < 80:
                    cloud_str = f"[yellow]{c:.0f}%[/yellow] (Mostly Cloudy)"
                case _:
                    cloud_str = f"[red]{cloud_cover:.0f}%[/red] (Overcast)"
            table.add_row("Cloud Cover", cloud_str)

        # Wind Speed
        if weather.wind_speed_ms is not None:
            wind_mph = weather.wind_speed_ms  # Already in mph
            match wind_mph:
                case w if w < 10:
                    wind_str = f"[green]{w:.1f} mph[/green] (Calm)"
                case w if w < 20:
                    wind_str = f"[yellow]{w:.1f} mph[/yellow] (Moderate)"
                case _:
                    wind_str = f"[red]{wind_mph:.1f} mph[/red] (Strong)"
            table.add_row("Wind Speed", wind_str)

        # Visibility
        if weather.visibility_km is not None:
            visibility_mi = weather.visibility_km * 0.621371
            table.add_row("Visibility", f"{visibility_mi:.1f} mi")

        # Condition
        if weather.condition:
            table.add_row("Condition", weather.condition)

        # Last Updated
        if weather.last_updated:
            table.add_row("Last Updated", weather.last_updated)

        console.print(table)

        # Observing Conditions Assessment
        console.print()
        status, warning = assess_observing_conditions(weather)
        seeing_score = calculate_seeing_conditions(weather)

        # Status indicator
        match status:
            case "excellent":
                status_color = "green"
                status_icon = "✓"
            case "good":
                status_color = "cyan"
                status_icon = "○"
            case "fair":
                status_color = "yellow"
                status_icon = "⚠"
            case "poor":
                status_color = "red"
                status_icon = "✗"
            case _:
                status_color = "dim"
                status_icon = "?"

        console.print(
            f"[bold]Observing Conditions:[/bold] [{status_color}]{status_icon} {status.title()}[/{status_color}]"
        )
        console.print(f"[dim]{warning}[/dim]")

        # Seeing Conditions
        console.print()
        if seeing_score >= 80:
            seeing_text = "[green]Excellent[/green]"
        elif seeing_score >= 60:
            seeing_text = "[yellow]Good[/yellow]"
        elif seeing_score >= 40:
            seeing_text = "[yellow]Fair[/yellow]"
        else:
            seeing_text = "[red]Poor[/red]"

        console.print(f"[bold]Seeing Conditions:[/bold] {seeing_text} ({seeing_score:.0f}/100)")
        console.print("[dim]Atmospheric steadiness for image sharpness[/dim]")

        console.print()

    except Exception as e:
        print_error(f"Failed to get weather: {e}")
        raise typer.Exit(code=1) from e


@app.command("today", rich_help_panel="Weather Information")
def show_today_weather(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Display hourly weather forecast for today (next 24 hours).

    Uses cached data if available, otherwise fetches from the Open-Meteo API
    and stores the result in the database.

    Examples:
        nexstar weather today
        nexstar weather today --json
    """
    try:
        from zoneinfo import ZoneInfo

        from timezonefinder import TimezoneFinder

        location = get_observer_location()
        forecasts = asyncio.run(fetch_hourly_weather_forecast(location, hours=24))

        if not forecasts:
            print_error("Weather forecast not available")
            raise typer.Exit(code=1) from None

        # Get timezone for location
        try:
            tf = TimezoneFinder()
            tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
            tz = ZoneInfo(tz_name) if tz_name else None
        except Exception:
            tz = None

        if json_output:
            import json

            output = {
                "location": {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "name": location.name,
                },
                "forecast": [
                    {
                        "timestamp": f.timestamp.isoformat(),
                        "temperature_f": f.temperature_f,
                        "dew_point_f": f.dew_point_f,
                        "humidity_percent": f.humidity_percent,
                        "cloud_cover_percent": f.cloud_cover_percent,
                        "wind_speed_mph": f.wind_speed_mph,
                        "seeing_score": f.seeing_score,
                    }
                    for f in forecasts
                ],
            }
            console.print(json.dumps(output, indent=2))
            return

        # Display formatted output
        location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
        console.print(f"\n[bold cyan]Weather Forecast Today: {location_name}[/bold cyan]\n")

        # Create hourly forecast table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Time", style="cyan")
        table.add_column("Temp", justify="right")
        table.add_column("Clouds", justify="right")
        table.add_column("Wind", justify="right")
        table.add_column("Seeing", justify="right")
        table.add_column("Quality")

        for forecast in forecasts[:24]:  # Show next 24 hours
            # Format time
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            if tz:
                local_time = forecast_ts.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = forecast_ts.strftime("%I:%M %p UTC")

            # Temperature
            temp_str = "-"
            if forecast.temperature_f is not None:
                temp_str = f"{forecast.temperature_f:.0f}°F"

            # Cloud cover
            cloud_str = "-"
            if forecast.cloud_cover_percent is not None:
                cloud_cover = forecast.cloud_cover_percent
                if cloud_cover < 20:
                    cloud_str = f"[green]{cloud_cover:.0f}%[/green]"
                elif cloud_cover < 50 or cloud_cover < 80:
                    cloud_str = f"[yellow]{cloud_cover:.0f}%[/yellow]"
                else:
                    cloud_str = f"[red]{cloud_cover:.0f}%[/red]"

            # Wind speed
            wind_str = "-"
            if forecast.wind_speed_mph is not None:
                wind_mph = forecast.wind_speed_mph
                if wind_mph < 10:
                    wind_str = f"[green]{wind_mph:.0f} mph[/green]"
                elif wind_mph < 20:
                    wind_str = f"[yellow]{wind_mph:.0f} mph[/yellow]"
                else:
                    wind_str = f"[red]{wind_mph:.0f} mph[/red]"

            # Seeing score
            seeing = forecast.seeing_score
            seeing_str = f"{seeing:.0f}/100"

            # Quality
            match seeing:
                case s if s >= 80:
                    quality = "[green]Excellent[/green]"
                case s if s >= 60:
                    quality = "[yellow]Good[/yellow]"
                case s if s >= 40:
                    quality = "[dim]Fair[/dim]"
                case _:
                    quality = "[red]Poor[/red]"

            table.add_row(time_str, temp_str, cloud_str, wind_str, seeing_str, quality)

        console.print(table)
        console.print()

    except Exception as e:
        print_error(f"Failed to get weather forecast: {e}")
        raise typer.Exit(code=1) from e


@app.command("next-3-days", rich_help_panel="Weather Information")
def show_next_3_days_weather(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Display daily weather summary for the next 3 days.

    Uses cached data if available, otherwise fetches from the Open-Meteo API
    and stores the result in the database.

    Examples:
        nexstar weather next-3-days
        nexstar weather next-3-days --json
    """
    try:
        from collections import defaultdict
        from zoneinfo import ZoneInfo

        from timezonefinder import TimezoneFinder

        location = get_observer_location()
        forecasts = asyncio.run(fetch_hourly_weather_forecast(location, hours=72))  # 3 days = 72 hours

        if not forecasts:
            print_error("Weather forecast not available")
            raise typer.Exit(code=1) from None

        # Get timezone for location
        try:
            tf = TimezoneFinder()
            tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
            tz = ZoneInfo(tz_name) if tz_name else None
        except Exception:
            tz = None

        # Group forecasts by day
        daily_weather = defaultdict(list)
        for forecast in forecasts:
            forecast_ts = forecast.timestamp
            if forecast_ts.tzinfo is None:
                forecast_ts = forecast_ts.replace(tzinfo=UTC)
            elif forecast_ts.tzinfo != UTC:
                forecast_ts = forecast_ts.astimezone(UTC)

            if tz:
                local_time = forecast_ts.astimezone(tz)
                day_key = local_time.date()
            else:
                day_key = forecast_ts.date()
            daily_weather[day_key].append(forecast)

        if json_output:
            import json

            daily_summaries = []
            for day, day_forecasts in sorted(daily_weather.items())[:3]:
                temps = [f.temperature_f for f in day_forecasts if f.temperature_f is not None]
                clouds = [f.cloud_cover_percent for f in day_forecasts if f.cloud_cover_percent is not None]
                seeing_scores = [f.seeing_score for f in day_forecasts]

                daily_summaries.append(
                    {
                        "date": day.isoformat(),
                        "temperature_avg_f": sum(temps) / len(temps) if temps else None,
                        "temperature_min_f": min(temps) if temps else None,
                        "temperature_max_f": max(temps) if temps else None,
                        "cloud_cover_avg_percent": sum(clouds) / len(clouds) if clouds else None,
                        "seeing_avg": sum(seeing_scores) / len(seeing_scores) if seeing_scores else None,
                    }
                )

            output = {
                "location": {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "name": location.name,
                },
                "daily_forecast": daily_summaries,
            }
            console.print(json.dumps(output, indent=2))
            return

        # Display formatted output
        location_name = location.name or f"{location.latitude:.4f}°, {location.longitude:.4f}°"
        console.print(f"\n[bold cyan]Weather Forecast - Next 3 Days: {location_name}[/bold cyan]\n")

        # Create daily summary table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Date", style="cyan")
        table.add_column("Temp", justify="right")
        table.add_column("Clouds", justify="right")
        table.add_column("Seeing", justify="right")
        table.add_column("Quality")

        for day, day_forecasts in sorted(daily_weather.items())[:3]:
            # Calculate daily averages
            temps = [f.temperature_f for f in day_forecasts if f.temperature_f is not None]
            clouds = [f.cloud_cover_percent for f in day_forecasts if f.cloud_cover_percent is not None]
            seeing_scores = [f.seeing_score for f in day_forecasts]

            # Format date
            date_str = day.strftime("%a %b %d")

            # Temperature range
            temp_str = "-"
            if temps:
                temp_min = min(temps)
                temp_max = max(temps)
                temp_str = f"{temp_min:.0f}°F" if temp_min == temp_max else f"{temp_min:.0f}-{temp_max:.0f}°F"

            # Average cloud cover
            cloud_str = "-"
            if clouds:
                avg_cloud = sum(clouds) / len(clouds)
                if avg_cloud < 20:
                    cloud_str = f"[green]{avg_cloud:.0f}%[/green]"
                elif avg_cloud < 50 or avg_cloud < 80:
                    cloud_str = f"[yellow]{avg_cloud:.0f}%[/yellow]"
                else:
                    cloud_str = f"[red]{avg_cloud:.0f}%[/red]"

            # Average seeing
            seeing_str = "-"
            quality = "[dim]-[/dim]"
            if seeing_scores:
                avg_seeing = sum(seeing_scores) / len(seeing_scores)
                seeing_str = f"{avg_seeing:.0f}/100"

                if avg_seeing >= 80:
                    quality = "[green]Excellent[/green]"
                elif avg_seeing >= 60:
                    quality = "[yellow]Good[/yellow]"
                elif avg_seeing >= 40:
                    quality = "[dim]Fair[/dim]"
                else:
                    quality = "[red]Poor[/red]"

            table.add_row(date_str, temp_str, cloud_str, seeing_str, quality)

        console.print(table)
        console.print()

    except Exception as e:
        print_error(f"Failed to get weather forecast: {e}")
        raise typer.Exit(code=1) from e


@app.command("historical", rich_help_panel="Weather Information")
def show_historical_weather(
    months: int = typer.Option(12, "--months", "-m", help="Number of months to show (3, 6, or 12, default: 12)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Display historical cloud cover climatology for the observer location.

    Shows monthly average cloud cover statistics based on historical weather data
    from Open-Meteo Historical API. Data is cached in the database for future use.

    Examples:
        nexstar weather historical
        nexstar weather historical --months 6
        nexstar weather historical --months 3 --json
    """
    try:
        location = get_observer_location()

        # Validate months parameter
        match months:
            case 3 | 6 | 12:
                pass
            case _:
                print_error("Months must be 3, 6, or 12")
                raise typer.Exit(code=1) from None

        # Determine which months we need to show
        from datetime import datetime

        current_month = datetime.now(UTC).month

        # Show last N months (rolling window)
        months_to_show = []
        for i in range(months):
            month_num = ((current_month - 1 - i) % 12) + 1
            months_to_show.append(month_num)
        months_to_show.reverse()  # Show in chronological order
        required_months = set(months_to_show)

        # Fetch historical data (will use cache if available, only fetch missing months)
        console.print("[dim]Checking database for historical weather data...[/dim]")
        monthly_stats = asyncio.run(fetch_historical_weather_climatology(location, required_months=required_months))

        if not monthly_stats:
            print_error("Historical weather data not available")
            raise typer.Exit(code=1) from None

        if json_output:
            import json

            output = {
                "location": {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "name": location.name,
                },
                "historical_data": [
                    {
                        "month": month,
                        "month_name": _get_month_name(month),
                        "avg_cloud_cover_percent": monthly_stats[month].get("avg"),
                        "min_cloud_cover_percent": monthly_stats[month].get("min"),
                        "max_cloud_cover_percent": monthly_stats[month].get("max"),
                        "p25_cloud_cover_percent": monthly_stats[month].get("p25"),
                        "p75_cloud_cover_percent": monthly_stats[month].get("p75"),
                    }
                    for month in months_to_show
                    if month in monthly_stats
                ],
            }
            console.print(json.dumps(output, indent=2))
            return

        # Display formatted output
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"
        console.print(f"\n[bold cyan]Historical Cloud Cover Climatology for {location_name}[/bold cyan]")
        console.print("[dim]Monthly averages based on historical weather data (2000-present)[/dim]")
        console.print(f"[dim]Showing last {months} months[/dim]\n")

        # Create table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Month", style="cyan")
        table.add_column("Average", justify="right", style="white")
        table.add_column("Range (Best-Worst)", justify="right", style="dim")
        table.add_column("25th-75th Percentile", justify="right", style="dim")
        table.add_column("Quality", style="green")

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        for month in months_to_show:
            if month not in monthly_stats:
                continue

            stats = monthly_stats[month]
            avg = stats.get("avg")
            min_val = stats.get("min")
            max_val = stats.get("max")
            p25 = stats.get("p25")
            p75 = stats.get("p75")

            month_name = month_names[month - 1]

            # Format average
            avg_str = f"{avg:.1f}%" if avg is not None else "[dim]-[/dim]"

            # Format range
            if min_val is not None and max_val is not None:
                range_str = f"{min_val:.0f}%-{max_val:.0f}%"
            else:
                range_str = "[dim]-[/dim]"

            # Format percentile range
            percentile_str = f"{p25:.0f}%-{p75:.0f}%" if p25 is not None and p75 is not None else "[dim]-[/dim]"

            # Format quality based on average
            if avg is not None:
                if avg < 30:
                    quality = "[green]Excellent[/green]"
                elif avg < 50:
                    quality = "[yellow]Good[/yellow]"
                elif avg < 70:
                    quality = "[yellow]Fair[/yellow]"
                else:
                    quality = "[red]Poor[/red]"
            else:
                quality = "[dim]-[/dim]"

            table.add_row(month_name, avg_str, range_str, percentile_str, quality)

        console.print(table)

        console.print("\n[bold]Understanding the Data:[/bold]")
        console.print("  • [dim]Average: Mean cloud cover percentage for the month[/dim]")
        console.print("  • [dim]Range: Minimum (best case) to Maximum (worst case) cloud cover[/dim]")
        console.print("  • [dim]25th-75th Percentile: Typical range (50% of days fall within this range)[/dim]")
        console.print("  • [dim]Quality: Overall assessment based on average cloud cover[/dim]")
        console.print(
            "\n[dim]💡 Tip: Lower cloud cover percentages indicate clearer skies and better observing conditions.[/dim]"
        )
        console.print(
            "[dim]💡 Tip: Use this data to plan Milky Way viewing trips - look for months with lower averages.[/dim]\n"
        )

    except Exception as e:
        print_error(f"Failed to get historical weather data: {e}")
        raise typer.Exit(code=1) from e


def _get_month_name(month: int) -> str:
    """Get full month name from month number."""
    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return month_names[month - 1] if 1 <= month <= 12 else "Unknown"
