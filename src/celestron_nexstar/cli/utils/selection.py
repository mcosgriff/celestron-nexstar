"""
Interactive Selection Utilities

Helper functions for prompting user to select from multiple options.
"""

from rich.prompt import Prompt
from rich.table import Table

from celestron_nexstar.api.catalogs import CelestialObject

from .output import console


def select_object(objects: list[CelestialObject], query: str) -> CelestialObject | None:
    """
    Interactively select an object from a list of matches.

    Args:
        objects: List of celestial objects to choose from
        query: Original search query (for display)

    Returns:
        Selected object or None if user cancels
    """
    if len(objects) == 0:
        return None

    if len(objects) == 1:
        return objects[0]

    # Show results table
    console.print(f"\n[yellow]Multiple objects found matching '{query}':[/yellow]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=5)
    table.add_column("Name", style="cyan", width=15)
    table.add_column("Type", style="yellow", width=10)
    table.add_column("RA", style="green", width=12)
    table.add_column("Dec", style="green", width=12)
    table.add_column("Mag", style="blue", width=6)
    table.add_column("Description", style="white")

    for i, obj in enumerate(objects, 1):
        ra_str = f"{obj.ra_hours:.2f}h"
        dec_str = f"{obj.dec_degrees:+.1f}°"
        mag_str = f"{obj.magnitude:.1f}" if obj.magnitude else "N/A"
        desc = obj.common_name or obj.description or ""

        table.add_row(str(i), obj.name, obj.object_type, ra_str, dec_str, mag_str, desc[:40])

    console.print(table)
    console.print()

    # Prompt for selection
    while True:
        try:
            choice = Prompt.ask(
                "[cyan]Select object number (or 'q' to cancel)[/cyan]",
                default="1",
            )

            if choice.lower() in ["q", "quit", "cancel", "exit"]:
                console.print("[yellow]Selection cancelled[/yellow]")
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(objects):
                selected = objects[idx]
                console.print(f"[green]Selected:[/green] {selected.name}")
                return selected
            else:
                console.print(f"[red]Invalid selection. Please enter 1-{len(objects)}[/red]")

        except ValueError:
            console.print("[red]Invalid input. Please enter a number or 'q' to cancel[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Selection cancelled[/yellow]")
            return None
