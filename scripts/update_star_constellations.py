#!/usr/bin/env python3
"""
Update constellation data for stars in the database.

This script assigns constellation names to stars based on:
1. Known mappings for well-known bright stars
2. Coordinate-based lookup using constellation boundaries
3. Nearest constellation center for stars without clear boundary match

Run this after importing stars to populate the constellation field.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from celestron_nexstar.api.database import get_database
from celestron_nexstar.api.enums import CelestialObjectType
from celestron_nexstar.api.models import CelestialObjectModel, ConstellationModel

console = Console()
logger = logging.getLogger(__name__)

# Known star-to-constellation mappings for well-known bright stars
# Format: (star_name_pattern, constellation_name)
# Pattern can be exact name or partial match
KNOWN_STAR_CONSTELLATIONS = {
    # Brightest stars
    "Sirius": "Canis Major",
    "Canopus": "Carina",
    "Arcturus": "Boötes",
    "Vega": "Lyra",
    "Capella": "Auriga",
    "Rigel": "Orion",
    "Procyon": "Canis Minor",
    "Betelgeuse": "Orion",
    "Achernar": "Eridanus",
    "Hadar": "Centaurus",
    "Altair": "Aquila",
    "Aldebaran": "Taurus",
    "Spica": "Virgo",
    "Antares": "Scorpius",
    "Pollux": "Gemini",
    "Fomalhaut": "Piscis Austrinus",
    "Deneb": "Cygnus",
    "Mimosa": "Crux",
    "Regulus": "Leo",
    "Adhara": "Canis Major",
    "Castor": "Gemini",
    "Bellatrix": "Orion",
    "Elnath": "Taurus",
    "Miaplacidus": "Carina",
    "Alnilam": "Orion",
    "Alnair": "Grus",
    "Alioth": "Ursa Major",
    "Mirphak": "Perseus",
    "Dubhe": "Ursa Major",
    "Wezen": "Canis Major",
    "Sargas": "Scorpius",
    "Kaus Australis": "Sagittarius",
    "Avior": "Carina",
    "Alkaid": "Ursa Major",
    "Menkalinan": "Auriga",
    "Atria": "Triangulum Australe",
    "Alhena": "Gemini",
    "Peacock": "Pavo",
    "Alsephina": "Vela",
    "Mirzam": "Canis Major",
    "Alphard": "Hydra",
    "Polaris": "Ursa Minor",
    "Hamal": "Aries",
    "Algol": "Perseus",
    "Denebola": "Leo",
    "Nunki": "Sagittarius",
    "Mirach": "Andromeda",
    "Alpheratz": "Andromeda",
    "Rasalhague": "Ophiuchus",
    "Kochab": "Ursa Minor",
    "Dschubba": "Scorpius",
    "Graffias": "Scorpius",
    "Shaula": "Scorpius",
    "Rasalgethi": "Hercules",
    "Rastaban": "Draco",
    "Eltanin": "Draco",
    "Kaus Media": "Sagittarius",
    "Kaus Borealis": "Sagittarius",
    "Arneb": "Lepus",
    "Gienah": "Corvus",
    "Mintaka": "Orion",
    "Saiph": "Orion",
    "Alnitak": "Orion",
    "Meissa": "Orion",
    "Algieba": "Leo",
    "Almach": "Andromeda",
    "Acrux": "Crux",
    "Gacrux": "Crux",
    "Mimosa": "Crux",
    "Hadar": "Centaurus",
    "Rigil Kentaurus": "Centaurus",
    "Toliman": "Centaurus",
}


def find_constellation_by_coordinates(
    ra_hours: float, dec_degrees: float, constellations: list[ConstellationModel]
) -> str | None:
    """
    Find constellation for a star based on coordinates.

    Uses constellation boundaries if available, otherwise finds nearest constellation center.

    Args:
        ra_hours: Star's right ascension in hours
        dec_degrees: Star's declination in degrees
        constellations: List of constellation models with boundary data

    Returns:
        Constellation name or None if not found
    """
    # First, try to find a constellation whose boundaries contain this star
    # (if boundaries are populated)
    for const in constellations:
        # Check if boundaries are set (not None and not zero-width)
        has_boundaries = (
            const.ra_min_hours is not None
            and const.ra_max_hours is not None
            and const.dec_min_degrees is not None
            and const.dec_max_degrees is not None
            and (const.ra_max_hours != const.ra_min_hours or const.dec_max_degrees != const.dec_min_degrees)
        )

        if has_boundaries:
            # Check if star is within constellation boundaries
            # Handle RA wrap-around (0-24 hours)
            ra_min = const.ra_min_hours
            ra_max = const.ra_max_hours

            # Check if RA range crosses 0h (e.g., 22h to 2h)
            if ra_min > ra_max:
                # Range crosses 0h
                in_ra = ra_hours >= ra_min or ra_hours <= ra_max
            else:
                # Normal range
                in_ra = ra_min <= ra_hours <= ra_max

            in_dec = const.dec_min_degrees <= dec_degrees <= const.dec_max_degrees

            if in_ra and in_dec:
                return const.name

    # If no boundary match (or boundaries not set), find nearest constellation center
    # Use a reasonable search radius based on constellation area
    min_distance = float("inf")
    nearest_const = None

    for const in constellations:
        # Calculate angular distance (simplified - using Euclidean distance in RA/Dec space)
        # This is approximate but should work for finding the nearest constellation
        ra_diff = abs(ra_hours - const.ra_hours)
        if ra_diff > 12:  # Handle wrap-around
            ra_diff = 24 - ra_diff

        dec_diff = abs(dec_degrees - const.dec_degrees)

        # Convert RA difference to degrees (1 hour = 15 degrees)
        ra_diff_deg = ra_diff * 15

        # Calculate approximate angular distance
        # Weight RA by cos(dec) to account for coordinate system
        cos_dec = abs(dec_degrees / 90.0) if abs(dec_degrees) < 90 else 0.1
        distance = (ra_diff_deg * cos_dec) ** 2 + dec_diff**2

        if distance < min_distance:
            min_distance = distance
            nearest_const = const

    # Use nearest constellation if it's reasonably close
    # For prominent constellations, use a generous radius (~45 degrees)
    # This is a heuristic - actual constellation boundaries can be irregular
    max_distance = 2025  # ~45 degrees squared

    if nearest_const and min_distance < max_distance:
        return nearest_const.name

    return None


def update_star_constellations(verbose: bool = False) -> tuple[int, int]:
    """
    Update constellation data for all stars in the database.

    Args:
        verbose: Show detailed progress

    Returns:
        (updated_count, not_found_count)
    """
    db = get_database()

    # Get all stars without constellation data
    with db._get_session() as session:
        stars = (
            session.query(CelestialObjectModel)
            .filter(CelestialObjectModel.object_type == CelestialObjectType.STAR.value)
            .filter(CelestialObjectModel.constellation.is_(None))
            .all()
        )

        # Get all constellations with boundary data
        constellations = session.query(ConstellationModel).all()

    if not stars:
        console.print("[green]✓[/green] All stars already have constellation data")
        return 0, 0

    console.print(f"[cyan]Found {len(stars)} stars without constellation data[/cyan]")
    console.print(f"[cyan]Using {len(constellations)} constellations for lookup[/cyan]")

    updated = 0
    not_found = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Updating star constellations...", total=len(stars))

        for star in stars:
            constellation = None

            # First, try known star mappings
            star_name_upper = star.name.upper()
            for known_name, const_name in KNOWN_STAR_CONSTELLATIONS.items():
                if known_name.upper() in star_name_upper or star_name_upper in known_name.upper():
                    constellation = const_name
                    break

            # If not found in known mappings, try coordinate-based lookup
            if not constellation:
                constellation = find_constellation_by_coordinates(star.ra_hours, star.dec_degrees, constellations)

            # Update the star if we found a constellation
            if constellation:
                with db._get_session() as session:
                    star_model = session.query(CelestialObjectModel).filter_by(id=star.id).first()
                    if star_model:
                        star_model.constellation = constellation
                        session.commit()
                        updated += 1
                        if verbose:
                            console.print(f"[dim]Updated {star.name} -> {constellation}[/dim]")
            else:
                not_found += 1
                if verbose:
                    console.print(f"[yellow]Could not determine constellation for {star.name}[/yellow]")

            progress.advance(task)

    console.print(f"\n[green]✓[/green] Updated {updated} stars")
    if not_found > 0:
        console.print(f"[yellow]⚠[/yellow] Could not determine constellation for {not_found} stars")

    return updated, not_found


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Update constellation data for stars")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")
    args = parser.parse_args()

    try:
        updated, not_found = update_star_constellations(verbose=args.verbose)
        sys.exit(0 if not_found == 0 else 1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Error updating star constellations")
        sys.exit(1)


if __name__ == "__main__":
    main()
