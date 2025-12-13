#!/usr/bin/env python3
"""Verify and add foreign key columns to stars table if missing."""

import sys

def main():
    try:
        from celestron_nexstar.api.database.database import get_database
        import sqlalchemy as sa
        from sqlalchemy import text
    except ImportError as e:
        print(f"ERROR: Failed to import required modules: {e}")
        return 1
    
    try:
        db = get_database()
        print(f"Database path: {db.db_path}")
        
        with db._get_session() as session:
            inspector = sa.inspect(session.bind)
            
            if "stars" not in inspector.get_table_names():
                print("ERROR: stars table does not exist!")
                return 1
            
            # Get current columns
            columns = {col["name"]: col for col in inspector.get_columns("stars")}
            print("\nCurrent columns in stars table:")
            for col_name in sorted(columns.keys()):
                print(f"  - {col_name}")
            print()
            
            # Check if foreign key columns exist
            has_constellation_id = "constellation_id" in columns
            has_asterism_id = "asterism_id" in columns
            
            print(f"Has constellation_id: {has_constellation_id}")
            print(f"Has asterism_id: {has_asterism_id}")
            print()
            
            if not has_constellation_id or not has_asterism_id:
                print("Adding missing columns...")
                
                # Enable foreign keys
                session.execute(text("PRAGMA foreign_keys=ON"))
                
                if not has_constellation_id:
                    print("  Adding constellation_id...")
                    try:
                        session.execute(text("ALTER TABLE stars ADD COLUMN constellation_id INTEGER"))
                        session.execute(text("CREATE INDEX IF NOT EXISTS ix_stars_constellation_id ON stars(constellation_id)"))
                        print("    ✓ constellation_id added")
                    except Exception as e:
                        print(f"    ✗ Failed to add constellation_id: {e}")
                
                if not has_asterism_id:
                    print("  Adding asterism_id...")
                    try:
                        session.execute(text("ALTER TABLE stars ADD COLUMN asterism_id INTEGER"))
                        session.execute(text("CREATE INDEX IF NOT EXISTS ix_stars_asterism_id ON stars(asterism_id)"))
                        print("    ✓ asterism_id added")
                    except Exception as e:
                        print(f"    ✗ Failed to add asterism_id: {e}")
                
                session.commit()
                print("\n✓ Columns added successfully!")
            else:
                print("✓ All foreign key columns already exist!")
        
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

