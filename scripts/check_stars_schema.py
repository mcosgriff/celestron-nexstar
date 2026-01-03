#!/usr/bin/env python3
"""Check stars table schema."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from celestron_nexstar.api.database.database import get_database
from sqlalchemy import text

def main():
    db = get_database()
    print(f"Database path: {db.db_path}")
    print()
    
    try:
        with db.get_session() as session:
            # Get SQLite version
            version_result = session.execute(text("SELECT sqlite_version()"))
            sqlite_version = version_result.scalar()
            print(f"SQLite version: {sqlite_version}")
            print()
            
            # Check if DROP COLUMN is supported (SQLite 3.35.0+)
            major, minor, patch = map(int, sqlite_version.split('.'))
            supports_drop_column = (major, minor, patch) >= (3, 35, 0)
            print(f"Supports DROP COLUMN: {supports_drop_column}")
            print()
            
            # Get table schema
            result = session.execute(text("PRAGMA table_info(stars)"))
            rows = result.fetchall()
            print("Columns in stars table:")
            print(f"{'Column Name':<30} {'Type':<20} {'Nullable':<10}")
            print("-" * 60)
            for row in rows:
                col_name = row[1]
                col_type = row[2]
                nullable = "Yes" if row[3] == 0 else "No"
                print(f"{col_name:<30} {col_type:<20} {nullable:<10}")
            print()
            
            column_names = [row[1] for row in rows]
            print("Summary:")
            print(f"  Has 'constellation' column: {('constellation' in column_names)}")
            print(f"  Has 'asterism' column: {('asterism' in column_names)}")
            print(f"  Has 'constellation_id' column: {('constellation_id' in column_names)}")
            print(f"  Has 'asterism_id' column: {('asterism_id' in column_names)}")
            
            if 'constellation' in column_names or 'asterism' in column_names:
                print()
                print("⚠️  Warning: Old string columns still exist!")
                if not supports_drop_column:
                    print("   SQLite version doesn't support DROP COLUMN.")
                    print("   The columns will remain but should be ignored by the application.")
                else:
                    print("   Migration may have failed. You may need to manually drop them.")
                    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())


