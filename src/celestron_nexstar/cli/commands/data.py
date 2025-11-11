"""
Data Management Commands

Commands for importing and managing catalog data sources.
"""

import asyncio

import typer
from rich.console import Console

from ..data_import import import_data_source, list_data_sources


app = typer.Typer(help="Data import and management commands")
console = Console()


@app.command("sync-ephemeris", rich_help_panel="Data Management")
def sync_ephemeris_files(
    force: bool = typer.Option(False, "--force", "-f", help="Force sync even if recently updated"),
    list_files: bool = typer.Option(
        False, "--list", "-l", help="List files that would be synced without actually syncing"
    ),
) -> None:
    """
    Sync ephemeris file information from NAIF to the database.

    Fetches the latest ephemeris file summaries from NASA JPL's NAIF servers
    and updates the local database with file metadata, coverage dates, and contents.

    This command should be run periodically to keep ephemeris file information
    up to date. By default, it only syncs once per day.

    Examples:
        nexstar data sync-ephemeris
        nexstar data sync-ephemeris --force
        nexstar data sync-ephemeris --list
    """
    import asyncio

    from rich.table import Table

    from ...api.database import list_ephemeris_files_from_naif, sync_ephemeris_files_from_naif

    try:
        if list_files:
            console.print("[cyan]Fetching ephemeris file information from NAIF...[/cyan]\n")
            files = asyncio.run(list_ephemeris_files_from_naif())

            if not files:
                console.print("[yellow]No ephemeris files found[/yellow]")
                return

            # Create table
            table = Table(title="Ephemeris Files Available from NAIF", show_header=True, header_style="bold magenta")
            table.add_column("Key", style="cyan", width=15)
            table.add_column("File", style="green", width=20)
            table.add_column("Type", style="yellow", width=10)
            table.add_column("Coverage", style="blue", width=15)
            table.add_column("Size (MB)", justify="right", style="magenta", width=10)
            table.add_column("Description", style="white")

            for file_info in sorted(files, key=lambda x: (x["file_type"], x["file_key"])):
                coverage = f"{file_info['coverage_start']}-{file_info['coverage_end']}"
                table.add_row(
                    file_info["file_key"],
                    file_info["filename"],
                    file_info["file_type"],
                    coverage,
                    f"{file_info['size_mb']:.1f}",
                    file_info["description"][:50] + ("..." if len(file_info["description"]) > 50 else ""),
                )

            console.print(table)
            console.print(f"\n[dim]Total: {len(files)} files[/dim]")
        else:
            console.print("[cyan]Fetching ephemeris file information from NAIF...[/cyan]")
            count = asyncio.run(sync_ephemeris_files_from_naif(force=force))
            console.print(f"[green]✓[/green] Synced {count} ephemeris files to database")
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to sync ephemeris files: {e}")
        raise typer.Exit(code=1) from e


@app.command("sources", rich_help_panel="Data Sources")
def sources() -> None:
    """
    List available data sources and their import status.

    Shows available catalogs that can be imported, including:
    - Number of objects available
    - Number already imported
    - License information
    """
    list_data_sources()


@app.command("import", rich_help_panel="Data Import")
def import_source(
    source: str = typer.Argument(..., help="Data source to import (e.g., 'openngc')"),
    mag_limit: float = typer.Option(
        15.0,
        "--mag-limit",
        "-m",
        help="Maximum magnitude to import (fainter objects are skipped)",
    ),
) -> None:
    """
    Import data from a catalog source.

    Downloads and imports celestial objects from the specified data source.
    Objects are filtered by magnitude to include only those visible with
    typical amateur telescopes.

    Available sources: openngc, yale_bsc, custom

    [bold green]Examples:[/bold green]

        # Import custom YAML catalog (catalogs.yaml)
        nexstar data import custom

        # Import OpenNGC catalog (default mag ≤ 15.0)
        nexstar data import openngc

        # Import with custom magnitude limit
        nexstar data import openngc --mag-limit 12.0

    [bold blue]Available Sources:[/bold blue]

        custom    - Custom YAML catalog (catalogs.yaml)
        openngc   - NGC/IC catalog (13,970 objects)
        yale_bsc  - Yale Bright Star Catalog (9,096 stars, mag ≤ 6.5)

    Use 'nexstar data sources' to see all available sources.
    """
    success = import_data_source(source, mag_limit)
    if not success:
        raise typer.Exit(code=1)


