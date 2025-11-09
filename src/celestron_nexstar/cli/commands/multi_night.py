"""
Multi-Night Planning Commands

Compare observing conditions across multiple nights and find the best night for specific objects.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table
from timezonefinder import TimezoneFinder

from ...api.catalogs import get_object_by_name
from ...api.observation_planner import ObservationPlanner
from ...api.utils import calculate_lst, ra_dec_to_alt_az
from ...api.visibility import assess_visibility


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


@app.command("week")
def show_week() -> None:
    """Compare observing conditions for the next 7 nights."""
    try:
        planner = ObservationPlanner()
        
        # Get location
        from ...api.observer import get_observer_location
        location = get_observer_location()
        if location is None:
            console.print("[red]No location set. Use 'nexstar location set' command.[/red]")
            raise typer.Exit(code=1) from None
        
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
        
        for night_date, sunset, conditions in nights:
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


@app.command("best-night")
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
            console.print("[red]No location set. Use 'nexstar location set' command.[/red]")
            raise typer.Exit(code=1) from None
        
        lat, lon = location.latitude, location.longitude
        tz = _get_local_timezone(lat, lon)
        
        console.print(f"\n[bold cyan]Best Night for {obj.name}[/bold cyan]")
        if obj.common_name:
            console.print(f"[dim]{obj.common_name}[/dim]")
        console.print(f"[dim]Checking next {days} nights...[/dim]\n")
        
        # Check each night
        nights_data = []
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
                    alt, az = ra_dec_to_alt_az(obj.ra_hours, obj.dec_degrees, lat, lon, transit_time)
                    
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
        nights_data.sort(key=lambda n: n["score"], reverse=True)
        
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
            date = night["date"]
            if tz:
                local_date = date.astimezone(tz)
                date_str = local_date.strftime("%a %b %d")
            else:
                date_str = date.strftime("%a %b %d")
            
            score = night["score"] * 100
            conditions = night["conditions"]
            
            # Quality
            quality = conditions.observing_quality_score
            if quality > 0.75:
                quality_text = "[green]Excellent[/green]"
            elif quality > 0.60:
                quality_text = "[yellow]Good[/yellow]"
            elif quality > 0.40:
                quality_text = "[dim]Fair[/dim]"
            else:
                quality_text = "[red]Poor[/red]"
            
            seeing = f"{conditions.seeing_score:.0f}/100"
            clouds = f"{conditions.weather.cloud_cover_percent or 100.0:.0f}%"
            
            # Transit time
            transit = night["transit_time"]
            if tz:
                transit_local = transit.astimezone(tz)
                transit_str = transit_local.strftime("%I:%M %p")
            else:
                transit_str = transit.strftime("%I:%M %p")
            
            altitude = f"{night['altitude']:.0f}°"
            moon = f"{conditions.moon_illumination * 100:.0f}%"
            
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
        best = nights_data[0]
        best_date = best["date"]
        if tz:
            best_local = best_date.astimezone(tz)
            best_date_str = best_local.strftime("%A, %B %d, %Y")
        else:
            best_date_str = best_date.strftime("%A, %B %d, %Y")
        
        # Format transit time for summary
        best_transit = best["transit_time"]
        if tz:
            best_transit_local = best_transit.astimezone(tz)
            best_transit_str = best_transit_local.strftime("%I:%M %p")
        else:
            best_transit_str = best_transit.strftime("%I:%M %p")
        
        console.print(f"\n[bold green]Best Night:[/bold green] {best_date_str}")
        console.print(f"  Score: {best['score']*100:.0f}/100")
        console.print(f"  Transit: {best_transit_str} at {best['altitude']:.0f}° altitude")
        console.print(f"  Seeing: {best['conditions'].seeing_score:.0f}/100")
        console.print(f"  Cloud Cover: {best['conditions'].weather.cloud_cover_percent or 100.0:.0f}%")
        console.print(f"  Moon: {best['conditions'].moon_illumination*100:.0f}% illuminated")
        
        if best["visibility"].is_visible:
            console.print(f"  [green]✓ Object will be visible[/green]")
        else:
            console.print(f"  [red]✗ Object may not be visible: {', '.join(best['visibility'].reasons)}[/red]")
        
    except Exception as e:
        console.print(f"[red]Error finding best night:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None

