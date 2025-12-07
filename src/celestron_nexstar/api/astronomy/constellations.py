"""
Constellation and Asterism Catalog

Static data for prominent constellations and famous asterisms visible
to binoculars and naked eye. Includes visibility calculations based on
observer location and time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from celestron_nexstar.api.core.utils import ra_dec_to_alt_az


logger = logging.getLogger(__name__)

__all__ = [
    "Asterism",
    "Constellation",
    "get_famous_asterisms",
    "get_prominent_constellations",
    "get_visible_asterisms",
    "get_visible_constellations",
    "populate_constellation_database",
]


@dataclass(frozen=True)
class Constellation:
    """A constellation with position and metadata."""

    name: str
    abbreviation: str
    ra_hours: float  # Right ascension of center (hours)
    dec_degrees: float  # Declination of center (degrees)
    area_sq_deg: float  # Size in square degrees
    brightest_star: str  # Name of brightest star
    magnitude: float  # Magnitude of brightest star
    season: str  # Best viewing season (Spring, Summer, Fall, Winter)
    hemisphere: str  # Northern, Southern, or Equatorial
    description: str  # Brief description


@dataclass(frozen=True)
class Asterism:
    """A star pattern (asterism) within or across constellations."""

    name: str
    alt_names: list[str]  # Alternative names
    ra_hours: float  # Right ascension of center
    dec_degrees: float  # Declination of center
    size_degrees: float  # Approximate angular size
    parent_constellation: str | None  # Primary constellation (if any)
    season: str  # Best viewing season
    hemisphere: str  # Visibility
    member_stars: list[str]  # Notable stars in the asterism
    description: str  # How to find and what it looks like
    wikipedia_url: str | None = None  # Wikipedia or reference URL
    cultural_info: str | None = None  # Cultural and mythological information
    guidepost_info: str | None = None  # How to use as a guidepost (e.g., points to Polaris)
    historical_notes: str | None = None  # Historical references and significance
    shape_description: str | None = None  # What the pattern looks like (e.g., "bowl and handle")


# NOTE: Constellation data is now stored in database seed files.
# See get_prominent_constellations() which loads from database.
# To regenerate seed files, run: python scripts/create_seed_files.py

# Removed _PROMINENT_CONSTELLATIONS_FALLBACK - data is now in constellations.json seed file
# Removed FAMOUS_ASTERISMS - data is now in asterisms.json seed file and loaded via get_famous_asterisms()


def get_prominent_constellations(db_session: None = None) -> list[Constellation]:  # db_session deprecated
    """
    Get list of prominent constellations from starplot.

    Args:
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of Constellation objects

    Raises:
        RuntimeError: If no constellations found
    """
    from celestron_nexstar.api.core.exceptions import DatabaseError

    try:
        from starplot.models import Constellation as StarplotConstellation

        constellations = []
        # Get all constellations from starplot
        for c in StarplotConstellation.all():
            # Convert starplot Constellation to our Constellation dataclass
            # starplot Constellation has: name, iau_id (3-letter abbreviation), ra (degrees), dec (degrees), etc.
            constellations.append(
                Constellation(
                    name=c.name or "",
                    abbreviation=c.iau_id or "",
                    ra_hours=c.ra / 15.0 if c.ra else 0.0,  # Convert degrees to hours
                    dec_degrees=c.dec if c.dec else 0.0,
                    area_sq_deg=0.0,  # Not available from starplot
                    brightest_star="",  # Not available from starplot
                    magnitude=0.0,  # Not available from starplot
                    season="",  # Not available from starplot
                    hemisphere="",  # Not available from starplot
                    description="",  # Not available from starplot
                )
            )
        if not constellations:
            raise DatabaseError("No constellations found. Please ensure starplot data is available.")
        return constellations
    except (ImportError, AttributeError, RuntimeError) as e:
        raise DatabaseError(
            "Could not load constellations from starplot. Please ensure starplot is properly installed."
        ) from e


def get_famous_asterisms(db_session: None = None) -> list[Asterism]:  # db_session deprecated
    """
    Get list of famous asterisms from database.

    Args:
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of Asterism objects

    Raises:
        RuntimeError: If no asterisms found in database (seed data required)
    """
    from celestron_nexstar.api.core.exceptions import DatabaseError
    from celestron_nexstar.api.database.duckdb_connection import get_duckdb_connection

    con = get_duckdb_connection()
    results = con.execute(
        """
        SELECT name, alt_names, ra_hours, dec_degrees, size_degrees, parent_constellation,
               description, stars, season, wikipedia_url, cultural_info, guidepost_info,
               historical_notes, shape_description
        FROM asterisms
        ORDER BY name
        """
    ).fetchall()

    if not results:
        raise DatabaseError("No asterisms found in database. Please seed the database by running: nexstar data seed")

    asterisms = []
    for row in results:
        # Parse alt_names and stars (stored as comma-separated strings)
        alt_names = [n.strip() for n in row[1].split(",")] if row[1] else []
        member_stars = [s.strip() for s in row[7].split(",")] if row[7] else []

        # Calculate hemisphere from declination
        dec = row[3]
        if dec > 30:
            hemisphere = "Northern"
        elif dec < -30:
            hemisphere = "Southern"
        else:
            hemisphere = "Equatorial"

        asterisms.append(
            Asterism(
                name=row[0],
                alt_names=alt_names,
                ra_hours=row[2],
                dec_degrees=dec,
                size_degrees=row[4] or 0.0,
                parent_constellation=row[5] or "",
                season=row[8] or "",
                hemisphere=hemisphere,
                member_stars=member_stars,
                description=row[6] or "",
                wikipedia_url=row[9],
                cultural_info=row[10],
                guidepost_info=row[11],
                historical_notes=row[12],
                shape_description=row[13],
            )
        )

    return asterisms


async def get_visible_constellations(
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
    db_session: None = None,  # Deprecated, kept for compatibility
) -> list[tuple[Constellation, float, float]]:
    """
    Get constellations visible above horizon at given time.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of (Constellation, altitude_deg, azimuth_deg) tuples sorted by altitude
    """
    if observation_time is None:
        observation_time = datetime.now(UTC)
    elif observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=UTC)
    else:
        observation_time = observation_time.astimezone(UTC)

    visible = []

    constellations = get_prominent_constellations()
    for constellation in constellations:
        # Calculate altitude and azimuth
        alt, az = ra_dec_to_alt_az(
            constellation.ra_hours,
            constellation.dec_degrees,
            latitude,
            longitude,
            observation_time,
        )

        if alt >= min_altitude_deg:
            visible.append((constellation, alt, az))

    # Sort by altitude (highest first)
    visible.sort(key=lambda x: x[1], reverse=True)

    return visible


async def get_visible_asterisms(
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
    db_session: None = None,  # Deprecated, kept for compatibility
) -> list[tuple[Asterism, float, float]]:
    """
    Get asterisms visible above horizon at given time.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)
        db_session: Deprecated parameter, kept for compatibility

    Returns:
        List of (Asterism, altitude_deg, azimuth_deg) tuples sorted by altitude
    """
    if observation_time is None:
        observation_time = datetime.now(UTC)
    elif observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=UTC)
    else:
        observation_time = observation_time.astimezone(UTC)

    visible = []

    asterisms = get_famous_asterisms()
    for asterism in asterisms:
        # Calculate altitude and azimuth
        alt, az = ra_dec_to_alt_az(
            asterism.ra_hours,
            asterism.dec_degrees,
            latitude,
            longitude,
            observation_time,
        )

        if alt >= min_altitude_deg:
            visible.append((asterism, alt, az))

    # Sort by altitude (highest first)
    visible.sort(key=lambda x: x[1], reverse=True)

    return visible


def populate_constellation_database(db_session: None = None) -> None:  # db_session deprecated
    """
    Populate database with constellation and asterism data.

    This should be called once to initialize the database with static data.
    Now uses seed data from JSON files instead of hardcoded Python data.

    Args:
        db_session: Deprecated parameter, kept for compatibility
    """
    from celestron_nexstar.api.database.duckdb_seeder import seed_asterisms_duckdb

    logger.info("Populating constellation database...")
    # Constellations come from starplot, only seed asterisms
    seed_asterisms_duckdb(force=True)
