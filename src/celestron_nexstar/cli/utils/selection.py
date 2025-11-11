"""
Interactive Selection Utilities

Helper functions for prompting user to select from multiple options.
"""

from collections.abc import Callable
from typing import TypeVar

from rich.prompt import Prompt
from rich.table import Table

from celestron_nexstar.api.catalogs import CelestialObject

from .output import console


T = TypeVar("T")


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


def select_from_list(
    items: list[T],
    title: str,
    display_func: Callable[[T], tuple[str, ...]] | None = None,
    headers: list[str] | None = None,
    current_item: T | None = None,
) -> T | None:
    """
    Generic interactive selection from a list of items.

    Args:
        items: List of items to select from
        title: Title to display above the selection table
        display_func: Function that takes an item and returns a tuple of strings for table columns.
                     If None, uses str(item) as a single column.
        headers: Column headers for the table. If None and display_func is provided, must match column count.
        current_item: Currently selected item (will be marked with *)

    Returns:
        Selected item or None if user cancels
    """
    if len(items) == 0:
        console.print("[yellow]No items available to select from[/yellow]")
        return None

    if len(items) == 1:
        return items[0]

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    # Determine column structure
    if display_func:
        sample_row = display_func(items[0])
        num_columns = len(sample_row)
        if headers is None:
            headers = [f"Column {i + 1}" for i in range(num_columns)]
        elif len(headers) != num_columns:
            raise ValueError(f"Number of headers ({len(headers)}) must match display_func output ({num_columns})")
    else:
        num_columns = 1
        headers = ["Item"]

    # Create table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right")

    for header in headers:
        table.add_column(header, style="cyan")

    # Populate table
    for i, item in enumerate(items, 1):
        # Check if this is the current item
        is_current = current_item is not None and item == current_item
        marker = "* " if is_current else "  "

        if display_func:
            row_data = display_func(item)
            # Apply marker to first column
            first_col = f"{marker}{row_data[0]}"
            if is_current:
                first_col = f"[bold]{first_col}[/bold]"
            table.add_row(str(i), first_col, *row_data[1:])
        else:
            item_str = f"{marker}{item}"
            if is_current:
                item_str = f"[bold]{item_str}[/bold]"
            table.add_row(str(i), item_str)

    console.print(table)
    console.print()

    # Prompt for selection
    while True:
        try:
            choice = Prompt.ask(
                "[cyan]Select number (or 'q' to cancel)[/cyan]",
                default="1" if current_item else None,
            )

            if choice.lower() in ["q", "quit", "cancel", "exit"]:
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(items):
                selected = items[idx]
                display_name = display_func(selected)[0] if display_func else str(selected)
                console.print(f"[green]Selected:[/green] {display_name}")
                return selected
            else:
                console.print(f"[red]Invalid selection. Please enter 1-{len(items)}[/red]")

        except ValueError:
            console.print("[red]Invalid input. Please enter a number or 'q' to cancel[/red]")
        except KeyboardInterrupt:
            return None
