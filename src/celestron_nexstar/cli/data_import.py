"""
Data Import Module

Provides CLI commands for importing catalog data from various sources.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from celestron_nexstar.api.catalogs.importers import map_openngc_type, parse_catalog_number, parse_ra_dec
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.database.database import CatalogDatabase, get_database


console = Console()


@dataclass
class DataSource:
    """Metadata about a catalog data source."""

    name: str
    description: str
    url: str
    objects_available: int
    license: str
    attribution: str
    importer: Callable[[Path, float, bool], tuple[int, int]]


# Parsing functions moved to api.importers


def _create_messier_entry(
    db: CatalogDatabase,
    messier_number: int,
    name: str,
    ra_hours: float,
    dec_degrees: float,
    obj_type: CelestialObjectType,
    magnitude: float | None,
    common_name: str | None,
    size_arcmin: float | None,
    hubble_type: str,
    common_names: str,
    constellation: str | None,
    verbose: bool = False,
) -> bool:
    """
    Create a Messier catalog entry from NGC/IC data.

    Returns:
        True if entry was created, False if it already existed or failed
    """
    messier_name = f"M{messier_number}"

    # Check if Messier entry already exists
    import asyncio

    existing_messier = asyncio.run(db.get_by_name(messier_name))
    if existing_messier:
        if verbose:
            console.print(f"[dim]Skipping duplicate Messier: {messier_name}[/dim]")
        return False

    try:
        # Use common name from NGC entry
        messier_common_name = common_name if common_name else None

        # Enhanced description for Messier objects
        messier_description_parts = []
        if hubble_type:
            messier_description_parts.append(f"Hubble type: {hubble_type}")
        messier_description_parts.append(f"NGC/IC: {name}")
        if common_names:
            messier_description_parts.append(f"Also known as: {common_names}")
        messier_description = "; ".join(messier_description_parts)

        asyncio.run(
            db.insert_object(
                name=messier_name,
                catalog="messier",
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                object_type=obj_type,
                magnitude=magnitude,
                common_name=messier_common_name,
                catalog_number=messier_number,
                size_arcmin=size_arcmin,
                description=messier_description,
                constellation=constellation,
            )
        )

        if verbose:
            console.print(f"[green]Created Messier entry: {messier_name} ({name})[/green]")
        return True
    except Exception as e:
        if verbose:
            console.print(f"[yellow]Warning: Error creating Messier entry {messier_name}: {e}[/yellow]")
        return False


def import_openngc(csv_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """
    Import OpenNGC catalog into database.

    Args:
        csv_path: Path to NGC.csv file
        mag_limit: Maximum magnitude to import
        verbose: Show detailed progress

    Returns:
        (imported_count, skipped_count)
    """
    db = get_database()

    # OpenNGC CSV format (semicolon-separated)
    # Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;...

    imported = 0
    skipped = 0
    errors = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

        total_rows = -1
        with open(csv_path, encoding="utf-8") as fp:
            total_rows = sum(1 for _ in fp) - 1

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Importing OpenNGC (mag ≤ {mag_limit})...", total=total_rows)

            for row in reader:
                name = row["Name"]
                obj_type_str = row["Type"]
                ra_str = row["RA"]
                dec_str = row["Dec"]
                constellation = row["Const"]
                v_mag_str = row["V-Mag"]
                b_mag_str = row["B-Mag"]
                common_names = row.get("Common names", "")

                # Skip nonexistent/duplicate/other
                if obj_type_str in ("NonEx", "Dup", "Other", ""):
                    skipped += 1
                    progress.advance(task)
                    continue

                # Parse coordinates
                coords = parse_ra_dec(ra_str, dec_str)
                if coords is None:
                    errors += 1
                    progress.advance(task)
                    continue

                ra_hours, dec_degrees = coords

                # Parse magnitude (prefer V-Mag, fallback to B-Mag)
                try:
                    if v_mag_str:
                        magnitude = float(v_mag_str)
                    elif b_mag_str:
                        magnitude = float(b_mag_str)
                    else:
                        magnitude = None
                except ValueError:
                    magnitude = None

                # Filter by magnitude
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Map object type
                obj_type = map_openngc_type(obj_type_str)

                # Extract catalog and number
                # Handle suffixes like "IC 0080 NED01"
                if name.startswith("NGC"):
                    catalog = "ngc"
                    num_str = name.replace("NGC", "").strip().split()[0]
                    try:
                        catalog_number = int(num_str)
                    except ValueError:
                        catalog_number = None
                elif name.startswith("IC"):
                    catalog = "ic"
                    num_str = name.replace("IC", "").strip().split()[0]
                    try:
                        catalog_number = int(num_str)
                    except ValueError:
                        catalog_number = None
                else:
                    catalog = "ngc"  # Default
                    catalog_number = None

                # Common name (first one if multiple)
                common_name = None
                if common_names:
                    common_name = common_names.split(",")[0].strip()

                # Size (MajAx in arcminutes)
                try:
                    size_arcmin = float(row["MajAx"]) if row.get("MajAx") else None
                except ValueError:
                    size_arcmin = None

                # Description (combine Hubble type and common names)
                hubble_type = row.get("Hubble", "")
                description_parts = []
                if hubble_type:
                    description_parts.append(f"Hubble type: {hubble_type}")
                if common_names:
                    description_parts.append(f"Also known as: {common_names}")
                description = "; ".join(description_parts) if description_parts else None

                # Extract Messier number from "M" column (format: "031", "001", etc.)
                messier_number = None
                m_col = row.get("M", "").strip()
                if m_col:
                    with suppress(ValueError):
                        # Remove leading zeros and convert to int
                        messier_number = int(m_col)

                # Check for duplicates before inserting
                # First check by name (most common case)
                import asyncio

                existing = asyncio.run(db.get_by_name(name))
                if existing:
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {name}[/dim]")
                    # Still check if we need to create Messier entry
                    if messier_number is not None and _create_messier_entry(
                        db,
                        messier_number,
                        name,
                        ra_hours,
                        dec_degrees,
                        obj_type,
                        magnitude,
                        common_name,
                        size_arcmin,
                        hubble_type,
                        common_names,
                        constellation,
                        verbose,
                    ):
                        imported += 1
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available (more efficient query)
                import asyncio

                if catalog_number is not None and asyncio.run(db.exists_by_catalog_number(catalog, catalog_number)):
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {catalog} {catalog_number}[/dim]")
                    # Still check if we need to create Messier entry
                    if messier_number is not None and _create_messier_entry(
                        db,
                        messier_number,
                        name,
                        ra_hours,
                        dec_degrees,
                        obj_type,
                        magnitude,
                        common_name,
                        size_arcmin,
                        hubble_type,
                        common_names,
                        constellation,
                        verbose,
                    ):
                        imported += 1
                    progress.advance(task)
                    continue

                # Insert NGC/IC object into database
                try:
                    import asyncio

                    asyncio.run(
                        db.insert_object(
                            name=name,
                            catalog=catalog,
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            object_type=obj_type,
                            magnitude=magnitude,
                            common_name=common_name,
                            catalog_number=catalog_number,
                            size_arcmin=size_arcmin,
                            description=description,
                            constellation=constellation,
                        )
                    )

                    imported += 1

                except Exception as e:
                    if verbose:
                        console.print(f"[yellow]Warning: Error importing {name}: {e}[/yellow]")
                    errors += 1

                # If this object has a Messier number, also create a Messier entry
                if messier_number is not None and _create_messier_entry(
                    db,
                    messier_number,
                    name,
                    ra_hours,
                    dec_degrees,
                    obj_type,
                    magnitude,
                    common_name,
                    size_arcmin,
                    hubble_type,
                    common_names,
                    constellation,
                    verbose,
                ):
                    imported += 1

                progress.advance(task)

    # Database commits are handled per-session, no explicit commit needed

    return imported, skipped


# parse_catalog_number moved to api.importers


def download_yale_bsc(json_path: Path) -> None:
    """
    Download Yale Bright Star Catalog in JSON format.

    Args:
        json_path: Path to save the JSON file
    """
    url = "https://raw.githubusercontent.com/aduboisforge/Bright-Star-Catalog-JSON/refs/heads/master/BSC.json"

    console.print("[dim]Downloading Yale Bright Star Catalog from GitHub...[/dim]")
    try:
        urllib.request.urlretrieve(url, json_path)
        console.print(f"[green]✓[/green] Downloaded to {json_path}")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to download: {e}")
        raise


def import_yale_bsc(json_path: Path, mag_limit: float = 6.5, verbose: bool = False) -> tuple[int, int]:
    """
    Import Yale Bright Star Catalog into database.

    Args:
        json_path: Path to bright_star_catalog.json file
        mag_limit: Maximum magnitude to import (default: 6.5, all stars in BSC)
        verbose: Show detailed progress

    Returns:
        (imported_count, skipped_count)
    """
    db = get_database()

    imported = 0
    skipped = 0
    errors = 0

    # Load JSON file
    try:
        with open(json_path, encoding="utf-8") as f:
            stars_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {json_path}")
        console.print("[dim]Use --download to fetch from GitHub[/dim]")
        raise
    except json.JSONDecodeError as e:
        console.print(f"[red]✗[/red] Invalid JSON: {e}")
        raise

    if not isinstance(stars_data, list):
        console.print("[red]✗[/red] Invalid JSON format: expected array of stars")
        raise ValueError("Invalid JSON format")

    total_stars = len(stars_data)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Importing Yale BSC (mag ≤ {mag_limit})...", total=total_stars)

        for star_data in stars_data:
            try:
                # Extract data from JSON
                # Format: {"harvard_ref_#":1,"RA":"00:05:09.90","DEC":"+45:13:45.00","MAG":"6.70","Title HD":"A1Vn",...}
                hr_number = star_data.get("harvard_ref_#")
                ra_str = star_data.get("RA", "")
                dec_str = star_data.get("DEC", "")
                mag_str = star_data.get("MAG", "")
                spectral_type = star_data.get("Title HD", "")

                # Skip if missing essential data
                if hr_number is None or not ra_str or not dec_str:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Parse RA from "HH:MM:SS.ss" format to decimal hours
                try:
                    ra_parts = ra_str.split(":")
                    ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60 + float(ra_parts[2]) / 3600
                except (ValueError, IndexError):
                    skipped += 1
                    progress.advance(task)
                    continue

                # Parse DEC from "+DD:MM:SS.ss" format to decimal degrees
                try:
                    dec_sign = 1 if not dec_str.startswith("-") else -1
                    dec_str_abs = dec_str.lstrip("+-")
                    dec_parts = dec_str_abs.split(":")
                    dec_degrees = dec_sign * (
                        float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600
                    )
                except (ValueError, IndexError):
                    skipped += 1
                    progress.advance(task)
                    continue

                # Parse magnitude
                try:
                    vmag = float(mag_str) if mag_str else None
                except ValueError:
                    vmag = None

                # Filter by magnitude
                if vmag is not None and vmag > mag_limit:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Build star name (use HR number as primary identifier)
                star_name = f"HR {hr_number}"

                # Look up common name from database star_name_mappings table
                import asyncio

                common_name = asyncio.run(db.get_common_name_by_hr(hr_number))
                if verbose and hr_number in [1708, 424, 2491]:  # Log for well-known stars
                    console.print(f"[dim]HR {hr_number}: common_name={common_name}[/dim]")

                # Build description
                description_parts = [f"HR {hr_number}"]
                if spectral_type:
                    description_parts.append(f"Spectral type: {spectral_type}")
                description = "; ".join(description_parts) if description_parts else None

                # Determine object type (check if double star)
                # Yale BSC marks double stars, but we'll use a simple heuristic
                # For now, treat all as stars unless we have better data
                obj_type = CelestialObjectType.STAR

                # Check for duplicates
                import asyncio

                existing = asyncio.run(db.get_by_name(star_name))
                if existing:
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {star_name}[/dim]")
                    progress.advance(task)
                    continue

                # Check by HR number if available
                if hr_number and asyncio.run(db.exists_by_catalog_number("yale_bsc", hr_number)):
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate HR {hr_number}[/dim]")
                    progress.advance(task)
                    continue

                # Insert into database
                try:
                    asyncio.run(
                        db.insert_object(
                            name=star_name,
                            catalog="yale_bsc",
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            object_type=obj_type,
                            magnitude=vmag,
                            common_name=common_name,
                            catalog_number=hr_number,
                            description=description,
                            constellation=None,  # Not available in this format
                        )
                    )

                    imported += 1

                except Exception as e:
                    if verbose:
                        console.print(f"[yellow]Warning: Error importing {star_name}: {e}[/yellow]")
                    errors += 1

            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error processing star: {e}[/yellow]")
                errors += 1

            progress.advance(task)

    # Database commits are handled per-session, no explicit commit needed

    return imported, skipped


def import_custom_yaml(yaml_path: Path, mag_limit: float = 99.0, verbose: bool = False) -> tuple[int, int]:
    """
    Import custom YAML catalog into database.

    Args:
        yaml_path: Path to YAML file
        mag_limit: Maximum magnitude to import
        verbose: Show detailed progress

    Returns:
        (imported_count, skipped_count)
    """
    db = get_database()

    # Load YAML
    try:
        with open(yaml_path, encoding="utf-8") as f:
            catalogs_data = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to read YAML file: {e}")
        return 0, 0

    if not catalogs_data:
        console.print("[yellow]Warning: Empty YAML file[/yellow]")
        return 0, 0

    console.print(f"[dim]Loaded {len(catalogs_data)} catalog(s) from YAML[/dim]")

    imported = 0
    skipped = 0
    errors = 0

    # Count total objects for progress bar
    total_objects = sum(len(objects) for objects in catalogs_data.values() if isinstance(objects, list))
    console.print(f"[dim]Found {total_objects} total object(s) to process[/dim]")

    if total_objects == 0:
        console.print("[yellow]⚠[/yellow] No objects found in YAML file. Check the file format.")
        return 0, 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing custom catalog...", total=total_objects)

        # Migrate each catalog
        for catalog_name, objects in catalogs_data.items():
            if not isinstance(objects, list):
                console.print(
                    f"[yellow]⚠[/yellow] Skipping '{catalog_name}': not a list (type: {type(objects).__name__})"
                )
                continue

            console.print(f"[dim]Processing catalog '{catalog_name}' with {len(objects)} object(s)[/dim]")

            for obj in objects:
                # Extract fields
                name = obj.get("name")
                if not name:
                    errors += 1
                    console.print(f"[yellow]⚠[/yellow] Skipping object without name: {obj}")
                    progress.advance(task)
                    continue

                common_name = obj.get("common_name")
                ra_hours = obj.get("ra_hours")
                dec_degrees = obj.get("dec_degrees")
                magnitude = obj.get("magnitude")
                object_type_str = obj.get("type")
                description = obj.get("description")

                # Validate required fields
                if ra_hours is None or dec_degrees is None or not object_type_str:
                    skipped += 1
                    missing_fields = []
                    if ra_hours is None:
                        missing_fields.append("ra_hours")
                    if dec_degrees is None:
                        missing_fields.append("dec_degrees")
                    if not object_type_str:
                        missing_fields.append("type")
                    console.print(
                        f"[yellow]⚠[/yellow] Skipping {name}: Missing required fields: {', '.join(missing_fields)}"
                    )
                    progress.advance(task)
                    continue

                # Filter by magnitude
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
                    console.print(f"[dim]Skipping {name}: magnitude {magnitude} > limit {mag_limit}[/dim]")
                    progress.advance(task)
                    continue

                # Map object type
                try:
                    object_type = CelestialObjectType(object_type_str)
                except ValueError:
                    if verbose:
                        console.print(f"[yellow]Warning: Unknown object type '{object_type_str}' for {name}[/yellow]")
                    object_type = CelestialObjectType.STAR

                # Determine if dynamic
                is_dynamic = object_type in (CelestialObjectType.PLANET, CelestialObjectType.MOON)

                # Extract parent planet for moons
                parent_planet = obj.get("parent_planet") or obj.get("parent")

                # Parse catalog number
                catalog_number = parse_catalog_number(name, catalog_name)

                # Check for duplicates before inserting
                import asyncio

                existing = asyncio.run(db.get_by_name(name))
                if existing:
                    skipped += 1
                    console.print(f"[dim]Skipping duplicate: {name} (already exists)[/dim]")
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available
                if catalog_number is not None and asyncio.run(
                    db.exists_by_catalog_number(catalog_name, catalog_number)
                ):
                    skipped += 1
                    console.print(f"[dim]Skipping duplicate: {catalog_name} {catalog_number} (already exists)[/dim]")
                    progress.advance(task)
                    continue

                # Extract constellation if present
                constellation = obj.get("constellation")

                # Insert into database
                try:
                    asyncio.run(
                        db.insert_object(
                            name=name,
                            catalog=catalog_name,
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            object_type=object_type,
                            magnitude=magnitude,
                            common_name=common_name,
                            catalog_number=catalog_number,
                            description=description,
                            constellation=constellation,  # Read from YAML if present
                            is_dynamic=is_dynamic,
                            ephemeris_name=name if is_dynamic else None,
                            parent_planet=parent_planet,
                        )
                    )

                    imported += 1

                except Exception as e:
                    errors += 1
                    # Always show errors, not just in verbose mode
                    console.print(f"[red]✗[/red] Error importing {name}: {e}")
                    if verbose:
                        import traceback

                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

                progress.advance(task)

    # Database commits are handled per-session, no explicit commit needed

    return imported, skipped


def download_openngc(output_path: Path) -> bool:
    """
    Download OpenNGC catalog from GitHub.

    Args:
        output_path: Where to save the CSV file

    Returns:
        True if successful
    """
    url = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv"

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading OpenNGC catalog...", total=None)

            with urllib.request.urlopen(url) as response:
                data = response.read()

            output_path.write_bytes(data)
            progress.update(task, completed=True)

        console.print(f"[green]✓[/green] Downloaded {len(data):,} bytes to {output_path}")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Download failed: {e}")
        return False


# Registry of available data sources
DATA_SOURCES: dict[str, DataSource] = {
    "custom": DataSource(
        name="Custom YAML",
        description="User-defined custom catalog (catalogs.yaml)",
        url="local file",
        objects_available=152,  # Default catalog size
        license="User-defined",
        attribution="User-defined",
        importer=import_custom_yaml,
    ),
    "openngc": DataSource(
        name="OpenNGC",
        description="NGC/IC catalog of deep-sky objects",
        url="https://github.com/mattiaverga/OpenNGC",
        objects_available=13970,
        license="CC-BY-SA-4.0",
        attribution="Mattia Verga and OpenNGC contributors",
        importer=import_openngc,
    ),
    "yale_bsc": DataSource(
        name="Yale Bright Star Catalog",
        description="Bright stars (magnitude ≤ 6.5)",
        url="https://github.com/aduboisforge/Bright-Star-Catalog-JSON",
        objects_available=9096,
        license="Public Domain",
        attribution="Yale University Observatory",
        importer=import_yale_bsc,
    ),
}


def list_data_sources() -> None:
    """Display available data sources."""
    import asyncio

    db = get_database()
    stats = asyncio.run(db.get_stats())

    table = Table(title="Available Data Sources")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Available", justify="right", style="yellow")
    table.add_column("Imported", justify="right", style="green")
    table.add_column("License", style="dim")

    for source_id, source in DATA_SOURCES.items():
        # Estimate imported count based on catalog
        if source_id == "openngc":
            imported = stats.objects_by_catalog.get("ngc", 0) + stats.objects_by_catalog.get("ic", 0)
            # Subtract the original 12 NGC objects from migration
            imported = max(0, imported - 12)
        elif source_id == "yale_bsc":
            imported = stats.objects_by_catalog.get("yale_bsc", 0)
        elif source_id == "custom":
            # Count objects from custom catalogs (messier, asterisms, planets, moons, etc.)
            custom_catalogs = ["messier", "asterisms", "planets", "moons", "ngc", "caldwell"]
            imported = sum(stats.objects_by_catalog.get(cat, 0) for cat in custom_catalogs)
        else:
            imported = 0

        table.add_row(
            source.name,
            source.description,
            f"{source.objects_available:,}",
            f"{imported:,}",
            source.license,
        )

    console.print(table)
    console.print(f"\n[dim]Total objects in database: {stats.total_objects:,}[/dim]")


def import_data_source(source_id: str, mag_limit: float = 15.0) -> bool:
    """
    Import data from a source.

    Args:
        source_id: ID of data source (e.g., "openngc")
        mag_limit: Maximum magnitude to import

    Returns:
        True if successful
    """
    if source_id not in DATA_SOURCES:
        console.print(f"[red]✗[/red] Unknown data source: {source_id}")
        console.print(f"[dim]Available sources: {', '.join(DATA_SOURCES.keys())}[/dim]")
        return False

    source = DATA_SOURCES[source_id]

    console.print(f"\n[bold cyan]Importing {source.name}[/bold cyan]")
    console.print(f"[dim]{source.description}[/dim]")
    console.print(f"[dim]License: {source.license}[/dim]")
    console.print(f"[dim]Attribution: {source.attribution}[/dim]\n")

    # Handle custom YAML catalog
    if source_id == "custom":
        # Find catalogs.yaml
        module_path = Path(__file__).parent
        yaml_path = module_path / "data" / "catalogs.yaml"

        if not yaml_path.exists():
            console.print(f"[red]✗[/red] Custom catalog not found at {yaml_path}")
            console.print("[dim]Create a catalogs.yaml file in src/celestron_nexstar/cli/data/[/dim]")
            return False

        console.print(f"Reading custom catalog from: {yaml_path}")
        console.print(f"Importing with magnitude limit: {mag_limit}\n")

        try:
            imported, skipped = source.importer(yaml_path, mag_limit, False)

            console.print("\n[green]✓[/green] Import complete!")
            console.print(f"  Imported: [green]{imported:,}[/green]")
            console.print(f"  Skipped:  [yellow]{skipped:,}[/yellow] (too faint or invalid)")

            # Show updated stats
            db = get_database()
            import asyncio

            stats = asyncio.run(db.get_stats())
            console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Import failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    # Download data for remote sources
    # Determine file extension based on source
    cache_path = Path("/tmp") / f"{source_id}.json" if source_id == "yale_bsc" else Path("/tmp") / f"{source_id}.csv"

    if not cache_path.exists():
        console.print("Downloading data...")
        if source_id == "openngc":
            if not download_openngc(cache_path):
                return False
        elif source_id == "yale_bsc":
            try:
                download_yale_bsc(cache_path)
            except Exception as e:
                console.print(f"[red]✗[/red] Download failed: {e}")
                return False
        else:
            console.print(f"[red]✗[/red] No downloader for {source_id}")
            return False

    # Import data
    console.print(f"\nImporting with magnitude limit: {mag_limit}")
    try:
        imported, skipped = source.importer(cache_path, mag_limit, False)

        console.print("\n[green]✓[/green] Import complete!")
        console.print(f"  Imported: [green]{imported:,}[/green]")
        console.print(f"  Skipped:  [yellow]{skipped:,}[/yellow] (too faint or invalid)")

        # Show updated stats
        db = get_database()
        import asyncio

        stats = asyncio.run(db.get_stats())
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Import failed: {e}")
        return False
