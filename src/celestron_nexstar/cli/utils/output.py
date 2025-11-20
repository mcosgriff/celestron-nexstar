"""
CLI Output Utilities

Rich console formatting utilities for beautiful CLI output.
"""

from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


if TYPE_CHECKING:
    from rich.console import RenderableType


# Create console with unicode detection
# If terminal doesn't support unicode properly, Rich will use ASCII alternatives
console = Console()

# Detect if we can safely use unicode symbols
# Rich handles this internally, but we can check explicitly
_use_unicode = console.is_terminal and not console.legacy_windows


def print_success(message: str) -> None:
    """Print success message in green."""
    # ✓ is widely supported (U+2713)
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print error message in red."""
    # ✗ is widely supported (U+2717)
    console.print(f"[red]✗[/red] {message}", style="red")


def print_warning(message: str) -> None:
    """Print warning message in yellow."""
    # ⚠ is widely supported (U+26A0)
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print info message in blue."""
    # Use U+2139 (info symbol) instead of U+1F6C8 (circled info emoji)
    # U+2139 is part of the Letterlike Symbols block and widely supported
    # U+1F6C8 is a newer emoji that requires emoji font support
    info_icon = "\u2139" if _use_unicode else "i"
    console.print(f"[blue]{info_icon}[/blue] {message}")


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
    table.add_column("Coordinate System", style="cyan")
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

    panel = Panel.fit(
        info_text,
        title="[bold]Telescope Information[/bold]",
        border_style="green",
        width=calculate_panel_width(info_text, console),
    )
    console.print(panel)


def calculate_panel_width(content: "RenderableType", console: Console | None = None) -> int | None:
    """
    Calculate optimal panel width based on content size.

    Measures the content width and adds padding for panel borders and title,
    while capping at terminal width to prevent overflow.

    Args:
        content: Rich renderable content (Text, str, etc.)
        console: Console instance to get terminal width. If None, uses global console.

    Returns:
        Calculated width or None if console width is unavailable
    """
    if console is None:
        console = globals()["console"]

    # Get plain text representation to measure width
    match content:
        case obj if hasattr(obj, "plain"):
            # Rich Text objects have a plain property
            plain_text = obj.plain
        case str() as s:
            plain_text = s
        case _:
            # Fallback to string representation
            plain_text = str(content)

    # Find the longest line
    content_lines = plain_text.split("\n")
    max_line_length = max(len(line) for line in content_lines) if content_lines else 0

    # Add padding for panel borders and title (roughly 15 chars)
    # Cap at terminal width to prevent overflow on small terminals
    if hasattr(console, "width"):
        width = getattr(console, "width", None)
        if width is not None and isinstance(width, int):
            result = min(max_line_length + 15, width)
            return int(result)
    return None


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
