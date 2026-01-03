#!/usr/bin/env python
"""
Seed the object_types table with comprehensive astronomical object type definitions.

This script loads object types from the database seeder and populates
the database. It handles both abbreviations and full names, creating mappings
so that objects with abbreviated subtypes (like "oc", "gc", "pn") display
properly in the UI.

Usage:
    python scripts/seed_object_types.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path so we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.database.database_seeder import seed_object_types

console = Console()


def main() -> None:
    """Main entry point."""
    try:
        console.print("[bold blue]Seeding object types...[/bold blue]")

        # Get database
        db = get_database()

        # Seed object types using the database seeder
        with db.get_session() as session:
            count = seed_object_types(session, force=True)

        # Print summary
        console.print()
        console.print("[bold green]Object types seeding complete![/bold green]")
        console.print(f"  Total records added/updated: {count}")
    except Exception as e:
        console.print(f"[red]Error seeding object types: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()