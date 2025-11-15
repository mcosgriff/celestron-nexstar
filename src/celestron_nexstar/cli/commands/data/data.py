"""
Data Management Commands

Commands for importing and managing catalog data sources.
"""

import asyncio
from pathlib import Path
from typing import Any

import typer
from click import Context
from rich.console import Console
from sqlalchemy import Row
from typer.core import TyperGroup

from celestron_nexstar.cli.data_import import import_data_source, list_data_sources


class SortedCommandsGroup(TyperGroup):
    """Custom Typer group that sorts commands alphabetically within each help panel."""

    def list_commands(self, ctx: Context) -> list[str]:
        """Return commands sorted alphabetically."""
        commands = super().list_commands(ctx)
        return sorted(commands)


app = typer.Typer(help="Data import and management commands", cls=SortedCommandsGroup)
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

    from celestron_nexstar.api.database.database import list_ephemeris_files_from_naif, sync_ephemeris_files_from_naif

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
    from celestron_nexstar.api.database.database import get_database
    from celestron_nexstar.api.database.models import CelestialObjectModel, StarNameMappingModel

    console.print("\n[bold cyan]Updating star common names[/bold cyan]\n")

    db = get_database()

    try:

        async def _update_star_names() -> None:
            from sqlalchemy import select

            async with db._AsyncSession() as session:
                # Get all Yale BSC objects without common_name
                stmt = select(CelestialObjectModel).where(
                    CelestialObjectModel.catalog == "yale_bsc",
                    (CelestialObjectModel.common_name.is_(None)) | (CelestialObjectModel.common_name == ""),
                )
                result = await session.execute(stmt)
                objects_to_update = result.scalars().all()

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
                    mapping_stmt = (
                        select(StarNameMappingModel).where(StarNameMappingModel.hr_number == hr_number).limit(1)
                    )
                    mapping_result = await session.execute(mapping_stmt)
                    mapping = mapping_result.scalar_one_or_none()

                    if mapping and mapping.common_name and mapping.common_name.strip():
                        obj.common_name = mapping.common_name.strip()
                        updated += 1

                if updated > 0:
                    await session.commit()
                    console.print(f"[green]✓[/green] Updated {updated} objects with common names")

                    # Repopulate FTS table to include the new common names
                    console.print("[dim]Updating search index...[/dim]")
                    await db.repopulate_fts_table()
                    console.print("[green]✓[/green] Search index updated")
                else:
                    console.print("[yellow]⚠[/yellow] No objects needed updating")

        asyncio.run(_update_star_names())

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
    from celestron_nexstar.api.database.database import get_database

    console.print("[cyan]Rebuilding FTS5 search index...[/cyan]\n")

    try:
        import asyncio

        db = get_database()
        asyncio.run(db.repopulate_fts_table())

        # Get count of indexed objects
        from sqlalchemy import func, select, text

        from celestron_nexstar.api.database.models import CelestialObjectModel

        async def _get_counts() -> tuple[int, int]:
            async with db._AsyncSession() as session:
                # FTS5 table requires raw SQL (virtual table)
                fts_result = await session.execute(text("SELECT COUNT(*) FROM objects_fts"))
                fts_count = fts_result.scalar() or 0
                # Use SQLAlchemy for objects count
                objects_result = await session.scalar(select(func.count(CelestialObjectModel.id)))
                objects_count = objects_result or 0
                return fts_count, objects_count

        fts_count, objects_count = asyncio.run(_get_counts())

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
    source: str = typer.Argument(..., help="Data source to import (e.g., 'celestial_stars_6')"),
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

    [bold green]Examples:[/bold green]

        # Import custom YAML catalog (planets and moons)
        nexstar data import custom

        # Import stars from celestial_data (mag ≤ 6)
        nexstar data import celestial_stars_6

        # Import DSOs with custom magnitude limit
        nexstar data import celestial_dsos_14 --mag-limit 12.0

        # Import Messier objects
        nexstar data import celestial_messier

        # Import constellations
        nexstar data import celestial_constellations

        # Import asterisms
        nexstar data import celestial_asterisms

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
    refresh_cache: bool = typer.Option(False, "--refresh-cache", help="Delete cached files and re-download everything"),
) -> None:
    """
    Set up the database for first-time use.

    This command initializes the database by:
    1. Creating database schema (via Alembic migrations)
    2. Importing ALL available catalog data from celestial_data (stars, DSOs, Messier, constellations, asterisms, local group) and custom YAML (planets, moons)
    3. Initializing ALL static reference data (meteor showers, constellations, dark sky sites, space events)
    4. Syncing ephemeris file metadata from NAIF (optional)

    If the database already exists and contains data, you'll be prompted to rebuild it.

    Examples:
        nexstar data setup
        nexstar data setup --skip-ephemeris
        nexstar data setup --mag-limit 12.0
        nexstar data setup --force  # Skip confirmation prompt
        nexstar data setup --refresh-cache  # Delete cache and re-download everything
    """
    from rich.table import Table

    from celestron_nexstar.api.database.database import get_database, rebuild_database
    from celestron_nexstar.cli.data_import import DATA_SOURCES

    console.print("\n[bold cyan]Setting up database...[/bold cyan]\n")

    db = get_database()
    should_rebuild = False

    # Check if database exists and has data
    if db.db_path.exists():
        try:
            import asyncio

            from sqlalchemy import text

            async def _check_tables() -> set[str]:
                async with db._engine.begin() as conn:
                    result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                    return {row[0] for row in result.fetchall()}

            existing_tables = asyncio.run(_check_tables())
            if "objects" not in existing_tables:
                console.print("[yellow]⚠[/yellow] Database exists but schema is missing")
                should_rebuild = True
            else:
                # Check if we have catalog data
                from sqlalchemy import func, select

                from celestron_nexstar.api.database.models import CelestialObjectModel

                with db._get_session_sync() as session:
                    object_count = session.scalar(select(func.count(CelestialObjectModel.id))) or 0
                    if object_count > 0:
                        console.print(f"[yellow]⚠[/yellow] Database already exists with {object_count:,} objects")
                        console.print("[dim]To import all available data, the database needs to be rebuilt.[/dim]\n")

                        if not force:
                            try:
                                response = typer.prompt(
                                    "Do you want to delete the existing database and rebuild with all data?",
                                    default="no",
                                    type=str,
                                )
                                # Normalize response: strip whitespace, handle empty string as "no"
                                response_normalized = (response or "no").strip().lower()
                                if response_normalized not in ("yes", "y"):
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

    # Clear cache if requested
    if refresh_cache:
        console.print("\n[yellow]Clearing cached files...[/yellow]\n")
        from celestron_nexstar.cli.data_import import get_cache_dir

        # Clear celestial data cache
        celestial_cache = get_cache_dir()
        deleted_count = 0
        if celestial_cache.exists():
            for file in celestial_cache.glob("*"):
                if file.is_file():
                    file.unlink()
                    deleted_count += 1
                    console.print(f"[dim]  Deleted: {file.name}[/dim]")
            if deleted_count > 0:
                console.print(f"[green]✓[/green] Cleared {deleted_count} file(s) from celestial data cache")
            else:
                console.print("[dim]  No files found in celestial data cache[/dim]")
        else:
            console.print("[dim]  Celestial data cache directory does not exist[/dim]")

        # Clear light pollution cache
        light_pollution_cache = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
        deleted_count = 0
        if light_pollution_cache.exists():
            for file in light_pollution_cache.glob("*.png"):
                file.unlink()
                deleted_count += 1
                console.print(f"[dim]  Deleted: {file.name}[/dim]")
            if deleted_count > 0:
                console.print(f"[green]✓[/green] Cleared {deleted_count} file(s) from light pollution cache")
            else:
                console.print("[dim]  No files found in light pollution cache[/dim]")
        else:
            console.print("[dim]  Light pollution cache directory does not exist[/dim]")

        console.print()

    # Rebuild database if needed
    if should_rebuild:
        console.print("\n[cyan]Rebuilding database with all available data...[/cyan]\n")

        # Filter sources to only include the most comprehensive catalogs
        # (e.g., stars_14 includes all stars from stars_6 and stars_8, so skip the smaller ones)
        default_sources = [
            source_id
            for source_id in DATA_SOURCES
            if source_id not in ("celestial_stars_6", "celestial_stars_8", "celestial_dsos_6", "celestial_dsos_14")
        ]

        # Show what sources will be imported
        console.print(f"[dim]Will import from {len(default_sources)} sources: {', '.join(default_sources)}[/dim]\n")
        console.print(
            "[dim]Note: Using most comprehensive catalogs (stars_14 includes stars_6 and stars_8, etc.)[/dim]\n"
        )

        try:
            # Use rebuild_database which handles everything
            # Note: import_data_source prints to console, so output should be visible
            console.print("[dim]Initializing database schema...[/dim]")

            result: dict[str, Any] = asyncio.run(
                rebuild_database(
                    backup_dir=None,  # Don't backup during setup
                    sources=default_sources,  # Import only comprehensive sources
                    mag_limit=mag_limit,
                    skip_backup=True,  # Skip backup during setup
                    dry_run=False,
                    force_download=refresh_cache,  # Force re-download if cache was cleared
                )
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
        from sqlalchemy import func, select

        from celestron_nexstar.api.database.models import (
            ConstellationModel,
            DarkSkySiteModel,
            MeteorShowerModel,
            StarNameMappingModel,
        )

        async def _check_and_seed_static_data() -> None:
            async with db._AsyncSession() as session:
                meteor_result = await session.scalar(select(func.count(MeteorShowerModel.id)))
                meteor_count = meteor_result or 0
                constellation_result = await session.scalar(select(func.count(ConstellationModel.id)))
                constellation_count = constellation_result or 0
                dark_sky_result = await session.scalar(select(func.count(DarkSkySiteModel.id)))
                dark_sky_count = dark_sky_result or 0
                star_mapping_result = await session.scalar(select(func.count(StarNameMappingModel.hr_number)))
                star_mapping_count = star_mapping_result or 0

                if meteor_count == 0 or constellation_count == 0 or dark_sky_count == 0 or star_mapping_count == 0:
                    console.print("[dim]Seeding static reference data...[/dim]")
                    from celestron_nexstar.api.database.database_seeder import seed_all

                    await seed_all(session, force=False)
                    console.print("[green]✓[/green] Static reference data seeded")
                else:
                    console.print("[green]✓[/green] Static reference data already exists")

        # Run async function - asyncio is imported at module level
        asyncio.run(_check_and_seed_static_data())
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Error checking static data: {e}")
        # Try to populate anyway
        try:
            # Note: These populate functions may expect sync sessions
            # This fallback is skipped as it requires sync sessions which are no longer available
            # The main seeding path above should handle this
            console.print("[yellow]⚠[/yellow] Fallback population skipped (requires sync sessions)")
        except Exception as e2:
            console.print(f"[yellow]⚠[/yellow] Failed to populate static data (non-critical): {e2}")

    # Sync ephemeris metadata (optional)
    if not skip_ephemeris:
        console.print("\n[cyan]Syncing ephemeris file metadata...[/cyan]")
        try:
            from celestron_nexstar.api.database.database import sync_ephemeris_files_from_naif

            # asyncio is imported at module level
            count = asyncio.run(sync_ephemeris_files_from_naif(force=False))
            console.print(f"[green]✓[/green] Synced {count} ephemeris files")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Ephemeris sync failed (non-critical): {e}")
            console.print("[dim]You can sync later with: nexstar data sync-ephemeris[/dim]")

    # Final summary
    console.print("\n[bold green]✓ Database setup complete![/bold green]\n")

    # Show stats
    try:
        stats = asyncio.run(db.get_stats())
        console.print(f"[dim]Total objects: {stats.total_objects:,}[/dim]")
        console.print(f"[dim]Database size: {db.db_path.stat().st_size / (1024 * 1024):.2f} MB[/dim]\n")
    except Exception:
        pass


@app.command("seed", rich_help_panel="Database Management")
def seed_database(
    force: bool = typer.Option(False, "--force", "-f", help="Clear existing data before seeding"),
    status: bool = typer.Option(False, "--status", "-s", help="Show current seed data status and exit"),
) -> None:
    """
    Seed the database with static reference data.

    Populates the database with static reference data from seed files:
    - Star name mappings
    - Meteor showers
    - Constellations and asterisms
    - Dark sky sites
    - Space events calendar

    This command is idempotent - it can be run multiple times without creating duplicates.
    Use --force to clear existing data before seeding.
    Use --status to show current seed data status without seeding.

    Examples:
        nexstar data seed
        nexstar data seed --force
        nexstar data seed --status
    """
    from celestron_nexstar.api.database.models import get_db_session

    # If status flag is set, show status and exit
    if status:
        console.print("\n[bold cyan]Seed Data Status[/bold cyan]\n")
        try:

            async def _get_status() -> dict[str, int]:
                from celestron_nexstar.api.database.database_seeder import get_seed_status

                async with get_db_session() as db_session:
                    return await get_seed_status(db_session)

            status_data = asyncio.run(_get_status())

            # Create a table to display status
            from rich.table import Table

            from celestron_nexstar.api.database.database_seeder import get_seed_data_path, load_seed_json

            # Get expected counts from seed files
            seed_dir = get_seed_data_path()
            expected_counts: dict[str, int] = {}
            seed_file_map = {
                "star_name_mappings": "star_name_mappings.json",
                "constellations": "constellations.json",
                "asterisms": "asterisms.json",
                "meteor_showers": "meteor_showers.json",
                "dark_sky_sites": "dark_sky_sites.json",
                "space_events": "space_events.json",
                "variable_stars": "variable_stars.json",
                "comets": "comets.json",
                "eclipses": "eclipses.json",
                "bortle_characteristics": "bortle_characteristics.json",
            }

            for data_type, filename in seed_file_map.items():
                try:
                    json_path = seed_dir / filename
                    if json_path.exists():
                        data = load_seed_json(filename)
                        expected_counts[data_type] = len(data)
                except Exception:
                    pass

            table = Table(show_header=True, header_style="bold", show_lines=False)
            table.add_column("Data Type", style="cyan", width=25)
            table.add_column("Expected", justify="right", width=10, style="dim")
            table.add_column("Count", justify="right", width=10)
            table.add_column("Status", width=15)

            total_records = 0
            total_expected = 0
            for data_type, count in sorted(status_data.items()):
                expected = expected_counts.get(data_type, 0)
                total_records += count
                total_expected += expected

                if expected > 0:
                    if count == expected:
                        status_str = "[green]Complete[/green]"
                    elif count > 0:
                        status_str = f"[yellow]Partial ({count}/{expected})[/yellow]"
                    else:
                        status_str = "[yellow]Not Seeded[/yellow]"
                else:
                    status_str = "[green]Seeded[/green]" if count > 0 else "[yellow]Not Seeded[/yellow]"

                display_name = data_type.replace("_", " ").title()
                expected_str = f"{expected:,}" if expected > 0 else "-"
                table.add_row(display_name, expected_str, str(count), status_str)

            console.print(table)

            expected_total_str = f"{total_expected:,}" if total_expected > 0 else "-"
            console.print(f"\n[bold]Expected seed records:[/bold] {expected_total_str}")
            console.print(f"[bold]Total seed records:[/bold] {total_records}")
            console.print("[dim]Run 'nexstar data seed' to populate missing data.[/dim]\n")
        except Exception as e:
            console.print(f"\n[red]✗[/red] Error checking seed status: {e}\n")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1) from e
        return

    console.print("\n[bold cyan]Seeding database with static reference data[/bold cyan]\n")

    try:

        async def _seed_all() -> dict[str, int]:
            from celestron_nexstar.api.database.database_seeder import seed_all

            async with get_db_session() as db_session:
                return await seed_all(db_session, force=force)

        results = asyncio.run(_seed_all())

        # Display results
        total_added = sum(results.values())
        if total_added > 0:
            console.print("\n[bold green]✓ Seeding complete![/bold green]")
            console.print("\n[bold]Summary:[/bold]")
            for data_type, count in results.items():
                if count > 0:
                    console.print(f"  [green]✓[/green] {data_type.replace('_', ' ').title()}: {count} record(s) added")
                else:
                    console.print(
                        f"  [dim]•[/dim] {data_type.replace('_', ' ').title()}: already seeded (no new records)"
                    )
            console.print(f"\n[dim]Total records added: {total_added}[/dim]\n")
        else:
            console.print("\n[bold]✓ All data already seeded[/bold]")
            console.print("[dim]No new records were added. Use --force to re-seed all data.[/dim]\n")

    except FileNotFoundError as e:
        console.print(f"\n[red]✗[/red] Seed data file not found: {e}\n")
        console.print("[dim]Make sure seed data files exist in the seed directory.[/dim]\n")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error seeding database: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e


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
    console.print("\n[bold cyan]Initializing static reference data[/bold cyan]\n")

    try:
        # Use database_seeder directly, which is async
        from celestron_nexstar.api.database.database_seeder import seed_all
        from celestron_nexstar.api.database.models import get_db_session

        async def _init_static_data() -> None:
            async with get_db_session() as db_session:
                # Use seed_all which handles all static data seeding
                await seed_all(db_session, force=False)

        asyncio.run(_init_static_data())

        console.print("\n[bold green]✓ All static data initialized![/bold green]")
        console.print("[dim]These datasets are now available offline.[/dim]\n")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Error initializing static data: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None


