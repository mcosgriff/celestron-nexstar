#!/usr/bin/env python
"""
Migrate variable_type string values to variable_type_id foreign keys.

This script finds all variable stars with variable_type values (abbreviations)
and updates them to use the proper variable_type_id foreign key reference.

Usage:
    python scripts/migrate_variable_star_types.py
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


def get_variable_type_mapping(session) -> dict[str, int]:
    """Get a mapping of variable star type names to IDs from object_types table."""
    result = session.execute(
        text("SELECT id, name FROM object_types WHERE category = 'variable_star_type'")
    ).fetchall()

    mapping = {}
    for row in result:
        type_id, name = row
        # Store both the name and lowercase version for case-insensitive matching
        mapping[name] = type_id
        mapping[name.lower()] = type_id

    return mapping


def migrate_variable_stars(session, type_mapping: dict[str, int]) -> tuple[int, int]:
    """
    Migrate variable_type strings to variable_type_id foreign keys.

    Returns:
        Tuple of (migrated_count, skipped_count)
    """
    console.print("\n[bold]Processing variable_stars table[/bold]")

    # Get all variable stars with non-null variable_type
    rows = session.execute(
        text("""
            SELECT id, variable_type, variable_type_id
            FROM variable_stars
            WHERE variable_type IS NOT NULL
        """)
    ).fetchall()

    console.print(f"[dim]Found {len(rows)} variable stars with type values[/dim]")

    migrated = 0
    skipped = 0

    for row in rows:
        var_id, type_str, existing_id = row

        # Skip if already has a variable_type_id
        if existing_id is not None:
            skipped += 1
            continue

        # Try to find matching variable type ID
        type_lower = type_str.lower().strip()

        # Try exact match first
        type_id = type_mapping.get(type_str)

        # Try lowercase match
        if type_id is None:
            type_id = type_mapping.get(type_lower)

        if type_id is not None:
            # Update the row with the variable_type_id
            session.execute(
                text("""
                    UPDATE variable_stars
                    SET variable_type_id = :type_id
                    WHERE id = :var_id
                """),
                {"type_id": type_id, "var_id": var_id}
            )
            migrated += 1

            if migrated % 10 == 0:
                console.print(f"[dim]  Migrated {migrated} variable stars...[/dim]")
        else:
            console.print(f"[yellow]Warning: No matching variable star type for '{type_str}'[/yellow]")

    console.print(f"[green]Migrated {migrated} variable stars, skipped {skipped}[/green]")

    return migrated, skipped


def main() -> None:
    """Main entry point."""
    try:
        console.print("[bold blue]Migrating variable star types to foreign keys...[/bold blue]")

        db = get_database()
        total_migrated = 0
        total_skipped = 0

        with db._get_session() as session:
            # Get variable type mapping
            console.print("[dim]Loading variable star type mappings...[/dim]")
            type_mapping = get_variable_type_mapping(session)
            console.print(f"[dim]Loaded {len(type_mapping)} variable star type mappings[/dim]")

            # Migrate variable stars
            try:
                migrated, skipped = migrate_variable_stars(session, type_mapping)
                total_migrated += migrated
                total_skipped += skipped
            except Exception as e:
                console.print(f"[red]Error migrating variable stars: {e}[/red]")
                import traceback
                traceback.print_exc()
                raise

            # Commit all changes
            session.commit()

        # Print summary
        console.print()
        console.print("[bold green]Migration complete![/bold green]")
        console.print(f"  Total migrated: {total_migrated}")
        console.print(f"  Total skipped:  {total_skipped}")

    except Exception as e:
        console.print(f"[red]Error during migration: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()