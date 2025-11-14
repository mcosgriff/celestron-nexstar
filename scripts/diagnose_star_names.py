#!/usr/bin/env python3
"""Diagnostic script to check star name mappings and search functionality."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import inspect, text

from celestron_nexstar.api.database import get_database
from celestron_nexstar.api.models import CelestialObjectModel, StarNameMappingModel


def main():
    db = get_database()
    engine = db._engine

    print("=" * 60)
    print("STAR NAME MAPPINGS DIAGNOSTIC")
    print("=" * 60)

    # Check if star_name_mappings table exists
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n1. Database tables: {sorted(tables)}")
    has_mappings_table = "star_name_mappings" in tables
    print(f"   star_name_mappings table exists: {has_mappings_table}")

    if not has_mappings_table:
        print("\n❌ ERROR: star_name_mappings table does not exist!")
        print("   Run: nexstar data setup --force")
        return

    # Check star_name_mappings data
    print("\n2. Star name mappings data:")
    async def _check_mappings_data():
        async with db._AsyncSession() as session:
            count_result = await session.execute(text("SELECT COUNT(*) FROM star_name_mappings"))
            count = count_result.scalar() or 0
            print(f"   Total mappings: {count}")

            if count == 0:
                print("   ❌ ERROR: star_name_mappings table is empty!")
                print("   Run: nexstar data setup --force")
                return

            # Check for Capella (HR 1708)
            result = await session.execute(
                text("SELECT hr_number, common_name, bayer_designation FROM star_name_mappings WHERE hr_number = 1708")
            )
            row = result.first()
            if row:
                print(f"   ✓ HR 1708 (Capella): common_name='{row[1]}', bayer='{row[2]}'")
            else:
                print("   ❌ ERROR: HR 1708 (Capella) not found in mappings!")

            # Check for Polaris (HR 424)
            result = await session.execute(
                text("SELECT hr_number, common_name, bayer_designation FROM star_name_mappings WHERE hr_number = 424")
            )
            row = result.first()
            if row:
                print(f"   ✓ HR 424 (Polaris): common_name='{row[1]}', bayer='{row[2]}'")
            else:
                print("   ⚠ HR 424 (Polaris) not found in mappings")

            # Sample mappings
            result = await session.execute(
                text("SELECT hr_number, common_name FROM star_name_mappings ORDER BY hr_number LIMIT 5")
            )
            rows = result.fetchall()
            print(f"\n   Sample mappings:")
            for r in rows:
                print(f"     HR {r[0]}: {r[1]}")

    import asyncio

    asyncio.run(_check_mappings_data())

    # Check Yale BSC objects
    print("\n3. Yale BSC objects:")
    async def _check_yale_bsc():
        async with db._AsyncSession() as session:
            # Check HR 1708 object
            result = await session.execute(
                text("SELECT name, common_name, catalog FROM objects WHERE name = 'HR 1708'")
            )
            row = result.first()
            if row:
                print(f"   HR 1708 object: name='{row[0]}', common_name='{row[1]}', catalog='{row[2]}'")
                if not row[1] or row[1].strip() == "":
                    print("   ❌ ERROR: HR 1708 object exists but common_name is empty!")
                    print("   Run: nexstar data update-star-names")
            else:
                print("   ❌ ERROR: HR 1708 object not found in database!")
                print("   Run: nexstar data import yale_bsc")

            # Check how many Yale BSC objects have common_name
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM objects WHERE catalog = 'yale_bsc' AND common_name IS NOT NULL AND common_name != ''"
                )
            )
            with_names = result.scalar() or 0
            result = await session.execute(text("SELECT COUNT(*) FROM objects WHERE catalog = 'yale_bsc'"))
            total = result.scalar() or 0
            print(f"\n   Yale BSC objects with common_name: {with_names}/{total}")
            if with_names == 0 and total > 0:
                print("   ❌ ERROR: No Yale BSC objects have common_name set!")
                print("   Run: nexstar data update-star-names")

    asyncio.run(_check_yale_bsc())

    # Test search functions
    print("\n4. Testing search functions:")
    print("   Testing db.search('Capella'):")
    import asyncio

    results = asyncio.run(db.search("Capella", limit=10))
    print(f"   Found {len(results)} results")
    for obj in results[:5]:
        print(f"     - {obj.name} (common_name: {obj.common_name})")

    print("\n   Testing db.get_by_name('Capella'):")
    obj = asyncio.run(db.get_by_name("Capella"))
    if obj:
        print(f"   ✓ Found: {obj.name} (common_name: {obj.common_name})")
    else:
        print("   ❌ Not found")

    # Test FTS5 directly
    print("\n5. Testing FTS5 search:")
    async def _test_fts():
        async with db._AsyncSession() as session:
            result = await session.execute(
                text("""
                    SELECT objects.id, objects.name, objects.common_name
                    FROM objects
                    JOIN objects_fts ON objects.id = objects_fts.rowid
                    WHERE objects_fts MATCH 'Capella'
                    LIMIT 5
                """)
            )
            rows = result.fetchall()
            print(f"   FTS5 search for 'Capella': {len(rows)} results")
            if len(rows) == 0:
                print("   ❌ ERROR: FTS5 search found nothing!")
                print("   Run: nexstar data rebuild-fts")
            else:
                for r in rows:
                    print(f"     - ID {r[0]}: name={r[1]}, common_name={r[2]}")

    asyncio.run(_test_fts())

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
