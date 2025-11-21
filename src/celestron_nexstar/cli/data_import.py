"""
Data Import Module

Provides CLI commands for importing catalog data from various sources.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from celestron_nexstar.api.catalogs.converters import CoordinateConverter
from celestron_nexstar.api.catalogs.importers import parse_catalog_number
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.core.exceptions import InvalidCatalogFormatError
from celestron_nexstar.api.database.database import get_database


console = Console()


T = TypeVar("T")


def _run_async_safe(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    import asyncio
    import concurrent.futures
    import threading

    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[T] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


def get_cache_dir() -> Path:
    """
    Get the cache directory for celestial data files.

    Returns:
        Path to ~/.cache/celestron-nexstar/celestial-data/
    """
    cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "celestial-data"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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
                existing = _run_async_safe(db.get_by_name(name))
                if existing:
                    skipped += 1
                    console.print(f"[dim]Skipping duplicate: {name} (already exists)[/dim]")
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available
                if catalog_number is not None and _run_async_safe(
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
                    _run_async_safe(
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


def download_celestial_data(filename: str, output_path: Path) -> bool:
    """
    Download a file from the celestial_data repository.

    Args:
        filename: Name of the file (e.g., "stars.6.min.geojson" or "starnames.csv")
        output_path: Where to save the file

    Returns:
        True if successful
    """
    # Use jsDelivr CDN for reliable downloads
    url = f"https://cdn.jsdelivr.net/gh/dieghernan/celestial_data@main/data/{filename}"

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Downloading {filename}...", total=None)

            with urllib.request.urlopen(url) as response:
                data = response.read()

            output_path.write_bytes(data)
            progress.update(task, completed=True)

        console.print(f"[green]✓[/green] Downloaded {len(data):,} bytes to {output_path}")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Download failed: {e}")
        return False


def import_celestial_data_geojson(
    geojson_path: Path,
    catalog: str,
    mag_limit: float = 15.0,
    verbose: bool = False,
    object_type_map: dict[str, CelestialObjectType] | None = None,
) -> tuple[int, int]:
    """
    Import celestial data from a GeoJSON file.

    GeoJSON format for celestial data:
    - coordinates: [RA in degrees, Dec in degrees] (GeoJSON uses [lon, lat] convention)
    - properties: Various fields depending on data type

    Args:
        geojson_path: Path to GeoJSON file
        catalog: Catalog name to use (e.g., "celestial_stars", "celestial_dsos")
        mag_limit: Maximum magnitude to import
        verbose: Show detailed progress
        object_type_map: Optional mapping from property field to CelestialObjectType

    Returns:
        (imported_count, skipped_count)
    """
    db = get_database()

    # Pre-fetch existing objects for deduplication
    console.print(f"[dim]Loading existing {catalog} objects for deduplication...[/dim]")
    existing_objects = _run_async_safe(db.get_existing_objects_set(catalog=catalog))
    console.print(f"[dim]Found {len(existing_objects):,} existing {catalog} objects[/dim]")

    imported = 0
    skipped = 0
    errors = 0

    # Load GeoJSON file
    try:
        with open(geojson_path, encoding="utf-8") as f:
            geojson_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {geojson_path}")
        raise
    except json.JSONDecodeError as e:
        console.print(f"[red]✗[/red] Invalid JSON: {e}")
        raise

    if geojson_data.get("type") != "FeatureCollection":
        console.print("[red]✗[/red] Invalid GeoJSON: expected FeatureCollection")
        raise InvalidCatalogFormatError("Invalid GeoJSON format")

    features = geojson_data.get("features", [])
    total_features = len(features)

    # Default object type mapping
    if object_type_map is None:
        object_type_map = {}

    # Collect all objects first, then deduplicate once, then batch insert
    all_objects: list[dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Processing {catalog} (mag ≤ {mag_limit})...", total=total_features)

        for feature in features:
            try:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})

                # Extract coordinates (GeoJSON format: [lon, lat] = [RA in degrees, Dec in degrees])
                coords = geometry.get("coordinates", [])
                if not coords or len(coords) < 2:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Convert RA from degrees to hours
                ra_degrees = float(coords[0])
                dec_degrees = float(coords[1])
                ra_hours = CoordinateConverter.ra_degrees_to_hours(ra_degrees)

                # Extract name (varies by data type)
                name = (
                    properties.get("name")
                    or properties.get("id")
                    or properties.get("designation")
                    or properties.get("Name")
                    or f"{catalog}_{imported + skipped + 1}"
                )

                # Extract magnitude
                magnitude = None
                for mag_field in ["mag", "magnitude", "Mag", "Magnitude", "vmag", "V-Mag"]:
                    if mag_field in properties:
                        try:
                            mag_val = properties[mag_field]
                            if mag_val is not None and mag_val != "":
                                magnitude = float(mag_val)
                                break
                        except (ValueError, TypeError):
                            pass

                # Filter by magnitude
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Determine object type
                # Default depends on catalog: DSO catalogs default to NEBULA, star catalogs default to STAR
                default_type = CelestialObjectType.NEBULA if "dso" in catalog.lower() else CelestialObjectType.STAR
                obj_type = default_type
                type_str = (
                    properties.get("type")
                    or properties.get("Type")
                    or properties.get("object_type")
                    or properties.get("objtype")
                )

                if type_str and type_str in object_type_map:
                    obj_type = object_type_map[type_str]
                elif type_str:
                    # Try to map common type strings
                    type_lower = str(type_str).lower()
                    if "galaxy" in type_lower or "gal" in type_lower:
                        obj_type = CelestialObjectType.GALAXY
                    elif "nebula" in type_lower or "neb" in type_lower:
                        obj_type = CelestialObjectType.NEBULA
                    elif "cluster" in type_lower or "cl" in type_lower:
                        obj_type = CelestialObjectType.CLUSTER
                    elif "star" in type_lower or "*" in type_lower:
                        obj_type = CelestialObjectType.STAR

                # Extract catalog number if available
                catalog_number = None
                for num_field in ["catalog_number", "number", "id", "ID"]:
                    if num_field in properties:
                        try:
                            num_val = properties[num_field]
                            if isinstance(num_val, (int, float)) or (isinstance(num_val, str) and num_val.isdigit()):
                                catalog_number = int(num_val)
                            if catalog_number:
                                break
                        except (ValueError, TypeError):
                            pass

                # Extract common name
                common_name = (
                    properties.get("common_name")
                    or properties.get("proper_name")
                    or properties.get("ProperName")
                    or properties.get("name_en")
                )

                # Extract size (in arcminutes)
                size_arcmin = None
                for size_field in ["size", "Size", "diam", "diameter", "majax", "MajAx"]:
                    if size_field in properties:
                        try:
                            size_val = properties[size_field]
                            if size_val:
                                size_arcmin = float(size_val)
                                break
                        except (ValueError, TypeError):
                            pass

                # Extract constellation
                constellation = (
                    properties.get("constellation")
                    or properties.get("Const")
                    or properties.get("const")
                    or properties.get("con")
                )

                # Build description from available properties
                description_parts = []
                for desc_field in ["description", "Description", "notes", "Notes", "note"]:
                    desc_val = properties.get(desc_field)
                    if desc_val:
                        description_parts.append(str(desc_val))
                        break

                # Add type information if available
                if type_str and type_str not in description_parts:
                    description_parts.insert(0, f"Type: {type_str}")

                description = "; ".join(description_parts) if description_parts else None

                # Add to collection (will deduplicate once at the end)
                all_objects.append(
                    {
                        "name": name,
                        "catalog": catalog,
                        "ra_hours": ra_hours,
                        "dec_degrees": dec_degrees,
                        "object_type": obj_type,
                        "magnitude": magnitude,
                        "common_name": common_name,
                        "catalog_number": catalog_number,
                        "size_arcmin": size_arcmin,
                        "description": description,
                        "constellation": constellation,
                    }
                )

            except Exception as e:
                errors += 1
                if verbose:
                    console.print(f"[yellow]Warning: Error processing feature: {e}[/yellow]")

            progress.advance(task)

    # Deduplicate once after all objects are created
    console.print(f"[dim]Deduplicating {len(all_objects):,} objects...[/dim]")
    seen_keys: set[tuple[str, str | None, int | None]] = set()
    deduplicated_objects: list[dict[str, Any]] = []
    for obj in all_objects:
        key = (obj["name"], obj.get("common_name"), obj.get("catalog_number"))
        # Check against both seen objects and existing database objects
        if key not in seen_keys and key not in existing_objects:
            # Also check by name alone (common_name might be None)
            name_key = (obj["name"], None, None)
            name_key2 = (obj["name"], obj["name"], None)
            if name_key not in existing_objects and name_key2 not in existing_objects:
                seen_keys.add(key)
                deduplicated_objects.append(obj)
            else:
                skipped += 1
        else:
            skipped += 1

    console.print(f"[dim]After deduplication: {len(deduplicated_objects):,} unique objects to import[/dim]")

    # Batch insert deduplicated objects
    batch_size = 1000
    num_batches = (len(deduplicated_objects) + batch_size - 1) // batch_size  # Ceiling division
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Importing {catalog}...", total=num_batches)

        for i in range(0, len(deduplicated_objects), batch_size):
            batch = deduplicated_objects[i : i + batch_size]
            try:
                batch_imported = _run_async_safe(db.insert_objects_batch(batch))
                imported += batch_imported
                # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                progress.advance(task)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                errors += len(batch)
                # Still advance progress even on error
                progress.advance(task)

    return imported, skipped


def import_celestial_stars(geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """
    Import stars from celestial_data GeoJSON with name matching from starnames.csv.

    Downloads starnames.csv to match HIP numbers to common star names.
    """
    # Download starnames.csv for name matching
    starnames_path_available: Path | None = None
    cache_dir = get_cache_dir()
    tmp_starnames_path: Path = cache_dir / "starnames.csv"
    if not tmp_starnames_path.exists():
        if verbose:
            console.print("[dim]Downloading starnames.csv for star name matching...[/dim]")
        if download_celestial_data("starnames.csv", tmp_starnames_path):
            starnames_path_available = tmp_starnames_path
        else:
            console.print("[yellow]Warning: Could not download starnames.csv, importing without name matching[/yellow]")
    else:
        starnames_path_available = tmp_starnames_path

    # Load star name mappings - id from CSV matches id in GeoJSON
    star_name_map: dict[int, str] = {}  # id -> common name
    if starnames_path_available is not None:
        try:
            with open(starnames_path_available, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    id_str = row.get("id", "").strip()
                    name = row.get("name", "").strip() or row.get("en", "").strip()  # Prefer "name", fallback to "en"
                    if id_str and name and id_str.isdigit():
                        csv_star_id = int(id_str)
                        if name and name != "NA":  # Skip "NA" values
                            star_name_map[csv_star_id] = name
            if verbose:
                console.print(f"[dim]Loaded {len(star_name_map):,} star name mappings[/dim]")
        except Exception as e:
            if verbose:
                console.print(f"[yellow]Warning: Could not load starnames.csv: {e}[/yellow]")

    # Import stars with name enhancement
    db = get_database()

    # Pre-fetch existing objects for deduplication
    console.print("[dim]Loading existing stars for deduplication...[/dim]")
    existing_objects = _run_async_safe(db.get_existing_objects_set(catalog="celestial_stars"))
    console.print(f"[dim]Found {len(existing_objects):,} existing stars[/dim]")

    imported = 0
    skipped = 0
    errors = 0

    # Load GeoJSON file
    try:
        with open(geojson_path, encoding="utf-8") as f:
            geojson_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {geojson_path}")
        raise
    except json.JSONDecodeError as e:
        console.print(f"[red]✗[/red] Invalid JSON: {e}")
        raise

    if geojson_data.get("type") != "FeatureCollection":
        console.print("[red]✗[/red] Invalid GeoJSON: expected FeatureCollection")
        raise InvalidCatalogFormatError("Invalid GeoJSON format")

    features = geojson_data.get("features", [])
    total_features = len(features)

    # Collect all objects first, then deduplicate once, then batch insert
    all_objects: list[dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Processing celestial_stars (mag ≤ {mag_limit})...", total=total_features)

        for feature in features:
            try:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})

                # Extract coordinates
                coords = geometry.get("coordinates", [])
                if not coords or len(coords) < 2:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Convert RA from degrees to hours
                ra_degrees = float(coords[0])
                dec_degrees = float(coords[1])
                ra_hours = CoordinateConverter.ra_degrees_to_hours(ra_degrees)

                # Extract id for name matching (id in CSV matches id in GeoJSON)
                star_id: int | None = None
                for id_field in ["id", "ID"]:
                    if id_field in properties:
                        try:
                            id_val = properties[id_field]
                            if isinstance(id_val, (int, float)) or (isinstance(id_val, str) and id_val.isdigit()):
                                star_id = int(id_val)
                            if star_id is not None:
                                break
                        except (ValueError, TypeError):
                            pass

                # Extract HIP number for catalog number (if available)
                hip_number: int | None = None
                for hip_field in ["hip", "HIP"]:
                    if hip_field in properties:
                        try:
                            hip_val = properties[hip_field]
                            if isinstance(hip_val, (int, float)) or (isinstance(hip_val, str) and hip_val.isdigit()):
                                hip_number = int(hip_val)
                            if hip_number is not None:
                                break
                        except (ValueError, TypeError):
                            pass

                # Extract name (will be enhanced with common name if available)
                name = (
                    properties.get("name")
                    or properties.get("designation")
                    or properties.get("Name")
                    or (
                        f"HIP {hip_number}"
                        if hip_number
                        else f"celestial_stars_{star_id}"
                        if star_id
                        else f"celestial_stars_{imported + skipped + 1}"
                    )
                )

                # Look up common name from starnames.csv using id
                common_name = None
                if star_id and star_id in star_name_map:
                    common_name = star_name_map[star_id]
                    # If the name is just a catalog number or ID, prefer the common name
                    if (
                        name.startswith("HIP ")
                        or name.startswith("celestial_stars_")
                        or (name.isdigit() and int(name) == star_id)
                    ):
                        name = common_name or name

                # Extract magnitude
                magnitude = None
                for mag_field in ["mag", "magnitude", "Mag", "Magnitude", "vmag", "V-Mag"]:
                    if mag_field in properties:
                        try:
                            mag_val = properties[mag_field]
                            if mag_val is not None and mag_val != "":
                                magnitude = float(mag_val)
                                break
                        except (ValueError, TypeError):
                            pass

                # Filter by magnitude
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
                    progress.advance(task)
                    continue

                # Extract catalog number (HIP number)
                catalog_number = hip_number

                # Extract constellation
                constellation = (
                    properties.get("constellation")
                    or properties.get("Const")
                    or properties.get("const")
                    or properties.get("con")
                )

                # Build description
                description_parts = []
                # Add Bayer designation if available
                bayer = properties.get("bayer") or properties.get("Bayer")
                if bayer:
                    description_parts.append(f"Bayer: {bayer}")
                # Add Flamsteed number if available
                flam = properties.get("flam") or properties.get("Flam")
                if flam:
                    description_parts.append(f"Flamsteed: {flam}")
                description = "; ".join(description_parts) if description_parts else None

                # Add to collection (will deduplicate once at the end)
                all_objects.append(
                    {
                        "name": name,
                        "catalog": "celestial_stars",
                        "ra_hours": ra_hours,
                        "dec_degrees": dec_degrees,
                        "object_type": CelestialObjectType.STAR,
                        "magnitude": magnitude,
                        "common_name": common_name,
                        "catalog_number": catalog_number,
                        "size_arcmin": None,
                        "description": description,
                        "constellation": constellation,
                    }
                )

            except Exception as e:
                errors += 1
                if verbose:
                    console.print(f"[yellow]Warning: Error processing feature: {e}[/yellow]")

            progress.advance(task)

    # Deduplicate once after all objects are created
    console.print(f"[dim]Deduplicating {len(all_objects):,} objects...[/dim]")
    seen_keys: set[tuple[str, str | None, int | None]] = set()
    deduplicated_objects: list[dict[str, Any]] = []
    for obj in all_objects:
        key = (obj["name"], obj.get("common_name"), obj.get("catalog_number"))
        # Check against both seen objects and existing database objects
        if key not in seen_keys and key not in existing_objects:
            # Also check by name alone (common_name might be None)
            name_key = (obj["name"], None, None)
            name_key2 = (obj["name"], obj["name"], None)
            if name_key not in existing_objects and name_key2 not in existing_objects:
                seen_keys.add(key)
                deduplicated_objects.append(obj)
            else:
                skipped += 1
        else:
            skipped += 1

    console.print(f"[dim]After deduplication: {len(deduplicated_objects):,} unique objects to import[/dim]")

    # Batch insert deduplicated objects
    batch_size = 1000
    num_batches = (len(deduplicated_objects) + batch_size - 1) // batch_size  # Ceiling division
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing celestial_stars...", total=num_batches)

        for i in range(0, len(deduplicated_objects), batch_size):
            batch = deduplicated_objects[i : i + batch_size]
            try:
                batch_imported = _run_async_safe(db.insert_objects_batch(batch))
                imported += batch_imported
                # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                progress.advance(task)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                errors += len(batch)
                # Still advance progress even on error
                progress.advance(task)

    return imported, skipped


def import_celestial_dsos(geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """Import DSOs from celestial_data GeoJSON."""
    # Map DSO types to our object types
    dso_type_map = {
        "Galaxy": CelestialObjectType.GALAXY,
        "Nebula": CelestialObjectType.NEBULA,
        "Cluster": CelestialObjectType.CLUSTER,
        "Open Cluster": CelestialObjectType.CLUSTER,
        "Globular Cluster": CelestialObjectType.CLUSTER,
        "Planetary Nebula": CelestialObjectType.NEBULA,
        "Emission Nebula": CelestialObjectType.NEBULA,
        "Reflection Nebula": CelestialObjectType.NEBULA,
        "Dark Nebula": CelestialObjectType.NEBULA,
        "Supernova Remnant": CelestialObjectType.NEBULA,
    }
    return import_celestial_data_geojson(
        geojson_path, catalog="celestial_dsos", mag_limit=mag_limit, verbose=verbose, object_type_map=dso_type_map
    )


def import_celestial_messier(geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """Import Messier objects from celestial_data GeoJSON."""
    return import_celestial_data_geojson(geojson_path, catalog="messier", mag_limit=mag_limit, verbose=verbose)


def import_celestial_local_group(geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """
    Import local group galaxies and Milky Way halo objects from celestial_data GeoJSON.

    Includes Local Group galaxies, Milky Way globular clusters, and dwarf galaxies.
    """
    # Map local group object types to our object types
    lg_type_map = {
        # Globular clusters
        "GC": CelestialObjectType.CLUSTER,
        "Globular Cluster": CelestialObjectType.CLUSTER,
        # Dwarf galaxies
        "dSph": CelestialObjectType.GALAXY,  # Dwarf spheroidal
        "dE": CelestialObjectType.GALAXY,  # Dwarf elliptical
        "dE5": CelestialObjectType.GALAXY,  # Dwarf elliptical type 5
        "UFD": CelestialObjectType.GALAXY,  # Ultra-faint dwarf
        # Irregular galaxies
        "IBm": CelestialObjectType.GALAXY,  # Irregular barred Magellanic
        "IBm V-VI": CelestialObjectType.GALAXY,
        "Im": CelestialObjectType.GALAXY,  # Irregular Magellanic
        "Im V-VI": CelestialObjectType.GALAXY,
        # Other galaxy types
        "Galaxy": CelestialObjectType.GALAXY,
    }
    return import_celestial_data_geojson(
        geojson_path, catalog="local_group", mag_limit=mag_limit, verbose=verbose, object_type_map=lg_type_map
    )


def import_celestial_constellations(
    geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False
) -> tuple[int, int]:
    """
    Import constellations from celestial_data GeoJSON into ConstellationModel.

    Args:
        geojson_path: Path to constellations GeoJSON file
        mag_limit: Not used for constellations (kept for interface consistency)
        verbose: Show detailed progress

    Returns:
        (imported_count, skipped_count)
    """

    from sqlalchemy import select

    from celestron_nexstar.api.database.models import ConstellationModel, get_db_session

    imported = 0
    skipped = 0
    errors = 0

    # Load GeoJSON file
    try:
        with open(geojson_path, encoding="utf-8") as f:
            geojson_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {geojson_path}")
        raise
    except json.JSONDecodeError as e:
        console.print(f"[red]✗[/red] Invalid JSON: {e}")
        raise

    if geojson_data.get("type") != "FeatureCollection":
        console.print("[red]✗[/red] Invalid GeoJSON: expected FeatureCollection")
        raise InvalidCatalogFormatError("Invalid GeoJSON format")

    features = geojson_data.get("features", [])
    total_features = len(features)

    # Collect all constellations first, then deduplicate once, then batch insert
    all_constellations: list[ConstellationModel] = []

    async def _import() -> tuple[int, int]:
        nonlocal imported, skipped, errors, all_constellations

        # Pre-fetch existing constellations for deduplication
        existing_names: set[str] = set()
        async with get_db_session() as db_session:
            result = await db_session.execute(select(ConstellationModel.name))
            existing_names = {row[0] for row in result.all()}
            console.print(f"[dim]Found {len(existing_names):,} existing constellations[/dim]")

        async with get_db_session() as db_session:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Importing constellations...", total=total_features)

                for feature in features:
                    try:
                        properties = feature.get("properties", {})
                        geometry = feature.get("geometry", {})

                        # Extract coordinates
                        coords = geometry.get("coordinates", [])
                        if not coords or len(coords) < 2:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Convert RA from degrees to hours
                        ra_degrees = float(coords[0])
                        dec_degrees = float(coords[1])
                        ra_hours = CoordinateConverter.ra_degrees_to_hours(ra_degrees)

                        # Extract constellation name (Latin name)
                        name = properties.get("name") or properties.get("Name") or properties.get("id")
                        if not name:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Check if already exists using pre-fetched set
                        if name in existing_names:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Extract abbreviation (3-letter IAU code)
                        abbreviation = (
                            properties.get("abbr")
                            or properties.get("Abbr")
                            or properties.get("abbreviation")
                            or properties.get("designation")
                            or name[:3].upper()
                        )

                        # Extract common name (English name)
                        common_name = (
                            properties.get("common_name") or properties.get("name_en") or properties.get("Name_en")
                        )

                        # Extract brightest star and magnitude
                        brightest_star = properties.get("brightest_star") or properties.get("key_star")
                        # Magnitude is not stored in ConstellationModel (calculated from brightest_star)

                        # Extract area
                        area_sq_deg = None
                        for area_field in ["area", "Area", "area_sq_deg", "size"]:
                            if area_field in properties:
                                try:
                                    area_sq_deg = float(properties[area_field])
                                    break
                                except (ValueError, TypeError):
                                    pass

                        # Extract mythology/description
                        mythology = (
                            properties.get("mythology")
                            or properties.get("description")
                            or properties.get("Description")
                        )

                        # Extract season
                        season = properties.get("season") or properties.get("Season")

                        # Calculate boundaries from geometry
                        # For Point geometry, use approximate bounds around center
                        # For Polygon/MultiPolygon, calculate actual bounds
                        geometry_type = geometry.get("type", "")
                        if geometry_type == "Point":
                            # Approximate bounds (will be improved with bounds file if available)
                            ra_min_hours = ra_hours - 1.0
                            ra_max_hours = ra_hours + 1.0
                            dec_min_degrees = dec_degrees - 10.0
                            dec_max_degrees = dec_degrees + 10.0
                        elif geometry_type in ("Polygon", "MultiPolygon"):
                            # Calculate bounds from polygon coordinates
                            coords_list = coords
                            if geometry_type == "Polygon":
                                # Polygon: [[[lon, lat], ...], ...] - use outer ring
                                coords_list = coords[0] if coords else []
                            elif geometry_type == "MultiPolygon":
                                # MultiPolygon: [[[[lon, lat], ...], ...], ...] - flatten all polygons
                                coords_list = []
                                for poly in coords:
                                    if poly:
                                        coords_list.extend(poly[0])

                            # Calculate min/max from all coordinates
                            if coords_list:
                                ra_values = [float(c[0]) for c in coords_list if len(c) >= 2]
                                dec_values = [float(c[1]) for c in coords_list if len(c) >= 2]
                                if ra_values and dec_values:
                                    ra_min_deg = min(ra_values)
                                    ra_max_deg = max(ra_values)
                                    dec_min_degrees = min(dec_values)
                                    dec_max_degrees = max(dec_values)
                                    ra_min_hours = CoordinateConverter.ra_degrees_to_hours(ra_min_deg)
                                    ra_max_hours = CoordinateConverter.ra_degrees_to_hours(ra_max_deg)
                                else:
                                    # Fallback to approximate
                                    ra_min_hours = ra_hours - 1.0
                                    ra_max_hours = ra_hours + 1.0
                                    dec_min_degrees = dec_degrees - 10.0
                                    dec_max_degrees = dec_degrees + 10.0
                            else:
                                # Fallback to approximate
                                ra_min_hours = ra_hours - 1.0
                                ra_max_hours = ra_hours + 1.0
                                dec_min_degrees = dec_degrees - 10.0
                                dec_max_degrees = dec_degrees + 10.0
                        else:
                            # Fallback to approximate
                            ra_min_hours = ra_hours - 1.0
                            ra_max_hours = ra_hours + 1.0
                            dec_min_degrees = dec_degrees - 10.0
                            dec_max_degrees = dec_degrees + 10.0

                        # Try to get bounds from properties if available (overrides geometry calculation)
                        if "ra_min" in properties:
                            ra_min_hours = CoordinateConverter.ra_degrees_to_hours(float(properties["ra_min"]))
                        if "ra_max" in properties:
                            ra_max_hours = CoordinateConverter.ra_degrees_to_hours(float(properties["ra_max"]))
                        if "dec_min" in properties:
                            dec_min_degrees = float(properties["dec_min"])
                        if "dec_max" in properties:
                            dec_max_degrees = float(properties["dec_max"])

                        # Create constellation model
                        constellation = ConstellationModel(
                            name=name,
                            abbreviation=abbreviation[:3],  # Ensure 3 characters
                            common_name=common_name,
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            ra_min_hours=ra_min_hours,
                            ra_max_hours=ra_max_hours,
                            dec_min_degrees=dec_min_degrees,
                            dec_max_degrees=dec_max_degrees,
                            area_sq_deg=area_sq_deg,
                            brightest_star=brightest_star,
                            mythology=mythology,
                            season=season,
                        )

                        all_constellations.append(constellation)

                    except Exception as e:
                        errors += 1
                        if verbose:
                            console.print(f"[yellow]Warning: Error processing constellation: {e}[/yellow]")

                    progress.advance(task)

            # Deduplicate once after all constellations are created
            console.print(f"[dim]Deduplicating {len(all_constellations):,} constellations...[/dim]")
            seen_names: set[str] = set()
            deduplicated_constellations: list[ConstellationModel] = []
            for const in all_constellations:
                if const.name not in seen_names and const.name not in existing_names:
                    seen_names.add(const.name)
                    deduplicated_constellations.append(const)
                else:
                    skipped += 1

            console.print(
                f"[dim]After deduplication: {len(deduplicated_constellations):,} unique constellations to import[/dim]"
            )

            # Batch insert deduplicated constellations
            batch_size = 100
            num_batches = (len(deduplicated_constellations) + batch_size - 1) // batch_size  # Ceiling division
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Importing constellations...", total=num_batches)

                for i in range(0, len(deduplicated_constellations), batch_size):
                    batch = deduplicated_constellations[i : i + batch_size]
                    try:
                        db_session.add_all(batch)
                        await db_session.commit()
                        imported += len(batch)
                        # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                        progress.advance(task)
                    except Exception as e:
                        if verbose:
                            console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                        errors += len(batch)
                        await db_session.rollback()
                        # Still advance progress even on error
                        progress.advance(task)

        return imported, skipped

    return _run_async_safe(_import())


def import_celestial_asterisms(geojson_path: Path, mag_limit: float = 15.0, verbose: bool = False) -> tuple[int, int]:
    """
    Import asterisms from celestial_data GeoJSON into AsterismModel.

    Args:
        geojson_path: Path to asterisms GeoJSON file
        mag_limit: Not used for asterisms (kept for interface consistency)
        verbose: Show detailed progress

    Returns:
        (imported_count, skipped_count)
    """

    from sqlalchemy import select

    from celestron_nexstar.api.database.models import AsterismModel, get_db_session

    imported = 0
    skipped = 0
    errors = 0

    # Load GeoJSON file
    try:
        with open(geojson_path, encoding="utf-8") as f:
            geojson_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {geojson_path}")
        raise
    except json.JSONDecodeError as e:
        console.print(f"[red]✗[/red] Invalid JSON: {e}")
        raise

    if geojson_data.get("type") != "FeatureCollection":
        console.print("[red]✗[/red] Invalid GeoJSON: expected FeatureCollection")
        raise InvalidCatalogFormatError("Invalid GeoJSON format")

    features = geojson_data.get("features", [])
    total_features = len(features)

    # Collect all asterisms first, then deduplicate once, then batch insert
    all_asterisms: list[AsterismModel] = []

    async def _import() -> tuple[int, int]:
        nonlocal imported, skipped, errors, all_asterisms

        # Pre-fetch existing asterisms for deduplication
        existing_names: set[str] = set()
        async with get_db_session() as db_session:
            result = await db_session.execute(select(AsterismModel.name))
            existing_names = {row[0] for row in result.all()}
            console.print(f"[dim]Found {len(existing_names):,} existing asterisms[/dim]")

        async with get_db_session() as db_session:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Importing asterisms...", total=total_features)

                for feature in features:
                    try:
                        properties = feature.get("properties", {})
                        geometry = feature.get("geometry", {})

                        # Extract coordinates
                        coords = geometry.get("coordinates", [])
                        if not coords or len(coords) < 2:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Convert RA from degrees to hours
                        ra_degrees = float(coords[0])
                        dec_degrees = float(coords[1])
                        ra_hours = CoordinateConverter.ra_degrees_to_hours(ra_degrees)

                        # Extract asterism name
                        name = properties.get("name") or properties.get("Name") or properties.get("id")
                        if not name:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Check if already exists using pre-fetched set
                        if name in existing_names:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Extract alternative names
                        alt_names = (
                            properties.get("alt_names")
                            or properties.get("altNames")
                            or properties.get("alternative_names")
                        )

                        # Extract size
                        size_degrees = None
                        for size_field in ["size", "Size", "size_degrees", "diam", "diameter"]:
                            if size_field in properties:
                                try:
                                    size_degrees = float(properties[size_field])
                                    break
                                except (ValueError, TypeError):
                                    pass

                        # Extract parent constellation
                        parent_constellation = (
                            properties.get("parent_constellation")
                            or properties.get("constellation")
                            or properties.get("Const")
                        )

                        # Extract description
                        description = (
                            properties.get("description") or properties.get("Description") or properties.get("notes")
                        )

                        # Extract component stars
                        stars = (
                            properties.get("stars")
                            or properties.get("component_stars")
                            or properties.get("member_stars")
                        )

                        # Extract season
                        season = properties.get("season") or properties.get("Season")

                        # Create asterism model
                        asterism = AsterismModel(
                            name=name,
                            alt_names=alt_names,
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            size_degrees=size_degrees,
                            parent_constellation=parent_constellation,
                            description=description,
                            stars=stars,
                            season=season,
                        )

                        all_asterisms.append(asterism)

                    except Exception as e:
                        errors += 1
                        if verbose:
                            console.print(f"[yellow]Warning: Error processing asterism: {e}[/yellow]")

                    progress.advance(task)

            # Deduplicate once after all asterisms are created
            console.print(f"[dim]Deduplicating {len(all_asterisms):,} asterisms...[/dim]")
            seen_names: set[str] = set()
            deduplicated_asterisms: list[AsterismModel] = []
            for asterism_item in all_asterisms:
                if asterism_item.name not in seen_names and asterism_item.name not in existing_names:
                    seen_names.add(asterism_item.name)
                    deduplicated_asterisms.append(asterism_item)
                else:
                    skipped += 1

            console.print(f"[dim]After deduplication: {len(deduplicated_asterisms):,} unique asterisms to import[/dim]")

            # Batch insert deduplicated asterisms
            batch_size = 100
            num_batches = (len(deduplicated_asterisms) + batch_size - 1) // batch_size  # Ceiling division
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Importing asterisms...", total=num_batches)

                for i in range(0, len(deduplicated_asterisms), batch_size):
                    batch = deduplicated_asterisms[i : i + batch_size]
                    try:
                        db_session.add_all(batch)
                        await db_session.commit()
                        imported += len(batch)
                        # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                        progress.advance(task)
                    except Exception as e:
                        if verbose:
                            console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                        errors += len(batch)
                        await db_session.rollback()
                        # Still advance progress even on error
                        progress.advance(task)

        return imported, skipped

    return _run_async_safe(_import())


# Registry of available data sources
DATA_SOURCES: dict[str, DataSource] = {
    "custom": DataSource(
        name="Custom YAML",
        description="User-defined custom catalog (catalogs.yaml) - Planets and Moons",
        url="local file",
        objects_available=25,  # Planets and moons
        license="User-defined",
        attribution="User-defined",
        importer=import_custom_yaml,
    ),
    "celestial_stars_6": DataSource(
        name="Celestial Data - Stars (mag ≤ 6)",
        description="Stars from celestial_data repository (magnitude ≤ 6)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=5000,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_stars(path, mag, verbose),
    ),
    "celestial_stars_8": DataSource(
        name="Celestial Data - Stars (mag ≤ 8)",
        description="Stars from celestial_data repository (magnitude ≤ 8)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=20000,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_stars(path, mag, verbose),
    ),
    "celestial_stars_14": DataSource(
        name="Celestial Data - Stars (mag ≤ 14)",
        description="Stars from celestial_data repository (magnitude ≤ 14)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=100000,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_stars(path, mag, verbose),
    ),
    "celestial_dsos_6": DataSource(
        name="Celestial Data - DSOs (mag ≤ 6)",
        description="Deep sky objects from celestial_data (magnitude ≤ 6)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=200,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_dsos(path, mag, verbose),
    ),
    "celestial_dsos_14": DataSource(
        name="Celestial Data - DSOs (mag ≤ 14)",
        description="Deep sky objects from celestial_data (magnitude ≤ 14)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=5000,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_dsos(path, mag, verbose),
    ),
    "celestial_dsos_20": DataSource(
        name="Celestial Data - DSOs (mag ≤ 20)",
        description="Deep sky objects from celestial_data (magnitude ≤ 20)",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=20000,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_dsos(path, mag, verbose),
    ),
    "celestial_dsos_bright": DataSource(
        name="Celestial Data - Bright DSOs",
        description="Hand-selected bright deep sky objects from celestial_data",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=200,  # Approximate
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_dsos(path, mag, verbose),
    ),
    "celestial_messier": DataSource(
        name="Celestial Data - Messier Objects",
        description="Messier catalog from celestial_data repository",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=110,
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_messier(path, mag, verbose),
    ),
    "celestial_asterisms": DataSource(
        name="Celestial Data - Asterisms",
        description="Asterisms (star patterns) from celestial_data repository",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=65,
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_asterisms(path, mag, verbose),
    ),
    "celestial_constellations": DataSource(
        name="Celestial Data - Constellations",
        description="88 IAU constellations from celestial_data repository",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=88,
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_constellations(path, mag, verbose),
    ),
    "celestial_local_group": DataSource(
        name="Celestial Data - Local Group",
        description="Local Group galaxies and Milky Way halo objects (globular clusters, dwarf galaxies) from celestial_data",
        url="https://github.com/dieghernan/celestial_data",
        objects_available=200,  # Approximate - includes galaxies and globular clusters
        license="BSD-3-Clause",
        attribution="Olaf Frohn and Diego Hernangómez",
        importer=lambda path, mag, verbose: import_celestial_local_group(path, mag, verbose),
    ),
}


def list_data_sources() -> None:
    """Display available data sources."""

    db = get_database()
    stats = _run_async_safe(db.get_stats())

    table = Table(title="Available Data Sources")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Available", justify="right", style="yellow")
    table.add_column("Imported", justify="right", style="green")
    table.add_column("License", style="dim")

    for source_id, source in DATA_SOURCES.items():
        # Estimate imported count based on catalog
        if source_id == "custom":
            # Count objects from custom catalogs (planets and moons only)
            custom_catalogs = ["planets", "moons"]
            imported = sum(stats.objects_by_catalog.get(cat, 0) for cat in custom_catalogs)
        elif source_id.startswith("celestial_stars"):
            imported = stats.objects_by_catalog.get("celestial_stars", 0)
        elif source_id.startswith("celestial_dsos"):
            imported = stats.objects_by_catalog.get("celestial_dsos", 0)
        elif source_id == "celestial_messier":
            # Count messier objects from celestial_data (may overlap with existing messier)
            imported = stats.objects_by_catalog.get("messier", 0)
        elif source_id == "celestial_asterisms":
            # Count from asterisms table, not objects table

            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import AsterismModel, get_db_session

            async def _count() -> int:
                async with get_db_session() as session:
                    result = await session.scalar(select(func.count(AsterismModel.id)))
                    return result or 0

            imported = _run_async_safe(_count())
        elif source_id == "celestial_constellations":
            # Count from constellations table, not objects table

            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import ConstellationModel, get_db_session

            async def _count() -> int:
                async with get_db_session() as session:
                    result = await session.scalar(select(func.count(ConstellationModel.id)))
                    return result or 0

            imported = _run_async_safe(_count())
        elif source_id == "celestial_local_group":
            imported = stats.objects_by_catalog.get("local_group", 0)
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


def import_data_source(source_id: str, mag_limit: float = 15.0, force_download: bool = False) -> bool:
    """
    Import data from a source.

    Args:
        source_id: ID of data source (e.g., "celestial_stars_6")
        mag_limit: Maximum magnitude to import
        force_download: Force re-download of cached files

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

            stats = _run_async_safe(db.get_stats())
            console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Import failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    # Download data for remote sources
    # Determine file path and download method based on source
    if source_id.startswith("celestial_"):
        # Map celestial_data source IDs to filenames
        filename_map = {
            "celestial_stars_6": "stars.6.min.geojson",
            "celestial_stars_8": "stars.8.min.geojson",
            "celestial_stars_14": "stars.14.min.geojson",
            "celestial_dsos_6": "dsos.6.min.geojson",
            "celestial_dsos_14": "dsos.14.min.geojson",
            "celestial_dsos_20": "dsos.20.min.geojson",
            "celestial_dsos_bright": "dsos.bright.min.geojson",
            "celestial_messier": "messier.min.geojson",
            "celestial_asterisms": "asterisms.min.geojson",
            "celestial_constellations": "constellations.min.geojson",
            "celestial_local_group": "lg.min.geojson",
        }
        filename = filename_map.get(source_id)
        if not filename:
            console.print(f"[red]✗[/red] Unknown celestial_data source: {source_id}")
            return False
        cache_dir = get_cache_dir()
        cache_path = cache_dir / filename
        if not cache_path.exists() or force_download:
            if force_download and cache_path.exists():
                console.print(f"[dim]Force re-download: removing cached {filename}...[/dim]")
                cache_path.unlink()
            console.print("Downloading data from celestial_data repository...")
            if not download_celestial_data(filename, cache_path):
                return False

        # Import data for celestial sources
        console.print(f"\nImporting with magnitude limit: {mag_limit}")
        try:
            imported, skipped = source.importer(cache_path, mag_limit, False)
        except Exception as e:
            console.print(f"[red]✗[/red] Import failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        console.print("\n[green]✓[/green] Import complete!")
        console.print(f"  Imported: [green]{imported:,}[/green]")
        console.print(f"  Skipped:  [yellow]{skipped:,}[/yellow] (too faint or invalid)")

        # Show updated stats
        db = get_database()
        stats = _run_async_safe(db.get_stats())
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True
    elif source_id == "custom":
        # Custom YAML doesn't need downloading - import directly
        console.print(f"\nImporting with magnitude limit: {mag_limit}")
        try:
            imported, skipped = source.importer(Path(""), mag_limit, False)
        except Exception as e:
            console.print(f"[red]✗[/red] Import failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        console.print("\n[green]✓[/green] Import complete!")
        console.print(f"  Imported: [green]{imported:,}[/green]")
        console.print(f"  Skipped:  [yellow]{skipped:,}[/yellow] (too faint or invalid)")

        # Show updated stats
        db = get_database()
        stats = _run_async_safe(db.get_stats())
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True
    else:
        console.print(f"[red]✗[/red] No downloader for {source_id}")
        return False
