"""
Catalog Commands

Commands for searching and managing celestial object catalogs.
"""

import asyncio
from pathlib import Path
from typing import Any

import typer
from click import Context
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer.core import TyperGroup

from celestron_nexstar.api.catalogs.catalogs import (
    CelestialObject,
    get_all_objects,
    get_catalog,
    get_object_by_name,
    get_object_names_for_completion,
    search_objects,
)
from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.observation.visibility import assess_visibility
from celestron_nexstar.cli.utils.database import check_database_setup
from celestron_nexstar.cli.utils.export import FileConsole
from celestron_nexstar.cli.utils.output import (
    calculate_panel_width,
    console,
    format_dec,
    format_ra,
    print_error,
    print_info,
    print_json,
)
from celestron_nexstar.cli.utils.selection import select_from_list, select_object
from celestron_nexstar.cli.utils.state import ensure_connected


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Celestial object catalog commands", cls=SortedCommandsGroup)


def _generate_export_filename(catalog: str) -> Path:
    """Generate export filename for catalog list."""
    from datetime import datetime

    date_str = datetime.now().strftime("%Y-%m-%d")
    catalog_safe = catalog.replace("_", "-").lower()
    filename = f"catalog-{catalog_safe}-{date_str}.csv"
    return Path(filename)


def _autocomplete_object_name(ctx: typer.Context, incomplete: str) -> list[str]:
    """
    Autocompletion function for object names.

    Returns names from the database that match the incomplete string.
    Case-insensitive matching and sorting.
    """
    return asyncio.run(get_object_names_for_completion(prefix=incomplete, limit=50))


@app.command(rich_help_panel="Search & Browse")
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
        # Check database setup first
        check_database_setup()

        # Search for objects
        catalog_name = None if catalog == "all" else catalog
        results = asyncio.run(search_objects(query, catalog_name))

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
            # Group results by match type
            from collections import defaultdict

            grouped_results: defaultdict[str, list[tuple[CelestialObject, str]]] = defaultdict(list)
            for obj, match_type in results:
                grouped_results[match_type].append((obj, match_type))

            # Match type display order and styling
            match_type_order = ["exact", "name", "alias", "description"]
            match_type_styles = {
                "exact": "bold green",
                "name": "cyan",
                "alias": "yellow",
                "description": "dim",
            }
            match_type_titles = {
                "exact": "Exact Matches",
                "name": "Name Matches",
                "alias": "Common Name Matches",
                "description": "Description Matches",
            }

            # Display tables for each match type (in order)
            total_found = len(results)
            for match_type in match_type_order:
                if match_type not in grouped_results:
                    continue

                type_results = grouped_results[match_type]
                type_count = len(type_results)

                # Create table for this match type
                table = Table(
                    title=f"{match_type_titles[match_type]} ({type_count})",
                    show_header=True,
                    header_style=match_type_styles.get(match_type, "white"),
                    title_style=match_type_styles.get(match_type, "white"),
                )
                table.add_column(
                    "Name",
                    style="cyan",
                )
                table.add_column("Catalog", style="magenta")
                table.add_column("Type", style="yellow")
                table.add_column("RA", style="green")
                table.add_column("Dec", style="green")
                table.add_column("Mag", style="blue")
                table.add_column("Description", style="white")

                for obj, _ in type_results:
                    ra_str = f"{obj.ra_hours:.2f}h"
                    dec_str = f"{obj.dec_degrees:+.1f}°"
                    mag_str = f"{obj.magnitude:.2f}" if obj.magnitude else "N/A"
                    desc = obj.common_name or obj.description or ""

                    table.add_row(obj.name, obj.catalog, obj.object_type, ra_str, dec_str, mag_str, desc[:40])

                console.print(table)
                console.print()  # Blank line between tables

            # Display any other match types not in the standard order
            for match_type, type_results in grouped_results.items():
                if match_type not in match_type_order:
                    type_count = len(type_results)
                    table = Table(
                        title=f"{match_type_titles.get(match_type, match_type.title())} ({type_count})",
                        show_header=True,
                        header_style="white",
                    )
                    table.add_column("Name", style="cyan")
                    table.add_column("Catalog", style="magenta")
                    table.add_column("Type", style="yellow")
                    table.add_column("RA", style="green")
                    table.add_column("Dec", style="green")
                    table.add_column("Mag", style="blue")
                    table.add_column("Description", style="white")

                    for obj, _ in type_results:
                        ra_str = f"{obj.ra_hours:.2f}h"
                        dec_str = f"{obj.dec_degrees:+.1f}°"
                        mag_str = f"{obj.magnitude:.2f}" if obj.magnitude else "N/A"
                        desc = obj.common_name or obj.description or ""

                        table.add_row(obj.name, obj.catalog, obj.object_type, ra_str, dec_str, mag_str, desc[:40])

                    console.print(table)
                    console.print()

            console.print(f"[dim]Total: {total_found} objects found[/dim]")
            print_info("Use 'nexstar catalog info <name>' for detailed information")

    except Exception as e:
        print_error(f"Search failed: {e}")
        raise typer.Exit(code=1) from None