@app.command("init-static", rich_help_panel="Database Management")
def init_static() -> None:
    """
    Initialize static reference data in the database.

    Populates the database with static reference data that works offline:
    - Meteor showers
    - Constellations and asterisms
    - Dark sky sites
    - Space events calendar (Planetary Society)

    This should be run once after database setup to enable offline functionality.
    """
    from ...api.constellations import populate_constellation_database
    from ...api.meteor_showers import populate_meteor_shower_database
    from ...api.models import get_db_session
    from ...api.space_events import populate_space_events_database
    from ...api.vacation_planning import populate_dark_sky_sites_database

    console.print("\n[bold cyan]Initializing static reference data[/bold cyan]\n")

    try:
        with get_db_session() as db:
            # Populate meteor showers
            console.print("[dim]Populating meteor showers...[/dim]")
            populate_meteor_shower_database(db)
            console.print("[green]✓[/green] Meteor showers populated")

            # Populate constellations
            console.print("[dim]Populating constellations and asterisms...[/dim]")
            populate_constellation_database(db)
            console.print("[green]✓[/green] Constellations populated")

            # Populate dark sky sites
            console.print("[dim]Populating dark sky sites...[/dim]")
            populate_dark_sky_sites_database(db)
            console.print("[green]✓[/green] Dark sky sites populated")

            # Populate space events
            console.print("[dim]Populating space events calendar...[/dim]")
            populate_space_events_database(db)
            console.print("[green]✓[/green] Space events populated")

        console.print("\n[bold green]✓ All static data initialized![/bold green]")
        console.print("[dim]These datasets are now available offline.[/dim]\n")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error initializing static data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("stats", rich_help_panel="Database Management")
