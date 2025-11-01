"""
CLI Output Utilities

Rich console formatting utilities for beautiful CLI output.
"""

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text


console = Console()


def print_success(message: str) -> None:
    """Print success message in green."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print error message in red."""
    console.print(f"[red]✗[/red] {message}", style="red")


def print_warning(message: str) -> None:
    """Print warning message in yellow."""
    console.print(f"[yellow]⚠[/yellow] {message}", style="yellow")


def print_info(message: str) -> None:
    """Print info message in blue."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_position_table(
    ra_hours: float | None = None,
    dec_degrees: float | None = None,
    azimuth: float | None = None,
    altitude: float | None = None,
) -> None:
    """
    Print telescope position in a formatted table.

    Args:
        ra_hours: Right Ascension in hours
        dec_degrees: Declination in degrees
        azimuth: Azimuth in degrees
        altitude: Altitude in degrees
    """
    table = Table(title="Telescope Position", show_header=True, header_style="bold magenta")
    table.add_column("Coordinate System", style="cyan", width=20)
    table.add_column("Value", style="green")

    if ra_hours is not None and dec_degrees is not None:
        ra_text = format_ra(ra_hours)
        dec_text = format_dec(dec_degrees)
        table.add_row("Right Ascension", ra_text)
        table.add_row("Declination", dec_text)

    if azimuth is not None and altitude is not None:
        table.add_row("Azimuth", f"{azimuth:.4f}°")
        table.add_row("Altitude", f"{altitude:.4f}°")

    console.print(table)


def format_ra(ra_hours: float) -> str:
    """
    Format Right Ascension for display.

    Args:
        ra_hours: RA in hours (0-24)

    Returns:
        Formatted string (e.g., "12h 30m 45.6s (12.5127h)")
    """
    hours = int(ra_hours)
    minutes = int((ra_hours - hours) * 60)
    seconds = ((ra_hours - hours) * 60 - minutes) * 60
    return f"{hours}h {minutes}m {seconds:.1f}s ({ra_hours:.4f}h)"


def format_dec(dec_degrees: float) -> str:
    """
    Format Declination for display.

    Args:
        dec_degrees: Dec in degrees (-90 to +90)

    Returns:
        Formatted string (e.g., "+45° 30' 15.2" (45.5042°)")
    """
    sign = "+" if dec_degrees >= 0 else "-"
    abs_dec = abs(dec_degrees)
    degrees = int(abs_dec)
    minutes = int((abs_dec - degrees) * 60)
    seconds = ((abs_dec - degrees) * 60 - minutes) * 60
    return f"{sign}{degrees}° {minutes}' {seconds:.1f}\" ({dec_degrees:+.4f}°)"


def print_telescope_info(model: int, firmware_major: int, firmware_minor: int) -> None:
    """
    Print telescope information in a panel.

    Args:
        model: Telescope model number
        firmware_major: Firmware major version
        firmware_minor: Firmware minor version
    """
    info_text = Text()
    info_text.append("Model: ", style="bold cyan")
    info_text.append(f"NexStar {model}SE\n", style="white")
    info_text.append("Firmware: ", style="bold cyan")
    info_text.append(f"{firmware_major}.{firmware_minor:02d}", style="white")

    panel = Panel(info_text, title="[bold]Telescope Information[/bold]", border_style="green")
    console.print(panel)


def print_json(data: dict[str, Any]) -> None:
    """Print data as JSON."""
    import json

    console.print_json(json.dumps(data))


def format_tracking_mode(mode_name: str) -> str:
    """
    Format tracking mode name for display.

    Args:
        mode_name: Mode name (e.g., "ALT_AZ", "EQ_NORTH")

    Returns:
        Formatted string (e.g., "Alt-Az", "EQ North")
    """
    mode_map = {
        "OFF": "Off",
        "ALT_AZ": "Alt-Az",
        "EQ_NORTH": "EQ North",
        "EQ_SOUTH": "EQ South",
    }
    return mode_map.get(mode_name, mode_name)
