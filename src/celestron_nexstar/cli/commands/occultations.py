"""
Asteroid Occultation Commands

Find star occultations by asteroids.
"""

from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from ...api.occultations import get_upcoming_occultations
from ...api.observer import get_observer_location
from ...cli.utils.export import create_file_console, export_to_text

app = typer.Typer(help="Asteroid occultation predictions")
console = Console()


@app.command("next")
def show_next(
    months: int = typer.Option(12, "--months", "-m", help="Number of months ahead to search (default: 12)"),
    min_magnitude: float = typer.Option(8.0, "--min-mag", help="Maximum star magnitude to include (default: 8.0)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """Find upcoming asteroid occultations."""
    location = get_observer_location()
    if not location:
        console.print("[red]Error: No observer location set. Use 'nexstar location set' to configure your location.[/red]")
        raise typer.Exit(1)

    occultations = get_upcoming_occultations(location, months_ahead=months, min_magnitude=min_magnitude)

    if not occultations:
        console.print("\n[yellow]Asteroid occultation predictions require specialized databases.[/yellow]")
        console.print("[dim]Full implementation coming soon. Check IOTA (International Occultation Timing Association)[/dim]")
        console.print("[dim]for detailed occultation predictions: https://www.lunar-occultations.com/iota/[/dim]\n")
        return

    if export:
        from datetime import datetime
        from ...api.observer import get_observer_location

        location = get_observer_location()
        if location.name:
            location_short = location.name.lower().replace(" ", "_").replace(",", "").replace(".", "")
            location_short = location_short.replace("_(default)", "").replace("_observatory", "")
            location_short = location_short[:20]
        else:
            location_short = "unknown"

        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"nexstar_occultations_{location_short}_{date_str}_next.txt"
        export_path_obj = Path(export_path) if export_path else Path(filename)
        file_console = create_file_console()
        # Would show content here
        content = file_console.file.getvalue()
        file_console.file.close()

        from ...cli.utils.export import export_to_text

        export_to_text(content, export_path_obj)
        console.print(f"\n[green]✓[/green] Exported to {export_path_obj}")
        return

    console.print("\n[bold]Upcoming Occultations:[/bold]")
    console.print("[dim]Full implementation coming soon[/dim]\n")


if __name__ == "__main__":
    app()

