#!/usr/bin/env python3
"""
Migrate YAML Catalog to SQLite Database

Reads the existing catalogs.yaml file and migrates all objects
to the new SQLite database format.

Usage:
    python scripts/migrate_catalog_to_sqlite.py

Options:
    --yaml PATH     Path to catalogs.yaml (default: auto-detect)
    --output PATH   Output database path (default: src/.../catalogs.db)
    --verbose       Show detailed progress
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from celestron_nexstar.api.database import CatalogDatabase
from celestron_nexstar.api.enums import CelestialObjectType


# Add src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def find_yaml_catalog() -> Path:
    """Find the catalogs.yaml file."""
    yaml_path = project_root / "src" / "celestron_nexstar" / "cli" / "data" / "catalogs.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(f"Could not find catalogs.yaml at {yaml_path}")

    return yaml_path


def parse_catalog_number(name: str, catalog: str) -> int | None:
    """
    Extract numeric catalog number from name.

    Examples:
        M31 → 31
        NGC 224 → 224
        IC 1101 → 1101
    """
    # Remove catalog prefix and common variations
    prefixes = ["M", "NGC", "IC", "C"]  # Messier, NGC, IC, Caldwell

    name_upper = name.upper().strip()

    for prefix in prefixes:
        if name_upper.startswith(prefix):
            # Extract numeric part
            num_str = name_upper[len(prefix) :].strip()
            try:
                return int(num_str)
            except ValueError:
                # Handle cases like "NGC 224A"
                # Extract leading digits only
                digits = ""
                for char in num_str:
                    if char.isdigit():
                        digits += char
                    else:
                        break
                if digits:
                    return int(digits)

    return None


def migrate_yaml_to_db(yaml_path: Path, db_path: Path, verbose: bool = False) -> None:
    """
    Migrate YAML catalog to SQLite database.

    Args:
        yaml_path: Path to catalogs.yaml
        db_path: Path to output database
        verbose: Show detailed progress
    """
    print(f"Migrating {yaml_path} → {db_path}")

    # Load YAML
    with open(yaml_path) as f:
        catalogs_data = yaml.safe_load(f)

    # Initialize database
    db = CatalogDatabase(db_path)
    db.init_schema()

    # Set metadata
    db.conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('version', '1.0.0')")
    db.conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)",
        (datetime.now(UTC).isoformat(),),
    )
    db.conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('source', 'YAML migration')",
    )

    # Migrate each catalog
    total_objects = 0

    for catalog_name, objects in catalogs_data.items():
        if verbose:
            print(f"\n[{catalog_name}] Migrating {len(objects)} objects...")

        for obj in objects:
            # Extract fields
            name = obj["name"]
            common_name = obj.get("common_name")
            ra_hours = obj["ra_hours"]
            dec_degrees = obj["dec_degrees"]
            magnitude = obj.get("magnitude")
            object_type_str = obj["type"]
            description = obj.get("description")

            # Map object type
            try:
                object_type = CelestialObjectType(object_type_str)
            except ValueError:
                print(f"Warning: Unknown object type '{object_type_str}' for {name}, using 'star'")
                object_type = CelestialObjectType.STAR

            # Determine if dynamic
            is_dynamic = object_type in (CelestialObjectType.PLANET, CelestialObjectType.MOON)

            # Extract parent planet for moons
            parent_planet = obj.get("parent")  # Some moons have this field

            # Parse catalog number
            catalog_number = parse_catalog_number(name, catalog_name)

            # Determine constellation (not in current YAML, but field exists)
            constellation = None  # TODO: Add constellation lookup

            # Insert into database
            object_id = db.insert_object(
                name=name,
                catalog=catalog_name,
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                object_type=object_type,
                magnitude=magnitude,
                common_name=common_name,
                catalog_number=catalog_number,
                description=description,
                constellation=constellation,
                is_dynamic=is_dynamic,
                ephemeris_name=name if is_dynamic else None,
                parent_planet=parent_planet,
            )

            if verbose:
                print(f"  {object_id:4d}: {name:20s} | {object_type.value:12s} | mag={magnitude}")

            total_objects += 1

    # Commit all changes
    db.commit()

    # Show statistics
    print("\n✓ Migration complete!")
    print(f"  Total objects: {total_objects}")

    stats = db.get_stats()
    print("\nDatabase statistics:")
    print(f"  Total objects: {stats.total_objects}")
    print(f"  Dynamic objects: {stats.dynamic_objects}")
    print(f"  Magnitude range: {stats.magnitude_range[0]:.1f} to {stats.magnitude_range[1]:.1f}")
    print("\nObjects by catalog:")
    for catalog, count in sorted(stats.objects_by_catalog.items()):
        print(f"  {catalog:20s}: {count:4d}")
    print("\nObjects by type:")
    for obj_type, count in sorted(stats.objects_by_type.items()):
        print(f"  {obj_type:20s}: {count:4d}")

    # Test search
    print("\n✓ Testing FTS5 search...")
    test_queries = ["andromeda", "orion", "jupiter"]
    for query in test_queries:
        results = db.search(query, limit=5)
        print(f"  '{query}': {len(results)} results")
        if results and verbose:
            for obj in results[:3]:
                print(f"    - {obj.name} ({obj.common_name or 'no common name'})")

    db.close()

    # Show database file size
    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"\nDatabase size: {size_mb:.2f} MB")
    print(f"Database location: {db_path}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate YAML catalog to SQLite")
    parser.add_argument("--yaml", type=Path, help="Path to catalogs.yaml")
    parser.add_argument("--output", type=Path, help="Output database path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")

    args = parser.parse_args()

    # Find YAML file
    yaml_path = args.yaml if args.yaml else find_yaml_catalog()

    # Determine output path
    db_path = args.output or yaml_path.parent / "catalogs.db"

    # Ensure output directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Run migration
    try:
        migrate_yaml_to_db(yaml_path, db_path, verbose=args.verbose)
        print("\n✓ Success!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
