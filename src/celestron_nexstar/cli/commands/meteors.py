"""
Enhanced Meteor Shower Commands

Find meteor showers with moon phase predictions and best viewing windows.
"""

from datetime import datetime
from pathlib import Path

import typer
from click import Context
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from ...api.meteor_shower_predictions import (
    MeteorShowerPrediction,
    get_best_viewing_windows,
    get_enhanced_meteor_predictions,
)
from ...api.observer import ObserverLocation, get_observer_location
from ...cli.utils.export import FileConsole, create_file_console, export_to_text


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Enhanced meteor shower predictions", cls=SortedCommandsGroup)
console = Console()


def _generate_export_filename(command: str = "meteors") -> Path:
    """Generate export filename for meteor commands."""
    from ...api.observer import get_observer_location

    location = get_observer_location()

    if location.name:
        location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]
    else:
        location_short = "unknown"

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_meteors_{location_short}_{date_str}_{command}.txt"
    return Path(filename)


@app.command("next")
def show_next(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find upcoming meteor showers with moon phase predictions."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    predictions = get_enhanced_meteor_predictions(location, months_ahead=months)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("next")
        file_console = create_file_console()
        _show_predictions_content(file_console, location, predictions, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_predictions_content(console, location, predictions, months)


@app.command("best")
def show_best(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    min_quality: str = typer.Option(
        "good", "--min-quality", help="Minimum viewing quality: excellent, good, fair, poor (default: good)"
    ),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find meteor showers with best viewing conditions (minimal moonlight)."""
    location = get_observer_location()
    if not location:
        console.print(
            "[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]"
        )
        raise typer.Exit(1)

    predictions = get_best_viewing_windows(location, months_ahead=months, min_quality=min_quality)

    if export:
        export_path_obj = Path(export_path) if export_path else _generate_export_filename("best")
        file_console = create_file_console()
        _show_predictions_content(file_console, location, predictions, months)
        content = file_console.file.getvalue()
        file_console.file.close()

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    _show_predictions_content(console, location, predictions, months)


def _show_predictions_content(
    output_console: Console | FileConsole,
    location: ObserverLocation,
    predictions: list[MeteorShowerPrediction],
    months: int,
) -> None:
    """Display meteor shower predictions."""
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

    output_console.print(f"\n[bold cyan]Meteor Shower Predictions for {location_name}[/bold cyan]")
    output_console.print(f"[dim]Searching next {months} months[/dim]\n")

    if not predictions:
        output_console.print("[yellow]No meteor showers found in the forecast period.[/yellow]\n")
        return

    # Get timezone for formatting
    try:
        _tz_finder = TimezoneFinder()
        tz_name = _tz_finder.timezone_at(lat=location.latitude, lng=location.longitude)
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:
        tz = None

    # Display predictions in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Shower")
    table.add_column("ZHR", justify="right")
    table.add_column("Adjusted ZHR", justify="right")
    table.add_column("Moon", justify="right")
    table.add_column("Quality")

    for pred in predictions:
        # Format date
        if tz:
            date_local = pred.date.astimezone(tz)
            date_str = date_local.strftime("%Y-%m-%d")
        else:
            date_str = pred.date.strftime("%Y-%m-%d UTC")

        # Format ZHR
        zhr_str = str(pred.zhr_peak)
        adj_zhr_str = f"{pred.zhr_adjusted:.0f}"

        # Format moon
        moon_str = f"{pred.moon_illumination:.0%}"

        # Format quality with color
        quality_colors = {
            "excellent": "[bold bright_green]Excellent[/bold bright_green]",
            "good": "[green]Good[/green]",
            "fair": "[yellow]Fair[/yellow]",
            "poor": "[red]Poor[/red]",
        }
        quality_str = quality_colors.get(pred.viewing_quality, pred.viewing_quality)

        table.add_row(date_str, pred.shower.name, zhr_str, adj_zhr_str, moon_str, quality_str)

    output_console.print(table)

    # Show details
    output_console.print("\n[bold]Prediction Details:[/bold]")
    for pred in predictions[:10]:  # Show first 10
        if tz:
            date_local = pred.date.astimezone(tz)
            date_str = date_local.strftime("%B %d, %Y")
        else:
            date_str = pred.date.strftime("%B %d, %Y UTC")

        output_console.print(f"\n  [bold]{pred.shower.name}[/bold] - {date_str}")
        output_console.print(f"    Peak ZHR: {pred.zhr_peak} → Adjusted: {pred.zhr_adjusted:.0f} (moon impact)")
        output_console.print(
            f"    Moon: {pred.moon_illumination:.0%} illuminated at {pred.moon_altitude:.0f}° altitude"
        )
        output_console.print(f"    Radiant: {pred.radiant_altitude:.0f}° altitude")
        output_console.print(f"    Quality: {pred.viewing_quality.capitalize()} - {pred.notes}")

    output_console.print("\n[bold]Viewing Tips:[/bold]")
    output_console.print("  • [green]ZHR = Zenithal Hourly Rate (meteors per hour under ideal conditions)[/green]")
    output_console.print("  • [yellow]Adjusted ZHR accounts for moonlight interference[/yellow]")
    output_console.print("  • [green]Best viewing: After midnight when radiant is highest[/green]")
    output_console.print("  • [dim]Don't stare at the radiant - meteors appear throughout the sky[/dim]")
    output_console.print("  • [dim]Give your eyes 20+ minutes to adapt to darkness[/dim]")
    output_console.print("\n[dim]💡 Tip: Use 'nexstar meteors best' to find showers with minimal moonlight![/dim]\n")


if __name__ == "__main__":
    app()
