"""
Catalog Commands

Commands for searching and managing celestial object catalogs.
"""

from typing import Literal

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from celestron_nexstar.api.catalogs import (
    ALL_CATALOGS,
    get_all_objects,
    get_catalog,
    get_object_by_name,
    search_objects,
)

from ..utils.output import console, format_dec, format_ra, print_error, print_info, print_json
from ..utils.selection import select_object
from ..utils.state import ensure_connected


app = typer.Typer(help="Celestial object catalog commands")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (name, type, description)"),
    catalog: str | None = typer.Option(None, help="Catalog to search (messier, bright_stars, planets, or 'all')"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Search object catalogs by name or description.

    Example:
        nexstar catalog search andromeda
        nexstar catalog search nebula
        nexstar catalog search M31
        nexstar catalog search orion --catalog messier
    """
    try:
        # Search for objects
        catalog_name = None if catalog == "all" else catalog
        results = search_objects(query, catalog_name)

        if not results:
            print_info(f"No objects found matching '{query}'")
            return

        if json_output:
            print_json(
                {
                    "results": [
                        {
                            "name": obj.name,
                            "common_name": obj.common_name,
                            "ra_hours": obj.ra_hours,
                            "dec_degrees": obj.dec_degrees,
                            "magnitude": obj.magnitude,
                            "type": obj.object_type,
                            "catalog": obj.catalog,
                            "description": obj.description,
                            "match_type": match_type,
                        }
                        for obj, match_type in results
                    ]
                }
            )
        else:
            # Create results table
            table = Table(
                title=f"Search Results for '{query}' ({len(results)} found)",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Name", style="cyan", width=15)
            table.add_column("Type", style="yellow", width=10)
            table.add_column("RA", style="green", width=12)
            table.add_column("Dec", style="green", width=12)
            table.add_column("Mag", style="blue", width=6)
            table.add_column("Match", style="dim", width=16)
            table.add_column("Description", style="white")

            for obj, match_type in results:
                ra_str = f"{obj.ra_hours:.2f}h"
                dec_str = f"{obj.dec_degrees:+.1f}°"
                mag_str = f"{obj.magnitude:.1f}" if obj.magnitude else "N/A"
                desc = obj.common_name or obj.description or ""

                table.add_row(obj.name, obj.object_type, ra_str, dec_str, mag_str, match_type, desc[:30])

            console.print(table)
            print_info("Use 'nexstar catalog info <name>' for detailed information")

    except Exception as e:
        print_error(f"Search failed: {e}")
        raise typer.Exit(code=1) from None


@app.command("list")
def list_catalog(
    catalog: Literal[
        "messier", "bright_stars", "asterisms", "ngc", "caldwell", "planets", "moons", "all"
    ] = typer.Option("all", help="Catalog to list"),
    object_type: str | None = typer.Option(
        None, "--type", help="Filter by type (star, galaxy, nebula, asterism, etc.)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    List objects in a catalog.

    Example:
        nexstar catalog list --catalog messier
        nexstar catalog list --catalog bright_stars
        nexstar catalog list --type nebula
        nexstar catalog list --catalog messier --type galaxy
    """
    try:
        # Get objects
        objects = get_all_objects() if catalog == "all" else get_catalog(catalog)

        # Filter by type if specified
        if object_type:
            # Ensure object_type is a string (handle Typer's OptionInfo edge case)
            type_str = str(object_type).lower() if object_type else None
            if type_str:
                objects = [obj for obj in objects if obj.object_type == type_str]

        # Update planetary positions for dynamic objects
        objects = [obj.with_current_position() for obj in objects]

        if not objects:
            print_info("No objects found")
            return

        if json_output:
            print_json(
                {
                    "objects": [
                        {
                            "name": obj.name,
                            "common_name": obj.common_name,
                            "ra_hours": obj.ra_hours,
                            "dec_degrees": obj.dec_degrees,
                            "magnitude": obj.magnitude,
                            "type": obj.object_type,
                            "catalog": obj.catalog,
                            "description": obj.description,
                        }
                        for obj in objects
                    ]
                }
            )
        else:
            # Create table
            catalog_display = catalog.replace("_", " ").title()
            type_filter = f" ({object_type})" if object_type else ""
            table = Table(
                title=f"{catalog_display} Catalog{type_filter} ({len(objects)} objects)",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Name", style="cyan", width=15)
            table.add_column("Type", style="yellow", width=10)
            if catalog == "moons":
                table.add_column("Parent Planet", style="yellow", width=15)
            table.add_column("RA", style="green", width=12)
            table.add_column("Dec", style="green", width=12)
            table.add_column("Mag", style="blue", width=6)
            table.add_column("Description", style="white")

            for obj in objects:
                ra_str = f"{obj.ra_hours:.2f}h"
                dec_str = f"{obj.dec_degrees:+.1f}°"
                mag_str = f"{obj.magnitude:.1f}" if obj.magnitude else "N/A"
                desc = obj.common_name or obj.description or ""

                if catalog == "moons":
                    table.add_row(obj.name, obj.object_type, obj.parent_planet, ra_str, dec_str, mag_str, desc[:40])
                else:
                    table.add_row(obj.name, obj.object_type, ra_str, dec_str, mag_str, desc[:40])

            console.print(table)

    except Exception as e:
        print_error(f"Failed to list catalog: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def info(
    object_name: str = typer.Argument(..., help="Object name (e.g., M31, Polaris, Andromeda)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    Get detailed information about a celestial object.

    Uses fuzzy matching - if multiple objects match, you'll be prompted to choose.

    Example:
        nexstar catalog info M31
        nexstar catalog info Polaris
        nexstar catalog info "Andromeda Galaxy"
        nexstar catalog info nebula  # Will show multiple matches
        nexstar catalog info M42 --json
    """
    try:
        # Get matching objects (fuzzy search)
        matches = get_object_by_name(object_name)

        if not matches:
            print_error(f"No objects found matching '{object_name}'")
            print_info("Try 'nexstar catalog search <query>' to find objects")
            raise typer.Exit(code=1) from None

        # If multiple matches, let user select
        obj = select_object(matches, object_name)
        if obj is None:
            raise typer.Exit(code=1) from None

        if json_output:
            print_json(
                {
                    "name": obj.name,
                    "common_name": obj.common_name,
                    "ra_hours": obj.ra_hours,
                    "dec_degrees": obj.dec_degrees,
                    "ra_formatted": format_ra(obj.ra_hours),
                    "dec_formatted": format_dec(obj.dec_degrees),
                    "magnitude": obj.magnitude,
                    "type": obj.object_type,
                    "catalog": obj.catalog,
                    "description": obj.description,
                }
            )
        else:
            # Create detailed info panel
            info_text = Text()

            # Name and common name
            info_text.append(f"{obj.name}", style="bold cyan")
            if obj.common_name:
                info_text.append(f" ({obj.common_name})", style="cyan")
            info_text.append("\n\n")

            # Coordinates
            info_text.append("Coordinates:\n", style="bold yellow")
            info_text.append(f"  RA:  {format_ra(obj.ra_hours)}\n", style="green")
            info_text.append(f"  Dec: {format_dec(obj.dec_degrees)}\n", style="green")
            info_text.append("\n")

            # Metadata
            info_text.append("Properties:\n", style="bold yellow")
            info_text.append(f"  Type:     {obj.object_type}\n", style="white")
            if obj.magnitude:
                info_text.append(f"  Magnitude: {obj.magnitude:.1f}\n", style="white")
            info_text.append(f"  Catalog:  {obj.catalog}\n", style="white")

            # Description
            if obj.description:
                info_text.append("\n")
                info_text.append("Description:\n", style="bold yellow")
                info_text.append(f"  {obj.description}\n", style="white")

            panel = Panel(info_text, title=f"[bold]{obj.name}[/bold]", border_style="cyan")
            console.print(panel)

            # Show goto hint
            print_info(f"Use 'nexstar goto radec --ra {obj.ra_hours:.4f} --dec {obj.dec_degrees:.4f}' to slew")

    except Exception as e:
        print_error(f"Failed to get object info: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def goto(
    object_name: str = typer.Argument(..., help="Object name to slew to (e.g., M31, Polaris)"),
    port: str | None = typer.Option(None, "--port", "-p", help="Serial port"),
    wait: bool = typer.Option(True, help="Wait for slew to complete"),
) -> None:
    """
    Slew telescope to a named celestial object.

    This is a convenience command that looks up the object's coordinates
    and performs a goto operation. Uses fuzzy matching - if multiple objects
    match, you'll be prompted to choose.

    Example:
        nexstar catalog goto M31
        nexstar catalog goto Polaris
        nexstar catalog goto "Andromeda Galaxy"
        nexstar catalog goto nebula  # Will show multiple matches
        nexstar catalog goto Vega --no-wait
    """
    try:
        # Look up objects (fuzzy search)
        matches = get_object_by_name(object_name)

        if not matches:
            print_error(f"No objects found matching '{object_name}'")
            print_info("Try 'nexstar catalog search <query>' to find objects")
            raise typer.Exit(code=1) from None

        # If multiple matches, let user select
        obj = select_object(matches, object_name)
        if obj is None:
            raise typer.Exit(code=1) from None

        # Get telescope
        ensure_connected(port)

        # Display object info
        display_name = obj.common_name or obj.name
        print_info(f"Slewing to {display_name} (RA {obj.ra_hours:.4f}h, Dec {obj.dec_degrees:+.4f}°)")

        # Perform goto
        from .goto import radec as goto_radec

        goto_radec(port=port, ra=obj.ra_hours, dec=obj.dec_degrees, wait=wait, progress=True)

    except Exception as e:
        print_error(f"Failed to goto object: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def catalogs() -> None:
    """
    Show available catalogs and statistics.

    Example:
        nexstar catalog catalogs
    """
    try:
        table = Table(title="Available Catalogs", show_header=True, header_style="bold magenta")
        table.add_column("Catalog", style="cyan", width=20)
        table.add_column("Objects", style="green", width=10)
        table.add_column("Description", style="white")

        for name, objects in ALL_CATALOGS.items():
            display_name = name.replace("_", " ").title()
            count = str(len(objects))

            # Get catalog description
            if name == "bright_stars":
                desc = "Bright stars including navigation stars and famous double stars"
            elif name == "messier":
                desc = "Complete Messier catalog objects visible with 6SE"
            elif name == "asterisms":
                desc = "Star patterns: Big Dipper, Orion's Belt, Summer Triangle, etc."
            elif name == "ngc":
                desc = "Notable NGC deep sky objects visible with 6SE"
            elif name == "caldwell":
                desc = "Selected Caldwell catalog highlights for amateur telescopes"
            elif name == "planets":
                desc = "Solar system planets and moons visible with 6SE"
            else:
                desc = ""

            table.add_row(display_name, count, desc)

        console.print(table)
        print_info("Use 'nexstar catalog list --catalog <name>' to view catalog contents")

    except Exception as e:
        print_error(f"Failed to show catalogs: {e}")
        raise typer.Exit(code=1) from e
