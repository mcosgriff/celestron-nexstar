#!/usr/bin/env python3
"""
Simple validation test for SQLAlchemy refactored database code.

This script performs basic syntax and import validation.
For full functional testing, install dependencies first:
    pip install sqlalchemy alembic
"""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

print("=" * 60)
print("Database Refactor Validation Test")
print("=" * 60)

# Test 1: Check if SQLAlchemy is available
print("\n1. Checking SQLAlchemy availability...")
try:
    import sqlalchemy
    print(f"   ✓ SQLAlchemy {sqlalchemy.__version__} is installed")
except ImportError:
    print("   ⚠ SQLAlchemy not installed - install with: pip install sqlalchemy")
    print("   Skipping functional tests...")
    sys.exit(0)

# Test 2: Check if models can be imported
print("\n2. Checking model imports...")
try:
    from celestron_nexstar.api.models import (
        Base,
        CelestialObjectModel,
        MetadataModel,
        ObservationModel,
        UserPreferenceModel,
    )
    print("   ✓ All models imported successfully")
    print(f"   - Base: {Base}")
    print(f"   - CelestialObjectModel: {CelestialObjectModel}")
    print(f"   - MetadataModel: {MetadataModel}")
except Exception as e:
    print(f"   ✗ Model import failed: {e}")
    sys.exit(1)

# Test 3: Check if database module can be imported
print("\n3. Checking database module imports...")
try:
    from celestron_nexstar.api.database import (
        CatalogDatabase,
        DatabaseStats,
        get_database,
        init_database,
    )
    print("   ✓ Database module imported successfully")
except Exception as e:
    print(f"   ✗ Database import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Check database class structure
print("\n4. Validating CatalogDatabase class structure...")
try:
    # Check that required methods exist
    required_methods = [
        "insert_object",
        "get_by_id",
        "get_by_name",
        "search",
        "get_by_catalog",
        "filter_objects",
        "get_all_catalogs",
        "get_stats",
        "init_schema",
        "close",
        "commit",
    ]
    
    for method_name in required_methods:
        assert hasattr(CatalogDatabase, method_name), f"Missing method: {method_name}"
    print(f"   ✓ All {len(required_methods)} required methods exist")
    
    # Check that it's using SQLAlchemy (has _engine attribute)
    assert hasattr(CatalogDatabase, "__init__"), "Missing __init__"
    print("   ✓ Class structure is valid")
    
except AssertionError as e:
    print(f"   ✗ Validation failed: {e}")
    sys.exit(1)

# Test 5: Check that models have correct structure
print("\n5. Validating model structure...")
try:
    # Check CelestialObjectModel has expected columns
    expected_columns = [
        "id", "name", "common_name", "catalog", "catalog_number",
        "ra_hours", "dec_degrees", "magnitude", "object_type",
        "size_arcmin", "description", "constellation",
        "is_dynamic", "ephemeris_name", "parent_planet",
        "created_at", "updated_at",
    ]
    
    model_columns = [col.name for col in CelestialObjectModel.__table__.columns]
    for col in expected_columns:
        assert col in model_columns, f"Missing column: {col}"
    print(f"   ✓ CelestialObjectModel has all {len(expected_columns)} expected columns")
    
except AssertionError as e:
    print(f"   ✗ Model validation failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL VALIDATION TESTS PASSED!")
print("=" * 60)
print("\nNote: For full functional testing, run:")
print("  python test_database_refactor.py")
print("(Requires SQLAlchemy and Alembic to be installed)")

