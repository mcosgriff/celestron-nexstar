#!/usr/bin/env python3
"""
Create missing database tables for ISS passes, constellations, asterisms, and meteor showers.

This script creates the tables directly using SQLAlchemy if they don't exist.
Run this if migrations aren't available or haven't been run yet.
"""

import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import inspect

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.database.models import AsterismModel, Base, ConstellationModel, ISSPassModel, MeteorShowerModel


def create_missing_tables() -> None:
    """Create missing tables if they don't exist."""
    db = get_database()
    engine = db._engine

    # Get list of existing tables
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # Tables we need
    required_tables = {
        "iss_passes": ISSPassModel,
        "constellations": ConstellationModel,
        "asterisms": AsterismModel,
        "meteor_showers": MeteorShowerModel,
    }

    # Create missing tables
    tables_to_create = []
    for table_name, _model in required_tables.items():
        if table_name not in existing_tables:
            tables_to_create.append(table_name)
            print(f"Creating table: {table_name}")
        else:
            print(f"Table {table_name} already exists")

    if tables_to_create:
        # Create all missing tables at once (checkfirst=True will skip if they exist)
        Base.metadata.create_all(
            engine,
            tables=[required_tables[name].__table__ for name in tables_to_create],
            checkfirst=True,
        )
        print(f"\n✓ Successfully created {len(tables_to_create)} table(s)")
    else:
        print("\n✓ All required tables already exist")

    # Verify all tables exist now
    inspector = inspect(engine)
    final_tables = set(inspector.get_table_names())
    missing = [name for name in required_tables if name not in final_tables]
    if missing:
        print(f"\n⚠ Warning: Some tables are still missing: {missing}")
        print("You may need to run Alembic migrations manually:")
        print("  uv run alembic upgrade head")
    else:
        print("\n✓ All required tables verified")


if __name__ == "__main__":
    try:
        create_missing_tables()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
