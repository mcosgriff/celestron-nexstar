"""
Space Weather Commands

Display current space weather conditions from NOAA SWPC including
NOAA scales, solar activity, geomagnetic conditions, and alerts.
"""

from collections import defaultdict
from datetime import datetime

import typer
from click import Context
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from celestron_nexstar.api.events.space_weather import (
    NOAAScale,
    OvationAuroraForecast,
    get_ovation_aurora_forecast,
    get_space_weather_conditions,
)


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Space weather conditions and alerts", cls=SortedCommandsGroup)
console = Console()


def _format_scale(scale: NOAAScale | None) -> str:
    """Format NOAA scale for display."""
    if scale is None:
        return "[dim]-[/dim]"
    match scale.level:
        case 0:
            return f"[green]{scale.scale_type}{scale.level} ({scale.display_name})[/green]"
        case level if level <= 2:
            return f"[yellow]{scale.scale_type}{scale.level} ({scale.display_name})[/yellow]"
        case level if level <= 3:
            return f"[red]{scale.scale_type}{scale.level} ({scale.display_name})[/red]"
        case _:
            return f"[bold red]{scale.scale_type}{scale.level} ({scale.display_name})[/bold red]"


def _format_value(value: float | None, unit: str = "", precision: int = 1) -> str:
    """Format a value with unit, or show dash if None."""
    if value is None:
        return "[dim]-[/dim]"
    return f"{value:.{precision}f}{unit}"