def stats() -> None:
    """
    Show database statistics.

    Displays information about the current catalog database:
    - Total number of objects
    - Objects by catalog
    - Objects by type
    - Magnitude range
    - Light pollution data statistics
    """
    from rich.table import Table
    from sqlalchemy import text

    from ...api.database import get_database

    db = get_database()
    db_stats = db.get_stats()

    # Overall stats
    console.print("\n[bold cyan]Database Statistics[/bold cyan]")
    console.print(f"Total objects: [green]{db_stats.total_objects:,}[/green]")
    console.print(f"Dynamic objects: [yellow]{db_stats.dynamic_objects}[/yellow] (planets/moons)")

    mag_min, mag_max = db_stats.magnitude_range
    if mag_min is not None and mag_max is not None:
        console.print(f"Magnitude range: [cyan]{mag_min:.1f}[/cyan] to [cyan]{mag_max:.1f}[/cyan]")

    # Objects by catalog
    catalog_table = Table(title="\nObjects by Catalog")
    catalog_table.add_column("Catalog", style="cyan")
    catalog_table.add_column("Count", justify="right", style="green")

    for catalog, count in sorted(db_stats.objects_by_catalog.items()):
        catalog_table.add_row(catalog, f"{count:,}")

    console.print(catalog_table)

    # Objects by type
    type_table = Table(title="Objects by Type")
    type_table.add_column("Type", style="cyan")
    type_table.add_column("Count", justify="right", style="green")

    for obj_type, count in sorted(db_stats.objects_by_type.items()):
        type_table.add_row(obj_type, f"{count:,}")

    console.print(type_table)

    # Light pollution statistics
    try:
        with db._get_session() as session:
            # Check if table exists
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='light_pollution_grid'")
            ).fetchone()

            if table_exists:
                # Get total count
                count_result = session.execute(text("SELECT COUNT(*) FROM light_pollution_grid")).fetchone()
                total_count = count_result[0] if count_result is not None else 0

                if total_count > 0:
                    # Get SQM range
                    sqm_range = session.execute(
                        text("SELECT MIN(sqm_value), MAX(sqm_value) FROM light_pollution_grid")
                    ).fetchone()
                    if sqm_range is not None:
                        sqm_min = sqm_range[0] if sqm_range[0] is not None else None
                        sqm_max = sqm_range[1] if sqm_range[1] is not None else None
                    else:
                        sqm_min = None
                        sqm_max = None

                    # Get coverage by region
                    region_counts = session.execute(
                        text(
                            "SELECT region, COUNT(*) FROM light_pollution_grid WHERE region IS NOT NULL GROUP BY region ORDER BY region"
                        )
                    ).fetchall()

                    # Check for SpatiaLite
                    spatialite_available = False
                    try:
                        session.execute(text("SELECT load_extension('mod_spatialite')"))
                        spatialite_available = True
                    except Exception:
                        pass

                    lp_table = Table(title="\nLight Pollution Data")
                    lp_table.add_column("Metric", style="cyan")
                    lp_table.add_column("Value", justify="right", style="green")

                    lp_table.add_row("Total grid points", f"{total_count:,}")
                    if sqm_min is not None and sqm_max is not None:
                        lp_table.add_row("SQM range", f"{sqm_min:.2f} to {sqm_max:.2f}")
                    if spatialite_available:
                        lp_table.add_row("SpatiaLite", "[green]Available[/green]")
                    else:
                        lp_table.add_row("SpatiaLite", "[dim]Not available[/dim]")

                    console.print(lp_table)

                    # Regions table if we have region data
                    if region_counts:
                        region_table = Table(title="Coverage by Region")
                        region_table.add_column("Region", style="cyan")
                        region_table.add_column("Grid Points", justify="right", style="green")

                        for region, count in region_counts:
                            region_name = region if region else "Unknown"
                            region_table.add_row(region_name, f"{count:,}")

                        console.print(region_table)
                else:
                    console.print("\n[dim]Light pollution data: [yellow]No data imported[/yellow][/dim]")
            else:
                console.print("\n[dim]Light pollution data: [yellow]Table not created[/yellow][/dim]")
    except Exception:
        # Silently skip if there's an error (table might not exist)
        pass

    # Database info
    if db_stats.last_updated:
        console.print(f"\n[dim]Last updated: {db_stats.last_updated.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        console.print(f"[dim]Database version: {db_stats.database_version}[/dim]")


@app.command("vacuum", rich_help_panel="Database Management")
def vacuum() -> None:
    """
    Reclaim unused space in the database by running VACUUM.

    SQLite doesn't automatically reclaim space when data is deleted.
    This command rebuilds the database file, removing free pages and
    reducing file size.

    Use this after deleting large amounts of data (e.g., light pollution data)
    to reduce the database file size.

    [bold green]Examples:[/bold green]

        # Reclaim space after deleting data
        nexstar data vacuum
    """
    from ...api.database import get_database, vacuum_database

    db = get_database()

    # Get file size before
    size_before = db.db_path.stat().st_size if db.db_path.exists() else 0

    console.print("\n[bold cyan]Running VACUUM on database[/bold cyan]\n")
    console.print(f"[dim]Database: {db.db_path}[/dim]")
    console.print(f"[dim]Size before: {size_before / (1024 * 1024):.2f} MB[/dim]\n")

    try:
        size_before_bytes, size_after_bytes = vacuum_database(db)
        size_reclaimed = size_before_bytes - size_after_bytes

        console.print("[bold green]✓ VACUUM complete![/bold green]\n")
        console.print(f"  Size before: [cyan]{size_before_bytes / (1024 * 1024):.2f} MB[/cyan]")
        console.print(f"  Size after:  [cyan]{size_after_bytes / (1024 * 1024):.2f} MB[/cyan]")
        if size_reclaimed > 0:
            console.print(f"  Space reclaimed: [green]{size_reclaimed / (1024 * 1024):.2f} MB[/green]\n")
        else:
            console.print("  No space to reclaim\n")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error running VACUUM: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("clear-light-pollution", rich_help_panel="Light Pollution Data")
def clear_light_pollution(
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
    vacuum: bool = typer.Option(
        True,
        "--vacuum/--no-vacuum",
        help="Run VACUUM after clearing to reclaim disk space (default: True)",
    ),
) -> None:
    """
    Clear all light pollution data from the database.

    This removes all stored SQM (Sky Quality Meter) values from the
    light_pollution_grid table. Use this before re-downloading data
    with different filters or to free up database space.

    [bold yellow]Warning:[/bold yellow] This action cannot be undone!

    [bold green]Examples:[/bold green]

        # Clear with confirmation prompt
        nexstar data clear-light-pollution

        # Clear without confirmation
        nexstar data clear-light-pollution --yes

        # Clear without vacuuming (faster, but doesn't reclaim space)
        nexstar data clear-light-pollution --no-vacuum
    """
    from ...api.database import get_database
    from ...api.light_pollution_db import clear_light_pollution_data

    db = get_database()

    # Check if table exists and get row count
    try:
        with db._get_session() as session:
            from sqlalchemy import text

            result = session.execute(text("SELECT COUNT(*) FROM light_pollution_grid")).fetchone()
            row_count = result[0] if result else 0
    except Exception:
        console.print("\n[yellow]⚠[/yellow] Light pollution table does not exist or is empty.\n")
        raise typer.Exit(code=0) from None

    if row_count == 0:
        console.print("\n[dim]Light pollution table is already empty.[/dim]\n")
        raise typer.Exit(code=0) from None

    # Show what will be deleted
    console.print("\n[bold yellow]⚠ Warning: This will delete all light pollution data![/bold yellow]\n")
    console.print(f"[dim]Rows to be deleted: {row_count:,}[/dim]\n")

    # Confirm unless --yes flag is used
    if not confirm:
        try:
            response = typer.prompt(
                "Are you sure you want to clear all light pollution data? (yes/no)",
                default="no",
            )
            if response.lower() not in ("yes", "y"):
                console.print("\n[dim]Operation cancelled.[/dim]\n")
                raise typer.Exit(code=0) from None
        except typer.Abort:
            console.print("\n[dim]Operation cancelled.[/dim]\n")
            raise typer.Exit(code=0) from None

    # Clear the data
    try:
        deleted_count = clear_light_pollution_data(db)
        console.print(
            f"\n[bold green]✓[/bold green] Cleared [green]{deleted_count:,}[/green] rows from light pollution table.\n"
        )

        # Run VACUUM to reclaim space
        if vacuum:
            from ...api.database import vacuum_database

            console.print("[dim]Running VACUUM to reclaim disk space...[/dim]")
            size_before, size_after = vacuum_database(db)
            size_reclaimed = size_before - size_after

            console.print("[bold green]✓[/bold green] Database optimized")
            console.print(f"  Size before: [cyan]{size_before / (1024 * 1024):.2f} MB[/cyan]")
            console.print(f"  Size after:  [cyan]{size_after / (1024 * 1024):.2f} MB[/cyan]")
            if size_reclaimed > 0:
                console.print(f"  Space reclaimed: [green]{size_reclaimed / (1024 * 1024):.2f} MB[/green]\n")
            else:
                console.print("  No space to reclaim\n")

        console.print("[dim]You can now re-download data with different filters if needed.[/dim]\n")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error clearing data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("download-light-pollution", rich_help_panel="Light Pollution Data")
def download_light_pollution(
    region: str | None = typer.Option(
        None,
        "--region",
        "-r",
        help="Region to download (world, north_america, south_america, europe, africa, asia, australia). Default: all",
    ),
    grid_resolution: float = typer.Option(
        0.1,
        "--grid-resolution",
        "-g",
        help="Grid resolution in degrees (default: 0.1° ≈ 11km). Smaller = more accurate but larger database",
    ),
    states: str | None = typer.Option(
        None,
        "--states",
        "-s",
        help="Comma-separated list of states/provinces to filter (e.g., 'Colorado,New Mexico'). Only works with north_america region.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-download even if data exists",
    ),
) -> None:
    """
    Download and import World Atlas 2024 light pollution data.

    Downloads light pollution maps from djlorenz.github.io and stores
    SQM (Sky Quality Meter) values in the database for offline access.

    [bold green]Examples:[/bold green]

        # Download all regions
        nexstar data download-light-pollution

        # Download specific region
        nexstar data download-light-pollution --region north_america

        # Download only specific states (reduces database size)
        nexstar data download-light-pollution --region north_america --states "Colorado,New Mexico"

        # Higher resolution (more accurate, larger database)
        nexstar data download-light-pollution --grid-resolution 0.05

    [bold blue]Regions:[/bold blue]

        world          - Full world map (large, ~65S to 75N)
        north_america  - North America (7N to 75N, 180W to 51W)
        south_america  - South America (57S to 14N, 93W to 33W)
        europe         - Europe (34N to 75N, 32W to 70E)
        africa         - Africa (36S to 38N, 26W to 64E)
        asia           - Asia (5N to 75N, 60E to 180E)
        australia      - Australia (48S to 8N, 94E to 180E)

    [bold yellow]Note:[/bold yellow] Requires Pillow (PIL) for image processing.
    Install with: pip install Pillow

    [bold cyan]State Filtering:[/bold cyan]
        Use --states to limit download to specific states/provinces.
        This significantly reduces database size. Example:
        --states "Colorado,New Mexico,Arizona"

        Supported: US states, Canadian provinces, Mexican states
        Only works with --region north_america
    """
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

    from ...api.light_pollution_db import download_world_atlas_data

    regions_to_download = [region] if region else None

    # Parse states filter
    state_filter = None
    if states:
        state_filter = [s.strip() for s in states.split(",") if s.strip()]
        if region != "north_america":
            console.print("\n[yellow]⚠[/yellow] [bold]Warning:[/bold] --states only works with --region north_america")
            console.print("Ignoring state filter.\n")
            state_filter = None

    console.print("\n[bold cyan]Downloading World Atlas 2024 Light Pollution Data[/bold cyan]\n")

    if regions_to_download:
        console.print(f"[dim]Region: {', '.join(regions_to_download)}[/dim]")
    else:
        console.print("[dim]Regions: All[/dim]")
    console.print(f"[dim]Grid resolution: {grid_resolution}°[/dim]")
    if state_filter:
        console.print(f"[dim]States filter: {', '.join(state_filter)}[/dim]")
    console.print()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading and processing...", total=None)

            from ...api.light_pollution_db import download_world_atlas_data

            results = asyncio.run(download_world_atlas_data(regions_to_download, grid_resolution, force, state_filter))

            progress.update(task, completed=100)

        console.print("\n[bold green]✓ Download complete![/bold green]\n")

        # Show results
        from rich.table import Table

        results_table = Table(title="Downloaded Regions")
        results_table.add_column("Region", style="cyan")
        results_table.add_column("Grid Points", justify="right", style="green")

        total_points = 0
        for region_name, count in results.items():
            results_table.add_row(region_name, f"{count:,}")
            total_points += count

        console.print(results_table)
        console.print(f"\n[bold]Total grid points:[/bold] [green]{total_points:,}[/green]")
        console.print("\n[dim]Light pollution data is now available offline in the database.[/dim]")
        console.print("[dim]The system will automatically use this data when APIs are unavailable.[/dim]\n")

    except ImportError as e:
        if "PIL" in str(e) or "Pillow" in str(e):
            console.print("\n[red]✗[/red] [bold]Pillow not installed[/bold]")
            console.print("\nInstall Pillow to process PNG images:")
            console.print("  [cyan]pip install Pillow[/cyan]\n")
        else:
            console.print(f"\n[red]✗[/red] Error: {e}\n")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error downloading data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
