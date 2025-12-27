#!/usr/bin/env python
"""
Seed the object_types table with comprehensive astronomical object type definitions.

This script loads object types from data/object_types_seed.yaml and populates
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

import yaml
from rich.console import Console
from sqlalchemy import text

from celestron_nexstar.api.database.database import get_database

console = Console()


def load_seed_data() -> list[dict]:
    """Load object types seed data from YAML file."""
    seed_file = Path(__file__).parent.parent / "data" / "object_types_seed.yaml"

    if not seed_file.exists():
        console.print(f"[red]Error: Seed file not found at {seed_file}[/red]")
        sys.exit(1)

    with open(seed_file) as f:
        data = yaml.safe_load(f)

    return data.get("object_types", [])


def seed_object_types() -> None:
    """Seed the object_types table with comprehensive type definitions."""
    console.print("[bold blue]Seeding object types...[/bold blue]")

    # Load seed data
    object_types = load_seed_data()
    console.print(f"[dim]Loaded {len(object_types)} object type definitions[/dim]")

    # Get database
    db = get_database()

    # Track stats
    inserted = 0
    skipped = 0
    updated = 0

    with db._get_session() as session:
        for obj_type in object_types:
            name = obj_type["name"]
            category = obj_type["category"]
            description = obj_type.get("description", "")

            # Check if this object type already exists
            result = session.execute(
                text("SELECT id, description FROM object_types WHERE name = :name"),
                {"name": name}
            ).fetchone()

            if result:
                # Update description if it's better/longer than existing
                existing_id, existing_desc = result
                if description and (not existing_desc or len(description) > len(existing_desc or "")):
                    session.execute(
                        text("UPDATE object_types SET description = :desc, category = :cat WHERE id = :id"),
                        {"desc": description, "cat": category, "id": existing_id}
                    )
                    updated += 1
                    console.print(f"[yellow]Updated:[/yellow] {name}")
                else:
                    skipped += 1
                    console.print(f"[dim]Skipped:[/dim] {name} (already exists)")
            else:
                # Insert new object type
                session.execute(
                    text("""
                        INSERT INTO object_types (name, category, description)
                        VALUES (:name, :category, :description)
                    """),
                    {"name": name, "category": category, "description": description}
                )
                inserted += 1
                console.print(f"[green]Inserted:[/green] {name}")

        session.commit()

    # Print summary
    console.print()
    console.print("[bold green]Object types seeding complete![/bold green]")
    console.print(f"  Inserted: {inserted}")
    console.print(f"  Updated:  {updated}")
    console.print(f"  Skipped:  {skipped}")
    console.print(f"  Total:    {inserted + updated + skipped}")


def main() -> None:
    """Main entry point."""
    try:
        seed_object_types()
    except Exception as e:
        console.print(f"[red]Error seeding object types: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()