@app.command()
def status() -> None:
    """Display current space weather conditions."""
    console.print("\n[bold cyan]Space Weather Conditions[/bold cyan]")
    console.print("[dim]Data from NOAA Space Weather Prediction Center[/dim]\n")

    try:
        conditions = get_space_weather_conditions()

        # NOAA Scales Table
        scales_table = Table(title="NOAA Space Weather Scales", show_header=True, header_style="bold")
        scales_table.add_column("Scale", style="cyan", width=15)
        scales_table.add_column("Level", justify="center", width=20)
        scales_table.add_column("Description", style="white")

        scales_table.add_row(
            "R-Scale (Radio Blackouts)",
            _format_scale(conditions.r_scale),
            "Solar flare impacts on radio communications",
        )
        scales_table.add_row(
            "S-Scale (Radiation Storms)", _format_scale(conditions.s_scale), "Solar radiation storm impacts"
        )
        scales_table.add_row(
            "G-Scale (Geomagnetic)",
            _format_scale(conditions.g_scale),
            "Geomagnetic storm impacts on power grids, aurora",
        )

        console.print(scales_table)
        console.print()

        # Geomagnetic Activity
        geomag_table = Table(title="Geomagnetic Activity", show_header=True, header_style="bold")
        geomag_table.add_column("Parameter", style="cyan", width=25)
        geomag_table.add_column("Value", justify="right", style="white")

        kp_display = _format_value(conditions.kp_index, "", 1)
        if conditions.kp_index is not None:
            match conditions.kp_index:
                case kp if kp >= 7:
                    kp_display = f"[bold red]{kp:.1f}[/bold red]"
                case kp if kp >= 5:
                    kp_display = f"[yellow]{kp:.1f}[/yellow]"
                case kp:
                    kp_display = f"[green]{kp:.1f}[/green]"

        geomag_table.add_row("Kp Index", kp_display)
        geomag_table.add_row("Ap Index", _format_value(conditions.ap_index, "", 0))

        console.print(geomag_table)
        console.print()

        # Solar Wind
        solar_wind_table = Table(title="Solar Wind", show_header=True, header_style="bold")
        solar_wind_table.add_column("Parameter", style="cyan", width=25)
        solar_wind_table.add_column("Value", justify="right", style="white")

        # Color code Bz (negative is good for aurora)
        bz_display = _format_value(conditions.solar_wind_bz, " nT", 1)
        if conditions.solar_wind_bz is not None:
            match conditions.solar_wind_bz:
                case bz if bz < -5:
                    bz_display = f"[green]{bz:.1f} nT[/green] (favorable for aurora)"
                case bz if bz < 0:
                    bz_display = f"[yellow]{bz:.1f} nT[/yellow]"
                case bz:
                    bz_display = f"[white]{bz:.1f} nT[/white]"

        solar_wind_table.add_row("Speed", _format_value(conditions.solar_wind_speed, " km/s", 0))
        solar_wind_table.add_row("Magnetic Field (Bt)", _format_value(conditions.solar_wind_bt, " nT", 1))
        solar_wind_table.add_row("Bz Component", bz_display)
        solar_wind_table.add_row("Density", _format_value(conditions.solar_wind_density, " particles/cm³", 1))

        console.print(solar_wind_table)
        console.print()

        # Solar Activity
        solar_table = Table(title="Solar Activity", show_header=True, header_style="bold")
        solar_table.add_column("Parameter", style="cyan", width=25)
        solar_table.add_column("Value", justify="right", style="white")

        xray_display = _format_value(conditions.xray_flux, " W/m²", 2)
        if conditions.xray_class:
            xray_display = f"{conditions.xray_class} ({xray_display})"

        solar_table.add_row("10.7cm Radio Flux", _format_value(conditions.radio_flux_107, " sfu", 1))
        solar_table.add_row("X-ray Flux", xray_display)

        console.print(solar_table)
        console.print()

        # Alerts
        if conditions.alerts:
            alert_text = Text()
            alert_text.append("Active Alerts:\n", style="bold yellow")
            for alert in conditions.alerts:
                alert_text.append(f"  ⚠ {alert}\n", style="yellow")
            console.print(
                Panel.fit(alert_text, title="[bold yellow]Space Weather Alerts[/bold yellow]", border_style="yellow")
            )
            console.print()

        # Information panel
        info_text = Text()
        info_text.append("About NOAA Scales:\n", style="bold")
        info_text.append("  • R-Scale: Radio blackouts from solar flares (R1-R5)\n", style="white")
        info_text.append("  • S-Scale: Solar radiation storms (S1-S5)\n", style="white")
        info_text.append("  • G-Scale: Geomagnetic storms (G1-G5)\n", style="white")
        info_text.append("\n")
        info_text.append("Aurora Visibility:\n", style="bold")
        info_text.append("  • G3+ storms often produce visible aurora at mid-latitudes\n", style="white")
        info_text.append("  • Negative Bz values enhance aurora activity\n", style="white")
        info_text.append("  • Use 'nexstar aurora tonight' for detailed aurora forecast\n", style="dim")

        console.print(Panel.fit(info_text, title="[dim]Information[/dim]", border_style="dim"))
        console.print()

        if conditions.last_updated:
            console.print(f"[dim]Last updated: {conditions.last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")

    except Exception as e:
        console.print(f"[red]✗[/red] Error fetching space weather data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e


@app.command()
def ovation() -> None:
    """Display Ovation aurora forecast (30-minute predictions)."""
    console.print("\n[bold cyan]Ovation Aurora Forecast[/bold cyan]")
    console.print("[dim]30-minute aurora probability predictions from NOAA SWPC[/dim]\n")

    try:
        forecasts = get_ovation_aurora_forecast()

        if not forecasts:
            console.print("[yellow]⚠[/yellow] Ovation aurora forecast data not available.\n")
            return

        # Group forecasts by timestamp
        forecasts_by_time: defaultdict[datetime, list[OvationAuroraForecast]] = defaultdict(list)
        for forecast in forecasts:
            forecasts_by_time[forecast.timestamp].append(forecast)

        # Display forecasts for each time period
        for timestamp in sorted(forecasts_by_time):
            time_forecasts = forecasts_by_time[timestamp]
            console.print(f"[bold]Forecast for {timestamp.strftime('%Y-%m-%d %H:%M UTC')}[/bold]")

            # Create a summary table
            forecast_table = Table(show_header=True, header_style="bold")
            forecast_table.add_column("Latitude", style="cyan", justify="right")
            forecast_table.add_column("Longitude", style="cyan", justify="right")
            forecast_table.add_column("Probability", justify="right", style="white")
            forecast_table.add_column("Type", style="dim")

            # Show a sample of forecasts (limit to avoid overwhelming output)
            # Sort by probability (intensity) and show top locations
            for forecast in sorted(time_forecasts, key=lambda x: x.probability, reverse=True)[:20]:
                # Display as percentage (probability is normalized 0.0-1.0)
                prob_percent = forecast.probability * 100
                prob_display = f"{prob_percent:.1f}%"
                if forecast.probability >= 0.7:
                    prob_display = f"[bold green]{prob_percent:.1f}%[/bold green]"
                elif forecast.probability >= 0.5:
                    prob_display = f"[yellow]{prob_percent:.1f}%[/yellow]"
                elif forecast.probability >= 0.3:
                    prob_display = f"[dim]{prob_percent:.1f}%[/dim]"

                forecast_table.add_row(
                    f"{forecast.latitude:.2f}°",
                    f"{forecast.longitude:.2f}°",
                    prob_display,
                    forecast.forecast_type,
                )

            console.print(forecast_table)
            console.print()

            if len(time_forecasts) > 20:
                console.print(f"[dim]... and {len(time_forecasts) - 20} more forecast points[/dim]\n")

        console.print(
            "[dim]💡 Tip: Values represent aurora intensity (0-100%) based on Ovation model predictions. "
            "Higher values indicate greater likelihood of visible aurora at that location.[/dim]\n"
        )

    except Exception as e:
        console.print(f"[red]✗[/red] Error fetching Ovation aurora forecast: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e
