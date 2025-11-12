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
            table.add_column("Key", style="cyan")
            table.add_column("File", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("Coverage", style="blue")
            table.add_column("Size (MB)", justify="right", style="magenta")
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


@app.command("update-star-names", rich_help_panel="Database Management")
def update_star_names() -> None:
    """
    Update existing Yale BSC stars with common names from star_name_mappings table.

    This command updates existing objects in the database that don't have common_name
    set by looking them up in the star_name_mappings table. Useful if you've added
    star name mappings after importing Yale BSC data.
    """
    from ...api.database import get_database
    from ...api.models import CelestialObjectModel, StarNameMappingModel

    console.print("\n[bold cyan]Updating star common names[/bold cyan]\n")

    db = get_database()

    try:
        with db._get_session() as session:
            # Get all Yale BSC objects without common_name
            objects_to_update = (
                session.query(CelestialObjectModel)
                .filter(
                    CelestialObjectModel.catalog == "yale_bsc",
                    (CelestialObjectModel.common_name.is_(None)) | (CelestialObjectModel.common_name == ""),
                )
                .all()
            )

            console.print(f"[dim]Found {len(objects_to_update)} Yale BSC objects without common names[/dim]")

            updated = 0
            for obj in objects_to_update:
                # Extract HR number from name (format: "HR 1708")
                if not obj.name or not obj.name.startswith("HR "):
                    continue

                try:
                    hr_number = int(obj.name.replace("HR ", "").strip())
                except ValueError:
                    continue

                # Look up common name
                mapping = (
                    session.query(StarNameMappingModel).filter(StarNameMappingModel.hr_number == hr_number).first()
                )

                if mapping and mapping.common_name and mapping.common_name.strip():
                    obj.common_name = mapping.common_name.strip()
                    updated += 1

            if updated > 0:
                session.commit()
                console.print(f"[green]✓[/green] Updated {updated} objects with common names")

                # Repopulate FTS table to include the new common names
                console.print("[dim]Updating search index...[/dim]")
                db.repopulate_fts_table()
                console.print("[green]✓[/green] Search index updated")
            else:
                console.print("[yellow]⚠[/yellow] No objects needed updating")

        console.print("\n[bold green]✓ Star names updated![/bold green]\n")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error updating star names: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("rebuild-fts", rich_help_panel="Database Management")
def rebuild_fts() -> None:
    """
    Rebuild the FTS5 full-text search index.

    This command repopulates the objects_fts table with all objects from the database.
    Useful if the FTS index is out of sync or if objects were imported before the FTS table was created.

    Example:
        nexstar data rebuild-fts
    """
    from ...api.database import get_database

    console.print("[cyan]Rebuilding FTS5 search index...[/cyan]\n")

    try:
        db = get_database()
        db.repopulate_fts_table()

        # Get count of indexed objects
        from sqlalchemy import text

        with db._get_session() as session:
            fts_count = session.execute(text("SELECT COUNT(*) FROM objects_fts")).scalar() or 0
            objects_count = session.execute(text("SELECT COUNT(*) FROM objects")).scalar() or 0

        console.print("[green]✓[/green] FTS index rebuilt successfully")
        console.print(f"[dim]  Indexed {fts_count:,} objects out of {objects_count:,} total[/dim]\n")

        if fts_count != objects_count:
            console.print(
                f"[yellow]⚠[/yellow] Warning: FTS index count ({fts_count:,}) doesn't match objects count ({objects_count:,})"
            )
            console.print("[dim]Some objects may not be searchable. Check for NULL names or descriptions.[/dim]\n")

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to rebuild FTS index: {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
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


@app.command("setup", rich_help_panel="Database Management")
def setup(
    skip_ephemeris: bool = typer.Option(False, "--skip-ephemeris", help="Skip ephemeris metadata sync (can be slow)"),
    mag_limit: float = typer.Option(
        15.0,
        "--mag-limit",
        "-m",
        help="Maximum magnitude to import for catalog data (default: 15.0)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt and rebuild database if it exists"
    ),
) -> None:
    """
    Set up the database for first-time use.

    This command initializes the database by:
    1. Creating database schema (via Alembic migrations)
    2. Importing ALL available catalog data (custom, OpenNGC, Yale BSC - ~18,000 objects)
    3. Initializing ALL static reference data (meteor showers, constellations, dark sky sites, space events)
    4. Syncing ephemeris file metadata from NAIF (optional)

    If the database already exists and contains data, you'll be prompted to rebuild it.

    Examples:
        nexstar data setup
        nexstar data setup --skip-ephemeris
        nexstar data setup --mag-limit 12.0
        nexstar data setup --force  # Skip confirmation prompt
    """
    from rich.table import Table
    from sqlalchemy import inspect, text

    from ...api.database import get_database, rebuild_database
    from ...api.models import get_db_session
    from ..data_import import DATA_SOURCES

    console.print("\n[bold cyan]Setting up database...[/bold cyan]\n")

    db = get_database()
    should_rebuild = False

    # Check if database exists and has data
    if db.db_path.exists():
        try:
            inspector = inspect(db._engine)
            existing_tables = set(inspector.get_table_names())
            if "objects" not in existing_tables:
                console.print("[yellow]⚠[/yellow] Database exists but schema is missing")
                should_rebuild = True
            else:
                # Check if we have catalog data
                with db._get_session() as session:
                    result = session.execute(text("SELECT COUNT(*) FROM objects")).scalar() or 0
                    if result > 0:
                        console.print(f"[yellow]⚠[/yellow] Database already exists with {result:,} objects")
                        console.print("[dim]To import all available data, the database needs to be rebuilt.[/dim]\n")

                        if not force:
                            try:
                                response = typer.prompt(
                                    "Do you want to delete the existing database and rebuild with all data? (yes/no)",
                                    default="no",
                                )
                                if response.lower() not in ("yes", "y"):
                                    console.print(
                                        "\n[dim]Operation cancelled. Use 'nexstar data rebuild' to rebuild later.[/dim]\n"
                                    )
                                    raise typer.Exit(code=0) from None
                            except typer.Abort:
                                console.print("\n[dim]Operation cancelled.[/dim]\n")
                                raise typer.Exit(code=0) from None

                        should_rebuild = True
                    else:
                        console.print("[yellow]⚠[/yellow] Database exists but is empty")
                        should_rebuild = True
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Error checking database: {e}")
            console.print("[dim]Will rebuild database[/dim]")
            should_rebuild = True
    else:
        console.print("[yellow]⚠[/yellow] Database does not exist - will create")
        should_rebuild = True

    # Rebuild database if needed
    if should_rebuild:
        console.print("\n[cyan]Rebuilding database with all available data...[/cyan]\n")

        # Show what sources will be imported
        console.print(f"[dim]Will import from {len(DATA_SOURCES)} sources: {', '.join(DATA_SOURCES.keys())}[/dim]\n")

        try:
            # Use rebuild_database which handles everything
            # Note: import_data_source prints to console, so output should be visible
            console.print("[dim]Initializing database schema...[/dim]")

            # Show progress for static data initialization
            console.print("\n[cyan]Initializing static reference data...[/cyan]")
            console.print("[dim]  • Meteor showers[/dim]")
            console.print("[dim]  • Constellations and asterisms[/dim]")
            console.print("[dim]  • Dark sky sites[/dim]")
            console.print("[dim]  • Space events[/dim]")

            result = rebuild_database(
                backup_dir=None,  # Don't backup during setup
                sources=list(DATA_SOURCES.keys()),  # Import all sources
                mag_limit=mag_limit,
                skip_backup=True,  # Skip backup during setup
                dry_run=False,
            )

            console.print("\n[green]✓[/green] Database rebuilt successfully\n")

            # Show import summary
            if result.get("imported_counts"):
                console.print("[bold]Imported Catalog Data:[/bold]")
                import_table = Table()
                import_table.add_column("Source", style="cyan")
                import_table.add_column("Imported", justify="right", style="green")

                total_imported = 0
                any_imported = False
                for source_id, (imported, _skipped) in result["imported_counts"].items():
                    source_name = DATA_SOURCES[source_id].name if source_id in DATA_SOURCES else source_id
                    import_table.add_row(source_name, f"{imported:,}")
                    total_imported += imported
                    if imported > 0:
                        any_imported = True

                console.print(import_table)
                console.print(f"\n[dim]Total objects imported: {total_imported:,}[/dim]\n")

                # Check if we actually got data
                if not any_imported:
                    console.print("[yellow]⚠[/yellow] Warning: No objects were imported from any source!")
                    console.print("[dim]This might indicate an issue with the import process.[/dim]")
                    console.print("[dim]Try running imports manually: nexstar data import custom[/dim]\n")
            else:
                console.print("[yellow]⚠[/yellow] Warning: No import results returned!")
                console.print("[dim]The rebuild completed but no data sources were processed.[/dim]\n")

            # Show static data summary
            if result.get("static_data"):
                console.print("[bold]Static Reference Data:[/bold]")
                static_table = Table()
                static_table.add_column("Data Type", style="cyan")
                static_table.add_column("Count", justify="right", style="green")

                static_data = result["static_data"]
                if static_data.get("meteor_showers", 0) > 0:
                    static_table.add_row("Meteor Showers", f"{static_data['meteor_showers']:,}")
                if static_data.get("constellations", 0) > 0:
                    static_table.add_row("Constellations", f"{static_data['constellations']:,}")
                if static_data.get("asterisms", 0) > 0:
                    static_table.add_row("Asterisms", f"{static_data['asterisms']:,}")
                if static_data.get("dark_sky_sites", 0) > 0:
                    static_table.add_row("Dark Sky Sites", f"{static_data['dark_sky_sites']:,}")
                if static_data.get("space_events", 0) > 0:
                    static_table.add_row("Space Events", f"{static_data['space_events']:,}")
                if static_data.get("light_pollution_grid_points", 0) > 0:
                    static_table.add_row(
                        "Light Pollution Grid Points", f"{static_data['light_pollution_grid_points']:,}"
                    )
                if static_data.get("weather_forecast_hours", 0) > 0:
                    static_table.add_row("Weather Forecast Hours", f"{static_data['weather_forecast_hours']:,}")

                if static_table.rows:
                    console.print(static_table)
                    console.print()

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to rebuild database: {e}")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1) from e
    else:
        # Database is already set up, just ensure migrations are current
        try:
            from alembic.config import Config

            from alembic import command  # type: ignore[attr-defined]

            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
        except Exception:
            pass

    # Ensure static data is populated (rebuild_database should have done this, but double-check)
    console.print("[cyan]Ensuring static reference data is populated...[/cyan]")
    try:
        with db._get_session() as session:
            meteor_count = session.execute(text("SELECT COUNT(*) FROM meteor_showers")).scalar() or 0
            constellation_count = session.execute(text("SELECT COUNT(*) FROM constellations")).scalar() or 0
            dark_sky_count = session.execute(text("SELECT COUNT(*) FROM dark_sky_sites")).scalar() or 0
            star_mapping_count = session.execute(text("SELECT COUNT(*) FROM star_name_mappings")).scalar() or 0

            if meteor_count == 0 or constellation_count == 0 or dark_sky_count == 0 or star_mapping_count == 0:
                console.print("[dim]Populating static reference data...[/dim]")
                from ...api.constellations import populate_constellation_database
                from ...api.meteor_showers import populate_meteor_shower_database
                from ...api.space_events import populate_space_events_database
                from ...api.star_name_mappings import populate_star_name_mappings_database
                from ...api.vacation_planning import populate_dark_sky_sites_database

                populate_meteor_shower_database(session)
                populate_constellation_database(session)
                populate_dark_sky_sites_database(session)
                populate_space_events_database(session)
                populate_star_name_mappings_database(session)
                console.print("[green]✓[/green] Static reference data populated")
            else:
                console.print("[green]✓[/green] Static reference data already exists")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Error checking static data: {e}")
        # Try to populate anyway
        try:
            with get_db_session() as session:
                from ...api.constellations import populate_constellation_database
                from ...api.meteor_showers import populate_meteor_shower_database
                from ...api.space_events import populate_space_events_database
                from ...api.vacation_planning import populate_dark_sky_sites_database

                populate_meteor_shower_database(session)
                populate_constellation_database(session)
                populate_dark_sky_sites_database(session)
                populate_space_events_database(session)
                console.print("[green]✓[/green] Static reference data populated")
        except Exception as e2:
            console.print(f"[yellow]⚠[/yellow] Failed to populate static data (non-critical): {e2}")

    # Sync ephemeris metadata (optional)
    if not skip_ephemeris:
        console.print("\n[cyan]Syncing ephemeris file metadata...[/cyan]")
        try:
            import asyncio

            from ...api.database import sync_ephemeris_files_from_naif

            count = asyncio.run(sync_ephemeris_files_from_naif(force=False))
            console.print(f"[green]✓[/green] Synced {count} ephemeris files")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Ephemeris sync failed (non-critical): {e}")
            console.print("[dim]You can sync later with: nexstar data sync-ephemeris[/dim]")

    # Final summary
    console.print("\n[bold green]✓ Database setup complete![/bold green]\n")

    # Show stats
    try:
        stats = db.get_stats()
        console.print(f"[dim]Total objects: {stats.total_objects:,}[/dim]")
        console.print(f"[dim]Database size: {db.db_path.stat().st_size / (1024 * 1024):.2f} MB[/dim]\n")
    except Exception:
        pass


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
    from ...api.star_name_mappings import populate_star_name_mappings_database
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

            # Populate star name mappings
            console.print("[dim]Populating star name mappings...[/dim]")
            populate_star_name_mappings_database(db)
            console.print("[green]✓[/green] Star name mappings populated")

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


@app.command("rebuild", rich_help_panel="Database Management")
def rebuild(
    backup_dir: str | None = typer.Option(
        None,
        "--backup-dir",
        help="Directory to store backups (default: ~/.nexstar/backups)",
    ),
    skip_backup: bool = typer.Option(
        False,
        "--skip-backup",
        help="Skip backup step (not recommended)",
    ),
    sources: str | None = typer.Option(
        None,
        "--sources",
        help="Comma-separated list of sources to import (default: all)",
    ),
    mag_limit: float = typer.Option(
        15.0,
        "--mag-limit",
        "-m",
        help="Maximum magnitude to import (default: 15.0)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force rebuild even if database exists",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without actually doing it",
    ),
) -> None:
    """
    Rebuild database from scratch and pull fresh data from all sources.

    This command:
    1. Backs up existing database (if present)
    2. Drops and recreates database schema using Alembic migrations
    3. Imports all available data sources in correct order
    4. Initializes static reference data
    5. Provides progress feedback and summary statistics

    [bold yellow]Warning:[/bold yellow] This will delete all existing data!

    [bold green]Examples:[/bold green]

        # Full rebuild with backup
        nexstar data rebuild

        # Rebuild without backup (not recommended)
        nexstar data rebuild --skip-backup

        # Rebuild only specific sources
        nexstar data rebuild --sources openngc,custom

        # Dry run to see what would happen
        nexstar data rebuild --dry-run

        # Rebuild with custom magnitude limit
        nexstar data rebuild --mag-limit 12.0
    """
    from pathlib import Path

    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    from ...api.database import get_database, rebuild_database

    console.print("\n[bold cyan]Rebuilding Database[/bold cyan]\n")

    # Parse sources
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]

    # Parse backup directory
    backup_path = Path(backup_dir) if backup_dir else None

    # Check if database exists and warn
    db = get_database()
    if db.db_path.exists() and not force and not dry_run:
        console.print("[yellow]⚠ Warning:[/yellow] Database already exists and will be replaced!")
        console.print("[dim]Use --force to proceed or --dry-run to preview[/dim]\n")
        try:
            response = typer.prompt("Continue? (yes/no)", default="no")
            if response.lower() not in ("yes", "y"):
                console.print("\n[dim]Operation cancelled.[/dim]\n")
                raise typer.Exit(code=0) from None
        except typer.Abort:
            console.print("\n[dim]Operation cancelled.[/dim]\n")
            raise typer.Exit(code=0) from None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Rebuilding database...", total=None)

            # Run rebuild
            result = rebuild_database(
                backup_dir=backup_path,
                sources=source_list,
                mag_limit=mag_limit,
                skip_backup=skip_backup,
                dry_run=dry_run,
            )

            progress.update(task, completed=True)

        if dry_run:
            console.print("\n[bold yellow][DRY RUN] No changes made[/bold yellow]\n")
            return

        # Display results
        console.print("\n[bold green]✓ Database rebuild complete![/bold green]\n")

        # Summary table
        summary_table = Table(title="Rebuild Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right", style="green")

        summary_table.add_row("Duration", f"{result['duration_seconds']:.1f} seconds")
        summary_table.add_row("Database size", f"{result['database_size_mb']:.2f} MB")

        if result["backup_path"]:
            backup_size = result["backup_path"].stat().st_size / (1024 * 1024)
            summary_table.add_row("Backup location", str(result["backup_path"]))
            summary_table.add_row("Backup size", f"{backup_size:.2f} MB")

        console.print(summary_table)

        # Imported objects
        if result["imported_counts"]:
            console.print("\n[bold]Imported Objects:[/bold]")
            import_table = Table()
            import_table.add_column("Source", style="cyan")
            import_table.add_column("Imported", justify="right", style="green")
            import_table.add_column("Skipped", justify="right", style="yellow")

            total_imported = 0
            for source_id, (imported, skipped) in result["imported_counts"].items():
                import_table.add_row(source_id, f"{imported:,}", f"{skipped:,}")
                total_imported += imported

            console.print(import_table)
            console.print(f"\n[bold]Total objects imported:[/bold] [green]{total_imported:,}[/green]")

        # Static data
        if result["static_data"]:
            console.print("\n[bold]Static Data:[/bold]")
            static_table = Table()
            static_table.add_column("Type", style="cyan")
            static_table.add_column("Count", justify="right", style="green")

            for data_type, count in result["static_data"].items():
                static_table.add_row(data_type.replace("_", " ").title(), f"{count:,}")

            console.print(static_table)

        # Final database stats
        db_stats = db.get_stats()
        console.print(f"\n[bold]Database now contains {db_stats.total_objects:,} objects[/bold]")
        console.print("\n[dim]Database rebuild complete![/dim]\n")

    except RuntimeError as e:
        console.print(f"\n[red]✗[/red] Rebuild failed: {e}\n")
        if "backup" in str(e).lower() or "restore" in str(e).lower():
            console.print("[yellow]Note:[/yellow] If a backup was created, it may have been restored.\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
