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
from typer.core import TyperGroup

from celestron_nexstar.api.core.exceptions import (
    CatalogNotFoundError,
    DatabaseRebuildError,
    DatabaseRestoreError,
)
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
    except (RuntimeError, AttributeError, ValueError, TypeError, KeyError, IndexError, OSError, TimeoutError) as e:
        # RuntimeError: async/await errors, event loop errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: network/file I/O errors
        # TimeoutError: request timeout
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
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
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

    except (RuntimeError, AttributeError, ValueError, TypeError, KeyError, IndexError) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
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
        except (
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
            FileNotFoundError,
            PermissionError,
        ) as e:
            # AttributeError: missing database attributes
            # RuntimeError: database connection errors
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: file I/O errors
            # FileNotFoundError: missing database file
            # PermissionError: file permission errors
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

        except (
            DatabaseRebuildError,
            RuntimeError,
            AttributeError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
            FileNotFoundError,
            PermissionError,
        ) as e:
            # DatabaseRebuildError: database rebuild errors
            # RuntimeError: async/await errors, import errors
            # AttributeError: missing attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: file I/O errors
            # FileNotFoundError: missing files
            # PermissionError: file permission errors
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
        except (AttributeError, RuntimeError, ValueError, TypeError, FileNotFoundError, OSError):
            # AttributeError: missing Alembic attributes
            # RuntimeError: migration errors
            # ValueError: invalid configuration
            # TypeError: wrong argument types
            # FileNotFoundError: missing alembic.ini
            # OSError: file I/O errors
            # Silently skip migration errors (non-critical)
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
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
        console.print(f"[yellow]⚠[/yellow] Error checking static data: {e}")
        # Try to populate anyway
        try:
            # Note: These populate functions may expect sync sessions
            # This fallback is skipped as it requires sync sessions which are no longer available
            # The main seeding path above should handle this
            console.print("[yellow]⚠[/yellow] Fallback population skipped (requires sync sessions)")
        except (RuntimeError, AttributeError, ValueError, TypeError) as e2:
            # RuntimeError: async/await errors
            # AttributeError: missing attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            console.print(f"[yellow]⚠[/yellow] Failed to populate static data (non-critical): {e2}")

    # Sync ephemeris metadata (optional)
    if not skip_ephemeris:
        console.print("\n[cyan]Syncing ephemeris file metadata...[/cyan]")
        try:
            from celestron_nexstar.api.database.database import sync_ephemeris_files_from_naif

            # asyncio is imported at module level
            count = asyncio.run(sync_ephemeris_files_from_naif(force=False))
            console.print(f"[green]✓[/green] Synced {count} ephemeris files")
        except (RuntimeError, AttributeError, ValueError, TypeError, KeyError, IndexError, OSError, TimeoutError) as e:
            # RuntimeError: async/await errors, event loop errors
            # AttributeError: missing attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: network/file I/O errors
            # TimeoutError: request timeout
            console.print(f"[yellow]⚠[/yellow] Ephemeris sync failed (non-critical): {e}")
            console.print("[dim]You can sync later with: nexstar data sync-ephemeris[/dim]")

    # Final summary
    console.print("\n[bold green]✓ Database setup complete![/bold green]\n")

    # Show stats
    try:
        stats = asyncio.run(db.get_stats())
        console.print(f"[dim]Total objects: {stats.total_objects:,}[/dim]")
        console.print(f"[dim]Database size: {db.db_path.stat().st_size / (1024 * 1024):.2f} MB[/dim]\n")
    except (RuntimeError, AttributeError, ValueError, TypeError, OSError, FileNotFoundError):
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # OSError: file I/O errors
        # FileNotFoundError: missing database file
        # Silently skip stats errors (non-critical)
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
                "planets": "sol_planets.json",
                "moons": "sol_moons.json",
            }

            for data_type, filename in seed_file_map.items():
                try:
                    json_path = seed_dir / filename
                    if json_path.exists():
                        data = load_seed_json(filename)
                        expected_counts[data_type] = len(data)
                except (FileNotFoundError, PermissionError, ValueError, TypeError, KeyError, IndexError):
                    # FileNotFoundError: missing seed file
                    # PermissionError: can't read file
                    # ValueError: invalid JSON format
                    # TypeError: wrong data types
                    # KeyError: missing keys in JSON
                    # IndexError: missing array indices
                    # Silently skip individual seed file errors
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
        except (
            RuntimeError,
            AttributeError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
            FileNotFoundError,
            PermissionError,
        ) as e:
            # RuntimeError: async/await errors, database errors
            # AttributeError: missing database/model attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: file I/O errors
            # FileNotFoundError: missing files
            # PermissionError: file permission errors
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

    except CatalogNotFoundError as e:
        console.print(f"\n[red]✗[/red] Seed data file not found: {e}\n")
        console.print("[dim]Make sure seed data files exist in the seed directory.[/dim]\n")
        raise typer.Exit(code=1) from e
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
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
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
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
        from celestron_nexstar.api.database.statistics import get_light_pollution_stats

        lp_stats = asyncio.run(get_light_pollution_stats())

        if lp_stats.table_exists and lp_stats.total_count is not None:
            if lp_stats.total_count > 0:
                lp_table = Table(title="\nLight Pollution Data")
                lp_table.add_column("Metric", style="cyan")
                lp_table.add_column("Value", justify="right", style="green")

                lp_table.add_row("Total grid points", f"{lp_stats.total_count:,}")
                if lp_stats.sqm_min is not None and lp_stats.sqm_max is not None:
                    lp_table.add_row("SQM range", f"{lp_stats.sqm_min:.2f} to {lp_stats.sqm_max:.2f}")
                lp_table.add_row("Spatial indexing", "[green]Geohash[/green]")

                console.print(lp_table)

                # Regions table if we have region data
                if lp_stats.region_counts:
                    region_table = Table(title="Coverage by Region")
                    region_table.add_column("Region", style="cyan")
                    region_table.add_column("Grid Points", justify="right", style="green")

                    for region, count in lp_stats.region_counts:
                        region_name = region if region else "Unknown"
                        region_table.add_row(region_name, f"{count:,}")

                    console.print(region_table)
            else:
                console.print("\n[dim]Light pollution data: [yellow]No data imported[/yellow][/dim]")
        else:
            console.print("\n[dim]Light pollution data: [yellow]Table not created[/yellow][/dim]")
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError):
        # AttributeError: missing database/model attributes
        # RuntimeError: database connection errors
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
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
            "planets": "sol_planets.json",
            "moons": "sol_moons.json",
        }

        for data_type, filename in seed_file_map.items():
            try:
                json_path = seed_dir / filename
                if json_path.exists():
                    data = load_seed_json(filename)
                    expected_counts[data_type] = len(data)
            except (FileNotFoundError, PermissionError, ValueError, TypeError, KeyError, IndexError):
                # FileNotFoundError: missing seed file
                # PermissionError: can't read file
                # ValueError: invalid JSON format
                # TypeError: wrong data types
                # KeyError: missing keys in JSON
                # IndexError: missing array indices
                # Silently skip individual seed file errors
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
    except (RuntimeError, AttributeError, ValueError, TypeError, KeyError, IndexError):
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # Silently skip if there's an error (tables might not exist)
        pass

    # TLE data statistics
    try:
        from celestron_nexstar.api.database.statistics import get_tle_stats

        tle_stats = asyncio.run(get_tle_stats())

        if tle_stats.table_exists and tle_stats.total_count is not None:
            if tle_stats.total_count > 0:
                tle_table = Table(title="\nTLE Data (Satellite Orbital Elements)")
                tle_table.add_column("Metric", style="cyan")
                tle_table.add_column("Value", justify="right", style="green")

                tle_table.add_row("Total TLE records", f"{tle_stats.total_count:,}")
                if tle_stats.unique_satellites is not None:
                    tle_table.add_row("Unique satellites", f"{tle_stats.unique_satellites:,}")

                if tle_stats.last_fetched:
                    last_fetched_str = tle_stats.last_fetched.strftime("%Y-%m-%d %H:%M:%S")
                    tle_table.add_row("Last fetched", last_fetched_str)

                if tle_stats.oldest_epoch and tle_stats.newest_epoch:
                    oldest_str = tle_stats.oldest_epoch.strftime("%Y-%m-%d")
                    newest_str = tle_stats.newest_epoch.strftime("%Y-%m-%d")
                    tle_table.add_row("TLE epoch range", f"{oldest_str} to {newest_str}")

                console.print(tle_table)

                # Groups table if we have group data
                if tle_stats.group_counts:
                    group_table = Table(title="TLE Data by Satellite Group")
                    group_table.add_column("Group", style="cyan")
                    group_table.add_column("Satellites", justify="right", style="green")

                    for group_name, count in tle_stats.group_counts:
                        display_name = group_name.title() if group_name else "Unknown"
                        group_table.add_row(display_name, f"{count:,}")

                    console.print(group_table)
            else:
                console.print("\n[dim]TLE data: [yellow]No data imported[/yellow][/dim]")
        else:
            console.print("\n[dim]TLE data: [yellow]Table not created[/yellow][/dim]")
    except (RuntimeError, AttributeError, ValueError, TypeError, KeyError, IndexError):
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
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
    except (RuntimeError, AttributeError, ValueError, TypeError, OSError, FileNotFoundError, PermissionError) as e:
        # RuntimeError: database errors
        # AttributeError: missing database attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # OSError: file I/O errors
        # FileNotFoundError: missing database file
        # PermissionError: file permission errors
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
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError, IndexError):
        # AttributeError: missing database/model attributes
        # RuntimeError: database connection errors, table doesn't exist
        # ValueError: invalid SQL
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
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
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: database errors
        # AttributeError: missing database/model attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
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
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
        TimeoutError,
    ) as e:
        # RuntimeError: async/await errors, download/processing errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors, network errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
        # TimeoutError: download timeout
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

    except DatabaseRebuildError as e:
        console.print(f"\n[red]✗[/red] Rebuild failed: {e}\n")
        console.print("[yellow]Note:[/yellow] If a backup was created, it may have been restored.\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
    except DatabaseRestoreError as e:
        console.print(f"\n[red]✗[/red] Restore failed: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from None
    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        FileNotFoundError,
        PermissionError,
    ) as e:
        # RuntimeError: async/await errors, database errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors
        # FileNotFoundError: missing files
        # PermissionError: file permission errors
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
            current_rev: str | None | list[str] = None
            try:
                current_rev = context.get_current_revision()
            except (AttributeError, RuntimeError, ValueError):
                # AttributeError: missing Alembic context attributes
                # RuntimeError: multiple heads or migration errors
                # ValueError: invalid revision format
                # Multiple heads in database - use get_current_heads() instead
                current_heads = context.get_current_heads()
                if len(current_heads) == 1:
                    current_rev = current_heads[0]
                elif len(current_heads) > 1:
                    # Multiple heads in database - we'll need to handle this
                    console.print(f"[yellow]⚠[/yellow] Database has multiple heads: {', '.join(current_heads)}")
                    console.print("[dim]Will attempt to upgrade to latest head(s).[/dim]\n")
                    current_rev = list(current_heads)  # Keep as list for now
                else:
                    current_rev = None

        # Get head revision(s) from script directory
        script = ScriptDirectory.from_config(alembic_cfg)
        try:
            # Try to get single head first (works when there's no branching)
            head_rev = script.get_current_head()
        except (AttributeError, RuntimeError, ValueError):
            # AttributeError: missing script attributes
            # RuntimeError: multiple heads or script errors
            # ValueError: invalid configuration
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
            except (AttributeError, RuntimeError, ValueError, TypeError) as e:
                # AttributeError: missing script attributes
                # RuntimeError: script errors
                # ValueError: invalid configuration
                # TypeError: wrong argument types
                console.print(f"[red]✗[/red] Error checking migrations: {e}")
                raise typer.Exit(code=1) from e

        # Check if there are pending migrations
        migrations_to_apply: list[str] | str = "unknown"
        current_rev_single: str | None = (
            (current_rev[0] if current_rev else None) if isinstance(current_rev, list) else current_rev
        )

        if current_rev_single is None:
            console.print("[yellow]⚠[/yellow] Database has no migration history")
            console.print("[dim]This is normal for a new database. Will apply all migrations.[/dim]\n")
            pending = True
            migrations_to_apply = "all migrations"
        elif isinstance(current_rev, list):
            # Multiple heads in database - always need to upgrade
            pending = True
            migrations_to_apply = "multiple branches (will be merged)"
            console.print("[yellow]⚠[/yellow] Database has multiple heads")
            console.print(f"[dim]Current heads: {', '.join(current_rev)}[/dim]")
            console.print("[dim]Will attempt to upgrade to latest head(s).[/dim]\n")
        elif head_rev is not None and head_rev != "heads" and current_rev_single == head_rev:
            console.print("[green]✓[/green] Database is up to date")
            console.print(f"[dim]Current revision: {current_rev_single}[/dim]\n")
            pending = False
        else:
            # Get the list of revisions that need to be applied
            pending = True
            try:
                # Get the upgrade path from current to head
                # walk_revisions returns revisions in order from start to end
                if head_rev is not None and current_rev_single is not None and head_rev != "heads":
                    upgrade_path = list(script.walk_revisions(current_rev_single, head_rev))
                    migrations_to_apply = [
                        str(rev.revision) for rev in upgrade_path if rev.revision != current_rev_single
                    ]
                elif head_rev == "heads":
                    # Multiple heads - can't easily determine path, will let Alembic handle it
                    migrations_to_apply = "multiple branches (will be merged)"

                    console.print("[yellow]⚠[/yellow] Database is not up to date")
                    console.print(f"[dim]Current revision: {current_rev_single}[/dim]")
                    console.print("[dim]Head revision: multiple branches[/dim]")
                    console.print("[dim]Alembic will apply merge migration automatically.[/dim]\n")
                else:
                    migrations_to_apply = "unknown"
            except (AttributeError, RuntimeError, ValueError, TypeError) as e:
                # AttributeError: missing Alembic attributes
                # RuntimeError: migration comparison errors
                # ValueError: invalid revision format
                # TypeError: wrong argument types
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
                try:
                    new_rev = context.get_current_revision()
                except (AttributeError, RuntimeError, ValueError):
                    # AttributeError: missing Alembic context attributes
                    # RuntimeError: multiple heads or migration errors
                    # ValueError: invalid revision format
                    # Multiple heads - use get_current_heads()
                    new_heads = context.get_current_heads()
                    new_rev = new_heads[0] if len(new_heads) == 1 else ", ".join(new_heads) if new_heads else "unknown"
                try:
                    head_rev_after = script.get_current_head()
                except (AttributeError, RuntimeError, ValueError):
                    # AttributeError: missing script attributes
                    # RuntimeError: multiple heads or script errors
                    # ValueError: invalid configuration
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
        except (AttributeError, RuntimeError, ValueError, TypeError, OSError, FileNotFoundError) as e:
            # AttributeError: missing Alembic attributes
            # RuntimeError: migration errors
            # ValueError: invalid configuration or revision format
            # TypeError: wrong argument types
            # OSError: file I/O errors
            # FileNotFoundError: missing alembic.ini or migration files
            console.print(f"\n[red]✗[/red] Error applying migrations: {e}\n")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1) from e

    except (AttributeError, RuntimeError, ValueError, TypeError, OSError, FileNotFoundError) as e:
        # AttributeError: missing Alembic attributes
        # RuntimeError: migration errors
        # ValueError: invalid configuration
        # TypeError: wrong argument types
        # OSError: file I/O errors
        # FileNotFoundError: missing alembic.ini
        console.print(f"\n[red]✗[/red] Error checking migrations: {e}\n")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(code=1) from e


