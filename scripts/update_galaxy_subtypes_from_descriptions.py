#!/usr/bin/env python
"""
Update galaxy object_subtype based on type abbreviations in descriptions.

This script parses "Type: XXX" from galaxy descriptions and maps the abbreviations
to proper galaxy subtypes (e.g., "dSph" -> "Dwarf Spheroidal").

Usage:
    python scripts/update_galaxy_subtypes_from_descriptions.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add parent directory to path so we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from celestron_nexstar.api.database.database import get_database

console = Console()

# Mapping of type abbreviations to full galaxy subtype names
TYPE_ABBREVIATIONS = {
    # Dwarf galaxies
    "dSph": "Dwarf Spheroidal",
    "dSph pec": "Dwarf Spheroidal",  # peculiar variant
    "dSph(t)": "Dwarf Spheroidal",   # transition type
    "dE": "Dwarf Elliptical",
    "dIrr": "Dwarf Irregular",
    "dIrr/dSph": "Dwarf Irregular",  # transition - classify as irregular
    "UFD": "Ultra-Faint Dwarf",

    # Irregular galaxies (Magellanic types)
    "IAm": "Irregular Galaxy",
    "IAm V-VI": "Irregular Galaxy",
    "IBm": "Irregular Galaxy",
    "IBm V-VI": "Irregular Galaxy",
    "IBm V-VI pec": "Irregular Galaxy",
    "Im": "Irregular Galaxy",
    "Im V-VI": "Irregular Galaxy",
    "Irr": "Irregular Galaxy",

    # Spiral galaxies (Hubble classification)
    "S": "Spiral Galaxy",
    "Sa": "Spiral Galaxy",
    "Sb": "Spiral Galaxy",
    "Sc": "Spiral Galaxy",
    "Sd": "Spiral Galaxy",

    # Barred spirals
    "SB": "Barred Spiral Galaxy",
    "SBa": "Barred Spiral Galaxy",
    "SBb": "Barred Spiral Galaxy",
    "SBc": "Barred Spiral Galaxy",
    "SBd": "Barred Spiral Galaxy",
    "SBm": "Barred Spiral Galaxy",
    "SBm V": "Barred Spiral Galaxy",
    "SBm V pec": "Barred Spiral Galaxy",

    # Intermediate barred spirals
    "SAB": "Spiral Galaxy",  # intermediate - classify as spiral
    "SABa": "Spiral Galaxy",
    "SABb": "Spiral Galaxy",
    "SABbc": "Spiral Galaxy",
    "SABbc I-II": "Spiral Galaxy",
    "SABc": "Spiral Galaxy",
    "SABd": "Spiral Galaxy",

    # Lenticular
    "S0": "Lenticular Galaxy",
    "S0/a": "S0/a Galaxy",

    # Elliptical
    "E": "Elliptical Galaxy",
    "E0": "Elliptical Galaxy",
    "E1": "Elliptical Galaxy",
    "E2": "Elliptical Galaxy",
    "E3": "Elliptical Galaxy",
    "E4": "Elliptical Galaxy",
    "E5": "Elliptical Galaxy",
    "E6": "Elliptical Galaxy",
    "E7": "Elliptical Galaxy",

    # Generic
    "Gal": "Galaxy",
    "gal": "Galaxy",
}


def extract_type_from_description(description: str) -> str | None:
    """
    Extract the galaxy type abbreviation from a description.

    Expects format like "Type: dSph" or "Type: SABbc I-II"

    Returns:
        The type abbreviation, or None if not found
    """
    if not description or "Type:" not in description:
        return None

    # Extract the type (everything between "Type: " and newline or end)
    match = re.search(r"Type:\s*([^\n]+)", description)
    if match:
        return match.group(1).strip()

    return None


def get_object_type_mapping(session) -> dict[str, int]:
    """Get a mapping of object type names to IDs."""
    result = session.execute(
        text("SELECT id, name FROM object_types")
    ).fetchall()

    mapping = {}
    for row in result:
        type_id, name = row
        mapping[name] = type_id

    return mapping


def update_galaxy_subtypes() -> None:
    """Update galaxy subtypes based on description type abbreviations."""
    console.print("[bold blue]Updating galaxy subtypes from descriptions...[/bold blue]")

    db = get_database()

    with db._get_session() as session:
        # Get object type mapping
        console.print("[dim]Loading object type mappings...[/dim]")
        type_mapping = get_object_type_mapping(session)
        console.print(f"[dim]Loaded {len(type_mapping)} object type mappings[/dim]")

        # Get all galaxies with descriptions containing "Type:" but no object_subtype
        galaxies = session.execute(
            text("""
                SELECT id, name, description, object_subtype, object_subtype_id
                FROM galaxies
                WHERE description LIKE 'Type:%'
            """)
        ).fetchall()

        console.print(f"[dim]Found {len(galaxies)} galaxies with Type: in description[/dim]\n")

        # Track statistics
        updated = 0
        already_set = 0
        unknown_types = {}

        # Create a table to show what will be updated
        table = Table(title="Galaxy Subtype Updates")
        table.add_column("Name", style="cyan")
        table.add_column("Type Abbrev", style="yellow")
        table.add_column("New Subtype", style="green")
        table.add_column("Status", style="magenta")

        for galaxy in galaxies:
            galaxy_id, name, description, current_subtype, current_subtype_id = galaxy

            # Extract type from description
            type_abbrev = extract_type_from_description(description)
            if not type_abbrev:
                continue

            # Check if already has a subtype
            if current_subtype or current_subtype_id:
                already_set += 1
                table.add_row(name, type_abbrev, current_subtype or f"ID:{current_subtype_id}", "Already Set")
                continue

            # Map abbreviation to full type name
            full_type_name = TYPE_ABBREVIATIONS.get(type_abbrev)

            if not full_type_name:
                # Track unknown types for reporting
                unknown_types[type_abbrev] = unknown_types.get(type_abbrev, 0) + 1
                table.add_row(name, type_abbrev, "???", "[red]Unknown Type[/red]")
                continue

            # Get object type ID
            type_id = type_mapping.get(full_type_name)

            if not type_id:
                console.print(f"[yellow]Warning: Type '{full_type_name}' not found in object_types table[/yellow]")
                table.add_row(name, type_abbrev, full_type_name, "[red]Type Not Found[/red]")
                continue

            # Update the galaxy
            session.execute(
                text("""
                    UPDATE galaxies
                    SET object_subtype = :subtype,
                        object_subtype_id = :type_id
                    WHERE id = :galaxy_id
                """),
                {
                    "subtype": full_type_name,
                    "type_id": type_id,
                    "galaxy_id": galaxy_id
                }
            )

            updated += 1
            table.add_row(name, type_abbrev, full_type_name, "[green]Updated[/green]")

        # Show the table
        console.print(table)

        # Commit changes
        session.commit()

    # Print summary
    console.print()
    console.print("[bold green]Update complete![/bold green]")
    console.print(f"  Galaxies updated:     {updated}")
    console.print(f"  Already had subtype:  {already_set}")

    if unknown_types:
        console.print()
        console.print("[bold yellow]Unknown type abbreviations found:[/bold yellow]")
        for abbrev, count in sorted(unknown_types.items()):
            console.print(f"  '{abbrev}': {count} galaxies")


def main() -> None:
    """Main entry point."""
    try:
        update_galaxy_subtypes()
    except Exception as e:
        console.print(f"[red]Error during update: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()