"""
Binocular Viewing Commands

Shows what's visible tonight through binoculars including ISS passes,
constellations, asterisms, and meteor showers.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.compass import azimuth_to_compass_8point, format_object_path
from ...api.constellations import get_visible_asterisms, get_visible_constellations
from ...api.iss_tracking import get_iss_passes_cached
from ...api.models import get_db_session
from ...api.observer import get_observer_location
from ...api.meteor_showers import get_active_showers, get_peak_showers, get_radiant_position
from ...api.optics import COMMON_BINOCULARS
from ...api.sun_moon import calculate_sun_times


app = typer.Typer(help="Binocular viewing commands")
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


def _format_local_time(dt: datetime, lat: float, lon: float) -> str:
    """Format datetime in local timezone, falling back to UTC if timezone unavailable."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = _get_local_timezone(lat, lon)
    if tz:
        local_dt = dt.astimezone(tz)
        return local_dt.strftime("%I:%M %p")
    else:
        return dt.strftime("%I:%M %p UTC")


def _get_current_season(dt: datetime) -> str:
    """
    Get the current season based on date.
    
    Args:
        dt: Datetime to check
        
    Returns:
        Season name: "Spring", "Summer", "Fall", or "Winter"
    """
    month = dt.month
    
    # Simple month-based season determination
    # Spring: Mar, Apr, May
    # Summer: Jun, Jul, Aug
    # Fall: Sep, Oct, Nov
    # Winter: Dec, Jan, Feb
    if month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    elif month in (9, 10, 11):
        return "Fall"
    else:  # 12, 1, 2
        return "Winter"


