#!/usr/bin/env python3
"""
Test script for SQLAlchemy refactored database code.

This script verifies that all database operations work correctly
after the migration from raw SQLite to SQLAlchemy ORM.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

# Import directly - package init may have dependencies but we'll handle errors
try:
    from celestron_nexstar.api.database import CatalogDatabase, init_database
    from celestron_nexstar.api.enums import CelestialObjectType
except ImportError as e:
    print(f"Import error: {e}")
    print("Trying direct module import...")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "database",
        project_root / "src" / "celestron_nexstar" / "api" / "database.py"
    )
    database_module = importlib.util.module_from_spec(spec)
    sys.modules["database"] = database_module
    spec.loader.exec_module(database_module)

    spec = importlib.util.spec_from_file_location(
        "enums",
        project_root / "src" / "celestron_nexstar" / "api" / "enums.py"
    )
    enums_module = importlib.util.module_from_spec(spec)
    sys.modules["enums"] = enums_module
    spec.loader.exec_module(enums_module)

    CatalogDatabase = database_module.CatalogDatabase
    init_database = database_module.init_database
    CelestialObjectType = enums_module.CelestialObjectType


def test_database_operations():
    """Test all database operations."""
    print("=" * 60)
    print("Testing SQLAlchemy Refactored Database")
    print("=" * 60)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        print(f"\n1. Creating test database at {db_path}")
        db = init_database(db_path)
        print("   ✓ Database initialized")

        print("\n2. Testing insert_object()")
        obj_id = db.insert_object(
            name="M31",
            catalog="messier",
            ra_hours=0.7113,
            dec_degrees=41.2692,
            object_type=CelestialObjectType.GALAXY,
            magnitude=3.4,
            common_name="Andromeda Galaxy",
            catalog_number=31,
            description="The Andromeda Galaxy, also known as Messier 31",
        )
        print(f"   ✓ Inserted object with ID: {obj_id}")
        assert obj_id == 1, "Expected ID to be 1"

        # Insert another object
        obj_id2 = db.insert_object(
            name="M42",
            catalog="messier",
            ra_hours=1.4703,
            dec_degrees=-5.3733,
            object_type=CelestialObjectType.NEBULA,
            magnitude=4.0,
            common_name="Orion Nebula",
            catalog_number=42,
            description="The Orion Nebula is a diffuse nebula",
        )
        print(f"   ✓ Inserted second object with ID: {obj_id2}")

        print("\n3. Testing get_by_id()")
        obj = db.get_by_id(1)
        assert obj is not None, "Object should exist"
        assert obj.name == "M31", f"Expected name 'M31', got '{obj.name}'"
        assert obj.common_name == "Andromeda Galaxy", "Common name mismatch"
        assert obj.magnitude == 3.4, "Magnitude mismatch"
        print("   ✓ get_by_id() works correctly")

        print("\n4. Testing get_by_name()")
        obj = db.get_by_name("M31")
        assert obj is not None, "Object should exist"
        assert obj.name == "M31", "Name mismatch"
        print("   ✓ get_by_name() works correctly")

        # Test case-insensitive
        obj = db.get_by_name("m31")
        assert obj is not None, "Case-insensitive search should work"
        print("   ✓ Case-insensitive search works")

        print("\n5. Testing get_by_catalog()")
        messier_objects = db.get_by_catalog("messier")
        assert len(messier_objects) == 2, f"Expected 2 objects, got {len(messier_objects)}"
        print(f"   ✓ Found {len(messier_objects)} objects in messier catalog")

        print("\n6. Testing filter_objects()")
        # Filter by type
        galaxies = db.filter_objects(object_type=CelestialObjectType.GALAXY)
        assert len(galaxies) == 1, f"Expected 1 galaxy, got {len(galaxies)}"
        assert galaxies[0].name == "M31", "Wrong galaxy returned"
        print("   ✓ Filter by object_type works")

        # Filter by magnitude
        bright_objects = db.filter_objects(max_magnitude=4.0)
        assert len(bright_objects) == 2, f"Expected 2 bright objects, got {len(bright_objects)}"
        print("   ✓ Filter by magnitude works")

        # Filter by catalog
        messier_filtered = db.filter_objects(catalog="messier")
        assert len(messier_filtered) == 2, "Filter by catalog failed"
        print("   ✓ Filter by catalog works")

        print("\n7. Testing search() - FTS5")
        # Search for "andromeda"
        results = db.search("andromeda", limit=10)
        assert len(results) > 0, "Search should return results"
        assert any(obj.name == "M31" for obj in results), "M31 should be in search results"
        print(f"   ✓ FTS5 search found {len(results)} results for 'andromeda'")

        # Search for "orion"
        results = db.search("orion", limit=10)
        assert len(results) > 0, "Search should return results"
        assert any(obj.name == "M42" for obj in results), "M42 should be in search results"
        print(f"   ✓ FTS5 search found {len(results)} results for 'orion'")

        print("\n8. Testing get_all_catalogs()")
        catalogs = db.get_all_catalogs()
        assert "messier" in catalogs, "messier catalog should exist"
        print(f"   ✓ Found catalogs: {catalogs}")

        print("\n9. Testing get_stats()")
        stats = db.get_stats()
        assert stats.total_objects == 2, f"Expected 2 objects, got {stats.total_objects}"
        assert "messier" in stats.objects_by_catalog, "messier should be in stats"
        assert stats.objects_by_catalog["messier"] == 2, "Should have 2 messier objects"
        assert "galaxy" in stats.objects_by_type, "galaxy should be in stats"
        assert "nebula" in stats.objects_by_type, "nebula should be in stats"
        print(f"   ✓ Stats: {stats.total_objects} objects")
        print(f"     - By catalog: {stats.objects_by_catalog}")
        print(f"     - By type: {stats.objects_by_type}")
        print(f"     - Magnitude range: {stats.magnitude_range}")

        print("\n10. Testing context manager")
        with CatalogDatabase(db_path) as db2:
            obj = db2.get_by_id(1)
            assert obj is not None, "Context manager should work"
        print("   ✓ Context manager works correctly")

        print("\n11. Testing commit() (backwards compatibility)")
        db.commit()  # Should not raise an error
        print("   ✓ commit() method exists and works (no-op)")

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        db.close()
        if db_path.exists():
            db_path.unlink()
            print(f"\n✓ Cleaned up test database")


if __name__ == "__main__":
    success = test_database_operations()
    sys.exit(0 if success else 1)

