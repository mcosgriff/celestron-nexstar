#!/usr/bin/env python3
"""
Fix Alembic migration state for ephemeris_files table.

This script stamps the database to the correct version if space_events
already exists, then applies the new ephemeris_files migration.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from celestron_nexstar.api.database import get_database
import sqlite3


def main():
    db = get_database()
    print(f"Database path: {db.db_path}")

    conn = sqlite3.connect(str(db.db_path))
    cursor = conn.cursor()

    # Check if space_events exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='space_events'")
    space_events_exists = cursor.fetchone() is not None

    # Check current Alembic version
    try:
        cursor.execute("SELECT version_num FROM alembic_version")
        current_version = cursor.fetchone()
        if current_version:
            print(f"Current Alembic version: {current_version[0]}")
        else:
            print("Alembic version table exists but is empty")
    except sqlite3.OperationalError:
        print("Alembic version table does not exist")
        current_version = None

    conn.close()

    if space_events_exists and (not current_version or current_version[0] != "030d966a662d"):
        print("\n⚠️  Database has space_events table but Alembic version is out of sync")
        print("Run this command to fix it:")
        print("  uv run alembic stamp 030d966a662d")
        print("\nThen run:")
        print("  uv run alembic upgrade head")
        return 1

    print("\n✅ Database state looks correct")
    print("You can now run: uv run alembic upgrade head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
