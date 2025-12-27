#!/usr/bin/env python3
"""Test script to manually trigger a celestial data import."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from celestron_nexstar.cli.data_import import import_celestial_stars, get_cache_dir

def test_stars_import():
    """Test importing stars."""
    cache_dir = get_cache_dir()
    stars_path = cache_dir / "stars.14.min.geojson"

    print(f"Cache dir: {cache_dir}")
    print(f"Stars file: {stars_path}")
    print(f"Stars file exists: {stars_path.exists()}")

    if not stars_path.exists():
        print("ERROR: Stars file not found!")
        return

    print("\nStarting stars import...")
    try:
        imported, skipped = import_celestial_stars(
            stars_path,
            mag_limit=14.0,
            verbose=True,
        )
        print(f"\n✓ Import complete!")
        print(f"  Imported: {imported}")
        print(f"  Skipped: {skipped}")
    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_stars_import()