#!/usr/bin/env python
"""
Migrate object_subtype string values to object_subtype_id foreign keys.

This script finds all objects with object_subtype values (abbreviations or full names)
and updates them to use the proper object_subtype_id foreign key reference.

Usage:
    python scripts/migrate_object_subtypes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path so we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from sqlalchemy import text

from celestron_nexstar.api.database.database import get_database

console = Console()

# Tables that have object_subtype and object_subtype_id columns
TABLES_TO_MIGRATE = [
    "stars",
    "clusters",
    "nebulae",
    "galaxies",
    "double_stars",
    "moons",
    "planets",
]


def get_object_type_mapping(session) -> dict[str, int]:
    """Get a mapping of object type names to IDs."""
    result = session.execute(
        text("SELECT id, name FROM object_types")
    ).fetchall()

    mapping = {}
    for row in result:
        type_id, name = row
        # Store both the name and lowercase version for case-insensitive matching
        mapping[name] = type_id
        mapping[name.lower()] = type_id

    return mapping


def migrate_table(session, table_name: str, type_mapping: dict[str, int]) -> tuple[int, int]:
    """
    Migrate object_subtype strings to object_subtype_id for a single table.

    Returns:
        Tuple of (migrated_count, skipped_count)
    """
    console.print(f"\n[bold]Processing table: {table_name}[/bold]")

    # Get all rows with non-null object_subtype
    rows = session.execute(
        text(f"""
            SELECT id, object_subtype, object_subtype_id
            FROM {table_name}
            WHERE object_subtype IS NOT NULL
        """)
    ).fetchall()

    console.print(f"[dim]Found {len(rows)} rows with object_subtype values[/dim]")

    migrated = 0
    skipped = 0

    for row in rows:
        obj_id, subtype_str, existing_id = row

        # Skip if already has an object_subtype_id
        if existing_id is not None:
            skipped += 1
            continue

        # Try to find matching object type ID
        subtype_lower = subtype_str.lower().strip()

        # Try exact match first
        type_id = type_mapping.get(subtype_str)

        # Try lowercase match
        if type_id is None:
            type_id = type_mapping.get(subtype_lower)

        if type_id is not None:
            # Update the row with the object_subtype_id
            session.execute(
                text(f"""
                    UPDATE {table_name}
                    SET object_subtype_id = :type_id
                    WHERE id = :obj_id
                """),
                {"type_id": type_id, "obj_id": obj_id}
            )
            migrated += 1

            if migrated % 100 == 0:
                console.print(f"[dim]  Migrated {migrated} rows...[/dim]")
        else:
            console.print(f"[yellow]Warning: No matching object type for '{subtype_str}'[/yellow]")

    console.print(f"[green]Migrated {migrated} rows, skipped {skipped} rows[/green]")

    return migrated, skipped


def migrate_all_tables() -> None:
    """Migrate object subtypes in all relevant tables."""
    console.print("[bold blue]Migrating object subtypes to foreign keys...[/bold blue]")

    db = get_database()

    total_migrated = 0
    total_skipped = 0

    with db.get_session() as session:
        # Get object type mapping
        console.print("[dim]Loading object type mappings...[/dim]")
        type_mapping = get_object_type_mapping(session)
        console.print(f"[dim]Loaded {len(type_mapping)} object type mappings[/dim]")

        # Migrate each table
        for table_name in TABLES_TO_MIGRATE:
            try:
                migrated, skipped = migrate_table(session, table_name, type_mapping)
                total_migrated += migrated
                total_skipped += skipped
            except Exception as e:
                console.print(f"[red]Error migrating {table_name}: {e}[/red]")
                continue

        # Commit all changes
        session.commit()

    # Print summary
    console.print()
    console.print("[bold green]Migration complete![/bold green]")
    console.print(f"  Total migrated: {total_migrated}")
    console.print(f"  Total skipped:  {total_skipped}")


def main() -> None:
    """Main entry point."""
    try:
        migrate_all_tables()
    except Exception as e:
        console.print(f"[red]Error during migration: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()