@app.command("list", rich_help_panel="Search & Browse")
def list_catalog(
    catalog: str | None = typer.Option(
        None, help="Catalog to list (or 'all' for all catalogs). If not provided, will prompt interactively."
    ),
    object_type: str | None = typer.Option(
        None, "--type", help="Filter by type (star, galaxy, nebula, asterism, etc.)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    export: bool = typer.Option(False, "--export", "-e", help="Export output to text file (auto-generates filename)"),
    export_path: str | None = typer.Option(
        None, "--export-path", help="Custom export file path (overrides auto-generated filename)"
    ),
) -> None:
    """
    List objects in a catalog.

    If run without --catalog, you'll be prompted to select from available
    catalogs interactively.

    Example:
        # Interactive selection
        nexstar catalog list

        # Direct selection
        nexstar catalog list --catalog messier
        nexstar catalog list --catalog bright_stars
        nexstar catalog list --type nebula
        nexstar catalog list --catalog messier --type galaxy
    """
    try:
        # Check database setup first
        check_database_setup()

        # Interactive selection if catalog not provided
        if catalog is None:
            catalog = _select_catalog_interactive()
            if catalog is None:
                print_info("Selection cancelled")
                return

        # Validate catalog name if not "all"
        if catalog != "all":
            db = get_database()
            available_catalogs = asyncio.run(db.get_all_catalogs())
            if catalog not in available_catalogs:
                print_error(
                    f"Invalid catalog: '{catalog}'. Available catalogs: {', '.join(sorted(available_catalogs))}, 'all'"
                )
                raise typer.Exit(code=1)

        # Get objects from database if catalog is specified, otherwise use YAML fallback
        if catalog == "all":
            objects = get_all_objects()
        else:
            # Try to get from database first, fallback to YAML if not in database
            db = get_database()
            db_objects = asyncio.run(db.get_by_catalog(catalog, limit=10000))  # Large limit to get all objects
            objects = db_objects or get_catalog(catalog)

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

        # Helper function to show catalog content
        def _show_catalog_content(
            output_console: Console | FileConsole,
            catalog_name: str,
            objects_list: list[CelestialObject],
            type_filter: str | None = None,
        ) -> None:
            catalog_display = catalog_name.replace("_", " ").title()
            type_suffix = f" ({type_filter})" if type_filter else ""
            table = Table(
                title=f"{catalog_display} Catalog{type_suffix} ({len(objects_list)} objects)",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="yellow")
            if catalog_name == "moons":
                table.add_column("Parent Planet", style="yellow")
            table.add_column("RA", style="green")
            table.add_column("Dec", style="green")
            table.add_column("Mag", style="blue")
            table.add_column("Description", style="white")

            for obj in objects_list:
                ra_str = f"{obj.ra_hours:.2f}h"
                dec_str = f"{obj.dec_degrees:+.1f}°"
                mag_str = f"{obj.magnitude:.2f}" if obj.magnitude else "N/A"
                desc = obj.common_name or obj.description or ""

                if catalog_name == "moons":
                    table.add_row(obj.name, obj.object_type, obj.parent_planet, ra_str, dec_str, mag_str, desc[:40])
                else:
                    table.add_row(obj.name, obj.object_type, ra_str, dec_str, mag_str, desc[:40])

            output_console.print(table)

        if export:
            import csv

            export_path_obj = Path(export_path) if export_path else _generate_export_filename(catalog)

            # Write CSV file
            with export_path_obj.open("w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "name",
                    "common_name",
                    "type",
                    "ra_hours",
                    "dec_degrees",
                    "magnitude",
                    "catalog",
                    "description",
                ]
                if catalog == "moons":
                    fieldnames.insert(3, "parent_planet")

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for obj in objects:
                    row = {
                        "name": obj.name,
                        "common_name": obj.common_name or "",
                        "type": obj.object_type,
                        "ra_hours": f"{obj.ra_hours:.4f}",
                        "dec_degrees": f"{obj.dec_degrees:.4f}",
                        "magnitude": f"{obj.magnitude:.2f}" if obj.magnitude is not None else "",
                        "catalog": obj.catalog,
                        "description": obj.description or "",
                    }
                    if catalog == "moons":
                        row["parent_planet"] = obj.parent_planet or ""
                    writer.writerow(row)

            console.print(f"\n[green]✓[/green] Exported {len(objects)} objects to {export_path_obj}")
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
            _show_catalog_content(console, catalog, objects, object_type)

    except Exception as e:
        print_error(f"Failed to list catalog: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Object Information")
def info(
    object_name: str = typer.Argument(
        ...,
        help="Object name (e.g., M31, Polaris, Andromeda)",
        autocompletion=_autocomplete_object_name,
    ),
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
        # Check database setup first
        check_database_setup()

        # Get matching objects (fuzzy search)
        matches = asyncio.run(get_object_by_name(object_name))

        if not matches:
            print_error(f"No objects found matching '{object_name}'")
            print_info("Try 'nexstar catalog search <query>' to find objects")
            raise typer.Exit(code=1) from None

        # If multiple matches, let user select
        obj = select_object(matches, object_name)
        if obj is None:
            raise typer.Exit(code=1) from None

        # Assess visibility
        visibility_info = assess_visibility(obj)

        # Get observing conditions and calculate visibility probability (like telescope tonight)
        visibility_probability = None
        try:
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            visibility_probability = planner._calculate_visibility_probability(obj, conditions, visibility_info)
        except Exception:
            # If we can't get conditions, just use observability_score
            visibility_probability = visibility_info.observability_score

        if json_output:
            visibility_data = {
                "is_visible": visibility_info.is_visible,
                "altitude_deg": visibility_info.altitude_deg,
                "azimuth_deg": visibility_info.azimuth_deg,
                "limiting_magnitude": visibility_info.limiting_magnitude,
                "observability_score": visibility_info.observability_score,
                "reasons": list(visibility_info.reasons),
            }

            # Add visibility probability if available
            if visibility_probability is not None:
                visibility_data["visibility_probability"] = visibility_probability

            # Get moons if this is a planet
            from celestron_nexstar.api.core.enums import CelestialObjectType

            output_data: dict[str, Any] = {
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
                "visibility": visibility_data,
            }

            if obj.object_type == CelestialObjectType.PLANET.value:
                db = get_database()
                moons = asyncio.run(db.get_moons_by_parent_planet(obj.name))
                if moons:
                    output_data["moons"] = [
                        {
                            "name": moon.name,
                            "magnitude": moon.magnitude,
                            "description": moon.description,
                        }
                        for moon in moons
                    ]

            print_json(output_data)
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
                info_text.append(f"  Magnitude: {obj.magnitude:.2f}\n", style="white")
            info_text.append(f"  Catalog:  {obj.catalog}\n", style="white")

            # Visibility information
            info_text.append("\n")
            info_text.append("Visibility:\n", style="bold yellow")
            if visibility_info.is_visible:
                info_text.append("  Status: ", style="white")
                info_text.append("✓ Visible\n", style="bold green")
            else:
                info_text.append("  Status: ", style="white")
                info_text.append("✗ Not Visible\n", style="bold red")

            if visibility_info.altitude_deg is not None:
                info_text.append(f"  Altitude: {visibility_info.altitude_deg:.1f}°\n", style="white")
            if visibility_info.azimuth_deg is not None:
                # Convert azimuth to cardinal direction
                az = visibility_info.azimuth_deg
                if az < 22.5 or az >= 337.5:
                    direction = "N"
                elif az < 67.5:
                    direction = "NE"
                elif az < 112.5:
                    direction = "E"
                elif az < 157.5:
                    direction = "SE"
                elif az < 202.5:
                    direction = "S"
                elif az < 247.5:
                    direction = "SW"
                elif az < 292.5:
                    direction = "W"
                else:
                    direction = "NW"
                info_text.append(f"  Azimuth: {visibility_info.azimuth_deg:.1f}° ({direction})\n", style="white")
            info_text.append(f"  Limiting Magnitude: {visibility_info.limiting_magnitude:.2f}\n", style="white")
            info_text.append(f"  Observability Score: {visibility_info.observability_score:.0%}\n", style="white")

            # Add visibility probability (Chance) if available
            if visibility_probability is not None:
                if visibility_probability >= 0.8:
                    prob_style = "bold green"
                elif visibility_probability >= 0.5:
                    prob_style = "yellow"
                elif visibility_probability >= 0.3:
                    prob_style = "red"
                else:
                    prob_style = "dim red"
                info_text.append("  Chance of Seeing: ", style="white")
                info_text.append(f"{visibility_probability:.0%}\n", style=prob_style)

            # Reasons
            if visibility_info.reasons:
                info_text.append("\n  Details:\n", style="dim")
                for reason in visibility_info.reasons:
                    info_text.append(f"    • {reason}\n", style="dim")

            # Moons (if this is a planet)
            from celestron_nexstar.api.core.enums import CelestialObjectType

            if obj.object_type == CelestialObjectType.PLANET.value:
                db = get_database()
                moons = asyncio.run(db.get_moons_by_parent_planet(obj.name))
                if moons:
                    info_text.append("\n")
                    info_text.append("Moons:\n", style="bold yellow")
                    for moon in moons:
                        mag_str = f" (mag {moon.magnitude:.2f})" if moon.magnitude else ""
                        info_text.append(f"  • {moon.name}{mag_str}\n", style="white")

            # Description
            if obj.description:
                info_text.append("\n")
                info_text.append("Description:\n", style="bold yellow")
                info_text.append(f"  {obj.description}\n", style="white")

            panel = Panel(
                info_text,
                title=f"[bold]{obj.name}[/bold]",
                border_style="cyan",
                width=calculate_panel_width(info_text, console),
            )
            console.print(panel)

            # Show goto hint
            print_info(f"Use 'nexstar goto radec --ra {obj.ra_hours:.4f} --dec {obj.dec_degrees:.4f}' to slew")

    except Exception as e:
        print_error(f"Failed to get object info: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Telescope Control")
def goto(
    object_name: str = typer.Argument(
        ...,
        help="Object name to slew to (e.g., M31, Polaris)",
        autocompletion=_autocomplete_object_name,
    ),
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
        # Check database setup first
        check_database_setup()

        # Look up objects (fuzzy search)
        matches = asyncio.run(get_object_by_name(object_name))

        if not matches:
            print_error(f"No objects found matching '{object_name}'")
            print_info("Try 'nexstar catalog search <query>' to find objects")
            raise typer.Exit(code=1) from None

        # If multiple matches, let user select
        obj = select_object(matches, object_name)
        if obj is None:
            raise typer.Exit(code=1) from None

        # Get telescope
        ensure_connected()

        # Display object info
        display_name = obj.common_name or obj.name
        print_info(f"Slewing to {display_name} (RA {obj.ra_hours:.4f}h, Dec {obj.dec_degrees:+.4f}°)")

        # Perform goto
        from celestron_nexstar.cli.commands.telescope.goto import radec as goto_radec

        goto_radec(ra=obj.ra_hours, dec=obj.dec_degrees, wait=wait, progress=True)

    except Exception as e:
        print_error(f"Failed to goto object: {e}")
        raise typer.Exit(code=1) from e


@app.command(rich_help_panel="Catalog Management")
def catalogs() -> None:
    """
    Show available catalogs and statistics.

    Example:
        nexstar catalog catalogs
    """
    try:
        # Check database setup first
        check_database_setup()

        db = get_database()
        stats = asyncio.run(db.get_stats())

        table = Table(title="Available Catalogs", show_header=True, header_style="bold magenta")
        table.add_column("Catalog", style="cyan")
        table.add_column("Objects", style="green")
        table.add_column("Description", style="white")

        # Catalog descriptions
        descriptions = {
            "bright_stars": "Bright stars including navigation stars and famous double stars",
            "messier": "Complete Messier catalog objects visible with 6SE",
            "asterisms": "Star patterns: Big Dipper, Orion's Belt, Summer Triangle, etc.",
            "ngc": "Notable NGC deep sky objects visible with 6SE",
            "ic": "Index Catalog deep sky objects",
            "caldwell": "Selected Caldwell catalog highlights for amateur telescopes",
            "planets": "Solar system planets and moons visible with 6SE",
            "moons": "Planetary moons",
            "yale_bsc": "Yale Bright Star Catalog",
        }

        # Sort catalogs by object count (descending)
        sorted_catalogs = sorted(stats.objects_by_catalog.items(), key=lambda x: x[1], reverse=True)

        for catalog_name, count in sorted_catalogs:
            # Only show catalogs that actually exist in the database
            # (sanity check - should already be filtered by the query)
            if count > 0:
                display_name = catalog_name.replace("_", " ").title()
                desc = descriptions.get(catalog_name, "")
                table.add_row(display_name, str(count), desc)

        console.print(table)
        print_info(f"Total objects in database: {stats.total_objects:,}")
        print_info("Use 'nexstar catalog list --catalog <name>' to view catalog contents")

    except Exception as e:
        print_error(f"Failed to show catalogs: {e}")
        raise typer.Exit(code=1) from e


def _select_catalog_interactive() -> str | None:
    """Interactively select a catalog."""
    db = get_database()
    stats = asyncio.run(db.get_stats())
    available_catalogs = ["all", *asyncio.run(db.get_all_catalogs())]

    # Catalog descriptions
    descriptions = {
        "all": "All catalogs combined",
        "bright_stars": "Bright stars including navigation stars and famous double stars",
        "messier": "Complete Messier catalog objects visible with 6SE",
        "asterisms": "Star patterns: Big Dipper, Orion's Belt, Summer Triangle, etc.",
        "ngc": "Notable NGC deep sky objects visible with 6SE",
        "ic": "Index Catalog deep sky objects",
        "caldwell": "Selected Caldwell catalog highlights for amateur telescopes",
        "planets": "Solar system planets and moons visible with 6SE",
        "moons": "Planetary moons",
    }

    def display_catalog(catalog: str) -> tuple[str, ...]:
        display_name = catalog.replace("_", " ").title()
        count = stats.objects_by_catalog.get(catalog, 0) if catalog != "all" else stats.total_objects
        description = descriptions.get(catalog, "Catalog")
        return (display_name, str(count), description)

    selected = select_from_list(
        available_catalogs,
        title="Select Catalog",
        display_func=display_catalog,
        headers=["Catalog", "Objects", "Description"],
    )

    return selected