@app.command("clear-cache", rich_help_panel="Data Management")
def clear_cache() -> None:
    """
    Delete all cached data files.

    This command removes cached files from:
    - Celestial data cache (~/.cache/celestron-nexstar/celestial-data/)
    - Light pollution cache (~/.cache/celestron-nexstar/light-pollution/)

    Use this if you want to force re-download of all data files.

    Examples:
        nexstar data clear-cache
    """
    from celestron_nexstar.cli.data_import import get_cache_dir

    console.print("\n[yellow]Clearing cached files...[/yellow]\n")

    # Clear celestial data cache
    celestial_cache = get_cache_dir()
    deleted_count = 0
    if celestial_cache.exists():
        for file in celestial_cache.glob("*"):
            if file.is_file():
                file.unlink()
                deleted_count += 1
                console.print(f"[dim]  Deleted: {file.name}[/dim]")
        if deleted_count > 0:
            console.print(f"[green]✓[/green] Cleared {deleted_count} file(s) from celestial data cache")
        else:
            console.print("[dim]  No files found in celestial data cache[/dim]")
    else:
        console.print("[dim]  Celestial data cache directory does not exist[/dim]")

    # Clear light pollution cache
    light_pollution_cache = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
    deleted_count = 0
    if light_pollution_cache.exists():
        for file in light_pollution_cache.glob("*.png"):
            file.unlink()
            deleted_count += 1
            console.print(f"[dim]  Deleted: {file.name}[/dim]")
        if deleted_count > 0:
            console.print(f"[green]✓[/green] Cleared {deleted_count} file(s) from light pollution cache")
        else:
            console.print("[dim]  No files found in light pollution cache[/dim]")
    else:
        console.print("[dim]  Light pollution cache directory does not exist[/dim]")

    console.print("\n[green]✓[/green] Cache clearing complete\n")


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

    from celestron_nexstar.api.database.database import get_database

    db = get_database()
    db_stats = asyncio.run(db.get_stats())

    # Overall stats
    console.print("\n[bold cyan]Database Statistics[/bold cyan]")
    console.print(f"Total objects: [green]{db_stats.total_objects:,}[/green]")
    console.print(f"Dynamic objects: [yellow]{db_stats.dynamic_objects}[/yellow] (planets/moons)")

    mag_min, mag_max = db_stats.magnitude_range
    if mag_min is not None and mag_max is not None:
        console.print(f"Magnitude range: [cyan]{mag_min:.2f}[/cyan] to [cyan]{mag_max:.2f}[/cyan]")

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

        async def _get_lp_stats() -> tuple[
            bool, int | None, tuple[float | None, float | None] | None, list[Row[tuple[str | None, int]]] | None
        ]:
            async with db._AsyncSession() as session:
                # Check if table exists
                table_check = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='light_pollution_grid'")
                )
                table_exists = table_check.fetchone() is not None

                if not table_exists:
                    return False, None, None, None

                # Get total count using SQLAlchemy
                from sqlalchemy import func, select

                from celestron_nexstar.api.database.models import LightPollutionGridModel

                total_count_result = await session.scalar(select(func.count(LightPollutionGridModel.id)))
                total_count = total_count_result or 0

                if total_count == 0:
                    return True, 0, None, None

                # Get SQM range using SQLAlchemy
                sqm_result = await session.execute(
                    select(
                        func.min(LightPollutionGridModel.sqm_value),
                        func.max(LightPollutionGridModel.sqm_value),
                    )
                )
                sqm_range = sqm_result.fetchone()
                if sqm_range is not None:
                    sqm_min = sqm_range[0] if sqm_range[0] is not None else None
                    sqm_max = sqm_range[1] if sqm_range[1] is not None else None
                else:
                    sqm_min = None
                    sqm_max = None

                # Get coverage by region using SQLAlchemy
                region_result = await session.execute(
                    select(
                        LightPollutionGridModel.region,
                        func.count(LightPollutionGridModel.id),
                    )
                    .where(LightPollutionGridModel.region.isnot(None))
                    .group_by(LightPollutionGridModel.region)
                    .order_by(LightPollutionGridModel.region)
                )
                region_counts = region_result.fetchall()

                return True, total_count, (sqm_min, sqm_max), list(region_counts)

        table_exists, total_count, sqm_range, region_counts = asyncio.run(_get_lp_stats())

        if table_exists and total_count is not None:
            if total_count > 0:
                sqm_min, sqm_max = sqm_range if sqm_range else (None, None)

                lp_table = Table(title="\nLight Pollution Data")
                lp_table.add_column("Metric", style="cyan")
                lp_table.add_column("Value", justify="right", style="green")

                lp_table.add_row("Total grid points", f"{total_count:,}")
                if sqm_min is not None and sqm_max is not None:
                    lp_table.add_row("SQM range", f"{sqm_min:.2f} to {sqm_max:.2f}")
                lp_table.add_row("Spatial indexing", "[green]Geohash[/green]")

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

    # Seed data statistics
    try:
        from celestron_nexstar.api.database.database_seeder import get_seed_data_path, get_seed_status, load_seed_json
        from celestron_nexstar.api.database.models import get_db_session

        async def _get_seed_status() -> dict[str, int]:
            async with get_db_session() as db_session:
                return await get_seed_status(db_session)

        seed_status = asyncio.run(_get_seed_status())

        # Get expected counts from seed files
        seed_dir = get_seed_data_path()
        expected_counts: dict[str, int] = {}
        seed_file_map = {
            "star_name_mappings": "star_name_mappings.json",
            "constellations": "constellations.json",
            "asterisms": "asterisms.json",
            "meteor_showers": "meteor_showers.json",
            "dark_sky_sites": "dark_sky_sites.json",
            "space_events": "space_events.json",
            "variable_stars": "variable_stars.json",
            "comets": "comets.json",
            "eclipses": "eclipses.json",
            "bortle_characteristics": "bortle_characteristics.json",
        }

        for data_type, filename in seed_file_map.items():
            try:
                json_path = seed_dir / filename
                if json_path.exists():
                    data = load_seed_json(filename)
                    expected_counts[data_type] = len(data)
            except Exception:
                pass

        seed_table = Table(title="\nSeed Data (Static Reference Data)")
        seed_table.add_column("Data Type", style="cyan")
        seed_table.add_column("Expected", justify="right", style="dim")
        seed_table.add_column("Count", justify="right", style="green")
        seed_table.add_column("Status", width=15)

        total_seed_records = 0
        total_expected = 0
        for data_type in sorted(seed_status.keys()):
            count = seed_status[data_type]
            expected = expected_counts.get(data_type, 0)
            total_seed_records += count
            total_expected += expected

            if expected > 0:
                if count == expected:
                    status_str = "[green]Complete[/green]"
                elif count > 0:
                    status_str = f"[yellow]Partial ({count}/{expected})[/yellow]"
                else:
                    status_str = "[yellow]Not Seeded[/yellow]"
            else:
                status_str = "[green]Seeded[/green]" if count > 0 else "[yellow]Not Seeded[/yellow]"

            display_name = data_type.replace("_", " ").title()
            expected_str = f"{expected:,}" if expected > 0 else "-"
            seed_table.add_row(display_name, expected_str, f"{count:,}", status_str)

        if total_seed_records > 0 or total_expected > 0:
            seed_table.add_row("", "", "", "")
            expected_total_str = f"{total_expected:,}" if total_expected > 0 else "-"
            seed_table.add_row("[bold]Total[/bold]", expected_total_str, f"[bold]{total_seed_records:,}[/bold]", "")

        console.print(seed_table)
    except Exception:
        # Silently skip if there's an error (tables might not exist)
        pass

    # TLE data statistics
    try:
        from datetime import datetime

        from sqlalchemy import func, select

        from celestron_nexstar.api.database.models import TLEModel, get_db_session

        async def _get_tle_stats() -> tuple[
            bool,
            int | None,
            list[Row[tuple[str | None, int]]] | None,
            int | None,
            datetime | None,
            tuple[datetime | None, datetime | None] | None,
        ]:
            async with get_db_session() as db_session:
                # Check if table exists
                table_check = await db_session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='tle_data'")
                )
                table_exists = table_check.fetchone() is not None

                if not table_exists:
                    return False, None, None, None, None, None

                total_tle_result = await db_session.scalar(select(func.count(TLEModel.norad_id)))
                total_tle_count = total_tle_result or 0

                if total_tle_count == 0:
                    return True, 0, None, None, None, None

                # Get counts by group
                group_result = await db_session.execute(
                    select(
                        TLEModel.satellite_group,
                        func.count(TLEModel.norad_id),
                    )
                    .where(TLEModel.satellite_group.isnot(None))
                    .group_by(TLEModel.satellite_group)
                    .order_by(TLEModel.satellite_group)
                )
                group_counts = group_result.fetchall()

                # Get unique satellite count
                unique_result = await db_session.scalar(select(func.count(func.distinct(TLEModel.norad_id))))
                unique_satellites = unique_result or 0

                # Get last fetched time
                last_fetched_result = await db_session.scalar(
                    select(func.max(TLEModel.fetched_at)).where(TLEModel.fetched_at.isnot(None))
                )
                last_fetched = last_fetched_result

                # Get oldest TLE epoch (to show data freshness)
                oldest_result = await db_session.scalar(
                    select(func.min(TLEModel.epoch)).where(TLEModel.epoch.isnot(None))
                )
                oldest_epoch = oldest_result
                newest_result = await db_session.scalar(
                    select(func.max(TLEModel.epoch)).where(TLEModel.epoch.isnot(None))
                )
                newest_epoch = newest_result

                return (
                    True,
                    total_tle_count,
                    list(group_counts),
                    unique_satellites,
                    last_fetched,
                    (oldest_epoch, newest_epoch),
                )

        table_exists, total_tle_count, group_counts, unique_satellites, last_fetched, epoch_range = asyncio.run(
            _get_tle_stats()
        )

        if table_exists and total_tle_count is not None:
            if total_tle_count > 0:
                oldest_epoch, newest_epoch = epoch_range if epoch_range else (None, None)

                tle_table = Table(title="\nTLE Data (Satellite Orbital Elements)")
                tle_table.add_column("Metric", style="cyan")
                tle_table.add_column("Value", justify="right", style="green")

                tle_table.add_row("Total TLE records", f"{total_tle_count:,}")
                tle_table.add_row("Unique satellites", f"{unique_satellites:,}")

                if last_fetched:
                    last_fetched_str = last_fetched.strftime("%Y-%m-%d %H:%M:%S")
                    tle_table.add_row("Last fetched", last_fetched_str)

                if oldest_epoch and newest_epoch:
                    oldest_str = oldest_epoch.strftime("%Y-%m-%d")
                    newest_str = newest_epoch.strftime("%Y-%m-%d")
                    tle_table.add_row("TLE epoch range", f"{oldest_str} to {newest_str}")

                console.print(tle_table)

                # Groups table if we have group data
                if group_counts:
                    group_table = Table(title="TLE Data by Satellite Group")
                    group_table.add_column("Group", style="cyan")
                    group_table.add_column("Satellites", justify="right", style="green")

                    for group_name, count in group_counts:
                        display_name = group_name.title() if group_name else "Unknown"
                        group_table.add_row(display_name, f"{count:,}")

                    console.print(group_table)
            else:
                console.print("\n[dim]TLE data: [yellow]No data imported[/yellow][/dim]")
        else:
            console.print("\n[dim]TLE data: [yellow]Table not created[/yellow][/dim]")
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
    from celestron_nexstar.api.database.database import get_database, vacuum_database

    db = get_database()

    # Get file size before
    size_before = db.db_path.stat().st_size if db.db_path.exists() else 0

    console.print("\n[bold cyan]Running VACUUM on database[/bold cyan]\n")
    console.print(f"[dim]Database: {db.db_path}[/dim]")
    console.print(f"[dim]Size before: {size_before / (1024 * 1024):.2f} MB[/dim]\n")

    try:
        import asyncio

        size_before_bytes, size_after_bytes = asyncio.run(vacuum_database(db))
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
    from celestron_nexstar.api.database.database import get_database
    from celestron_nexstar.api.database.light_pollution_db import clear_light_pollution_data

    db = get_database()

    # Check if table exists and get row count
    try:
        with db._get_session_sync() as session:
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
            from celestron_nexstar.api.database.database import vacuum_database

            console.print("[dim]Running VACUUM to reclaim disk space...[/dim]")
            import asyncio

            size_before, size_after = asyncio.run(vacuum_database(db))
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

    from celestron_nexstar.api.database.light_pollution_db import download_world_atlas_data

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

            from celestron_nexstar.api.database.light_pollution_db import download_world_atlas_data

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

    from celestron_nexstar.api.database.database import get_database, rebuild_database

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
            response = typer.prompt("Continue? (yes/no)", default="no", type=str)
            # Normalize response: strip whitespace, handle empty string as "no"
            response_normalized = (response or "no").strip().lower()
            if response_normalized not in ("yes", "y"):
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

            # Run rebuild - rebuild_database is now async
            result: dict[str, Any] = asyncio.run(
                rebuild_database(
                    backup_dir=backup_path,
                    sources=source_list,
                    mag_limit=mag_limit,
                    skip_backup=skip_backup,
                    dry_run=dry_run,
                )
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
        db_stats = asyncio.run(db.get_stats())
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


@app.command("migrate", rich_help_panel="Database Management")
def run_migrations(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be migrated without applying changes"),
) -> None:
    """
    Check for pending Alembic migrations and apply them if needed.

    This command checks the current database revision against the latest migration
    and applies any pending migrations. If the database is already up to date,
    it will report that no migrations are needed.

    Examples:
        nexstar data migrate
        nexstar data migrate --dry-run  # Preview what would be migrated
    """
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from alembic import command  # type: ignore[attr-defined]
    from celestron_nexstar.api.database.database import get_database

    console.print("\n[bold cyan]Checking database migrations...[/bold cyan]\n")

    db = get_database()

    # Check if database exists
    if not db.db_path.exists():
        console.print("[yellow]⚠[/yellow] Database does not exist. Creating it...")
        # Create empty database file
        db.db_path.parent.mkdir(parents=True, exist_ok=True)
        db.db_path.touch()

    # Configure Alembic
    alembic_cfg = Config("alembic.ini")
    # Always set database URL to ensure we're using the correct database
    # Use the same database path as the database instance
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.db_path}")

    try:
        # Get current revision from database
        # Alembic needs a sync engine, so create one
        from sqlalchemy import create_engine

        sync_engine = create_engine(f"sqlite:///{db.db_path}", connect_args={"check_same_thread": False})
        with sync_engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

        # Get head revision(s) from script directory
        script = ScriptDirectory.from_config(alembic_cfg)
        try:
            # Try to get single head first (works when there's no branching)
            head_rev = script.get_current_head()
        except Exception:
            # Multiple heads detected - use get_heads() instead
            try:
                heads_list = script.get_heads()
                if len(heads_list) == 1:
                    head_rev = heads_list[0]
                elif len(heads_list) > 1:
                    # Multiple heads detected - look for a merge migration
                    console.print("[yellow]⚠[/yellow] Multiple migration heads detected")
                    console.print(f"[dim]Found {len(heads_list)} head(s): {', '.join(heads_list)}[/dim]")

                    # Search all revisions for a merge migration that combines these heads
                    merge_found = False
                    for rev in script.walk_revisions():
                        if hasattr(rev, "down_revision") and rev.down_revision:
                            down_rev = rev.down_revision
                            # Check if this is a merge migration (has tuple of down_revisions)
                            if isinstance(down_rev, tuple) and len(down_rev) > 1:
                                # Check if this merge migration combines all current heads
                                down_rev_set = set(down_rev) if isinstance(down_rev, tuple) else {down_rev}
                                heads_set = set(heads_list)
                                if down_rev_set == heads_set:
                                    merge_found = True
                                    head_rev = rev.revision
                                    console.print(f"[dim]Found merge migration: {rev.revision}[/dim]\n")
                                    break

                    if not merge_found:
                        console.print("[dim]No merge migration found. Will attempt to upgrade all branches.[/dim]\n")
                        # Use "heads" to upgrade all branches - Alembic will apply merge migrations if they exist
                        head_rev = "heads"
                else:
                    head_rev = None
            except Exception as e:
                console.print(f"[red]✗[/red] Error checking migrations: {e}")
                raise typer.Exit(code=1) from e

        # Check if there are pending migrations
        migrations_to_apply: list[str] | str = "unknown"
        if current_rev is None:
            console.print("[yellow]⚠[/yellow] Database has no migration history")
            console.print("[dim]This is normal for a new database. Will apply all migrations.[/dim]\n")
            pending = True
            migrations_to_apply = "all migrations"
        elif head_rev is not None and head_rev != "heads" and current_rev == head_rev:
            console.print("[green]✓[/green] Database is up to date")
            console.print(f"[dim]Current revision: {current_rev}[/dim]\n")
            pending = False
        else:
            # Get the list of revisions that need to be applied
            pending = True
            try:
                # Get the upgrade path from current to head
                # walk_revisions returns revisions in order from start to end
                if head_rev is not None and current_rev is not None and head_rev != "heads":
                    upgrade_path = list(script.walk_revisions(current_rev, head_rev))
                    migrations_to_apply = [str(rev.revision) for rev in upgrade_path if rev.revision != current_rev]
                elif head_rev == "heads":
                    # Multiple heads - can't easily determine path, will let Alembic handle it
                    migrations_to_apply = "multiple branches (will be merged)"

                    console.print("[yellow]⚠[/yellow] Database is not up to date")
                    console.print(f"[dim]Current revision: {current_rev}[/dim]")
                    console.print("[dim]Head revision: multiple branches[/dim]")
                    console.print("[dim]Alembic will apply merge migration automatically.[/dim]\n")
                else:
                    migrations_to_apply = "unknown"
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not determine upgrade path: {e}")
                console.print(f"[dim]Current revision: {current_rev}[/dim]")
                console.print(f"[dim]Head revision: {head_rev}[/dim]")
                console.print("[dim]Will attempt to upgrade to head anyway.[/dim]\n")
                migrations_to_apply = "unknown"

        if not pending:
            console.print("[bold green]No migrations needed![/bold green]\n")
            return

        if dry_run:
            console.print("[bold yellow][DRY RUN] Would apply migrations:[/bold yellow]")
            if isinstance(migrations_to_apply, list):
                for rev_str in migrations_to_apply:
                    console.print(f"  - {rev_str}")
            else:  # str
                console.print(f"  - {migrations_to_apply}")
            console.print("\n[dim]Run without --dry-run to apply migrations.[/dim]\n")
            return

        # Apply migrations
        console.print("[cyan]Applying migrations...[/cyan]\n")
        try:
            # Dispose of existing connections to ensure Alembic uses fresh connections
            import asyncio

            async def _dispose_engine() -> None:
                await db._engine.dispose()

            asyncio.run(_dispose_engine())

            # Use upgrade to head - this will apply ALL pending migrations in sequence
            # Alembic will automatically apply all migrations from current state to head
            # Use the determined head_rev (which may be "heads" for multiple branches)
            upgrade_target = head_rev if head_rev is not None else "head"
            command.upgrade(alembic_cfg, upgrade_target)
            console.print("\n[bold green]✓ Migrations applied successfully![/bold green]\n")

            # Verify the new revision after applying migrations
            # Get a fresh connection to ensure we see the updated state
            asyncio.run(_dispose_engine())  # Close existing connections
            from sqlalchemy import create_engine

            sync_engine = create_engine(f"sqlite:///{db.db_path}", connect_args={"check_same_thread": False})
            with sync_engine.connect() as connection:
                context = MigrationContext.configure(connection)
                new_rev = context.get_current_revision()
                try:
                    head_rev_after = script.get_current_head()
                except Exception:
                    # Multiple heads - get the merge migration if it exists
                    heads_list = script.get_heads()
                    if len(heads_list) == 1:
                        head_rev_after = heads_list[0]
                    else:
                        # Look for merge migration
                        head_rev_after = None
                        for rev in script.walk_revisions():
                            if hasattr(rev, "down_revision") and rev.down_revision:
                                down_rev = rev.down_revision
                                if isinstance(down_rev, tuple) and len(down_rev) > 1:
                                    down_rev_set = set(down_rev) if isinstance(down_rev, tuple) else {down_rev}
                                    heads_set = set(heads_list)
                                    if down_rev_set == heads_set:
                                        head_rev_after = rev.revision
                                        break
                        if head_rev_after is None:
                            head_rev_after = heads_list[0] if heads_list else None

                if new_rev == head_rev_after:
                    console.print(f"[dim]Database is now at revision: {new_rev}[/dim]\n")
                else:
                    console.print(f"[yellow]⚠[/yellow] Database revision: {new_rev}")
                    console.print(f"[yellow]⚠[/yellow] Head revision: {head_rev_after}")
                    console.print("[yellow]⚠[/yellow] Database may not be fully up to date. Run migrate again.\n")
        except Exception as e:
            console.print(f"\n[red]✗[/red] Error applying migrations: {e}\n")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1) from e

    except Exception as e:
        console.print(f"\n[red]✗[/red] Error checking migrations: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e


@app.command("rebuild-seed", rich_help_panel="Database Management")
def rebuild_seed_files(
    data_type: str = typer.Argument(
        ...,
        help="Type of seed data to rebuild: 'comets', 'variable_stars', or 'all'",
    ),
    max_magnitude: float = typer.Option(
        10.0,
        "--max-mag",
        "-m",
        help="Maximum magnitude to include (default: 10.0 for comets, 8.0 for variable stars)",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        "-l",
        help="Maximum number of records to fetch (0 = no limit, default: 0)",
    ),
) -> None:
    """
    Rebuild seed files by fetching data from external sources.

    This command fetches the latest data from authoritative sources and rebuilds
    the seed JSON files used by the database seeder.

    Data Sources:
    - Comets: Minor Planet Center (MPC) and COBS (Comet Observation Database)
    - Variable Stars: AAVSO VSX (Variable Star Index) and GCVS (General Catalog of Variable Stars)

    Examples:
        nexstar data rebuild-seed comets
        nexstar data rebuild-seed variable_stars --max-mag 8.0
        nexstar data rebuild-seed all --limit 100
    """
    from celestron_nexstar.api.database.database_seeder import get_seed_data_path

    console.print(f"\n[bold cyan]Rebuilding seed files for: {data_type}[/bold cyan]\n")

    seed_dir = get_seed_data_path()
    seed_dir.mkdir(parents=True, exist_ok=True)

    if data_type in ("comets", "all"):
        console.print("[bold]Fetching comet data...[/bold]")
        try:
            comets_data = _fetch_comets_data(max_magnitude=max_magnitude, limit=limit if limit > 0 else None)
            comets_path = seed_dir / "comets.json"
            with open(comets_path, "w", encoding="utf-8") as f:
                import json

                json.dump(comets_data, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✓[/green] Wrote {len(comets_data)} comets to {comets_path}")
        except Exception as e:
            console.print(f"[red]✗[/red] Error fetching comet data: {e}")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    if data_type in ("variable_stars", "all"):
        console.print("\n[bold]Fetching variable star data...[/bold]")
        try:
            vs_mag_limit = min(max_magnitude, 8.0)  # Variable stars typically brighter
            variable_stars_data = _fetch_variable_stars_data(
                max_magnitude=vs_mag_limit, limit=limit if limit > 0 else None
            )
            variable_stars_path = seed_dir / "variable_stars.json"
            with open(variable_stars_path, "w", encoding="utf-8") as f:
                import json

                json.dump(variable_stars_data, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✓[/green] Wrote {len(variable_stars_data)} variable stars to {variable_stars_path}")
        except Exception as e:
            console.print(f"[red]✗[/red] Error fetching variable star data: {e}")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    console.print("\n[bold green]✓ Seed file rebuild complete![/bold green]")
    console.print("[dim]Run 'nexstar data seed --force' to update the database with new data.[/dim]\n")


def _fetch_comets_data(max_magnitude: float = 10.0, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Fetch comet data from external sources.

    Sources:
    - Minor Planet Center (MPC) - official source
    - COBS (Comet Observation Database) - comprehensive observations

    Args:
        max_magnitude: Maximum magnitude to include
        limit: Maximum number of comets to fetch (None = no limit)

    Returns:
        List of comet dictionaries in seed file format
    """
    import aiohttp

    comets: list[dict[str, Any]] = []

    async def _fetch_from_mpc() -> list[dict[str, Any]]:
        """Fetch bright comets from Minor Planet Center."""
        # MPC provides comet orbital elements via their website
        # For bright comets, we can query their database
        # Note: MPC doesn't have a public API, so we'll parse their HTML/text pages
        url = "https://minorplanetcenter.net/iau/Ephemerides/Comets/Soft00Cmt.txt"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        text = await response.text()
                        parsed = _parse_mpc_comet_data(text, max_magnitude)
                        if parsed:
                            console.print(f"[green]✓[/green] Fetched {len(parsed)} comets from MPC")
                        return parsed
                    else:
                        console.print(f"[yellow]⚠[/yellow] MPC returned status {response.status}")
            except aiohttp.ClientError as e:
                console.print(f"[yellow]⚠[/yellow] Network error fetching from MPC: {e}")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Error fetching from MPC: {e}")
                console.print(f"[dim]Error type: {type(e).__name__}[/dim]")

        return []

    async def _fetch_from_cobs() -> list[dict[str, Any]]:
        """Fetch comet data from COBS (Comet Observation Database)."""
        # COBS has a web interface but may not have a public API
        # For now, we'll use a fallback approach
        return []

    # Try MPC first
    import asyncio

    mpc_comets = asyncio.run(_fetch_from_mpc())
    if mpc_comets:
        comets.extend(mpc_comets)

    # If we still don't have data, inform the user
    if not comets:
        console.print("[yellow]⚠[/yellow] Could not fetch comet data from external sources.")
        console.print(
            "[dim]The existing seed file will be preserved. Check your internet connection and try again.[/dim]"
        )
        # Load existing seed file if it exists
        from celestron_nexstar.api.database.database_seeder import get_seed_data_path, load_seed_json

        seed_dir = get_seed_data_path()
        existing_file = seed_dir / "comets.json"
        if existing_file.exists():
            try:
                from typing import cast

                existing_data = load_seed_json("comets.json")
                console.print(f"[dim]Found existing seed file with {len(existing_data)} comets.[/dim]")
                return cast(list[dict[str, Any]], existing_data)
            except Exception:
                pass
        return []

    # Apply limit if specified
    if limit and len(comets) > limit:
        comets = comets[:limit]

    return comets


def _parse_mpc_comet_data(text: str, max_magnitude: float) -> list[dict[str, Any]]:
    """
    Parse MPC comet data format.

    MPC format is a text file with comet orbital elements.
    Format documentation: https://minorplanetcenter.net/iau/info/CometOrbitFormat.html
    """
    from datetime import UTC, datetime

    comets: list[dict[str, Any]] = []
    lines = text.strip().split("\n")

    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue

        try:
            # MPC format: Designation code, Epoch (Y M D), q, e, i, w, Node, T (YYYYMMDD), H, G, Full name, Reference
            # Example: "CJ95O010  1997 03 30.4369  0.910384  0.994930  130.3983  281.9480   89.6379  20251113  -2.0  4.0  C/1995 O1 (Hale-Bopp)  MPEC 2022-S20"
            parts = line.split()
            if len(parts) < 12:
                continue

            # Parse orbital elements (fixed positions)
            # Parts: [0]=designation_code, [1]=epoch_year, [2]=epoch_month, [3]=epoch_day,
            #        [4]=q, [5]=e, [6]=i, [7]=w, [8]=Node, [9]=T (YYYYMMDD), [10]=H, [11]=G,
            #        [12+]=full_name, [last]=reference
            q = float(parts[4])  # Perihelion distance in AU
            e = float(parts[5])  # Eccentricity
            # i, w, Node skipped for now
            t_yyyymmdd = parts[9]  # Time of perihelion as YYYYMMDD
            h_magnitude = float(parts[10])  # Absolute magnitude H
            # G (magnitude slope) is in parts[11], but we don't use it

            # Parse perihelion date from YYYYMMDD format
            if len(t_yyyymmdd) == 8:
                t_year = int(t_yyyymmdd[:4])
                t_month = int(t_yyyymmdd[4:6])
                t_day = int(t_yyyymmdd[6:8])
            else:
                # Fallback: try to parse from epoch if T format is unexpected
                t_year = int(parts[1])
                t_month = int(parts[2])
                t_day = int(float(parts[3]))

            # Calculate perihelion date
            perihelion_date = datetime(t_year, t_month, t_day, tzinfo=UTC)

            # Extract full designation name (everything between G and the last field)
            if len(parts) > 12:
                # Full name is from parts[12] to parts[-2] (last is reference)
                full_name_parts = parts[12:-1] if len(parts) > 13 else parts[12:]
                designation = " ".join(full_name_parts)
            else:
                # Fallback to designation code
                designation = parts[0]

            # Rough magnitude estimate (comets are brightest near perihelion)
            peak_magnitude = h_magnitude + 5.0  # Rough estimate

            if peak_magnitude > max_magnitude:
                continue

            # Determine if periodic (eccentricity < 1.0 and period can be calculated)
            is_periodic = e < 1.0
            period_years = None
            if is_periodic:
                # Calculate period from semi-major axis: P = sqrt(a^3)
                # a = q / (1 - e)
                a = q / (1 - e)
                period_years = (a**1.5) ** 0.5  # Kepler's third law

            # Use designation as name
            name = designation

            comet = {
                "name": name,
                "designation": designation,
                "perihelion_date": perihelion_date.isoformat(),
                "perihelion_distance_au": q,
                "peak_magnitude": peak_magnitude,
                "peak_date": perihelion_date.isoformat(),
                "is_periodic": is_periodic,
                "period_years": period_years,
                "notes": f"Orbital data from MPC. Eccentricity: {e:.3f}",
            }

            comets.append(comet)
        except (ValueError, IndexError):
            # Skip malformed lines
            continue

    return comets


def _fetch_variable_stars_data(max_magnitude: float = 8.0, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Fetch variable star data from external sources.

    Sources:
    - AAVSO VSX (Variable Star Index) - comprehensive database
    - GCVS (General Catalog of Variable Stars) - official catalog

    Args:
        max_magnitude: Maximum magnitude to include
        limit: Maximum number of stars to fetch (None = no limit)

    Returns:
        List of variable star dictionaries in seed file format
    """
    import aiohttp

    stars: list[dict[str, Any]] = []

    async def _fetch_from_vsx() -> list[dict[str, Any]]:
        """Fetch variable stars from AAVSO VSX."""
        # VSX API endpoint
        # Note: VSX may have rate limits, so we'll query well-known bright stars
        # For a full catalog, we'd need to use VSX's search API or download the full catalog
        # VSX uses abbreviated constellation names (e.g., "R Boo" not "R Bootis")
        well_known_names = [
            "Algol",  # bet Per
            "Mira",  # omi Cet
            "del Cep",  # Delta Cephei
            "bet Lyr",  # Beta Lyrae
            "R Leo",  # R Leonis
            "R Hya",  # R Hydrae
            "chi Cyg",  # Chi Cygni
            "R Cas",  # R Cassiopeiae
            "R Car",  # R Carinae
            "R Dor",  # R Doradus
            "R Cen",  # R Centauri
            "R Boo",  # R Bootis
            "R Vir",  # R Virginis
            "R UMa",  # R Ursae Majoris
            "R CMa",  # R Canis Majoris
            "R Gem",  # R Geminorum
            "R Aur",  # R Aurigae
            "R And",  # R Andromedae
        ]

        from urllib.parse import quote

        async with aiohttp.ClientSession() as session:
            fetched_stars = []
            for name in well_known_names:
                try:
                    # URL-encode the star name to handle spaces and special characters
                    encoded_name = quote(name)
                    # Use vsx.aavso.org directly (www.aavso.org redirects)
                    url = f"https://vsx.aavso.org/index.php?view=api.object&format=json&ident={encoded_name}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            try:
                                data = await response.json()
                                star = _parse_vsx_data(data, max_magnitude)
                                if star:
                                    fetched_stars.append(star)
                                    console.print(f"[dim]✓ Fetched {name}[/dim]")
                                else:
                                    console.print(
                                        f"[dim]✗ {name}: Parsed but filtered out (magnitude or missing data)[/dim]"
                                    )
                            except Exception as parse_error:
                                # Check if response is HTML (error page) instead of JSON
                                text = await response.text()
                                if text.strip().startswith("<"):
                                    console.print(f"[dim]✗ {name}: API returned HTML (not found or error)[/dim]")
                                else:
                                    console.print(f"[dim]✗ {name}: Parse error: {parse_error}[/dim]")
                        else:
                            console.print(f"[dim]✗ {name}: HTTP {response.status}[/dim]")
                        # Small delay to avoid rate limiting
                        import asyncio

                        await asyncio.sleep(0.5)
                except Exception as e:
                    console.print(f"[dim]✗ {name}: Error: {e}[/dim]")
                    continue

            return fetched_stars

    async def _fetch_from_gcvs() -> list[dict[str, Any]]:
        """Fetch from GCVS catalog via VizieR or NASA Open Data Portal."""
        # GCVS is available via VizieR/CDS
        # For now, we'll use a simplified approach
        # Full implementation would query VizieR or download from NASA's Open Data Portal
        return []

    # Try VSX first, then GCVS
    import asyncio

    vsx_stars = asyncio.run(_fetch_from_vsx())
    if vsx_stars:
        stars.extend(vsx_stars)

    # Try GCVS as additional source
    gcvs_stars = asyncio.run(_fetch_from_gcvs())
    if gcvs_stars:
        # Avoid duplicates by name
        existing_names = {s["name"] for s in stars}
        for star in gcvs_stars:
            if star["name"] not in existing_names:
                stars.append(star)
                existing_names.add(star["name"])

    # If we still don't have data, inform the user
    if not stars:
        console.print("[yellow]⚠[/yellow] Could not fetch variable star data from external sources.")
        console.print(
            "[dim]The existing seed file will be preserved. Check your internet connection and try again.[/dim]"
        )
        # Load existing seed file if it exists
        from celestron_nexstar.api.database.database_seeder import get_seed_data_path, load_seed_json

        seed_dir = get_seed_data_path()
        existing_file = seed_dir / "variable_stars.json"
        if existing_file.exists():
            try:
                from typing import cast

                existing_data = load_seed_json("variable_stars.json")
                console.print(f"[dim]Found existing seed file with {len(existing_data)} variable stars.[/dim]")
                return cast(list[dict[str, Any]], existing_data)
            except Exception:
                pass
        return []

    # Apply limit if specified
    if limit and len(stars) > limit:
        stars = stars[:limit]

    return stars


def _parse_vsx_data(data: Any, max_magnitude: float) -> dict[str, Any] | None:
    """
    Parse AAVSO VSX API response.

    VSX API returns JSON with star information.
    Format: https://www.aavso.org/vsx/index.php?view=api.doc
    """
    import re

    try:
        # VSX API returns data wrapped in "VSXObject" key
        # Format: {"VSXObject": {"Name": "...", ...}} or {"VSXObject": []} if not found
        star_data: dict[str, Any] | None = None
        if isinstance(data, dict):
            # Check if wrapped in VSXObject
            if "VSXObject" in data:
                vsx_obj = data["VSXObject"]
                # Handle empty array (star not found)
                if isinstance(vsx_obj, list):
                    if len(vsx_obj) == 0:
                        return None  # Star not found
                    # If it's a list with items, take the first one
                    vsx_obj = vsx_obj[0]
                # Now vsx_obj should be a dict
                if isinstance(vsx_obj, dict) and "Name" in vsx_obj:
                    star_data = vsx_obj
            # Or it might be a dict with Name directly
            elif "Name" in data:
                star_data = data
        elif isinstance(data, list) and len(data) > 0:
            # If it's a list, take the first element
            first_item = data[0]
            if isinstance(first_item, dict):
                if "VSXObject" in first_item:
                    vsx_obj = first_item["VSXObject"]
                    if isinstance(vsx_obj, dict) and "Name" in vsx_obj:
                        star_data = vsx_obj
                elif "Name" in first_item:
                    star_data = first_item

        if star_data is None or "Name" not in star_data:
            return None

        name = star_data.get("Name", "")
        if not name:
            return None

        # Extract coordinates (RA/Dec in degrees, convert to hours/degrees)
        ra_deg = star_data.get("RA2000")
        dec_deg = star_data.get("Declination2000")

        if ra_deg is None or dec_deg is None:
            return None

        ra_hours = float(ra_deg) / 15.0  # Convert degrees to hours
        dec_degrees = float(dec_deg)

        # Extract magnitude range
        # VSX returns magnitudes as strings like "2.09 V" or "3.30 V"
        max_mag = star_data.get("MaxMag", star_data.get("Max", None))
        min_mag = star_data.get("MinMag", star_data.get("Min", None))

        if max_mag is None or min_mag is None:
            # Try alternative field names
            max_mag = star_data.get("MaximumMagnitude")
            min_mag = star_data.get("MinimumMagnitude")

        if max_mag is None or min_mag is None:
            return None

        # Parse magnitude strings (e.g., "2.09 V" -> 2.09)
        def parse_magnitude(mag: Any) -> float | None:
            if mag is None:
                return None
            mag_str = str(mag).strip()
            # Extract numeric value (handle formats like "2.09 V" or "3.30")
            match = re.match(r"([+-]?\d+\.?\d*)", mag_str)
            if match:
                return float(match.group(1))
            return None

        max_mag_float = parse_magnitude(max_mag)
        min_mag_float = parse_magnitude(min_mag)

        if max_mag_float is None or min_mag_float is None:
            return None

        # Check magnitude limit
        if max_mag_float > max_magnitude:
            return None

        # Extract variable type
        var_type_raw = star_data.get("VarType") or star_data.get("VariabilityType") or "unknown"
        var_type = str(var_type_raw).lower().replace(" ", "_")

        # Extract period (in days)
        period = star_data.get("Period", star_data.get("PeriodDays", 0.0))
        period_days = float(period) if period else 0.0

        # Extract designation
        designation = star_data.get("OID", star_data.get("Identifier", ""))

        # Build notes
        notes_parts = []
        if var_type != "unknown":
            notes_parts.append(f"Variable type: {var_type}")
        if period_days > 0:
            notes_parts.append(f"Period: {period_days:.2f} days")
        notes = ". ".join(notes_parts) if notes_parts else "Data from AAVSO VSX"

        return {
            "name": name,
            "designation": designation or name,
            "variable_type": var_type,
            "period_days": period_days,
            "magnitude_min": min_mag_float,
            "magnitude_max": max_mag_float,
            "ra_hours": ra_hours,
            "dec_degrees": dec_degrees,
            "notes": notes,
        }
    except (ValueError, KeyError, TypeError) as e:
        console.print(f"[dim]Error parsing VSX data: {e}[/dim]")
        return None
