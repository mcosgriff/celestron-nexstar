#!/usr/bin/env python3
"""
Import OpenNGC Catalog into Database

Downloads and imports NGC/IC catalog from OpenNGC project into
the SQLite database. Filters objects by visibility (magnitude <= 15)
for NexStar 6SE telescope.

Usage:
    python scripts/import_openngc.py [--download] [--verbose]

Options:
    --download      Download fresh data from GitHub
    --csv PATH      Use existing CSV file
    --mag-limit N   Maximum magnitude (default: 15.0)
    --verbose       Show detailed progress
"""

import argparse
import sys
from pathlib import Path

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.core.enums import CelestialObjectType


# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def download_openngc(output_path: Path) -> None:
    """Download OpenNGC catalog from GitHub."""
    import urllib.request

    url = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv"

    print("Downloading OpenNGC catalog from GitHub...")
    print(f"  URL: {url}")

    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()

        output_path.write_bytes(data)
        print(f"  Downloaded: {len(data):,} bytes")
        print(f"  Saved to: {output_path}")

    except Exception as e:
        print(f"Error downloading: {e}")
        raise


def parse_ra_dec(ra_str: str, dec_str: str) -> tuple[float, float] | None:
    """
    Parse RA/Dec from OpenNGC format.

    RA format: HH:MM:SS.ss
    Dec format: ±DD:MM:SS.s

    Returns:
        (ra_hours, dec_degrees) or None if invalid
    """
    try:
        # Parse RA (HH:MM:SS.ss → hours)
        ra_parts = ra_str.split(":")
        ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60 + float(ra_parts[2]) / 3600

        # Parse Dec (±DD:MM:SS.s → degrees)
        dec_sign = 1 if not dec_str.startswith("-") else -1
        dec_str_abs = dec_str.lstrip("+-")
        dec_parts = dec_str_abs.split(":")
        dec_degrees = dec_sign * (float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600)

        return ra_hours, dec_degrees

    except (ValueError, IndexError):
        return None


def map_object_type(type_str: str) -> CelestialObjectType:
    """
    Map OpenNGC type codes to CelestialObjectType.

    OpenNGC types:
        * or ** = Star
        *Ass = Association of stars
        OCl = Open cluster
        GCl = Globular cluster
        Cl+N = Cluster with nebulosity
        G = Galaxy
        GPair = Galaxy pair
        GTrpl = Galaxy triplet
        GGroup = Group of galaxies
        PN = Planetary nebula
        HII = HII ionized region
        DrkN = Dark nebula
        EmN = Emission nebula
        Neb = Generic nebula
        RfN = Reflection nebula
        SNR = Supernova remnant
        Nova = Nova star
        NonEx = Nonexistent object
        Dup = Duplicate record
        Other = Other classification
    """
    type_map = {
        "*": CelestialObjectType.STAR,
        "**": CelestialObjectType.DOUBLE_STAR,
        "*Ass": CelestialObjectType.CLUSTER,
        "OCl": CelestialObjectType.CLUSTER,
        "GCl": CelestialObjectType.CLUSTER,
        "Cl+N": CelestialObjectType.CLUSTER,
        "G": CelestialObjectType.GALAXY,
        "GPair": CelestialObjectType.GALAXY,
        "GTrpl": CelestialObjectType.GALAXY,
        "GGroup": CelestialObjectType.GALAXY,
        "PN": CelestialObjectType.NEBULA,
        "HII": CelestialObjectType.NEBULA,
        "DrkN": CelestialObjectType.NEBULA,
        "EmN": CelestialObjectType.NEBULA,
        "Neb": CelestialObjectType.NEBULA,
        "RfN": CelestialObjectType.NEBULA,
        "SNR": CelestialObjectType.NEBULA,
        "Nova": CelestialObjectType.STAR,
    }

    return type_map.get(type_str, CelestialObjectType.NEBULA)  # Default to nebula


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
    import csv

    print("Importing OpenNGC catalog...")
    print(f"  CSV: {csv_path}")
    print(f"  Magnitude limit: {mag_limit}")

    db = get_database()

    # OpenNGC CSV format (semicolon-separated)
    # Name;Type;RA;Dec;Const;MajAx;MinAx;PosAng;B-Mag;V-Mag;...

    imported = 0
    skipped = 0
    errors = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

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
                continue

            # Parse coordinates
            coords = parse_ra_dec(ra_str, dec_str)
            if coords is None:
                if verbose:
                    print(f"  Warning: Invalid coordinates for {name}, skipping")
                errors += 1
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
                continue

            # Map object type
            obj_type = map_object_type(obj_type_str)

            # Extract catalog and number
            # NGC 224 → catalog=ngc, number=224
            # IC 1101 → catalog=ic, number=1101
            # Handle suffixes like "IC 0080 NED01"
            if name.startswith("NGC"):
                catalog = "ngc"
                num_str = name.replace("NGC", "").strip().split()[0]  # Take first part only
                try:
                    catalog_number = int(num_str)
                except ValueError:
                    catalog_number = None
            elif name.startswith("IC"):
                catalog = "ic"
                num_str = name.replace("IC", "").strip().split()[0]  # Take first part only
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

                if verbose and imported % 500 == 0:
                    print(f"  Imported {imported:,} objects...")

            except Exception as e:
                if verbose:
                    print(f"  Error importing {name}: {e}")
                errors += 1

    # Commit all changes
    db.commit()

    print("\n✓ Import complete!")
    print(f"  Imported: {imported:,}")
    print(f"  Skipped: {skipped:,} (too faint or invalid)")
    print(f"  Errors: {errors:,}")

    return imported, skipped


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Import OpenNGC catalog")
    parser.add_argument("--download", action="store_true", help="Download fresh data from GitHub")
    parser.add_argument("--csv", type=Path, help="Use existing CSV file")
    parser.add_argument("--mag-limit", type=float, default=15.0, help="Maximum magnitude (default: 15.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")

    args = parser.parse_args()

    # Determine CSV path
    if args.csv:
        csv_path = args.csv
    elif args.download:
        csv_path = Path("/tmp/NGC.csv")
        download_openngc(csv_path)
    else:
        # Check if /tmp/NGC.csv exists
        csv_path = Path("/tmp/NGC.csv")
        if not csv_path.exists():
            print("No CSV file found. Use --download to fetch from GitHub or --csv to specify path.")
            sys.exit(1)

    # Run import
    try:
        _imported, _skipped = import_openngc(csv_path, args.mag_limit, args.verbose)

        # Show updated statistics
        db = get_database()
        stats = db.get_stats()

        print("\nUpdated database statistics:")
        print(f"  Total objects: {stats.total_objects:,}")
        print(f"  Magnitude range: {stats.magnitude_range[0]:.1f} to {stats.magnitude_range[1]:.1f}")
        print("\nObjects by catalog:")
        for catalog, count in sorted(stats.objects_by_catalog.items()):
            print(f"  {catalog:20s}: {count:,}")

        print("\n✓ Success!")
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
