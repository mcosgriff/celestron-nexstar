"""
Data Import Module

Provides CLI commands for importing catalog data from various sources.
"""

from __future__ import annotations

import csv
import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
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


# _run_async_safe removed - all database functions are now synchronous


def get_cache_dir() -> Path:
    """
    Get the cache directory for celestial data files.

    Returns:
        Path to ~/.cache/celestron-nexstar/celestial-data/
    """
    cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "celestial-data"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def geojson_to_spatialite_geometry_async(geojson_geom: dict[str, Any], db_session: Any) -> Any | None:
    """
    Convert GeoJSON geometry to GeoAlchemy2 WKTElement for SpatiaLite.

    Args:
        geojson_geom: GeoJSON geometry object (dict with 'type' and 'coordinates')
        db_session: SQLAlchemy session with GeoAlchemy2/SpatiaLite loaded

    Returns:
        GeoAlchemy2 WKTElement or None if conversion fails
    """
    geom_type = geojson_geom.get("type", "")
    coords = geojson_geom.get("coordinates", [])

    if not geom_type or not coords:
        return None

    try:
        # Convert GeoJSON coordinates to WKT (Well-Known Text) format
        # GeoJSON uses [lon, lat] = [RA_deg, Dec_deg] for celestial coordinates
        wkt = None

        if geom_type == "Point":
            if len(coords) >= 2:
                ra_deg, dec_deg = float(coords[0]), float(coords[1])
                wkt = f"POINT({ra_deg} {dec_deg})"

        elif geom_type == "LineString":
            points = []
            for coord in coords:
                if len(coord) >= 2:
                    ra_deg, dec_deg = float(coord[0]), float(coord[1])
                    points.append(f"{ra_deg} {dec_deg}")
            if points:
                wkt = f"LINESTRING({', '.join(points)})"

        elif geom_type == "MultiLineString":
            lines = []
            for line_coords in coords:
                points = []
                for coord in line_coords:
                    if len(coord) >= 2:
                        ra_deg, dec_deg = float(coord[0]), float(coord[1])
                        points.append(f"{ra_deg} {dec_deg}")
                if points:
                    lines.append(f"({', '.join(points)})")
            if lines:
                wkt = f"MULTILINESTRING({', '.join(lines)})"

        elif geom_type == "Polygon":
            # Polygon: [[[lon, lat], ...], ...] - first ring is exterior, rest are holes
            rings = []
            for ring_coords in coords:
                points = []
                for coord in ring_coords:
                    if len(coord) >= 2:
                        ra_deg, dec_deg = float(coord[0]), float(coord[1])
                        points.append(f"{ra_deg} {dec_deg}")
                if points:
                    # Close the ring (first point = last point)
                    if points[0] != points[-1]:
                        points.append(points[0])
                    rings.append(f"({', '.join(points)})")
            if rings:
                wkt = f"POLYGON({', '.join(rings)})"

        elif geom_type == "MultiPolygon":
            # MultiPolygon: [[[[lon, lat], ...], ...], ...]
            polygons = []
            for poly_coords in coords:
                rings = []
                for ring_coords in poly_coords:
                    points = []
                    for coord in ring_coords:
                        if len(coord) >= 2:
                            ra_deg, dec_deg = float(coord[0]), float(coord[1])
                            points.append(f"{ra_deg} {dec_deg}")
                    if points:
                        # Close the ring
                        if points[0] != points[-1]:
                            points.append(points[0])
                        rings.append(f"({', '.join(points)})")
                if rings:
                    polygons.append(f"({', '.join(rings)})")
            if polygons:
                wkt = f"MULTIPOLYGON({', '.join(polygons)})"

        if not wkt:
            return None

        # Use GeoAlchemy2's WKTElement to create geometry (properly handles SpatiaLite)
        # SRID 0 = no projection (we're using angular coordinates directly)
        from geoalchemy2 import WKTElement

        return WKTElement(wkt, srid=0)

    except ImportError:
        console.print("[yellow]Warning: GeoAlchemy2 not available, cannot create geometry[/yellow]")
        return None
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to convert geometry to SpatiaLite: {e}[/yellow]")
        return None


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
                existing = db.get_by_name(name)
                if existing:
                    skipped += 1
                    console.print(f"[dim]Skipping duplicate: {name} (already exists)[/dim]")
                    progress.advance(task)
                    continue

                # Also check by catalog + catalog_number if available
                if catalog_number is not None and db.exists_by_catalog_number(catalog_name, catalog_number):
                    skipped += 1
                    console.print(f"[dim]Skipping duplicate: {catalog_name} {catalog_number} (already exists)[/dim]")
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
    object_enhancer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
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
    status_msg = f"Loading existing {catalog} objects for deduplication..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    existing_objects = db.get_existing_objects_set(catalog=catalog)
    status_msg = f"Found {len(existing_objects):,} existing {catalog} objects"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

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

    # Use progress callback if provided, otherwise use Rich Progress
    use_rich_progress = progress_callback is None
    progress_obj = None
    task = None
    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task(f"Processing {catalog} (mag ≤ {mag_limit})...", total=total_features)
    else:
        # Emit initial progress via callback
        if progress_callback:
            progress_callback(f"Processing {catalog} (mag ≤ {mag_limit})...", 0, total_features)

    for feature in features:
        try:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})

            # Extract coordinates (GeoJSON format: [lon, lat] = [RA in degrees, Dec in degrees])
            coords = geometry.get("coordinates", [])
            if not coords or len(coords) < 2:
                skipped += 1
                # Update progress
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    processed = len(all_objects) + skipped + errors
                    progress_callback(f"Processing {catalog}...", processed, total_features)
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
                # Update progress
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    processed = len(all_objects) + skipped + errors
                    progress_callback(f"Processing {catalog}...", processed, total_features)
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

            # Build object dictionary
            obj_dict = {
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

            # Store geometry dict for DSOs (will be converted after batch insert)
            # For DSO catalogs, store the full geometry from GeoJSON
            if "dso" in catalog.lower():
                obj_dict["_temp_geometry"] = geometry

            # Apply object enhancer if provided (e.g., for DSO name mapping)
            if object_enhancer:
                obj_dict = object_enhancer(obj_dict)

            # Add to collection (will deduplicate once at the end)
            all_objects.append(obj_dict)

        except Exception as e:
            errors += 1
            if verbose:
                console.print(f"[yellow]Warning: Error processing feature: {e}[/yellow]")

        # Update progress
        if use_rich_progress and task is not None:
            progress_obj.advance(task)  # type: ignore[union-attr]
        elif progress_callback:
            processed = len(all_objects) + skipped + errors
            progress_callback(f"Processing {catalog}...", processed, total_features)

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

    # Close processing progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

    # Batch insert deduplicated objects
    batch_size = 1000
    num_batches = (len(deduplicated_objects) + batch_size - 1) // batch_size  # Ceiling division

    # Use progress callback if provided, otherwise use Rich Progress
    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task(f"Importing {catalog}...", total=num_batches)
    else:
        # Emit initial import progress via callback
        if progress_callback:
            progress_callback(f"Importing {catalog}...", 0, num_batches)

        for i in range(0, len(deduplicated_objects), batch_size):
            batch = deduplicated_objects[i : i + batch_size]
            try:
                batch_imported = db.insert_objects_batch(batch)
                imported += batch_imported

                # For DSO objects, update geometry from GeoJSON after insert
                if "dso" in catalog.lower():
                    with db._get_session() as db_session:
                        from sqlalchemy import select

                        from celestron_nexstar.api.database.models import (
                            ClusterModel,
                            GalaxyModel,
                            NebulaModel,
                        )

                        # Map object types to model classes
                        from typing import cast

                        type_to_model: dict[CelestialObjectType, type[GalaxyModel | NebulaModel | ClusterModel]] = {
                            CelestialObjectType.GALAXY: GalaxyModel,
                            CelestialObjectType.NEBULA: NebulaModel,
                            CelestialObjectType.CLUSTER: ClusterModel,
                        }

                        for obj in batch:
                            if "_temp_geometry" not in obj or not obj["_temp_geometry"]:
                                continue

                            try:
                                obj_type: CelestialObjectType | str | None = obj.get("object_type")
                                if isinstance(obj_type, str):
                                    obj_type = CelestialObjectType(obj_type)

                                if not isinstance(obj_type, CelestialObjectType):
                                    continue

                                model_class = type_to_model.get(obj_type)
                                if not model_class:
                                    continue

                                # Find the inserted object by name
                                # Type ignore: model_class is a union of model types, but select() needs a specific type
                                result = db_session.execute(
                                    select(model_class).where(model_class.name == obj["name"]).limit(1)  # type: ignore[arg-type]
                                )
                                model_obj = result.scalar_one_or_none()

                                if model_obj:
                                    # Convert GeoJSON geometry to SpatiaLite geometry
                                    geometry_blob = geojson_to_spatialite_geometry_async(
                                        obj["_temp_geometry"], db_session
                                    )
                                    if geometry_blob:
                                        # Type ignore: model_obj is a union type, but we know it has geometry attribute
                                        model_obj.geometry = geometry_blob  # type: ignore[misc]
                                        db_session.commit()
                            except Exception as e:
                                if verbose:
                                    console.print(
                                        f"[yellow]Warning: Failed to update geometry for {obj.get('name', 'unknown')}: {e}[/yellow]"
                                    )
                                db_session.rollback()

                # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    batch_num = (i // batch_size) + 1
                    progress_callback(f"Importing {catalog}...", batch_num, num_batches)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                errors += len(batch)
                # Still advance progress even on error
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    batch_num = (i // batch_size) + 1
                    progress_callback(f"Importing {catalog}...", batch_num, num_batches)

    # Close import progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

    return imported, skipped


# Known star-to-constellation mappings for well-known bright stars
# These override coordinate-based lookup for accuracy
KNOWN_STAR_CONSTELLATIONS: dict[str, str] = {
    "Sirius": "Canis Major",
    "Canopus": "Carina",
    "Arcturus": "Boötes",
    "Vega": "Lyra",
    "Capella": "Auriga",
    "Rigel": "Orion",
    "Procyon": "Canis Minor",
    "Betelgeuse": "Orion",
    "Achernar": "Eridanus",
    "Hadar": "Centaurus",
    "Altair": "Aquila",
    "Aldebaran": "Taurus",
    "Spica": "Virgo",
    "Antares": "Scorpius",
    "Pollux": "Gemini",
    "Fomalhaut": "Piscis Austrinus",
    "Deneb": "Cygnus",
    "Mimosa": "Crux",
    "Regulus": "Leo",
    "Adhara": "Canis Major",
    "Castor": "Gemini",
    "Bellatrix": "Orion",
    "Elnath": "Taurus",
    "Miaplacidus": "Carina",
    "Alnilam": "Orion",
    "Alnair": "Grus",
    "Alioth": "Ursa Major",
    "Mirphak": "Perseus",
    "Dubhe": "Ursa Major",
    "Wezen": "Canis Major",
    "Sargas": "Scorpius",
    "Kaus Australis": "Sagittarius",
    "Avior": "Carina",
    "Alkaid": "Ursa Major",
    "Menkalinan": "Auriga",
    "Atria": "Triangulum Australe",
    "Alhena": "Gemini",
    "Peacock": "Pavo",
    "Alsephina": "Vela",
    "Mirzam": "Canis Major",
    "Alphard": "Hydra",
    "Polaris": "Ursa Minor",
    "Hamal": "Aries",
    "Algol": "Perseus",
    "Denebola": "Leo",
    "Nunki": "Sagittarius",
    "Mirach": "Andromeda",
    "Alpheratz": "Andromeda",
    "Rasalhague": "Ophiuchus",
    "Kochab": "Ursa Minor",
    "Dschubba": "Scorpius",
    "Graffias": "Scorpius",
    "Shaula": "Scorpius",
    "Rasalgethi": "Hercules",
    "Rastaban": "Draco",
    "Eltanin": "Draco",
    "Kaus Media": "Sagittarius",
    "Kaus Borealis": "Sagittarius",
    "Arneb": "Lepus",
    "Gienah": "Corvus",
    "Mintaka": "Orion",
    "Saiph": "Orion",
    "Alnitak": "Orion",
    "Meissa": "Orion",
    "Algieba": "Leo",
    "Almach": "Andromeda",
    "Acrux": "Crux",
    "Gacrux": "Crux",
    "Rigil Kentaurus": "Centaurus",
    "Toliman": "Centaurus",
}


def _find_constellation_by_coordinates_async(
    ra_hours: float,
    dec_degrees: float,
    constellations: list[Any],
    star_name: str | None = None,
) -> str | None:
    """
    Find constellation for a star based on coordinates.

    Uses known mappings for well-known stars, then SpatiaLite spatial functions for accurate
    point-in-polygon checks, then constellation boundaries, otherwise finds nearest constellation center.

    Args:
        ra_hours: Star's right ascension in hours
        dec_degrees: Star's declination in degrees
        constellations: List of ConstellationModel objects with boundary data
        star_name: Optional star name for known star lookup
        db_session: Optional database session for SpatiaLite queries

    Returns:
        Constellation name or None if not found
    """
    # First, check known star mappings for well-known stars
    if star_name and star_name in KNOWN_STAR_CONSTELLATIONS:
        return KNOWN_STAR_CONSTELLATIONS[star_name]

    from sqlalchemy import select

    from celestron_nexstar.api.database.models import ConstellationModel

    # Convert RA from hours to degrees for SpatiaLite (treating as longitude)
    ra_degrees = ra_hours * 15.0

    # Get database session for SpatiaLite queries
    from celestron_nexstar.api.database.models import get_db_session

    with get_db_session() as db_session:
        # First, try GeoAlchemy2 spatial query (most accurate)
        try:
            from geoalchemy2 import functions

            # Create a point geometry for the star position
            point_wkt = f"POINT({ra_degrees} {dec_degrees})"

            # Query constellations where the point is within the geometry
            # Use ST_Contains (GeoAlchemy2 automatically translates to SpatiaLite Contains)
            stmt = select(ConstellationModel.name).where(
                functions.ST_Contains(ConstellationModel.geometry, functions.ST_GeomFromText(point_wkt, 0))
            )

            result = db_session.execute(stmt)
            constellation_name = result.scalar_one_or_none()
            if constellation_name:
                return constellation_name
        except Exception:
            # If spatial query fails, fall back to other methods
            pass

    # Fallback to bounding box check (faster but less accurate)
    for const in constellations:
        if not isinstance(const, ConstellationModel):
            continue

        # Check if boundaries are set (not None and not zero-width)
        has_boundaries = (
            const.ra_min_hours is not None
            and const.ra_max_hours is not None
            and const.dec_min_degrees is not None
            and const.dec_max_degrees is not None
            and (const.ra_max_hours != const.ra_min_hours or const.dec_max_degrees != const.dec_min_degrees)
        )

        if has_boundaries:
            # Check if star is within constellation boundaries
            # Handle RA wrap-around (0-24 hours)
            ra_min = const.ra_min_hours
            ra_max = const.ra_max_hours

            # Check if RA range crosses 0h (e.g., 22h to 2h)
            in_ra = ra_hours >= ra_min or ra_hours <= ra_max if ra_min > ra_max else ra_min <= ra_hours <= ra_max

            in_dec = const.dec_min_degrees <= dec_degrees <= const.dec_max_degrees

            if in_ra and in_dec:
                return const.name

    # If no boundary match (or boundaries not set), find nearest constellation center
    min_distance = float("inf")
    nearest_const = None

    for const in constellations:
        if not isinstance(const, ConstellationModel):
            continue

        # Calculate angular distance (simplified - using Euclidean distance in RA/Dec space)
        ra_diff = abs(ra_hours - const.ra_hours)
        if ra_diff > 12:  # Handle wrap-around
            ra_diff = 24 - ra_diff

        dec_diff = abs(dec_degrees - const.dec_degrees)

        # Convert RA difference to degrees (1 hour = 15 degrees)
        ra_diff_deg = ra_diff * 15

        # Calculate approximate angular distance
        # Weight RA by cos(dec) to account for coordinate system
        cos_dec = abs(dec_degrees / 90.0) if abs(dec_degrees) < 90 else 0.1
        distance = (ra_diff_deg * cos_dec) ** 2 + dec_diff**2

        if distance < min_distance:
            min_distance = distance
            nearest_const = const

    # Use nearest constellation if it's reasonably close
    # For prominent constellations, use a generous radius (~45 degrees)
    max_distance = 2025  # ~45 degrees squared

    if nearest_const and min_distance < max_distance:
        return nearest_const.name

    return None


def import_celestial_stars(
    geojson_path: Path,
    mag_limit: float = 15.0,
    verbose: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[int, int]:
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
    status_msg = "Loading existing stars for deduplication..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    existing_objects = db.get_existing_objects_set(catalog="celestial_stars")
    status_msg = f"Found {len(existing_objects):,} existing stars"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

    # Pre-load constellations for coordinate-based lookup
    status_msg = "Loading constellations for coordinate-based lookup..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    from celestron_nexstar.api.database.models import ConstellationModel, get_db_session

    def _load_constellations() -> list[ConstellationModel]:
        with get_db_session() as session:
            from sqlalchemy import select

            result = session.execute(select(ConstellationModel))
            return list(result.scalars().all())

    constellations = _load_constellations()
    status_msg = f"Loaded {len(constellations):,} constellations for coordinate lookup"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

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

    # Use progress callback if provided, otherwise use Rich Progress
    use_rich_progress = progress_callback is None
    progress_obj = None
    task = None
    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task(f"Processing celestial_stars (mag ≤ {mag_limit})...", total=total_features)
    else:
        # Emit initial progress via callback
        if progress_callback:
            progress_callback(f"Processing celestial_stars (mag ≤ {mag_limit})...", 0, total_features)

        for feature in features:
            try:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})

                # Extract coordinates
                coords = geometry.get("coordinates", [])
                if not coords or len(coords) < 2:
                    skipped += 1
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing celestial_stars...", processed, total_features)
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
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing celestial_stars...", processed, total_features)
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

                # If not found in properties, determine from coordinates
                if not constellation and constellations:
                    # Use sync wrapper since we're in a sync context
                    constellation = _find_constellation_by_coordinates_async(
                        ra_hours, dec_degrees, constellations, name
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

            # Update progress
            if use_rich_progress and task is not None:
                if progress_obj is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
            elif progress_callback:
                processed = len(all_objects) + skipped + errors
                progress_callback("Processing celestial_stars...", processed, total_features)

    # Close processing progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

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

    # Use progress callback if provided, otherwise use Rich Progress
    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task("Importing celestial_stars...", total=num_batches)
    else:
        # Emit initial import progress via callback
        if progress_callback:
            progress_callback("Importing celestial_stars...", 0, num_batches)

        for i in range(0, len(deduplicated_objects), batch_size):
            batch = deduplicated_objects[i : i + batch_size]
            try:
                batch_imported = db.insert_objects_batch(batch)
                imported += batch_imported
                # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    batch_num = (i // batch_size) + 1
                    progress_callback("Importing celestial_stars...", batch_num, num_batches)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                errors += len(batch)
                # Still advance progress even on error
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    batch_num = (i // batch_size) + 1
                    progress_callback("Importing celestial_stars...", batch_num, num_batches)

    # Close import progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

    return imported, skipped


def import_celestial_dsos(
    geojson_path: Path,
    mag_limit: float = 15.0,
    verbose: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """Import DSOs from celestial_data GeoJSON."""
    # Load DSO names mapping from dsonames.csv
    dso_names_map: dict[str, str] = {}
    cache_dir = get_cache_dir()
    dsonames_path = cache_dir / "dsonames.csv"

    if dsonames_path.exists():
        try:
            with open(dsonames_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Map catalog ID (id column) to proper name (name column)
                    catalog_id = row.get("id", "").strip()
                    proper_name = row.get("name", "").strip()
                    if catalog_id and proper_name:
                        dso_names_map[catalog_id] = proper_name
            if verbose:
                console.print(f"[dim]Loaded {len(dso_names_map):,} DSO names from dsonames.csv[/dim]")
        except Exception as e:
            if verbose:
                console.print(f"[yellow]Warning: Could not load dsonames.csv: {e}[/yellow]")
    else:
        if verbose:
            console.print("[yellow]Warning: dsonames.csv not found. DSO proper names will not be available.[/yellow]")

    # Map DSO types to our object types
    # The celestial_data GeoJSON uses abbreviated type codes:
    # Galaxy types: g, s, s0, e, i, sd (spiral, lenticular, elliptical, irregular, etc.)
    # Cluster types: oc (open cluster), gc (globular cluster)
    # Nebula types: bn (bright nebula), pn (planetary nebula), dn (dark nebula), snr (supernova remnant)
    # Other: sfr (star forming region)
    dso_type_map = {
        # Full names (for compatibility)
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
        # Abbreviated codes from celestial_data GeoJSON
        "g": CelestialObjectType.GALAXY,  # Galaxy (generic)
        "s": CelestialObjectType.GALAXY,  # Spiral galaxy
        "s0": CelestialObjectType.GALAXY,  # Lenticular galaxy
        "e": CelestialObjectType.GALAXY,  # Elliptical galaxy
        "i": CelestialObjectType.GALAXY,  # Irregular galaxy
        "sd": CelestialObjectType.GALAXY,  # S0/a galaxy
        "oc": CelestialObjectType.CLUSTER,  # Open cluster
        "gc": CelestialObjectType.CLUSTER,  # Globular cluster
        "bn": CelestialObjectType.NEBULA,  # Bright nebula
        "pn": CelestialObjectType.NEBULA,  # Planetary nebula
        "dn": CelestialObjectType.NEBULA,  # Dark nebula
        "snr": CelestialObjectType.NEBULA,  # Supernova remnant
        "sfr": CelestialObjectType.NEBULA,  # Star forming region (treat as nebula)
    }

    # Map abbreviated type codes to descriptive names for display in descriptions
    dso_type_descriptions = {
        # Galaxy types
        "g": "Galaxy",
        "s": "Spiral Galaxy",
        "s0": "Lenticular Galaxy",
        "e": "Elliptical Galaxy",
        "i": "Irregular Galaxy",
        "sd": "S0/a Galaxy",
        # Cluster types
        "oc": "Open Cluster",
        "gc": "Globular Cluster",
        # Nebula types
        "bn": "Bright Nebula",
        "pn": "Planetary Nebula",
        "dn": "Dark Nebula",
        "snr": "Supernova Remnant",
        "sfr": "Star Forming Region",
    }

    # Custom function to enhance DSO objects with proper names and descriptive types
    def enhance_dso_object(obj: dict[str, Any]) -> dict[str, Any]:
        """Enhance DSO object with proper name from dsonames.csv and descriptive type."""
        # Get the catalog ID (name field typically contains catalog ID like "NGC 40")
        catalog_id = obj.get("name", "").strip()

        # Look up proper name in the mapping
        if catalog_id in dso_names_map:
            proper_name = dso_names_map[catalog_id]
            # Set common_name to the proper name
            obj["common_name"] = proper_name
            # If the name is just a catalog ID, we could optionally update it
            # For now, we'll keep the catalog ID as name and set proper name as common_name

        # Replace abbreviated type codes in description with descriptive names
        description = obj.get("description", "")
        if description:
            # Check if description contains "Type: <abbreviation>"
            import re

            pattern = r"Type:\s*([a-z0-9]+)"
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                type_code = match.group(1).lower()
                if type_code in dso_type_descriptions:
                    # Replace the abbreviation with the descriptive name
                    descriptive_name = dso_type_descriptions[type_code]
                    obj["description"] = description.replace(f"Type: {type_code}", f"Type: {descriptive_name}")

        return obj

    # Import with name enhancement
    return import_celestial_data_geojson(
        geojson_path,
        catalog="celestial_dsos",
        mag_limit=mag_limit,
        verbose=verbose,
        object_type_map=dso_type_map,
        object_enhancer=enhance_dso_object,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )


def import_celestial_messier(
    geojson_path: Path,
    mag_limit: float = 15.0,
    verbose: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """Import Messier objects from celestial_data GeoJSON."""
    return import_celestial_data_geojson(
        geojson_path,
        catalog="messier",
        mag_limit=mag_limit,
        verbose=verbose,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )


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
        "GC/UFD": CelestialObjectType.CLUSTER,  # Globular cluster or ultra-faint dwarf (treat as cluster)
        # Dwarf galaxies
        "dSph": CelestialObjectType.GALAXY,  # Dwarf spheroidal
        "dSph pec": CelestialObjectType.GALAXY,  # Dwarf spheroidal peculiar
        "dSph pec::": CelestialObjectType.GALAXY,  # Dwarf spheroidal peculiar (variant)
        "dSph(t)": CelestialObjectType.GALAXY,  # Dwarf spheroidal transition
        "dSph/dE3": CelestialObjectType.GALAXY,  # Dwarf spheroidal/dwarf elliptical
        "dE": CelestialObjectType.GALAXY,  # Dwarf elliptical
        "dE3": CelestialObjectType.GALAXY,  # Dwarf elliptical type 3
        "dE4": CelestialObjectType.GALAXY,  # Dwarf elliptical type 4
        "dE5": CelestialObjectType.GALAXY,  # Dwarf elliptical type 5
        "dE5/p": CelestialObjectType.GALAXY,  # Dwarf elliptical type 5 peculiar
        "UFD": CelestialObjectType.GALAXY,  # Ultra-faint dwarf
        # Irregular galaxies
        "IBm": CelestialObjectType.GALAXY,  # Irregular barred Magellanic
        "IBm V-VI": CelestialObjectType.GALAXY,  # Irregular barred Magellanic type V-VI
        "IBm V-VI::": CelestialObjectType.GALAXY,  # Irregular barred Magellanic type V-VI (variant)
        "IBm V-VI pec": CelestialObjectType.GALAXY,  # Irregular barred Magellanic type V-VI peculiar
        "IAm": CelestialObjectType.GALAXY,  # Irregular Magellanic
        "IAm V-VI": CelestialObjectType.GALAXY,  # Irregular Magellanic type V-VI
        "IABm V-VI": CelestialObjectType.GALAXY,  # Irregular barred Magellanic type V-VI
        "Im": CelestialObjectType.GALAXY,  # Irregular Magellanic
        "Im V-VI": CelestialObjectType.GALAXY,  # Irregular Magellanic type V-VI
        "Im V-VI::": CelestialObjectType.GALAXY,  # Irregular Magellanic type V-VI (variant)
        "dIrr": CelestialObjectType.GALAXY,  # Dwarf irregular
        "dIrr::": CelestialObjectType.GALAXY,  # Dwarf irregular (variant)
        "dIrr/dSph": CelestialObjectType.GALAXY,  # Dwarf irregular/dwarf spheroidal
        # Spiral galaxies
        "SAb II": CelestialObjectType.GALAXY,  # Spiral unbarred type II
        "SAcd III-IV": CelestialObjectType.GALAXY,  # Spiral unbarred type III-IV
        "SABbc I-II": CelestialObjectType.GALAXY,  # Spiral barred type I-II
        "SBm V": CelestialObjectType.GALAXY,  # Spiral barred Magellanic type V
        "SBm V pec": CelestialObjectType.GALAXY,  # Spiral barred Magellanic type V peculiar
        # Compact/other galaxy types
        "cE2": CelestialObjectType.GALAXY,  # Compact elliptical type 2
        # Generic
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

    Uses constellations.min.geojson for metadata and constellations.bounds.min.geojson
    for accurate MultiPolygon boundaries for spatial queries.

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

    # Load main constellations GeoJSON file (for metadata)
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

    # Load bounds file for accurate MultiPolygon boundaries (REQUIRED)
    bounds_data: dict[str, dict[str, Any]] = {}
    bounds_path = geojson_path.parent / "constellations.bounds.min.geojson"
    if not bounds_path.exists():
        error_msg = f"Constellation bounds file not found at {bounds_path}. This file is required for accurate spatial queries. Please download it first."
        console.print(f"[red]✗[/red] {error_msg}")
        raise FileNotFoundError(error_msg)

    try:
        with open(bounds_path, encoding="utf-8") as f:
            bounds_geojson = json.load(f)
        if bounds_geojson.get("type") != "FeatureCollection":
            error_msg = f"Invalid bounds file format: expected FeatureCollection, got {bounds_geojson.get('type')}"
            console.print(f"[red]✗[/red] {error_msg}")
            raise InvalidCatalogFormatError(error_msg)

        bounds_features = bounds_geojson.get("features", [])
        # Create a mapping by constellation ID/name
        for bound_feature in bounds_features:
            props = bound_feature.get("properties", {})
            const_id = props.get("id") or props.get("name")
            if const_id:
                bounds_data[const_id] = bound_feature.get("geometry")

        if not bounds_data:
            error_msg = f"No constellation boundaries found in bounds file: {bounds_path}"
            console.print(f"[red]✗[/red] {error_msg}")
            raise InvalidCatalogFormatError(error_msg)

        console.print(f"[green]Loaded {len(bounds_data)} constellation boundaries from bounds file[/green]")
        if verbose:
            sample_ids = list(bounds_data.keys())[:5]
            console.print(f"[dim]Sample bounds IDs: {sample_ids}[/dim]")
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in bounds file: {e}"
        console.print(f"[red]✗[/red] {error_msg}")
        raise InvalidCatalogFormatError(error_msg) from e
    except Exception as e:
        error_msg = f"Error loading bounds file: {e}"
        console.print(f"[red]✗[/red] {error_msg}")
        raise RuntimeError(error_msg) from e

    # Collect all constellations first, then deduplicate once, then batch insert
    all_constellations: list[ConstellationModel] = []

    # Pre-fetch existing constellations for deduplication
    # Check both name and abbreviation since both have unique constraints
    existing_names: set[str] = set()
    existing_abbreviations: set[str] = set()
    with get_db_session() as db_session:
        result = db_session.execute(select(ConstellationModel.name, ConstellationModel.abbreviation))
        for row in result.all():
            existing_names.add(row[0])
            if row[1]:
                existing_abbreviations.add(row[1])
        console.print(f"[dim]Found {len(existing_names):,} existing constellations[/dim]")

    with get_db_session() as db_session:
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
                    properties.get("brightest_star") or properties.get("key_star")
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
                        properties.get("mythology") or properties.get("description") or properties.get("Description")
                    )

                    # Extract season
                    season = properties.get("season") or properties.get("Season")

                    # Get geometry from bounds file (REQUIRED - no fallback)
                    constellation_geometry: dict[str, Any] | None = None
                    polygon_coords_for_star_search: list[list[list[float]]] | None = None

                    # Get geometry from bounds file (required for accurate spatial queries)
                    const_id = properties.get("id") or name
                    if not const_id:
                        error_msg = f"Constellation {name} has no ID in properties. Cannot match with bounds file."
                        console.print(f"[red]✗[/red] {error_msg}")
                        errors += 1
                        progress.advance(task)
                        continue

                    if const_id not in bounds_data:
                        error_msg = f"Constellation {name} (ID: {const_id}) not found in bounds file. Available IDs: {list(bounds_data.keys())[:10]}"
                        console.print(f"[red]✗[/red] {error_msg}")
                        errors += 1
                        progress.advance(task)
                        continue

                    constellation_geometry = bounds_data[const_id]
                    geometry = constellation_geometry  # Use bounds geometry for calculations
                    if verbose:
                        geom_type = (
                            constellation_geometry.get("type", "unknown")
                            if isinstance(constellation_geometry, dict)
                            else "unknown"
                        )
                        console.print(
                            f"[dim]Using bounds geometry for {name} (ID: {const_id}, type: {geom_type})[/dim]"
                        )

                    if not constellation_geometry:
                        error_msg = f"Constellation {name} (ID: {const_id}) has no geometry in bounds file."
                        console.print(f"[red]✗[/red] {error_msg}")
                        errors += 1
                        progress.advance(task)
                        continue

                    # Calculate boundaries from geometry
                    # For Point geometry, use approximate bounds around center
                    # For Polygon/MultiPolygon, calculate actual bounds
                    geometry_type = geometry.get("type", "")
                    if geometry_type == "Point":
                        # Approximate bounds (bounds file should have MultiPolygon, but fallback if needed)
                        ra_min_hours = ra_hours - 1.0
                        ra_max_hours = ra_hours + 1.0
                        dec_min_degrees = dec_degrees - 10.0
                        dec_max_degrees = dec_degrees + 10.0
                    elif geometry_type in ("Polygon", "MultiPolygon"):
                        # Store geometry for point-in-polygon checks (use bounds geometry if available)
                        if not constellation_geometry:
                            constellation_geometry = geometry

                        # Calculate bounds from polygon coordinates
                        coords = geometry.get("coordinates", [])
                        coords_list = coords
                        if geometry_type == "Polygon":
                            # Polygon: [[[lon, lat], ...], ...] - use outer ring
                            coords_list = coords[0] if coords else []
                            # Store polygon coordinates for star search
                            if coords_list:
                                polygon_coords_for_star_search = [coords_list]
                        elif geometry_type == "MultiPolygon":
                            # MultiPolygon: [[[[lon, lat], ...], ...], ...] - flatten all polygons
                            coords_list = []
                            polygon_coords_for_star_search = []
                            for poly in coords:
                                if poly and poly[0]:
                                    outer_ring = poly[0]
                                    coords_list.extend(outer_ring)
                                    polygon_coords_for_star_search.append(outer_ring)

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

                    # Convert GeoJSON geometry to SpatiaLite geometry BLOB
                    geometry_blob: bytes | None = None
                    if constellation_geometry:
                        # We'll convert this after we have a database session
                        # Store the geometry dict for later conversion
                        pass

                    # Create constellation model (geometry will be set after batch insert)
                    # Note: brightest_star is now a foreign key (brightest_star_id), not a string field
                    # It will be set during sync operation
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
                        brightest_star_id=None,  # Will be set during sync operation
                        mythology=mythology,
                        season=season,
                        geometry=None,  # Will be set after conversion
                    )

                    # Store geometry dict for later conversion
                    constellation._temp_geometry = constellation_geometry  # type: ignore[attr-defined]

                    all_constellations.append(constellation)

                except Exception as e:
                    errors += 1
                    if verbose:
                        console.print(f"[yellow]Warning: Error processing constellation: {e}[/yellow]")

                progress.advance(task)

        # Deduplicate once after all constellations are created
        console.print(f"[dim]Deduplicating {len(all_constellations):,} constellations...[/dim]")
        seen_names: set[str] = set()
        seen_abbreviations: set[str] = set()
        deduplicated_constellations: list[ConstellationModel] = []
        for const in all_constellations:
            # Check both name and abbreviation for uniqueness
            name_conflict = const.name in seen_names or const.name in existing_names
            abbrev_conflict = const.abbreviation in seen_abbreviations or const.abbreviation in existing_abbreviations
            if not name_conflict and not abbrev_conflict:
                seen_names.add(const.name)
                seen_abbreviations.add(const.abbreviation)
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
                    # Convert geometries to SpatiaLite format for this batch before inserting
                    for const in batch:
                        if hasattr(const, "_temp_geometry") and getattr(const, "_temp_geometry", None):
                            try:
                                temp_geom = getattr(const, "_temp_geometry", None)
                                if temp_geom:
                                    geometry_blob = geojson_to_spatialite_geometry_async(temp_geom, db_session)
                                if geometry_blob:
                                    const.geometry = geometry_blob
                                    if verbose:
                                        geom_type = (
                                            temp_geom.get("type", "unknown")
                                            if isinstance(temp_geom, dict)
                                            else "unknown"
                                        )
                                        console.print(f"[dim]Set geometry for {const.name} (type: {geom_type})[/dim]")
                                else:
                                    console.print(
                                        f"[yellow]Warning: Failed to convert geometry for {const.name} - conversion returned None[/yellow]"
                                    )
                                    if verbose:
                                        geom_type = (
                                            temp_geom.get("type", "unknown")
                                            if isinstance(temp_geom, dict)
                                            else "unknown"
                                        )
                                        console.print(f"[dim]Geometry type was: {geom_type}[/dim]")
                            except Exception as e:
                                console.print(
                                    f"[yellow]Warning: Error converting geometry for {const.name}: {e}[/yellow]"
                                )
                                if verbose:
                                    import traceback

                                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                            # Clean up temp attribute
                            if hasattr(const, "_temp_geometry"):
                                delattr(const, "_temp_geometry")
                        else:
                            if verbose:
                                console.print(f"[yellow]Warning: No _temp_geometry found for {const.name}[/yellow]")

                    db_session.add_all(batch)
                    db_session.commit()
                    imported += len(batch)
                    # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                    progress.advance(task)
                except Exception as e:
                    # Log the error (always show errors, not just in verbose mode)
                    console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                    if verbose:
                        import traceback

                        console.print(f"[dim]{traceback.format_exc()}[/dim]")
                    errors += len(batch)
                    db_session.rollback()
                    # Still advance progress even on error
                    progress.advance(task)

    return imported, skipped


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

    def _import() -> tuple[int, int]:
        nonlocal imported, skipped, errors, all_asterisms

        # Pre-fetch existing asterisms for deduplication
        existing_names: set[str] = set()
        with get_db_session() as db_session:
            from sqlalchemy import select

            result = db_session.execute(select(AsterismModel.name))
            existing_names = {row[0] for row in result.all()}
            console.print(f"[dim]Found {len(existing_names):,} existing asterisms[/dim]")

        # Pre-load constellations for spatial lookup using ST_Within
        from celestron_nexstar.api.database.models import ConstellationModel

        def _load_constellations() -> list[ConstellationModel]:
            with get_db_session() as session:
                from sqlalchemy import select

                result = session.execute(select(ConstellationModel))
                return list(result.scalars().all())

        constellations = _load_constellations()
        console.print(f"[dim]Loaded {len(constellations):,} constellations for spatial lookup[/dim]")

        with get_db_session() as db_session:
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
                        # Asterisms use loc_lon/loc_lat properties for location, not geometry coordinates
                        # (geometry is MultiLineString for drawing the pattern)
                        ra_degrees = None
                        dec_degrees = None
                        if "loc_lon" in properties and "loc_lat" in properties:
                            ra_degrees = float(properties["loc_lon"])
                            dec_degrees = float(properties["loc_lat"])
                        else:
                            # Fallback: try to get from geometry if it's a Point
                            coords = geometry.get("coordinates", [])
                            if coords and len(coords) >= 2:
                                if geometry.get("type") == "Point":
                                    ra_degrees = float(coords[0])
                                    dec_degrees = float(coords[1])
                                elif geometry.get("type") == "MultiLineString" and coords:
                                    # Use first point of first line as approximate location
                                    first_line = coords[0] if isinstance(coords, list) and coords else []
                                    if first_line and len(first_line) > 0:
                                        first_point = first_line[0] if isinstance(first_line, list) else []
                                        if first_point and len(first_point) >= 2:
                                            ra_degrees = float(first_point[0])
                                            dec_degrees = float(first_point[1])

                        if ra_degrees is None or dec_degrees is None:
                            skipped += 1
                            progress.advance(task)
                            continue

                        # Convert RA from degrees to hours
                        ra_hours = CoordinateConverter.ra_degrees_to_hours(ra_degrees)

                        # Extract asterism name
                        # Asterisms use abbreviated property 'n' for name
                        name = (
                            properties.get("n")
                            or properties.get("name")
                            or properties.get("Name")
                            or properties.get("id")
                        )
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
                        # Asterisms use 'es' for Spanish name
                        alt_names = (
                            properties.get("es")
                            or properties.get("alt_names")
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

                        # Extract parent constellation from properties first (if available)
                        parent_constellation = (
                            properties.get("parent_constellation")
                            or properties.get("constellation")
                            or properties.get("Const")
                        )

                        # If not in properties, find it using ST_Within spatial query
                        # Check if asterism position is within constellation boundaries
                        if not parent_constellation:
                            parent_constellation = _find_constellation_by_coordinates_async(
                                ra_hours, dec_degrees, constellations, name
                            )

                        # Extract description
                        description = (
                            properties.get("description") or properties.get("Description") or properties.get("notes")
                        )

                        # Extract component stars from properties first (if available)
                        stars_from_props = (
                            properties.get("stars")
                            or properties.get("component_stars")
                            or properties.get("member_stars")
                        )

                        # Always try to find stars from MultiLineString geometry
                        # The MULTILINESTRING geometry represents the pattern connecting stars
                        # We'll find stars near the geometry points
                        geometry_points_for_star_search: list[tuple[float, float]] | None = None
                        geometry_type = geometry.get("type", "")
                        if geometry_type == "MULTILINESTRING":
                            # Extract all points from MULTILINESTRING coordinates
                            # MULTILINESTRING: [[[lon, lat], ...], ...] - each line is a list of points
                            all_points: list[tuple[float, float]] = []
                            geom_coords = geometry.get("coordinates", [])
                            if isinstance(geom_coords, list):
                                for line in geom_coords:
                                    if isinstance(line, list):
                                        for point in line:
                                            if isinstance(point, list) and len(point) >= 2:
                                                all_points.append((float(point[0]), float(point[1])))
                            if all_points:
                                # Store geometry points to find stars later (after we have database access)
                                geometry_points_for_star_search = all_points

                        # Extract season
                        season = properties.get("season") or properties.get("Season")

                        # Extract extended information fields
                        wikipedia_url = (
                            properties.get("wikipedia_url")
                            or properties.get("wikipedia")
                            or properties.get("url")
                            or properties.get("reference_url")
                        )
                        cultural_info = (
                            properties.get("cultural_info")
                            or properties.get("cultural")
                            or properties.get("mythology")
                            or properties.get("mythological_info")
                        )
                        guidepost_info = (
                            properties.get("guidepost_info")
                            or properties.get("guidepost")
                            or properties.get("navigation_info")
                            or properties.get("finding_info")
                        )
                        historical_notes = (
                            properties.get("historical_notes")
                            or properties.get("history")
                            or properties.get("historical")
                        )
                        shape_description = (
                            properties.get("shape_description")
                            or properties.get("shape")
                            or properties.get("appearance")
                        )

                        # Always find stars from MultiLineString geometry if available
                        # This gives us the actual stars that make up the asterism pattern
                        stars = stars_from_props  # Start with stars from properties if available
                        brightest_star = None
                        if geometry_points_for_star_search:
                            try:
                                from sqlalchemy import select

                                from celestron_nexstar.api.core.utils import angular_separation
                                from celestron_nexstar.api.database.database import get_database
                                from celestron_nexstar.api.database.models import StarModel

                                db_instance = get_database()

                                # Search for stars near each geometry point
                                # Returns tuple of (star_name, star_model) for finding brightest
                                def _find_stars_near_points(
                                    db: Any, points: list[tuple[float, float]]
                                ) -> tuple[set[str], list[StarModel]]:
                                    found_names: set[str] = set()
                                    found_models: list[StarModel] = []
                                    with db._get_session() as session:
                                        for lon_deg, lat_deg in points:
                                            # Convert lon back to RA hours
                                            point_ra_hours = CoordinateConverter.ra_degrees_to_hours(lon_deg)
                                            point_dec_degrees = lat_deg

                                            # Search for stars within 2 arcminutes of this point
                                            # (asterism lines connect stars, so stars should be very close)
                                            search_radius_deg = 2.0 / 60.0  # 2 arcminutes in degrees
                                            ra_range_hours = search_radius_deg / 15.0
                                            ra_min = (point_ra_hours - ra_range_hours) % 24.0
                                            ra_max = (point_ra_hours + ra_range_hours) % 24.0
                                            dec_min = max(-90.0, point_dec_degrees - search_radius_deg)
                                            dec_max = min(90.0, point_dec_degrees + search_radius_deg)

                                            # Query stars in bounding box
                                            if ra_min <= ra_max:
                                                stmt = (
                                                    select(StarModel)
                                                    .where(
                                                        StarModel.ra_hours.between(ra_min, ra_max),
                                                        StarModel.dec_degrees.between(dec_min, dec_max),
                                                    )
                                                    .limit(10)
                                                )
                                            else:
                                                stmt = (
                                                    select(StarModel)
                                                    .where(
                                                        (StarModel.ra_hours >= ra_min) | (StarModel.ra_hours <= ra_max),
                                                        StarModel.dec_degrees.between(dec_min, dec_max),
                                                    )
                                                    .limit(10)
                                                )

                                            result = session.execute(stmt)
                                            star_models = result.scalars().all()

                                            # Check angular separation and find closest star
                                            for star_model in star_models:
                                                separation_deg = angular_separation(
                                                    point_ra_hours,
                                                    point_dec_degrees,
                                                    star_model.ra_hours,
                                                    star_model.dec_degrees,
                                                )
                                                separation_arcmin = separation_deg * 60.0

                                                # If within 2 arcminutes, consider it part of the asterism
                                                if separation_arcmin <= 2.0:
                                                    # Prefer common name, fallback to name
                                                    # Use name even if it's a catalog identifier (better than nothing)
                                                    star_name = star_model.common_name or star_model.name
                                                    if star_name and star_name not in found_names:
                                                        found_names.add(star_name)
                                                        found_models.append(star_model)
                                                        # Only add the first star found at this point (closest match)
                                                        break

                                    return found_names, found_models

                                # Run function to find stars from geometry
                                found_star_names, found_star_models = _find_stars_near_points(
                                    db_instance, geometry_points_for_star_search
                                )

                                if found_star_names:
                                    # Use geometry-found stars (they're more accurate than properties)
                                    # Merge with stars from properties if any
                                    if stars_from_props:
                                        # Merge both sets
                                        props_stars = {s.strip() for s in stars_from_props.split(",") if s.strip()}
                                        all_star_names = found_star_names | props_stars
                                        stars = ",".join(sorted(all_star_names))
                                    else:
                                        stars = ",".join(sorted(found_star_names))

                                    # Find brightest star from the found stars
                                    # Brightest = smallest magnitude value (most negative is brightest)
                                    if found_star_models:
                                        brightest_star_model = min(
                                            found_star_models,
                                            key=lambda s: s.magnitude if s.magnitude is not None else float("inf"),
                                        )
                                        if brightest_star_model.magnitude is not None:
                                            brightest_star = (
                                                brightest_star_model.common_name or brightest_star_model.name
                                            )

                                    if verbose:
                                        console.print(
                                            f"[dim]Found {len(found_star_names)} stars from geometry for {name}"
                                            + (f", brightest: {brightest_star}" if brightest_star else "")
                                            + "[/dim]"
                                        )
                                else:
                                    # No stars found from geometry, but we might have stars from properties
                                    if verbose and not stars_from_props:
                                        console.print(f"[dim]No stars found from geometry for {name}[/dim]")
                            except Exception as e:
                                if verbose:
                                    console.print(
                                        f"[yellow]Warning: Could not find stars from geometry for {name}: {e}[/yellow]"
                                    )
                                # On error, keep stars from properties if available
                                if not stars:
                                    stars = stars_from_props

                        # Ensure stars is set (even if None/empty)
                        # Convert None to empty string for database consistency
                        stars_value = stars if stars else None
                        brightest_star_value = brightest_star if brightest_star else None

                        # Create asterism model (geometry will be set after conversion)
                        asterism = AsterismModel(
                            name=name,
                            alt_names=alt_names,
                            ra_hours=ra_hours,
                            dec_degrees=dec_degrees,
                            size_degrees=size_degrees,
                            parent_constellation=parent_constellation,
                            description=description,
                            stars=stars_value,
                            season=season,
                            wikipedia_url=wikipedia_url,
                            cultural_info=cultural_info,
                            guidepost_info=guidepost_info,
                            historical_notes=historical_notes,
                            shape_description=shape_description,
                            brightest_star=brightest_star_value,  # Brightest star found from geometry
                            geometry=None,  # Will be set after conversion
                        )

                        # Store geometry dict for later conversion
                        asterism._temp_geometry = geometry  # type: ignore[attr-defined]

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

            # Convert geometries to SpatiaLite format before batch insert
            console.print("[dim]Converting geometries to SpatiaLite format...[/dim]")
            for asterism in deduplicated_asterisms:
                if hasattr(asterism, "_temp_geometry") and asterism._temp_geometry:  # type: ignore[attr-defined]
                    geometry_blob = geojson_to_spatialite_geometry_async(asterism._temp_geometry, db_session)  # type: ignore[attr-defined]
                    if geometry_blob:
                        asterism.geometry = geometry_blob
                    # Clean up temp attribute
                    delattr(asterism, "_temp_geometry")  # type: ignore[attr-defined]

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
                        db_session.commit()
                        imported += len(batch)
                        # Advance by 1 per batch so TimeRemainingColumn can calculate properly
                        progress.advance(task)
                    except Exception as e:
                        if verbose:
                            console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
                        errors += len(batch)
                        db_session.rollback()
                        # Still advance progress even on error
                        progress.advance(task)

        return imported, skipped

    return _import()


def download_wds_catalog(output_path: Path) -> bool:
    """
    Download the Washington Double Star Catalog (WDS) from US Naval Observatory.

    Args:
        output_path: Where to save the WDS catalog file

    Returns:
        True if successful
    """
    # WDS catalog is available from US Naval Observatory
    # The main catalog file is wdsweb_sum.txt (or wdsweb_summ2.txt)
    # Try multiple possible URLs (in order of preference)
    urls = [
        "https://astro.gsu.edu/wds/Webtextfiles/wdsweb_summ2.txt",  # Georgia State University mirror (most reliable)
        "https://www.astro.gsu.edu/wds/wdsweb_sum.txt",  # Alternative GSU URL
        "https://www.usno.navy.mil/static/files/astrometry/wds/wdsweb_sum.txt",
        "https://www.usno.navy.mil/USNO/astrometry/optical-IR-prod/wds/WDS/wdsweb_sum.txt",
    ]

    # Create a request with User-Agent header to avoid 403 errors
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Create SSL context that doesn't verify certificates (some servers have invalid certs)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    for url in urls:
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Downloading WDS catalog from {url.split('/')[-2]}...", total=None)

                request = urllib.request.Request(url, headers=req_headers)
                with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
                    data = response.read()

                output_path.write_bytes(data)
                progress.update(task, completed=True)

            console.print(f"[green]✓[/green] Downloaded {len(data):,} bytes to {output_path}")
            return True

        except urllib.error.HTTPError as e:
            if e.code == 403:
                console.print(f"[yellow]⚠[/yellow] Access denied for {url}, trying next URL...")
                continue
            else:
                console.print(f"[yellow]⚠[/yellow] HTTP {e.code} for {url}, trying next URL...")
                continue
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Error with {url}: {e}, trying next URL...")
            continue

    console.print("[red]✗[/red] All download attempts failed.")
    console.print("[yellow]Please download the WDS catalog manually:[/yellow]")
    console.print("[dim]1. Visit: https://astro.gsu.edu/wds/Webtextfiles/wdsweb_summ2.txt[/dim]")
    console.print("[dim]   (or https://www.usno.navy.mil/USNO/astrometry/optical-IR-prod/wds/WDS/)[/dim]")
    console.print(f"[dim]2. Save the file as: {output_path}[/dim]")
    console.print("[dim]3. Run the import command again[/dim]")
    return False


def import_wds_catalog(
    wds_path: Path,
    mag_limit: float = 15.0,
    verbose: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """
    Import Washington Double Star Catalog (WDS) data.

    WDS format is a fixed-width text file. The catalog is available from:
    https://www.usno.navy.mil/USNO/astrometry/optical-IR-prod/wds/WDS/

    Args:
        wds_path: Path to WDS catalog text file
        mag_limit: Maximum magnitude to import (fainter objects are skipped)
        verbose: Show detailed progress
        progress_callback: Optional callback function(status, current, total) for progress updates

    Returns:
        (imported_count, skipped_count)
    """
    db = get_database()

    # Pre-fetch existing objects for deduplication
    status_msg = "Loading existing WDS objects for deduplication..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    existing_objects = db.get_existing_objects_set(catalog="wds")
    status_msg = f"Found {len(existing_objects):,} existing WDS objects"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

    # Pre-load constellations for coordinate-based lookup
    status_msg = "Loading constellations for coordinate-based lookup..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    from celestron_nexstar.api.database.models import ConstellationModel, get_db_session

    def _load_constellations() -> list[ConstellationModel]:
        with get_db_session() as session:
            from sqlalchemy import select

            result = session.execute(select(ConstellationModel))
            return list(result.scalars().all())

    constellations = _load_constellations()
    status_msg = f"Loaded {len(constellations):,} constellations for coordinate lookup"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

    imported = 0
    skipped = 0
    errors = 0

    # WDS catalog format (fixed-width columns):
    # Columns 1-10: WDS designation (e.g., "00013+1539")
    # Columns 11-18: Discoverer designation
    # Columns 19-28: RA (hours, minutes, seconds)
    # Columns 29-37: Dec (degrees, arcminutes, arcseconds)
    # Columns 38-42: First magnitude
    # Columns 43-47: Second magnitude
    # Columns 48-52: Separation (arcseconds)
    # Columns 53-56: Position angle (degrees)
    # Columns 57-61: Epoch of observation
    # Columns 62-66: Number of observations
    # And more...

    if not wds_path.exists():
        console.print(f"[red]✗[/red] File not found: {wds_path}")
        raise FileNotFoundError(f"WDS catalog not found: {wds_path}")

    # Read WDS catalog file
    all_objects: list[dict[str, Any]] = []

    # Use progress callback if provided, otherwise use Rich Progress
    use_rich_progress = progress_callback is None
    progress_obj = None
    task = None

    # First pass: count lines
    with open(wds_path, encoding="utf-8", errors="ignore") as f:
        total_lines = sum(1 for _ in f)

    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task(f"Processing WDS catalog (mag ≤ {mag_limit})...", total=total_lines)
    else:
        # Emit initial progress via callback
        if progress_callback:
            progress_callback(f"Processing WDS catalog (mag ≤ {mag_limit})...", 0, total_lines)

    with open(wds_path, encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if len(line.strip()) < 10:  # Skip very short lines
                # Update progress
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    processed = len(all_objects) + skipped + errors
                    progress_callback("Processing WDS catalog...", processed, total_lines)
                continue

            try:
                # Parse fixed-width format
                wds_designation = line[0:10].strip()
                discoverer = line[10:18].strip()

                # Skip header lines or invalid entries
                if not wds_designation or wds_designation.startswith("#") or "WDS" in wds_designation.upper():
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing WDS catalog...", processed, total_lines)
                    continue

                # Parse RA (hours, minutes, seconds)
                ra_h_str = line[18:21].strip()
                ra_m_str = line[21:24].strip()
                ra_s_str = line[24:28].strip()

                try:
                    ra_h = float(ra_h_str) if ra_h_str else 0.0
                    ra_m = float(ra_m_str) if ra_m_str else 0.0
                    ra_s = float(ra_s_str) if ra_s_str else 0.0
                    ra_hours = ra_h + (ra_m / 60.0) + (ra_s / 3600.0)
                except (ValueError, TypeError):
                    skipped += 1
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing WDS catalog...", processed, total_lines)
                    continue

                # Parse Dec (degrees, arcminutes, arcseconds)
                dec_sign = line[28:29].strip()
                dec_d_str = line[29:32].strip()
                dec_m_str = line[32:35].strip()
                dec_s_str = line[35:38].strip()

                try:
                    dec_d = float(dec_d_str) if dec_d_str else 0.0
                    dec_m = float(dec_m_str) if dec_m_str else 0.0
                    dec_s = float(dec_s_str) if dec_s_str else 0.0
                    dec_degrees = dec_d + (dec_m / 60.0) + (dec_s / 3600.0)
                    if dec_sign == "-":
                        dec_degrees = -dec_degrees

                    # Validate declination is within valid range (-90 to 90 degrees)
                    if not (-90.0 <= dec_degrees <= 90.0):
                        # Check if this might be a parsing error (e.g., arcminutes treated as degrees)
                        # If dec_d is > 90, it might be arcminutes instead
                        if abs(dec_d) > 90 and abs(dec_d) < 5400:  # 5400 arcmin = 90 degrees
                            # Try treating dec_d as arcminutes
                            dec_degrees = (dec_d / 60.0) + (dec_m / 3600.0) + (dec_s / 216000.0)
                            if dec_sign == "-":
                                dec_degrees = -dec_degrees

                        # If still invalid, skip this entry
                        if not (-90.0 <= dec_degrees <= 90.0):
                            if verbose:
                                console.print(
                                    f"[yellow]Warning: Skipping {wds_designation} - invalid declination {dec_degrees:.2f}° "
                                    f"(parsed as d={dec_d}, m={dec_m}, s={dec_s})[/yellow]"
                                )
                            skipped += 1
                            # Update progress
                            if use_rich_progress and task is not None:
                                progress_obj.advance(task)  # type: ignore[union-attr]
                            elif progress_callback:
                                processed = len(all_objects) + skipped + errors
                                progress_callback("Processing WDS catalog...", processed, total_lines)
                            continue
                except (ValueError, TypeError):
                    skipped += 1
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing WDS catalog...", processed, total_lines)
                    continue

                # Parse magnitudes (primary and secondary)
                mag1_str = line[37:42].strip()
                mag2_str = line[42:47].strip()

                primary_magnitude = None
                secondary_magnitude = None
                magnitude = None  # Combined magnitude (brighter of the two)

                try:
                    if mag1_str:
                        primary_magnitude = float(mag1_str)
                        if mag2_str:
                            secondary_magnitude = float(mag2_str)
                            # Use brighter magnitude for filtering
                            magnitude = min(primary_magnitude, secondary_magnitude)
                        else:
                            magnitude = primary_magnitude
                except (ValueError, TypeError):
                    pass

                # Filter by magnitude (use brighter of the two)
                if magnitude is not None and magnitude > mag_limit:
                    skipped += 1
                    # Update progress
                    if use_rich_progress and task is not None and progress_obj is not None:
                        progress_obj.advance(task)  # type: ignore[union-attr]
                    elif progress_callback:
                        processed = len(all_objects) + skipped + errors
                        progress_callback("Processing WDS catalog...", processed, total_lines)
                    continue

                # Parse separation and position angle
                sep_str = line[47:52].strip()
                pa_str = line[52:56].strip()

                separation = None
                position_angle = None
                try:
                    if sep_str:
                        separation = float(sep_str)
                    if pa_str:
                        position_angle = float(pa_str)
                except (ValueError, TypeError):
                    pass

                # Build name (use WDS designation as primary name)
                name = wds_designation
                common_name = discoverer if discoverer else None

                # Determine constellation from coordinates using spatial query
                constellation = _find_constellation_by_coordinates_async(ra_hours, dec_degrees, constellations, name)

                # Build description
                description_parts = []
                if discoverer:
                    description_parts.append(f"Discoverer: {discoverer}")
                if separation is not None:
                    description_parts.append(f'Separation: {separation:.2f}"')
                if position_angle is not None:
                    description_parts.append(f"PA: {position_angle:.1f}°")
                if mag1_str and mag2_str:
                    description_parts.append(f"Magnitudes: {mag1_str}, {mag2_str}")
                description = "; ".join(description_parts) if description_parts else "Double star from WDS"

                # Add to collection
                # Note: insert_objects_batch will automatically create POINT geometry from RA/Dec
                all_objects.append(
                    {
                        "name": name,
                        "catalog": "wds",
                        "ra_hours": ra_hours,
                        "dec_degrees": dec_degrees,
                        "object_type": CelestialObjectType.DOUBLE_STAR,
                        "magnitude": magnitude,  # Brighter of the two for filtering/sorting
                        "primary_magnitude": primary_magnitude,
                        "secondary_magnitude": secondary_magnitude,
                        "common_name": common_name,
                        "catalog_number": None,  # WDS doesn't use numeric catalog numbers
                        "size_arcmin": separation / 60.0 if separation else None,  # Convert arcsec to arcmin
                        "description": description,
                        "constellation": constellation,
                    }
                )

            except Exception as e:
                errors += 1
                if verbose:
                    console.print(f"[yellow]Warning: Error processing line {line_num}: {e}[/yellow]")

                # Update progress
                if use_rich_progress and task is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
                elif progress_callback:
                    processed = len(all_objects) + skipped + errors
                    progress_callback("Processing WDS catalog...", processed, total_lines)

    # Deduplicate
    status_msg = f"Deduplicating {len(all_objects):,} objects..."
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)
    seen_keys: set[tuple[str, str | None, int | None]] = set()
    deduplicated_objects: list[dict[str, Any]] = []
    for obj in all_objects:
        key = (obj["name"], obj.get("common_name"), obj.get("catalog_number"))
        if key not in seen_keys and key not in existing_objects:
            name_key = (obj["name"], None, None)
            if name_key not in existing_objects:
                seen_keys.add(key)
                deduplicated_objects.append(obj)
            else:
                skipped += 1
        else:
            skipped += 1

    status_msg = f"After deduplication: {len(deduplicated_objects):,} unique objects to import"
    console.print(f"[dim]{status_msg}[/dim]")
    if status_callback:
        status_callback(status_msg)

    # Close processing progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

    # Batch insert
    batch_size = 1000
    num_batches = (len(deduplicated_objects) + batch_size - 1) // batch_size

    if use_rich_progress:
        progress_obj = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        progress_obj.__enter__()
        task = progress_obj.add_task("Importing WDS catalog...", total=num_batches)
    else:
        # Emit initial import progress via callback
        if progress_callback:
            progress_callback("Importing WDS catalog...", 0, num_batches)

    for i in range(0, len(deduplicated_objects), batch_size):
        batch = deduplicated_objects[i : i + batch_size]
        try:
            batch_imported = db.insert_objects_batch(batch)
            imported += batch_imported
            # Update progress
            if use_rich_progress and task is not None:
                if progress_obj is not None:
                    progress_obj.advance(task)  # type: ignore[union-attr]
            elif progress_callback:
                batch_num = (i // batch_size) + 1
                progress_callback("Importing WDS catalog...", batch_num, num_batches)
        except Exception as e:
            if verbose:
                console.print(f"[yellow]Warning: Error importing batch: {e}[/yellow]")
            errors += len(batch)
            # Update progress even on error
            if use_rich_progress and task is not None:
                progress_obj.advance(task)  # type: ignore[union-attr]
            elif progress_callback:
                batch_num = (i // batch_size) + 1
                progress_callback("Importing WDS catalog...", batch_num, num_batches)

    # Close import progress if using Rich
    if use_rich_progress and progress_obj is not None:
        progress_obj.__exit__(None, None, None)

    if errors > 0:
        console.print(f"[yellow]⚠[/yellow] {errors} errors occurred during import")

    return imported, skipped


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
    "wds": DataSource(
        name="Washington Double Star Catalog (WDS)",
        description="Washington Double Star Catalog from US Naval Observatory",
        url="https://www.usno.navy.mil/USNO/astrometry/optical-IR-prod/wds/WDS/",
        objects_available=150000,  # Approximate - WDS contains over 150,000 double stars
        license="Public Domain",
        attribution="US Naval Observatory",
        importer=lambda path, mag, verbose: import_wds_catalog(path, mag, verbose),
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

            def _count() -> int:
                with get_db_session() as session:
                    result = session.scalar(select(func.count(AsterismModel.id)))
                    return result or 0

            imported = _count()
        elif source_id == "celestial_constellations":
            # Count from constellations table, not objects table

            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import ConstellationModel, get_db_session

            def _count() -> int:
                with get_db_session() as session:
                    result = session.scalar(select(func.count(ConstellationModel.id)))
                    return result or 0

            imported = _count()
        elif source_id == "celestial_local_group":
            imported = stats.objects_by_catalog.get("local_group", 0)
        elif source_id == "wds":
            imported = stats.objects_by_catalog.get("wds", 0)
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

            stats = db.get_stats()
            console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Import failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    # Handle WDS catalog
    if source_id == "wds":
        cache_dir = get_cache_dir()
        cache_path = cache_dir / "wdsweb_summ2.txt"  # Use summ2 version (more complete)
        if not cache_path.exists() or force_download:
            if force_download and cache_path.exists():
                console.print("[dim]Force re-download: removing cached WDS catalog...[/dim]")
                cache_path.unlink()
            console.print("Downloading WDS catalog from US Naval Observatory...")
            if not download_wds_catalog(cache_path):
                return False

        # Import WDS data
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

        stats = db.get_stats()
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True

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

        # Download additional files for certain sources
        if source_id.startswith("celestial_stars"):
            # Also download starnames.csv for proper star names
            starnames_filename = "starnames.csv"
            starnames_path = cache_dir / starnames_filename
            if not starnames_path.exists() or force_download:
                if force_download and starnames_path.exists():
                    starnames_path.unlink()
                console.print("Downloading starnames.csv from celestial_data repository...")
                download_celestial_data(starnames_filename, starnames_path)

        if source_id.startswith("celestial_dsos"):
            # Also download dsonames.csv for proper DSO names
            dsonames_filename = "dsonames.csv"
            dsonames_path = cache_dir / dsonames_filename
            if not dsonames_path.exists() or force_download:
                if force_download and dsonames_path.exists():
                    dsonames_path.unlink()
                console.print("Downloading dsonames.csv from celestial_data repository...")
                download_celestial_data(dsonames_filename, dsonames_path)

        if source_id == "celestial_constellations":
            # Also download bounds file for accurate MultiPolygon boundaries
            bounds_filename = "constellations.bounds.min.geojson"
            bounds_path = cache_dir / bounds_filename
            if not bounds_path.exists() or force_download:
                if force_download and bounds_path.exists():
                    bounds_path.unlink()
                console.print("Downloading constellation bounds from celestial_data repository...")
                download_celestial_data(bounds_filename, bounds_path)

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
        stats = db.get_stats()
        console.print(f"\n[bold]Database now contains {stats.total_objects:,} objects[/bold]")

        return True

    # If we get here, the source wasn't handled
    console.print(f"[red]✗[/red] No downloader for {source_id}")
    return False
