"""
Data Import Module

Provides CLI commands for importing catalog data from various sources.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from ..api.database import get_database
from ..api.enums import CelestialObjectType
from ..api.importers import map_openngc_type, parse_catalog_number, parse_ra_dec


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

                # Check for duplicates before inserting
                # First check by name (most common case)
                existing = db.get_by_name(name)
                if existing:
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {name}[/dim]")
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available (more efficient query)
                if catalog_number is not None and db.exists_by_catalog_number(catalog, catalog_number):
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {catalog} {catalog_number}[/dim]")
                    progress.advance(task)
                    continue

                # Insert into database
                try:
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

                    imported += 1

                except Exception as e:
                    if verbose:
                        console.print(f"[yellow]Warning: Error importing {name}: {e}[/yellow]")
                    errors += 1

                progress.advance(task)

    # Commit all changes
    db.commit()

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

                # Common name (none in this format)
                common_name = None

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
                existing = db.get_by_name(star_name)
                if existing:
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {star_name}[/dim]")
                    progress.advance(task)
                    continue

                # Check by HR number if available
                if hr_number and db.exists_by_catalog_number("yale_bsc", hr_number):
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate HR {hr_number}[/dim]")
                    progress.advance(task)
                    continue

                # Insert into database
                try:
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

    # Commit all changes
    db.commit()

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
    with open(yaml_path, encoding="utf-8") as f:
        catalogs_data = yaml.safe_load(f)

    if not catalogs_data:
        console.print("[yellow]Warning: Empty YAML file[/yellow]")
        return 0, 0

    imported = 0
    skipped = 0
    errors = 0

    # Count total objects for progress bar
    total_objects = sum(len(objects) for objects in catalogs_data.values() if isinstance(objects, list))

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
                continue

            for obj in objects:
                # Extract fields
                name = obj.get("name")
                if not name:
                    errors += 1
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
                    if verbose:
                        console.print(f"[yellow]Warning: Missing required fields for {name}[/yellow]")
                    errors += 1
                    progress.advance(task)
                    continue

                # Filter by magnitude
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
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
                existing = db.get_by_name(name)
                if existing:
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {name}[/dim]")
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available
                if catalog_number is not None and db.exists_by_catalog_number(catalog_name, catalog_number):
                    skipped += 1
                    if verbose:
                        console.print(f"[dim]Skipping duplicate: {catalog_name} {catalog_number}[/dim]")
                    progress.advance(task)
                    continue

                # Extract constellation if present
                constellation = obj.get("constellation")

                # Insert into database
                try:
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

                    imported += 1

                except Exception as e:
                    if verbose:
                        console.print(f"[yellow]Warning: Error importing {name}: {e}[/yellow]")
                    errors += 1

                progress.advance(task)

    # Commit all changes
    db.commit()

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
    db = get_database()
    stats = db.get_stats()

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
            stats = db.get_stats()
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
        stats = db.get_stats()
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Import failed: {e}")
        return False