@app.command("tonight")
def show_tonight(
    binoculars: str = typer.Option("10x50", "--model", "-m", help="Binocular model (e.g., 10x50, 7x50, 15x70)"),
) -> None:
    """
    Show what's visible tonight with binoculars.

    Displays ISS passes, visible constellations, asterisms, and active meteor showers
    optimized for binocular viewing. Uses your configured location.
    """
    try:
        # Validate binocular model
        if binoculars not in COMMON_BINOCULARS:
            console.print(f"[red]Unknown binocular model: {binoculars}[/red]")
            console.print(f"Available models: {', '.join(COMMON_BINOCULARS.keys())}")
            raise typer.Exit(code=1)

        optics = COMMON_BINOCULARS[binoculars]

        # Get location
        location = get_observer_location()
        if not location:
            console.print("[red]Error:[/red] No location configured. Use 'nexstar location set' first.")
            raise typer.Exit(code=1)

        lat, lon = location.latitude, location.longitude
        location_name = location.name or f"{lat:.2f}°, {lon:.2f}°"

        # Get current time and sunset/sunrise
        now = datetime.now(UTC)
        sun_times = calculate_sun_times(lat, lon, now)
        sunset = sun_times["sunset"]
        sunrise = sun_times["sunrise"]

        # Display header
        console.print(f"\n[bold cyan]Binocular Viewing for {location_name}[/bold cyan]")
        console.print(f"[dim]Using: {optics.display_name}[/dim]")
        console.print(f"[dim]Sunset: {_format_local_time(sunset, lat, lon)} | Sunrise: {_format_local_time(sunrise, lat, lon)}[/dim]\n")

        # ISS Passes
        console.print("[bold green]ISS Visible Passes[/bold green]")
        console.print("[dim]International Space Station passes visible from your location[/dim]\n")

        with get_db_session() as db:
            iss_passes = get_iss_passes_cached(lat, lon, start_time=now, days=7, min_altitude_deg=10.0, db_session=db)

        if iss_passes:
            table_iss = Table(expand=True)
            table_iss.add_column("Date", style="cyan", width=12)
            table_iss.add_column("Rise Time", style="green", width=12)
            table_iss.add_column("Max Alt", justify="right", width=10)
            table_iss.add_column("Path", style="dim")  # No width - will expand to fill space
            table_iss.add_column("Duration", justify="right", width=12)
            table_iss.add_column("Quality", width=12)

            for iss_pass in iss_passes[:10]:  # Show next 10 passes
                # Only show passes that are actually visible (sunlit)
                if not iss_pass.is_visible:
                    continue

                # Format date and time
                rise_time_str = _format_local_time(iss_pass.rise_time, lat, lon)
                date_str = iss_pass.rise_time.strftime("%a %b %d")

                # Format path
                path = format_object_path(
                    iss_pass.rise_azimuth_deg,
                    iss_pass.max_azimuth_deg,
                    iss_pass.max_altitude_deg,
                    iss_pass.set_azimuth_deg,
                )

                # Duration in minutes
                duration_min = iss_pass.duration_seconds // 60

                # Quality color
                quality = iss_pass.quality_rating
                if quality == "Excellent":
                    quality_text = "[green]Excellent[/green]"
                elif quality == "Very Good":
                    quality_text = "[green]Very Good[/green]"
                elif quality == "Good":
                    quality_text = "[yellow]Good[/yellow]"
                else:
                    quality_text = "[dim]Fair[/dim]"

                table_iss.add_row(
                    date_str,
                    rise_time_str,
                    f"{iss_pass.max_altitude_deg:.0f}°",
                    path,
                    f"{duration_min}m {iss_pass.duration_seconds % 60}s",
                    quality_text,
                )

            console.print(table_iss)
            console.print("[dim]Quality based on maximum altitude: Excellent >70°, Very Good >50°, Good >30°[/dim]")
        else:
            console.print("[yellow]No visible ISS passes in the next 7 days[/yellow]")

        console.print()

        # Meteor Showers
        console.print("[bold green]Active Meteor Showers[/bold green]")
        console.print("[dim]Best viewed with naked eye or binoculars for wide-field sweeping[/dim]\n")

        active_showers = get_active_showers(now)
        peak_showers = get_peak_showers(now, tolerance_days=3)

        if active_showers:
            table_showers = Table(expand=True)
            table_showers.add_column("Shower", style="bold", width=20)
            table_showers.add_column("Status", style="cyan", width=12)
            table_showers.add_column("ZHR", justify="right", width=8)
            table_showers.add_column("Radiant", style="dim", width=20)
            table_showers.add_column("Notes", style="dim")  # No width - will expand to fill space

            for shower in active_showers:
                # Check if at peak
                is_peak = shower in peak_showers
                status = "[green]At Peak[/green]" if is_peak else "Active"

                # Calculate radiant position at midnight
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if midnight < now:
                    midnight = midnight.replace(day=midnight.day + 1)
                alt, az = get_radiant_position(shower, lat, lon, midnight)

                radiant_dir = azimuth_to_compass_8point(az)
                radiant_text = f"{radiant_dir}, {alt:.0f}° high"

                # Peak date
                peak_date = f"{shower.peak_month}/{shower.peak_day}"
                notes = f"Peak: {peak_date}, {shower.velocity_km_s} km/s"

                table_showers.add_row(
                    shower.name,
                    status,
                    str(shower.zhr_peak),
                    radiant_text,
                    notes,
                )

            console.print(table_showers)
            console.print("[dim]ZHR = Zenithal Hourly Rate (meteors per hour under ideal conditions)[/dim]")
            console.print("[dim]Actual rates are typically 25-50% of ZHR due to non-ideal conditions[/dim]")
        else:
            console.print("[yellow]No major meteor showers currently active[/yellow]")

        console.print()

        # Visible Constellations
        console.print("[bold green]Prominent Constellations (Tonight)[/bold green]")
        console.print("[dim]Best constellations visible from your location[/dim]\n")

        # Calculate for midnight
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if midnight < now:
            midnight = midnight.replace(day=midnight.day + 1)

        visible_constellations = get_visible_constellations(lat, lon, midnight, min_altitude_deg=20.0)

        if visible_constellations:
            current_season = _get_current_season(now)
            
            table_const = Table(expand=True)
            table_const.add_column("Constellation", style="bold", width=15)
            table_const.add_column("Direction", justify="right", width=10)
            table_const.add_column("Altitude", justify="right", width=10)
            table_const.add_column("Season", style="dim", width=20)
            table_const.add_column("Highlights", style="dim")  # No width - will expand to fill space

            for constellation, alt, az in visible_constellations[:12]:  # Top 12
                direction = azimuth_to_compass_8point(az)

                description = constellation.description

                # Check if constellation is out of season
                season_display = constellation.season
                if constellation.season != current_season:
                    season_display = f"{constellation.season} (best in {constellation.season.lower()}, visible out of season)"

                table_const.add_row(
                    constellation.name,
                    direction,
                    f"{alt:.0f}°",
                    season_display,
                    description,
                )

            console.print(table_const)
            console.print("[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]")
        else:
            console.print("[yellow]No prominent constellations currently visible[/yellow]")

        console.print()

        # Visible Asterisms
        console.print("[bold green]Famous Star Patterns (Asterisms)[/bold green]")
        console.print("[dim]Easily recognizable patterns visible through binoculars[/dim]\n")

        visible_asterisms = get_visible_asterisms(lat, lon, midnight, min_altitude_deg=20.0)

        if visible_asterisms:
            table_ast = Table(expand=True)
            table_ast.add_column("Asterism", style="bold", width=20)
            table_ast.add_column("Direction", justify="right", width=10)
            table_ast.add_column("Altitude", justify="right", width=10)
            table_ast.add_column("Size", justify="right", width=8)
            table_ast.add_column("Description", style="dim")  # No width - will expand to fill space

            for asterism, alt, az in visible_asterisms[:10]:  # Top 10
                direction = azimuth_to_compass_8point(az)

                description = asterism.description or ""

                table_ast.add_row(
                    asterism.name,
                    direction,
                    f"{alt:.0f}°",
                    f"{asterism.size_degrees:.0f}°" if asterism.size_degrees else "—",
                    description,
                )

            console.print(table_ast)
            console.print("[dim]💡 Tip: Estimate altitude with your hand - hold arm outstretched: fist = 10°, thumb = 2°, pinky = 1°[/dim]")
        else:
            console.print("[yellow]No prominent asterisms currently visible[/yellow]")

        console.print("\n[bold cyan]Viewing Tips for Binoculars:[/bold cyan]")
        console.print("  • Allow 20-30 minutes for dark adaptation")
        console.print("  • Use a tripod or stable support for extended viewing")
        console.print(f"  • Your {optics.display_name} have a {optics.exit_pupil_mm:.1f}mm exit pupil")
        console.print(f"  • Light gathering: {optics.light_gathering_power:.0f}x more than naked eye")
        console.print("  • Start with wide-field asterisms, then zoom in on constellations")
        console.print("  • For meteor showers, sweep the sky slowly around the radiant\n")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