@app.command("rebuild-seed", rich_help_panel="Database Management")
def rebuild_seed_files(
    data_type: str = typer.Argument(
        ...,
        help="Type of seed data to rebuild: 'comets', 'variable_stars', 'dark_sky_sites', or 'all'",
    ),
    skip_scraping: bool = typer.Option(
        False,
        "--skip-scraping",
        help="Skip web scraping for dark_sky_sites (use existing seed file only). Recommended if you have ethical concerns about scraping.",
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
    - Dark Sky Sites: International Dark-Sky Association (IDA) official list

    Examples:
        nexstar data rebuild-seed comets
        nexstar data rebuild-seed variable_stars --max-mag 8.0
        nexstar data rebuild-seed dark_sky_sites
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
        except (
            RuntimeError,
            AttributeError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
            FileNotFoundError,
            PermissionError,
            TimeoutError,
        ) as e:
            # RuntimeError: async/await errors, API errors
            # AttributeError: missing attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: file I/O errors, network errors
            # FileNotFoundError: missing files
            # PermissionError: file permission errors
            # TimeoutError: request timeout
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
        except (
            RuntimeError,
            AttributeError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            OSError,
            FileNotFoundError,
            PermissionError,
            TimeoutError,
        ) as e:
            # RuntimeError: async/await errors, API errors
            # AttributeError: missing attributes
            # ValueError: invalid data format
            # TypeError: wrong data types
            # KeyError: missing keys in data
            # IndexError: missing array indices
            # OSError: file I/O errors, network errors
            # FileNotFoundError: missing files
            # PermissionError: file permission errors
            # TimeoutError: request timeout
            console.print(f"[red]✗[/red] Error fetching variable star data: {e}")
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    if data_type in ("dark_sky_sites", "all"):
        console.print("\n[bold]Fetching dark sky sites data...[/bold]")
        if skip_scraping:
            console.print("[yellow]⚠[/yellow] Skipping web scraping (--skip-scraping flag set)")
            console.print("[dim]Using existing seed file only. To update data, remove --skip-scraping flag.[/dim]")
            console.print(
                "[dim]Note: Consider contacting IDA to request official data access: https://www.darksky.org/contact/[/dim]"
            )
            dark_sites_path = seed_dir / "dark_sky_sites.json"
            if dark_sites_path.exists():
                from celestron_nexstar.api.database.database_seeder import load_seed_json

                existing_data = load_seed_json("dark_sky_sites.json")
                count = len(
                    [
                        item
                        for item in existing_data
                        if not (isinstance(item, dict) and any(key.startswith("_") for key in item))
                    ]
                )
                console.print(f"[green]✓[/green] Using existing seed file with {count} dark sky sites")
            else:
                console.print(
                    "[yellow]⚠[/yellow] No existing seed file found. Run without --skip-scraping to create one."
                )
        else:
            console.print("[yellow]⚠[/yellow] [bold]Ethical Notice:[/bold] This will scrape the IDA website.")
            console.print(
                "[dim]The IDA website uses Cloudflare protection. Scraping may violate their terms of service.[/dim]"
            )
            console.print("[dim]Consider:[/dim]")
            console.print("[dim]  • Contacting IDA for official data access: https://www.darksky.org/contact/[/dim]")
            console.print("[dim]  • Using --skip-scraping to use existing data only[/dim]")
            console.print("[dim]  • Manually updating the seed file from official sources[/dim]")
            console.print()
            proceed = typer.confirm("Do you want to proceed with scraping?", default=False)
            if not proceed:
                console.print("[yellow]Skipping dark sky sites scraping.[/yellow]")
                console.print("[dim]Use --skip-scraping flag to skip this prompt in the future.[/dim]")
            else:
                try:
                    dark_sites_data = asyncio.run(_fetch_dark_sky_sites_data())
                    dark_sites_path = seed_dir / "dark_sky_sites.json"
                    with open(dark_sites_path, "w", encoding="utf-8") as f:
                        import json

                        json.dump(dark_sites_data, f, indent=2, ensure_ascii=False)
                    count = len(
                        [
                            item
                            for item in dark_sites_data
                            if not (isinstance(item, dict) and any(key.startswith("_") for key in item))
                        ]
                    )
                    console.print(f"[green]✓[/green] Wrote {count} dark sky sites to {dark_sites_path}")
                except (
                    RuntimeError,
                    AttributeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    OSError,
                    FileNotFoundError,
                    PermissionError,
                    TimeoutError,
                ) as e:
                    # RuntimeError: async/await errors, API errors, browser automation errors
                    # AttributeError: missing attributes
                    # ValueError: invalid data format
                    # TypeError: wrong data types
                    # KeyError: missing keys in data
                    # IndexError: missing array indices
                    # OSError: file I/O errors, network errors
                    # FileNotFoundError: missing files
                    # PermissionError: file permission errors
                    # TimeoutError: request timeout
                    console.print(f"[red]✗[/red] Error fetching dark sky sites data: {e}")
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
            except (TimeoutError, ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
                # TimeoutError: request timeout
                # ValueError: invalid JSON or data format
                # TypeError: wrong data types
                # KeyError: missing keys in response
                # IndexError: missing array indices
                # AttributeError: missing attributes in response
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
            except (FileNotFoundError, PermissionError, ValueError, TypeError, KeyError, IndexError):
                # FileNotFoundError: missing seed file
                # PermissionError: can't read file
                # ValueError: invalid JSON format
                # TypeError: wrong data types
                # KeyError: missing keys in JSON
                # IndexError: missing array indices
                # Silently skip if seed file doesn't exist or is invalid
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
                            except (ValueError, TypeError, KeyError, IndexError, AttributeError) as parse_error:
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
                except (
                    aiohttp.ClientError,
                    TimeoutError,
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    AttributeError,
                    RuntimeError,
                ) as e:
                    # aiohttp.ClientError: HTTP/network errors
                    # TimeoutError: request timeout
                    # ValueError: invalid data format
                    # TypeError: wrong data types
                    # KeyError: missing keys in response
                    # IndexError: missing array indices
                    # AttributeError: missing attributes in response
                    # RuntimeError: async/await errors
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
            except (FileNotFoundError, PermissionError, ValueError, TypeError, KeyError, IndexError):
                # FileNotFoundError: missing seed file
                # PermissionError: can't read file
                # ValueError: invalid JSON format
                # TypeError: wrong data types
                # KeyError: missing keys in JSON
                # IndexError: missing array indices
                # Silently skip if seed file doesn't exist or is invalid
                pass
        return []

    # Apply limit if specified
    if limit and len(stars) > limit:
        stars = stars[:limit]

    return stars


async def _fetch_dark_sky_sites_data() -> list[dict[str, Any]]:
    """
    Fetch dark sky sites data from the International Dark-Sky Association (IDA).

    This function fetches the latest list of International Dark Sky Places from the IDA website,
    geocodes their locations, estimates Bortle class and SQM values, and merges with existing data.

    Note: The IDA website uses Cloudflare protection which may prevent automated scraping.
    If scraping fails, consider:
    - Manually updating the seed file
    - Checking if IDA provides an official API or data export
    - Using alternative data sources

    Data Source: International Dark-Sky Association (IDA)
    URL: https://darksky.org/what-we-do/international-dark-sky-places/all-places/

    Returns:
        List of dark sky site dictionaries in seed file format
    """
    import re
    from datetime import datetime

    import aiohttp

    from celestron_nexstar.api.database.database_seeder import get_seed_data_path, load_seed_json

    ida_base_url = "https://darksky.org"
    ida_places_url = f"{ida_base_url}/what-we-do/international-dark-sky-places/all-places/?_location_dropdown=usa"
    geocode_url = "https://nominatim.openstreetmap.org/search"

    def estimate_bortle_from_description(description: str, designation: str) -> int:
        """Estimate Bortle class from description and designation type."""
        desc_lower = description.lower()
        desig_lower = designation.lower()

        if "sanctuary" in desig_lower:
            return 1
        if "park" in desig_lower or "reserve" in desig_lower:
            if any(word in desc_lower for word in ["darkest", "pristine", "exceptional", "excellent"]):
                return 1
            return 2
        if "community" in desig_lower:
            return 2
        if "urban" in desig_lower:
            return 3
        return 2

    def estimate_sqm_from_bortle(bortle: int) -> float:
        """Estimate SQM value from Bortle class."""
        sqm_map = {1: 22.0, 2: 21.8, 3: 21.3, 4: 20.4, 5: 19.1, 6: 18.0, 7: 17.0, 8: 16.0, 9: 15.0}
        return sqm_map.get(bortle, 21.0)

    async def geocode_location(name: str, country: str = "") -> tuple[float, float] | None:
        """Geocode a location name to get latitude and longitude."""
        query = f"{name}, {country}" if country else name

        try:
            async with aiohttp.ClientSession() as session:
                params: dict[str, str | int] = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
                headers = {"User-Agent": "Celestron-NexStar/1.0 (Dark Sky Sites Data Compilation)"}

                async with session.get(geocode_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data: list[dict[str, Any]] = await response.json()
                        if data:
                            return (float(data[0]["lat"]), float(data[0]["lon"]))
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            # aiohttp.ClientError: HTTP/network errors
            # TimeoutError: request timeout
            # ValueError: invalid JSON or coordinates
            # TypeError: wrong data types
            # KeyError: missing keys in response
            # IndexError: missing array indices
            # AttributeError: missing attributes in response
            # Silently skip geocoding errors
            pass

        return None

    def generate_geohash(lat: float, lon: float) -> str:
        """Generate a geohash for a location."""
        try:
            from celestron_nexstar.api.location.geohash_utils import encode

            return encode(lat, lon, precision=9)
        except ImportError:
            return ""

    # Try to load existing data to merge with
    seed_dir = get_seed_data_path()
    existing_file = seed_dir / "dark_sky_sites.json"
    existing_places: list[dict[str, Any]] = []
    existing_names: set[str] = set()

    if existing_file.exists():
        try:
            existing_data = load_seed_json("dark_sky_sites.json")
            # Filter out metadata objects
            existing_places = [
                item
                for item in existing_data
                if not (isinstance(item, dict) and any(key.startswith("_") for key in item))
            ]
            existing_names = {place["name"].lower() for place in existing_places}
            console.print(f"[dim]Found {len(existing_places)} existing dark sky sites[/dim]")
        except (FileNotFoundError, PermissionError, ValueError, TypeError, KeyError, IndexError):
            # FileNotFoundError: missing seed file
            # PermissionError: can't read file
            # ValueError: invalid JSON format
            # TypeError: wrong data types
            # KeyError: missing keys in JSON
            # IndexError: missing array indices
            # Silently skip if seed file doesn't exist or is invalid
            pass

    # Fetch places from IDA website
    # Note: The IDA website may use JavaScript to load content dynamically, which means
    # BeautifulSoup (which only parses static HTML) may not see all places. The IDA has
    # over 200 certified places, so if we find fewer than that, the website structure
    # may have changed or requires JavaScript rendering.
    places: list[dict[str, Any]] = []

    try:
        # Try to import BeautifulSoup
        try:
            from bs4 import BeautifulSoup

        except ImportError:
            console.print("[yellow]⚠[/yellow] BeautifulSoup4 not installed. Install with: pip install beautifulsoup4")
            console.print("[dim]Falling back to existing seed file.[/dim]")
            return existing_places

        # Try to use Playwright or Selenium for JavaScript rendering
        # The IDA website has a "Load More" button that needs to be clicked to see all places
        use_browser_automation = False
        browser_html = None

        # Try Playwright first (faster and more modern)
        try:
            from playwright.async_api import async_playwright

            console.print("[dim]Using Playwright to render JavaScript and click 'Load More' button...[/dim]")
            console.print("[dim]Loading page (this may take a moment - Cloudflare challenge may appear)...[/dim]")
            async with async_playwright() as p:
                try:
                    # Launch browser with more realistic settings to avoid Cloudflare detection
                    # Non-headless mode is less likely to be detected by Cloudflare
                    # Set headless=False if you want to see the browser (useful for debugging)
                    # For production, you might want to try headless=True first, then fall back to False
                    browser = await p.chromium.launch(
                        headless=False,  # Non-headless is less likely to trigger Cloudflare
                        timeout=30000,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-sandbox",
                        ],
                    )
                except (RuntimeError, AttributeError, ValueError, TypeError, OSError, FileNotFoundError) as e:
                    # RuntimeError: browser launch errors
                    # AttributeError: missing Playwright attributes
                    # ValueError: invalid browser options
                    # TypeError: wrong argument types
                    # OSError: system errors
                    # FileNotFoundError: Chromium not found
                    console.print(f"[yellow]⚠[/yellow] Failed to launch browser: {e}")
                    console.print("[dim]Make sure Chromium is installed: uv run playwright install chromium[/dim]")
                    raise

                # Create a context with realistic browser settings
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                page = await context.new_page()

                # Remove webdriver property to avoid detection
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                try:
                    console.print(f"[dim]Navigating to {ida_places_url}...[/dim]")
                    # Try 'load' first, which waits for all resources
                    await page.goto(ida_places_url, wait_until="load", timeout=60000)
                    console.print("[dim]Page loaded, waiting for Cloudflare challenge (if present)...[/dim]")

                    # Wait for Cloudflare challenge to complete
                    # Cloudflare usually shows a challenge page, then redirects
                    await page.wait_for_timeout(10000)  # Give Cloudflare time to process

                    # Check if we're on a Cloudflare challenge page
                    page_title = await page.title()
                    page_url = page.url
                    if (
                        "just a moment" in page_title.lower()
                        or "checking your browser" in page_title.lower()
                        or "challenge" in page_url.lower()
                    ):
                        console.print("[dim]Cloudflare challenge detected, waiting for it to complete...[/dim]")
                        # Wait for redirect away from challenge page
                        try:
                            await page.wait_for_function(
                                "window.location.href.indexOf('challenge') === -1 && document.title.toLowerCase().indexOf('just a moment') === -1",
                                timeout=30000,
                            )
                            console.print("[dim]Cloudflare challenge completed[/dim]")
                        except (TimeoutError, RuntimeError, AttributeError):
                            # TimeoutError: challenge timeout
                            # RuntimeError: Playwright errors
                            # AttributeError: missing page attributes
                            console.print(
                                "[yellow]⚠[/yellow] Cloudflare challenge may still be active, continuing anyway..."
                            )

                    console.print("[dim]Waiting for JavaScript to render content...[/dim]")
                    await page.wait_for_timeout(5000)  # Give JavaScript more time to render

                    # Wait for content to appear - look for common elements
                    try:
                        # Wait for either the load more button or some content to appear
                        await page.wait_for_selector(
                            "button.facetwp-load-more, .facetwp-template, [class*='place'], [class*='card'], .facetwp-results",
                            timeout=15000,
                            state="visible",
                        )
                        console.print("[dim]Content elements detected[/dim]")
                    except (TimeoutError, RuntimeError, AttributeError):
                        # TimeoutError: selector timeout
                        # RuntimeError: Playwright errors
                        # AttributeError: missing page attributes
                        console.print("[yellow]⚠[/yellow] No expected content elements found, but continuing...")

                    # Scroll to trigger lazy loading
                    console.print("[dim]Scrolling to trigger content loading...[/dim]")
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(3000)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(2000)

                    # Check page content length
                    content_length = len(await page.content())
                    console.print(f"[dim]Page HTML length: {content_length} characters[/dim]")
                except (RuntimeError, AttributeError, ValueError, TypeError, TimeoutError) as e:
                    # RuntimeError: Playwright errors, page load errors
                    # AttributeError: missing page attributes
                    # ValueError: invalid page content
                    # TypeError: wrong data types
                    # TimeoutError: page load timeout
                    console.print(f"[yellow]⚠[/yellow] Failed to load page: {e}")
                    await browser.close()
                    raise

                # Click "Load More" button repeatedly until all places are loaded
                console.print("[dim]Looking for 'Load More' button...[/dim]")
                max_clicks = 20  # Safety limit
                clicks = 0

                while clicks < max_clicks:
                    try:
                        # Check current content length to see if clicking is adding content
                        current_content = await page.content()
                        current_length = len(current_content)

                        # Look for "Load More" button with various possible selectors
                        # Note: The IDA site uses FacetWP with class "facetwp-load-more"
                        load_more_selectors = [
                            "button.facetwp-load-more",  # Specific to IDA site
                            "[class*='facetwp-load-more']",  # More flexible
                            "button:has-text('Load More')",
                            "button:has-text('Load more')",
                            "button:has-text('Show More')",
                            "button:has-text('Show more')",
                            "a:has-text('Load More')",
                            "a:has-text('Load more')",
                            "a:has-text('Show More')",
                            "a:has-text('Show more')",
                            "text='Load More'",
                            "text='Load more'",
                            "[class*='load-more']",
                            "[class*='loadMore']",
                            "[class*='show-more']",
                            "[class*='showMore']",
                            "[id*='load-more']",
                            "[id*='loadMore']",
                            "[id*='show-more']",
                            "[id*='showMore']",
                            "[aria-label*='Load More']",
                            "[aria-label*='Load more']",
                        ]

                        button_found = False
                        for selector in load_more_selectors:
                            try:
                                button = page.locator(selector).first
                                if await button.is_visible(timeout=2000):
                                    await button.click(timeout=5000)
                                    # FacetWP uses AJAX, so wait a bit longer for content to load
                                    await page.wait_for_timeout(4000)  # Wait for AJAX content to load

                                    # Wait for the button to become visible again (if more content is available)
                                    # or wait for loading indicator to disappear
                                    from contextlib import suppress

                                    with suppress(Exception):
                                        await page.wait_for_selector(
                                            "button.facetwp-load-more:not([disabled])", timeout=3000, state="visible"
                                        )  # Button might not reappear if all content is loaded

                                    # Scroll down to trigger any lazy loading
                                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                    await page.wait_for_timeout(2000)

                                    clicks += 1
                                    button_found = True
                                    console.print(f"[dim]Clicked 'Load More' ({clicks} times)...[/dim]")
                                    break
                            except (TimeoutError, RuntimeError, AttributeError):
                                # TimeoutError: selector timeout
                                # RuntimeError: Playwright errors
                                # AttributeError: missing page/button attributes
                                # Continue to next iteration
                                continue

                        if not button_found:
                            # No more button found, we've loaded everything
                            if clicks == 0:
                                console.print(
                                    "[dim]No 'Load More' button found - checking if content is already loaded...[/dim]"
                                )
                                # Try scrolling to see if more content loads
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                await page.wait_for_timeout(3000)
                                new_content = await page.content()
                                if len(new_content) > current_length:
                                    console.print("[dim]Scrolling loaded more content, continuing...[/dim]")
                                    continue
                            else:
                                console.print(f"[dim]No more 'Load More' button found after {clicks} clicks[/dim]")
                            break
                    except (RuntimeError, AttributeError, ValueError, TypeError, TimeoutError) as e:
                        # RuntimeError: Playwright errors
                        # AttributeError: missing page attributes
                        # ValueError: invalid page content
                        # TypeError: wrong data types
                        # TimeoutError: operation timeout
                        console.print(f"[dim]Error during button click loop: {e}[/dim]")
                        break

                # Get the fully rendered HTML
                console.print("[dim]Extracting page content...[/dim]")
                browser_html = await page.content()

                # Debug: Save HTML to file for inspection
                import os

                debug_file = os.path.join(os.path.expanduser("~"), "ida_page_debug.html")
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(browser_html)
                console.print(f"[dim]Saved page HTML to {debug_file} for debugging[/dim]")

                await context.close()
                await browser.close()
                use_browser_automation = True
                console.print(f"[green]✓[/green] Loaded page with browser automation ({clicks} 'Load More' clicks)")

        except ImportError:
            # Playwright not installed, try Selenium
            pass
        except (RuntimeError, AttributeError, ValueError, TypeError, TimeoutError, OSError) as e:
            # RuntimeError: Playwright errors, browser automation errors
            # AttributeError: missing Playwright attributes
            # ValueError: invalid browser options
            # TypeError: wrong argument types
            # TimeoutError: operation timeout
            # OSError: system errors
            # Browser automation failed, fall back to static HTML
            console.print(f"[yellow]⚠[/yellow] Browser automation failed: {e}")
            console.print("[dim]Falling back to static HTML parsing (may miss many places)...[/dim]")
            use_browser_automation = False
            browser_html = None

        # If Playwright failed or wasn't available, try Selenium
        if not use_browser_automation:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support import expected_conditions
                from selenium.webdriver.support.ui import WebDriverWait

                console.print("[dim]Using Selenium to render JavaScript and click 'Load More' button...[/dim]")
                options = Options()
                options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

                driver = webdriver.Chrome(options=options)
                driver.get(ida_places_url)

                # Click "Load More" button repeatedly
                max_clicks = 20
                clicks = 0
                while clicks < max_clicks:
                    try:
                        # Try various selectors for the Load More button
                        # Note: The IDA site uses FacetWP with class "facetwp-load-more"
                        load_more_selectors = [
                            "//button[contains(@class, 'facetwp-load-more')]",  # Specific to IDA site
                            "//button[contains(text(), 'Load More')]",
                            "//button[contains(text(), 'Load more')]",
                            "//a[contains(text(), 'Load More')]",
                            "//a[contains(text(), 'Load more')]",
                            "//*[contains(@class, 'load-more')]",
                            "//*[contains(@class, 'loadMore')]",
                        ]

                        button_found = False
                        for xpath in load_more_selectors:
                            try:
                                button = WebDriverWait(driver, 2).until(
                                    expected_conditions.element_to_be_clickable((By.XPATH, xpath))
                                )
                                button.click()
                                import time

                                time.sleep(4)  # FacetWP uses AJAX, wait longer for content to load
                                clicks += 1
                                button_found = True
                                console.print(f"[dim]Clicked 'Load More' ({clicks} times)...[/dim]", end="\r")
                                break
                            except (TimeoutError, RuntimeError, AttributeError):
                                # TimeoutError: selector timeout
                                # RuntimeError: Selenium errors
                                # AttributeError: missing driver/button attributes
                                # Continue to next iteration
                                continue

                        if not button_found:
                            break
                    except (RuntimeError, AttributeError, ValueError, TypeError, TimeoutError):
                        # RuntimeError: Selenium errors
                        # AttributeError: missing driver attributes
                        # ValueError: invalid page content
                        # TypeError: wrong data types
                        # TimeoutError: operation timeout
                        break

                console.print()  # New line after progress
                browser_html = driver.page_source
                driver.quit()
                use_browser_automation = True
                console.print("[green]✓[/green] Loaded page with browser automation")

            except ImportError:
                console.print(
                    "[yellow]⚠[/yellow] Neither Playwright nor Selenium is installed. "
                    "Install one to extract all places:"
                )
                console.print("[dim]  pip install playwright  # Recommended (faster)[/dim]")
                console.print("[dim]  playwright install chromium[/dim]")
                console.print("[dim]  OR[/dim]")
                console.print("[dim]  pip install selenium  # Alternative[/dim]")
                console.print("[dim]Falling back to static HTML parsing (may miss many places)...[/dim]")

        # Use browser-rendered HTML if available, otherwise use static HTML
        if use_browser_automation and browser_html:
            html = browser_html
        else:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; Celestron-NexStar/1.0; +https://github.com/mcosgriff/celestron-nexstar)",
                }

                console.print(f"[dim]Fetching from {ida_places_url}...[/dim]")

                async with session.get(
                    ida_places_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        console.print(f"[yellow]⚠[/yellow] IDA website returned status {response.status}")
                        console.print("[dim]Falling back to existing seed file.[/dim]")
                        return existing_places

                    html = await response.text()

        soup = BeautifulSoup(html, "html.parser")

        # Debug: Check what's actually on the page
        page_text = soup.get_text()
        console.print(f"[dim]Page text length: {len(page_text)} characters[/dim]")

        # Look for common patterns that might indicate places
        if "International Dark Sky" in page_text or "Dark Sky Park" in page_text:
            console.print("[dim]Found dark sky place keywords in page text[/dim]")
        else:
            console.print("[yellow]⚠[/yellow] No dark sky place keywords found - page may not have loaded correctly")

        # The IDA website might have different structures - try multiple approaches
        # Approach 1: Look for links to individual place pages (various URL patterns)
        place_links = soup.find_all("a", href=re.compile(r"/places/|/idsp/|/find/|/conservation/", re.I))

        # Also try looking for any links that might contain place names
        # The IDA website might list places in various formats
        all_links = soup.find_all("a", href=True)
        for link in all_links:
            href_attr = link.get("href", "")
            href = str(href_attr) if href_attr else ""
            # Look for patterns like /places/name or /idsp/name
            if href and re.search(r"/(places|idsp|find)/[^/]+", href, re.I) and link not in place_links:
                place_links.append(link)

        # Initialize seen_names early to avoid "used before definition" error
        seen_names: set[str] = set()

        # Also look for place names in the text content - they might be in divs, spans, or other elements
        # Look for elements that might contain place information
        if not place_links:
            console.print("[dim]No links found, trying to find place names in text content...[/dim]")
            # Look for common patterns like "Park Name" or "Name National Park"
            place_name_patterns = soup.find_all(
                string=re.compile(
                    r"(National Park|State Park|International Dark Sky|Dark Sky Park|Dark Sky Reserve|Dark Sky Sanctuary)",
                    re.I,
                )
            )
            if place_name_patterns:
                console.print(f"[dim]Found {len(place_name_patterns)} potential place name patterns in text[/dim]")

            # Try to find place cards or list items that might contain place information
            # Look for common card/list patterns
            cards = soup.find_all(["div", "article", "li"], class_=re.compile(r"card|item|place|location|park", re.I))
            if cards:
                console.print(f"[dim]Found {len(cards)} potential place cards/items[/dim]")
                # Try to extract place names from cards
                for card in cards[:50]:  # Limit to first 50 to avoid too much processing
                    text = card.get_text(strip=True)
                    # Look for place name patterns in card text
                    name_match = re.search(
                        r"^([A-Z][a-zA-Z\s&]+?)(?:\s+(?:National|State|International Dark Sky|Dark Sky))", text
                    )
                    if name_match:
                        name = name_match.group(1).strip()
                        if len(name) > 3 and name.lower() not in seen_names:
                            # Try to find a link within the card
                            card_link = card.find("a", href=True)
                            if card_link:
                                href_attr = card_link.get("href", "")
                                href = str(href_attr) if href_attr else ""
                                if href and href not in [str(link.get("href", "") or "") for link in place_links]:
                                    place_links.append(card_link)

        console.print(f"[dim]Found {len(place_links)} place links[/dim]")

        # Extract unique place names from links
        for link in place_links:
            try:
                # Get text from link or from parent elements
                name_text = link.get_text(strip=True)
                name = str(name_text) if name_text else ""
                if not name:
                    # Try getting from title attribute or data attributes
                    title_attr = link.get("title", "") or link.get("data-name", "")
                    name = str(title_attr) if title_attr else ""

                if not name or len(name) < 3:
                    continue

                # Clean up the name (remove extra whitespace, common prefixes)
                name = re.sub(r"\s+", " ", name).strip()
                name = re.sub(r"^(International Dark Sky |Dark Sky )", "", name, flags=re.I)

                if name.lower() in seen_names or name.lower() in existing_names:
                    continue

                seen_names.add(name.lower())

                # Try to extract designation from link text or nearby elements
                designation = "International Dark Sky Place"
                link_text = link.get_text(strip=True)
                parent = link.parent

                # Look for designation keywords
                if re.search(r"Park", link_text, re.I):
                    designation = "International Dark Sky Park"
                elif re.search(r"Reserve", link_text, re.I):
                    designation = "International Dark Sky Reserve"
                elif re.search(r"Sanctuary", link_text, re.I):
                    designation = "International Dark Sky Sanctuary"
                elif re.search(r"Community", link_text, re.I):
                    designation = "International Dark Sky Community"
                elif re.search(r"Urban", link_text, re.I):
                    designation = "Urban Night Sky Place"

                # Try to get description from nearby elements
                description = designation
                if parent:
                    desc_elem = parent.find(
                        ["p", "div", "span"], class_=re.compile(r"description|summary|excerpt|text", re.I)
                    )
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)

                # Try to extract location from link or nearby text
                country = ""
                location_text = link_text + " " + (parent.get_text() if parent else "")
                location_match = re.search(
                    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", location_text
                )
                if location_match:
                    country = location_match.group(2)

                places.append(
                    {"name": name, "designation": designation, "description": description, "country": country}
                )

            except (ValueError, TypeError, AttributeError, KeyError, IndexError):
                # ValueError: invalid regex match or data format
                # TypeError: wrong data types
                # AttributeError: missing BeautifulSoup attributes
                # KeyError: missing keys in data
                # IndexError: missing array indices
                # Continue to next place
                continue

        # Approach 2: Look for text content that might contain place names
        # Sometimes places are listed in plain text or in lists
        if len(places) < 100:
            console.print("[dim]Trying alternative extraction methods...[/dim]")

            # Look for list items or divs that might contain place information
            # Find all tags first, then filter by text content
            name_pattern = re.compile(
                r"(National Park|State Park|National Monument|National Preserve|National Recreation Area|"
                r"International Dark Sky|Dark Sky Park|Dark Sky Reserve|Dark Sky Sanctuary|"
                r"Dark Sky Community|Urban Night Sky)",
                re.I,
            )
            list_items = []
            for tag_name in ["li", "div", "p"]:
                items = soup.find_all(tag_name)
                # Filter items by text content matching the pattern
                for item in items:
                    text = item.get_text(strip=True)
                    if text and name_pattern.search(text):
                        list_items.append(item)

            for item in list_items:
                text = item.get_text(strip=True)
                # Try to extract place name (usually before the designation)
                match = re.search(
                    r"^([^,]+?)\s*(?:National Park|State Park|National Monument|International Dark Sky)", text, re.I
                )
                if match:
                    name = match.group(1).strip()
                    if name and len(name) > 3 and name.lower() not in seen_names and name.lower() not in existing_names:
                        seen_names.add(name.lower())
                        # Determine designation
                        designation = "International Dark Sky Place"
                        if "Park" in text:
                            designation = "International Dark Sky Park"
                        elif "Reserve" in text:
                            designation = "International Dark Sky Reserve"
                        elif "Sanctuary" in text:
                            designation = "International Dark Sky Sanctuary"
                        elif "Community" in text:
                            designation = "International Dark Sky Community"
                        elif "Urban" in text:
                            designation = "Urban Night Sky Place"

                        places.append(
                            {
                                "name": name,
                                "designation": designation,
                                "description": text,
                                "country": "",
                            }
                        )

        # Approach 3: If we still didn't find many places, try looking for structured data (JSON-LD, data attributes)
        if len(places) < 100:
            # Look for JSON-LD structured data
            json_ld_scripts = soup.find_all("script", type="application/ld+json")
            for script in json_ld_scripts:
                try:
                    import json

                    script_string = script.string
                    if script_string is None:
                        continue
                    data: dict[str, Any] | list[dict[str, Any]] = json.loads(script_string)
                    # Process structured data if found
                    if isinstance(data, dict) and "name" in data:
                        place_name: str = str(data.get("name", ""))
                        if (
                            place_name
                            and place_name.lower() not in seen_names
                            and place_name.lower() not in existing_names
                        ):
                            places.append(
                                {
                                    "name": place_name,
                                    "designation": data.get("description", "International Dark Sky Place"),
                                    "description": data.get("description", ""),
                                    "country": data.get("address", {}).get("addressCountry", "")
                                    if isinstance(data.get("address"), dict)
                                    else "",
                                }
                            )
                except (ValueError, TypeError, AttributeError, KeyError, IndexError):
                    # ValueError: invalid JSON-LD or data format
                    # TypeError: wrong data types
                    # AttributeError: missing BeautifulSoup attributes
                    # KeyError: missing keys in JSON-LD
                    # IndexError: missing array indices
                    # Continue to next element
                    continue

            # Look for data attributes or map markers
            data_places = soup.find_all(attrs={"data-name": True}) or soup.find_all(attrs={"data-place": True})
            for elem in data_places:
                try:
                    name_attr = elem.get("data-name") or elem.get("data-place")
                    name = str(name_attr) if name_attr else ""
                    if name and name.lower() not in seen_names and name.lower() not in existing_names:
                        seen_names.add(name.lower())
                        places.append(
                            {
                                "name": name,
                                "designation": "International Dark Sky Place",
                                "description": elem.get_text(strip=True) or "International Dark Sky Place",
                                "country": "",
                            }
                        )
                except (ValueError, TypeError, AttributeError, KeyError):
                    # ValueError: invalid data attribute format
                    # TypeError: wrong data types
                    # AttributeError: missing BeautifulSoup attributes
                    # KeyError: missing data attributes
                    # Continue to next element
                    continue

        console.print(f"[dim]Extracted {len(places)} unique places from IDA website[/dim]")

        # Warn if we found very few places (IDA has 200+ certified places)
        if len(places) < 100:
            console.print(
                f"[yellow]⚠[/yellow] Only found {len(places)} places, but IDA has 200+ certified places. "
                "The website may use JavaScript to load content dynamically."
            )
            console.print(
                "[dim]You may need to manually add more places to the seed file, or the website structure may have changed.[/dim]"
            )

    except (
        RuntimeError,
        AttributeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        TimeoutError,
        ImportError,
    ) as e:
        # RuntimeError: async/await errors, browser automation errors
        # AttributeError: missing attributes
        # ValueError: invalid data format
        # TypeError: wrong data types
        # KeyError: missing keys in data
        # IndexError: missing array indices
        # OSError: file I/O errors, network errors
        # TimeoutError: request timeout
        # ImportError: missing dependencies (Playwright, Selenium, BeautifulSoup)
        console.print(f"[yellow]⚠[/yellow] Error fetching from IDA website: {e}")
        console.print("[dim]Falling back to existing seed file.[/dim]")
        return existing_places

    if not places:
        console.print("[yellow]⚠[/yellow] No new places found from IDA website.")
        console.print("[dim]The existing seed file will be preserved.[/dim]")
        console.print(
            "[dim]The IDA website may use JavaScript to load content. Consider manually adding places or using "
            "browser automation tools for a complete list.[/dim]"
        )
        return existing_places

    # Process places: geocode, estimate values
    console.print(f"[dim]Processing {len(places)} new places...[/dim]")
    processed: list[dict[str, Any]] = []

    # Use semaphore to limit concurrent geocoding requests (5 at a time)
    # This significantly speeds up processing while respecting rate limits
    semaphore = asyncio.Semaphore(5)

    async def geocode_with_rate_limit(place: dict[str, Any]) -> dict[str, Any] | None:
        """Geocode a place with rate limiting via semaphore."""
        async with semaphore:
            coords = await geocode_location(place["name"], place.get("country", ""))
            if not coords:
                return None

            lat, lon = coords
            bortle = estimate_bortle_from_description(place["description"], place["designation"])
            sqm = estimate_sqm_from_bortle(bortle)
            geohash = generate_geohash(lat, lon)

            return {
                "name": place["name"],
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "geohash": geohash,
                "bortle_class": bortle,
                "sqm_value": sqm,
                "description": place["description"],
                "notes": f"{place['designation']}. Data from International Dark-Sky Association.",
            }

    # Process all places concurrently with rate limiting
    console.print(f"[dim]Geocoding {len(places)} places (5 concurrent requests)...[/dim]")
    tasks = [geocode_with_rate_limit(place) for place in places]
    # asyncio.gather returns a tuple, convert to list
    results_tuple = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[dict[str, Any] | BaseException | None] = list(results_tuple)

    # Process results - filter out exceptions and None values
    for i, result_item in enumerate(results, 1):
        # Skip exceptions
        if isinstance(result_item, Exception):
            continue
        # Skip None values
        if result_item is None:
            continue
        # At this point, result_item must be dict[str, Any]
        # Use explicit type check to help mypy
        if isinstance(result_item, dict):
            processed.append(result_item)
        if i % 10 == 0:
            console.print(f"[dim]Processed {i}/{len(places)} places...[/dim]", end="\r")

    console.print()  # New line after progress

    # Merge with existing - ensure both are lists of dicts
    # Filter out any metadata objects from existing_places
    existing_dicts: list[dict[str, Any]] = [
        item for item in existing_places if isinstance(item, dict) and "name" in item
    ]
    merged: list[dict[str, Any]] = existing_dicts + processed
    merged.sort(key=lambda x: x["name"])

    # Add attribution metadata at the beginning
    result: list[dict[str, Any]] = [
        {
            "_comment": "Data sourced from the International Dark-Sky Association (IDA) official list of International Dark Sky Places. URL: https://www.darksky.org/our-work/conservation/idsp/",
            "_attribution": "International Dark-Sky Association (IDA) - https://www.darksky.org/",
            "_note": f"Bortle class and SQM values are estimates based on designation type and site descriptions. Last updated: {datetime.now().strftime('%Y-%m-%d')}. For the most up-to-date information and official designations, visit the IDA website.",
        },
        *merged,
    ]

    console.print(f"[green]✓[/green] Processed {len(processed)} new places, {len(existing_dicts)} existing places kept")
    console.print(f"[dim]Total: {len(merged)} dark sky sites[/dim]")

    return result


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
        elif isinstance(data, list) and data:
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
