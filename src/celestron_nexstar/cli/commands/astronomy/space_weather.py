"""
Space Weather Commands

Display current space weather conditions from NOAA SWPC including
NOAA scales, solar activity, geomagnetic conditions, and alerts.
"""

import typer
from click import Context
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from celestron_nexstar.api.events.space_weather import (
    NOAAScale,
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
    if scale.level == 0:
        return f"[green]{scale.scale_type}{scale.level} ({scale.display_name})[/green]"
    elif scale.level <= 2:
        return f"[yellow]{scale.scale_type}{scale.level} ({scale.display_name})[/yellow]"
    elif scale.level <= 3:
        return f"[red]{scale.scale_type}{scale.level} ({scale.display_name})[/red]"
    else:
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
            if conditions.kp_index >= 7:
                kp_display = f"[bold red]{conditions.kp_index:.1f}[/bold red]"
            elif conditions.kp_index >= 5:
                kp_display = f"[yellow]{conditions.kp_index:.1f}[/yellow]"
            else:
                kp_display = f"[green]{conditions.kp_index:.1f}[/green]"

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
            if conditions.solar_wind_bz < -5:
                bz_display = f"[green]{conditions.solar_wind_bz:.1f} nT[/green] (favorable for aurora)"
            elif conditions.solar_wind_bz < 0:
                bz_display = f"[yellow]{conditions.solar_wind_bz:.1f} nT[/yellow]"
            else:
                bz_display = f"[white]{conditions.solar_wind_bz:.1f} nT[/white]"

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
                Panel(alert_text, title="[bold yellow]Space Weather Alerts[/bold yellow]", border_style="yellow")
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

        console.print(Panel(info_text, title="[dim]Information[/dim]", border_style="dim"))
        console.print()

        if conditions.last_updated:
            console.print(f"[dim]Last updated: {conditions.last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")

    except Exception as e:
        console.print(f"[red]✗[/red] Error fetching space weather data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e
