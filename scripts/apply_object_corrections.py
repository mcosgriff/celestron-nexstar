#!/usr/bin/env python
"""
Apply manual corrections to objects with missing or incorrect data.

This script loads corrections from src/celestron_nexstar/data/seed/object_corrections.json
and applies them to the database, fixing known data quality issues.

Usage:
    python scripts/apply_object_corrections.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path so we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from rich.console import Console
from sqlalchemy import text

from celestron_nexstar.api.database.database import get_database

console = Console()


def load_corrections() -> list[dict]:
    """Load corrections from JSON file."""
    corrections_file = Path(__file__).parent.parent / "src" / "celestron_nexstar" / "data" / "seed" / "object_corrections.json"

    if not corrections_file.exists():
        console.print(f"[red]Error: Corrections file not found at {corrections_file}[/red]")
        sys.exit(1)

    with open(corrections_file) as f:
        data = json.load(f)

    return data


def get_object_type_id(session, type_name: str) -> int | None:
    """Get the ID for an object type by name."""
    result = session.execute(
        text("SELECT id FROM object_types WHERE LOWER(name) = LOWER(:name)"),
        {"name": type_name}
    ).fetchone()

    return result[0] if result else None


def apply_correction(session, correction: dict) -> bool:
    """
    Apply a single correction to an object.

    Returns:
        True if correction was applied, False if object not found or error
    """
    name = correction["name"]
    catalog = correction.get("catalog")
    subtype = correction.get("object_subtype")
    description = correction.get("description")

    # Find the object
    # Try galaxies first (most corrections are for galaxies)
    query = "SELECT id, object_subtype_id FROM galaxies WHERE name = :name"
    params = {"name": name}

    if catalog:
        query += " AND catalog = :catalog"
        params["catalog"] = catalog

    result = session.execute(text(query), params).fetchone()

    if not result:
        console.print(f"[yellow]Object not found: {name}[/yellow]")
        return False

    obj_id, existing_subtype_id = result

    # Get the object type ID for the subtype
    if subtype:
        subtype_id = get_object_type_id(session, subtype)

        if not subtype_id:
            console.print(f"[yellow]Object type not found: {subtype}[/yellow]")
            return False

        # Update the object
        updates = []
        params = {"id": obj_id}

        if not existing_subtype_id:  # Only update if not already set
            updates.append("object_subtype = :subtype")
            params["subtype"] = subtype

            updates.append("object_subtype_id = :subtype_id")
            params["subtype_id"] = subtype_id

        if description:
            updates.append("description = :description")
            params["description"] = description

        if updates:
            update_query = f"UPDATE galaxies SET {', '.join(updates)} WHERE id = :id"
            session.execute(text(update_query), params)
            console.print(f"[green]✓[/green] Updated: {name}")
            return True
        else:
            console.print(f"[dim]Skipped (already correct): {name}[/dim]")
            return False

    return False


def apply_all_corrections() -> None:
    """Apply all corrections from the corrections file."""
    console.print("[bold blue]Applying object corrections...[/bold blue]")

    # Load corrections
    corrections = load_corrections()
    console.print(f"[dim]Loaded {len(corrections)} corrections[/dim]")

    db = get_database()

    applied = 0
    skipped = 0
    errors = 0

    with db._get_session() as session:
        for correction in corrections:
            try:
                if apply_correction(session, correction):
                    applied += 1
                else:
                    skipped += 1
            except Exception as e:
                console.print(f"[red]Error applying correction for {correction.get('name', 'unknown')}: {e}[/red]")
                errors += 1

        session.commit()

    # Print summary
    console.print()
    console.print("[bold green]Corrections complete![/bold green]")
    console.print(f"  Applied: {applied}")
    console.print(f"  Skipped: {skipped}")
    console.print(f"  Errors:  {errors}")


def main() -> None:
    """Main entry point."""
    try:
        apply_all_corrections()
    except Exception as e:
        console.print(f"[red]Error applying corrections: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()