"""
ASCII Solar System Visualization

Creates an ASCII art representation of the solar system showing planets
in their current orbital positions (top-down view).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import NamedTuple

from celestron_nexstar.api.ephemeris.ephemeris import PLANET_NAMES
from celestron_nexstar.api.ephemeris.skyfield_utils import get_skyfield_loader


class PlanetPosition(NamedTuple):
    """Planet position in 2D space."""

    name: str
    x: float  # AU, heliocentric
    y: float  # AU, heliocentric
    distance_au: float  # Distance from Sun in AU


# Major planets to display (excluding moons)
MAJOR_PLANETS = ["mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]

# Planet symbols for ASCII art
PLANET_SYMBOLS = {
    "mercury": "☿",
    "venus": "♀",
    "earth": "⊕",
    "mars": "♂",
    "jupiter": "♃",
    "saturn": "♄",
    "uranus": "♅",
    "neptune": "♆",
}

# Planet names for display
PLANET_DISPLAY_NAMES = {
    "mercury": "Mercury",
    "venus": "Venus",
    "earth": "Earth",
    "mars": "Mars",
    "jupiter": "Jupiter",
    "saturn": "Saturn",
    "uranus": "Uranus",
    "neptune": "Neptune",
}


def get_heliocentric_positions(dt: datetime | None = None) -> list[PlanetPosition]:
    """
    Get heliocentric positions of major planets.

    Args:
        dt: Datetime to calculate positions for (default: now in UTC)

    Returns:
        List of PlanetPosition objects with x, y coordinates in AU
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    try:
        loader = get_skyfield_loader()
        ts = loader.timescale()
        eph = loader("de440s.bsp")
        t = ts.from_datetime(dt)

        sun = eph["sun"]
        earth = eph["earth"]
        positions: list[PlanetPosition] = []

        # Get all planets
        for planet_name in MAJOR_PLANETS:
            if planet_name == "earth":
                # Earth is special - it's the observer, so get its position directly
                earth_pos = sun.at(t).observe(earth).position.au
                positions.append(
                    PlanetPosition(
                        name="earth",
                        x=float(earth_pos[0]),
                        y=float(earth_pos[1]),
                        distance_au=float(math.sqrt(earth_pos[0] ** 2 + earth_pos[1] ** 2)),
                    )
                )
                continue

            if planet_name not in PLANET_NAMES:
                continue

            ephemeris_name, _bsp_file = PLANET_NAMES[planet_name]

            # Extract name part if numeric ID format
            if " " in ephemeris_name and ephemeris_name[0].isdigit():
                spice_target = ephemeris_name.split(" ", 1)[1]
            else:
                spice_target = ephemeris_name

            try:
                target = eph[spice_target]
            except KeyError:
                try:
                    target = eph[ephemeris_name.upper()]
                except KeyError:
                    continue

            # Get heliocentric position
            planet_pos = sun.at(t).observe(target).position.au

            positions.append(
                PlanetPosition(
                    name=planet_name,
                    x=float(planet_pos[0]),
                    y=float(planet_pos[1]),
                    distance_au=float(math.sqrt(planet_pos[0] ** 2 + planet_pos[1] ** 2)),
                )
            )

        return sorted(positions, key=lambda p: p.distance_au)

    except Exception:
        return []


def create_solar_system_ascii(dt: datetime | None = None, width: int = 80, height: int = 40) -> str:
    """
    Create ASCII art representation of the solar system.

    Args:
        dt: Datetime to calculate positions for (default: now in UTC)
        width: Width of ASCII canvas in characters
        height: Height of ASCII canvas in characters

    Returns:
        Multi-line string with ASCII art
    """
    positions = get_heliocentric_positions(dt)
    if not positions:
        return "Unable to calculate planetary positions."

    # Find the maximum distance to scale the view
    max_distance = max(p.distance_au for p in positions) if positions else 40.0
    # Add some padding
    max_distance *= 1.2

    # Create a 2D grid
    grid: list[list[str]] = [[" " for _ in range(width)] for _ in range(height)]

    # Center of the grid (Sun position)
    center_x = width // 2
    center_y = height // 2

    # Draw orbits (approximate circles) - use lighter dots
    for planet in positions:
        if planet.distance_au > 0:
            # Scale distance to grid coordinates
            radius_x = int((planet.distance_au / max_distance) * (width // 2 - 2))
            radius_y = int((planet.distance_au / max_distance) * (height // 2 - 2))

            # Draw orbit circle (approximate with dots) - sparser for outer planets
            step = 3 if planet.distance_au < 2.0 else 5
            for angle in range(0, 360, step):
                rad = math.radians(angle)
                x = center_x + int(radius_x * math.cos(rad))
                y = center_y + int(radius_y * math.sin(rad))
                if 0 <= x < width and 0 <= y < height and grid[y][x] == " ":
                    grid[y][x] = "·"

    # Draw Sun at center first (so planets can overwrite if needed, but we'll redraw it)
    grid[center_y][center_x] = "☉"

    # Draw planets at their positions (will overwrite orbit dots)
    for planet in positions:
        # Scale position to grid coordinates
        x = center_x + int((planet.x / max_distance) * (width // 2 - 2))
        y = center_y + int((planet.y / max_distance) * (height // 2 - 2))

        if 0 <= x < width and 0 <= y < height:
            symbol = PLANET_SYMBOLS.get(planet.name, "●")
            grid[y][x] = symbol

    # Ensure Sun is always visible at center (redraw if overwritten)
    grid[center_y][center_x] = "☉"

    # Convert grid to string
    lines = ["".join(row) for row in grid]

    # Build the output
    output_lines = []
    output_lines.append("Solar System (Top-Down View)")
    if dt:
        output_lines.append(f"Date: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    output_lines.append("")
    output_lines.extend(lines)
    output_lines.append("")
    output_lines.append("Legend:")
    for planet in sorted(positions, key=lambda p: p.distance_au):
        symbol = PLANET_SYMBOLS.get(planet.name, "●")
        name = PLANET_DISPLAY_NAMES.get(planet.name, planet.name.capitalize())
        distance = planet.distance_au
        output_lines.append(f"  {symbol} {name:8s} - {distance:5.2f} AU from Sun")

    return "\n".join(output_lines)
