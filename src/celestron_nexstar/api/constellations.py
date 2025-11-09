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
from typing import TYPE_CHECKING

from ..coordinate_utils import ra_dec_to_alt_az


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


# Prominent constellations for naked-eye and binocular viewing
# Focusing on the most recognizable and historically significant ones
PROMINENT_CONSTELLATIONS = [
    # Winter Northern Hemisphere
    Constellation(
        name="Orion",
        abbreviation="Ori",
        ra_hours=5.5,
        dec_degrees=5.0,
        area_sq_deg=594,
        brightest_star="Rigel",
        magnitude=0.18,
        season="Winter",
        hemisphere="Equatorial",
        description="The Hunter - one of the most recognizable constellations with bright stars and nebulae",
    ),
    Constellation(
        name="Canis Major",
        abbreviation="CMa",
        ra_hours=6.75,
        dec_degrees=-20.0,
        area_sq_deg=380,
        brightest_star="Sirius",
        magnitude=-1.46,
        season="Winter",
        hemisphere="Equatorial",
        description="The Great Dog - contains Sirius, the brightest star in the night sky",
    ),
    Constellation(
        name="Taurus",
        abbreviation="Tau",
        ra_hours=4.5,
        dec_degrees=15.0,
        area_sq_deg=797,
        brightest_star="Aldebaran",
        magnitude=0.87,
        season="Winter",
        hemisphere="Northern",
        description="The Bull - contains the Pleiades and Hyades star clusters",
    ),
    Constellation(
        name="Gemini",
        abbreviation="Gem",
        ra_hours=7.0,
        dec_degrees=22.0,
        area_sq_deg=514,
        brightest_star="Pollux",
        magnitude=1.14,
        season="Winter",
        hemisphere="Northern",
        description="The Twins - features the bright stars Castor and Pollux",
    ),
    Constellation(
        name="Auriga",
        abbreviation="Aur",
        ra_hours=6.0,
        dec_degrees=42.0,
        area_sq_deg=657,
        brightest_star="Capella",
        magnitude=0.08,
        season="Winter",
        hemisphere="Northern",
        description="The Charioteer - contains the brilliant star Capella and several star clusters",
    ),
    # Spring Northern Hemisphere
    Constellation(
        name="Leo",
        abbreviation="Leo",
        ra_hours=10.5,
        dec_degrees=15.0,
        area_sq_deg=947,
        brightest_star="Regulus",
        magnitude=1.36,
        season="Spring",
        hemisphere="Northern",
        description="The Lion - a prominent zodiac constellation with a distinctive sickle shape",
    ),
    Constellation(
        name="Ursa Major",
        abbreviation="UMa",
        ra_hours=11.0,
        dec_degrees=50.0,
        area_sq_deg=1280,
        brightest_star="Alioth",
        magnitude=1.76,
        season="Spring",
        hemisphere="Northern",
        description="The Great Bear - contains the famous Big Dipper asterism",
    ),
    Constellation(
        name="Boötes",
        abbreviation="Boo",
        ra_hours=14.5,
        dec_degrees=30.0,
        area_sq_deg=907,
        brightest_star="Arcturus",
        magnitude=-0.05,
        season="Spring",
        hemisphere="Northern",
        description="The Herdsman - features brilliant Arcturus, one of the brightest stars",
    ),
    Constellation(
        name="Virgo",
        abbreviation="Vir",
        ra_hours=13.5,
        dec_degrees=-3.0,
        area_sq_deg=1294,
        brightest_star="Spica",
        magnitude=0.98,
        season="Spring",
        hemisphere="Equatorial",
        description="The Maiden - zodiac constellation with the bright star Spica",
    ),
    # Summer Northern Hemisphere
    Constellation(
        name="Cygnus",
        abbreviation="Cyg",
        ra_hours=20.5,
        dec_degrees=42.0,
        area_sq_deg=804,
        brightest_star="Deneb",
        magnitude=1.25,
        season="Summer",
        hemisphere="Northern",
        description="The Swan - flies along the Milky Way with distinctive cross shape",
    ),
    Constellation(
        name="Lyra",
        abbreviation="Lyr",
        ra_hours=18.75,
        dec_degrees=36.0,
        area_sq_deg=286,
        brightest_star="Vega",
        magnitude=0.03,
        season="Summer",
        hemisphere="Northern",
        description="The Lyre - small but prominent, dominated by brilliant Vega",
    ),
    Constellation(
        name="Aquila",
        abbreviation="Aql",
        ra_hours=19.5,
        dec_degrees=4.0,
        area_sq_deg=652,
        brightest_star="Altair",
        magnitude=0.76,
        season="Summer",
        hemisphere="Equatorial",
        description="The Eagle - features Altair in the Summer Triangle",
    ),
    Constellation(
        name="Scorpius",
        abbreviation="Sco",
        ra_hours=16.75,
        dec_degrees=-26.0,
        area_sq_deg=497,
        brightest_star="Antares",
        magnitude=1.06,
        season="Summer",
        hemisphere="Southern",
        description="The Scorpion - distinctive J-shape with red supergiant Antares",
    ),
    Constellation(
        name="Sagittarius",
        abbreviation="Sgr",
        ra_hours=19.0,
        dec_degrees=-25.0,
        area_sq_deg=867,
        brightest_star="Kaus Australis",
        magnitude=1.79,
        season="Summer",
        hemisphere="Southern",
        description="The Archer - points toward galactic center, rich in deep-sky objects",
    ),
    # Fall Northern Hemisphere
    Constellation(
        name="Pegasus",
        abbreviation="Peg",
        ra_hours=22.5,
        dec_degrees=20.0,
        area_sq_deg=1121,
        brightest_star="Enif",
        magnitude=2.38,
        season="Fall",
        hemisphere="Northern",
        description="The Winged Horse - features the Great Square of Pegasus",
    ),
    Constellation(
        name="Andromeda",
        abbreviation="And",
        ra_hours=1.0,
        dec_degrees=38.0,
        area_sq_deg=722,
        brightest_star="Alpheratz",
        magnitude=2.07,
        season="Fall",
        hemisphere="Northern",
        description="The Princess - contains the famous Andromeda Galaxy (M31)",
    ),
    Constellation(
        name="Cassiopeia",
        abbreviation="Cas",
        ra_hours=1.0,
        dec_degrees=60.0,
        area_sq_deg=598,
        brightest_star="Schedar",
        magnitude=2.24,
        season="Fall",
        hemisphere="Northern",
        description="The Queen - distinctive W or M shape, circumpolar in northern latitudes",
    ),
    Constellation(
        name="Perseus",
        abbreviation="Per",
        ra_hours=3.0,
        dec_degrees=45.0,
        area_sq_deg=615,
        brightest_star="Mirfak",
        magnitude=1.79,
        season="Fall",
        hemisphere="Northern",
        description="The Hero - contains the variable star Algol and Double Cluster",
    ),
    # Year-round Southern Hemisphere
    Constellation(
        name="Crux",
        abbreviation="Cru",
        ra_hours=12.5,
        dec_degrees=-60.0,
        area_sq_deg=68,
        brightest_star="Acrux",
        magnitude=0.77,
        season="Spring",
        hemisphere="Southern",
        description="The Southern Cross - most distinctive southern constellation, smallest of all",
    ),
    Constellation(
        name="Centaurus",
        abbreviation="Cen",
        ra_hours=13.0,
        dec_degrees=-47.0,
        area_sq_deg=1060,
        brightest_star="Alpha Centauri",
        magnitude=-0.01,
        season="Spring",
        hemisphere="Southern",
        description="The Centaur - contains Alpha Centauri, closest star system to Earth",
    ),
]

# Famous asterisms for binocular and naked-eye viewing
FAMOUS_ASTERISMS = [
    Asterism(
        name="Big Dipper",
        alt_names=["The Plough", "Ursa Major asterism"],
        ra_hours=11.5,
        dec_degrees=53.0,
        size_degrees=25.0,
        parent_constellation="Ursa Major",
        season="Spring",
        hemisphere="Northern",
        member_stars=["Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"],
        description="Seven bright stars forming a ladle shape. Use the pointer stars (Dubhe and Merak) to find Polaris",
    ),
    Asterism(
        name="Little Dipper",
        alt_names=["Ursa Minor asterism"],
        ra_hours=15.0,
        dec_degrees=75.0,
        size_degrees=20.0,
        parent_constellation="Ursa Minor",
        season="Year-round",
        hemisphere="Northern",
        member_stars=["Polaris", "Kochab", "Pherkad"],
        description="Seven stars forming a smaller ladle. Polaris marks the end of the handle and North Celestial Pole",
    ),
    Asterism(
        name="Summer Triangle",
        alt_names=["Great Triangle"],
        ra_hours=19.5,
        dec_degrees=35.0,
        size_degrees=50.0,
        parent_constellation=None,
        season="Summer",
        hemisphere="Northern",
        member_stars=["Vega", "Deneb", "Altair"],
        description="Large triangle formed by three of the brightest stars in the summer sky",
    ),
    Asterism(
        name="Winter Triangle",
        alt_names=["Great Southern Triangle"],
        ra_hours=6.5,
        dec_degrees=-5.0,
        size_degrees=60.0,
        parent_constellation=None,
        season="Winter",
        hemisphere="Equatorial",
        member_stars=["Sirius", "Procyon", "Betelgeuse"],
        description="Large triangle connecting the brightest stars of winter: Sirius, Procyon, and Betelgeuse",
    ),
    Asterism(
        name="Winter Hexagon",
        alt_names=["Winter Circle"],
        ra_hours=6.0,
        dec_degrees=10.0,
        size_degrees=70.0,
        parent_constellation=None,
        season="Winter",
        hemisphere="Equatorial",
        member_stars=["Sirius", "Rigel", "Aldebaran", "Capella", "Pollux", "Procyon"],
        description="Six bright stars forming a large hexagon dominating winter skies",
    ),
    Asterism(
        name="Spring Triangle",
        alt_names=["Great Diamond"],
        ra_hours=13.0,
        dec_degrees=25.0,
        size_degrees=55.0,
        parent_constellation=None,
        season="Spring",
        hemisphere="Northern",
        member_stars=["Arcturus", "Spica", "Regulus"],
        description="Triangle of three bright stars marking the spring sky",
    ),
    Asterism(
        name="Great Square of Pegasus",
        alt_names=["Autumn Square"],
        ra_hours=23.0,
        dec_degrees=20.0,
        size_degrees=20.0,
        parent_constellation="Pegasus",
        season="Fall",
        hemisphere="Northern",
        member_stars=["Markab", "Scheat", "Algenib", "Alpheratz"],
        description="Four stars forming a large square. Alpheratz actually belongs to Andromeda",
    ),
    Asterism(
        name="Northern Cross",
        alt_names=["Cygnus Cross"],
        ra_hours=20.5,
        dec_degrees=42.0,
        size_degrees=25.0,
        parent_constellation="Cygnus",
        season="Summer",
        hemisphere="Northern",
        member_stars=["Deneb", "Albireo", "Sadr"],
        description="Cross shape formed by the main stars of Cygnus the Swan",
    ),
    Asterism(
        name="Pleiades",
        alt_names=["Seven Sisters", "M45"],
        ra_hours=3.75,
        dec_degrees=24.0,
        size_degrees=2.0,
        parent_constellation="Taurus",
        season="Winter",
        hemisphere="Northern",
        member_stars=["Alcyone", "Atlas", "Electra", "Maia", "Merope", "Taygeta", "Pleione"],
        description="Stunning open star cluster visible to naked eye. Six or seven stars easily visible",
    ),
    Asterism(
        name="Hyades",
        alt_names=["Face of the Bull"],
        ra_hours=4.5,
        dec_degrees=16.0,
        size_degrees=5.5,
        parent_constellation="Taurus",
        season="Winter",
        hemisphere="Northern",
        member_stars=["Aldebaran", "Theta Tauri"],
        description="V-shaped cluster forming the bull's face. Aldebaran is foreground star, not cluster member",
    ),
    Asterism(
        name="Orion's Belt",
        alt_names=["The Belt", "Three Kings"],
        ra_hours=5.6,
        dec_degrees=-1.2,
        size_degrees=3.0,
        parent_constellation="Orion",
        season="Winter",
        hemisphere="Equatorial",
        member_stars=["Alnitak", "Alnilam", "Mintaka"],
        description="Three bright stars in a straight line. Points to Sirius and Aldebaran",
    ),
    Asterism(
        name="Sickle of Leo",
        alt_names=["Question Mark"],
        ra_hours=10.3,
        dec_degrees=18.0,
        size_degrees=20.0,
        parent_constellation="Leo",
        season="Spring",
        hemisphere="Northern",
        member_stars=["Regulus", "Algieba", "Adhafera"],
        description="Backward question mark shape forming the lion's head and mane",
    ),
    Asterism(
        name="Teapot",
        alt_names=["Sagittarius Teapot"],
        ra_hours=19.0,
        dec_degrees=-27.0,
        size_degrees=15.0,
        parent_constellation="Sagittarius",
        season="Summer",
        hemisphere="Southern",
        member_stars=["Kaus Australis", "Nunki", "Ascella"],
        description="Eight stars forming a teapot shape. The spout points toward Scorpius",
    ),
    Asterism(
        name="False Cross",
        alt_names=["Diamond Cross"],
        ra_hours=8.75,
        dec_degrees=-58.0,
        size_degrees=10.0,
        parent_constellation=None,
        season="Spring",
        hemisphere="Southern",
        member_stars=["Aspidiske", "Markeb"],
        description="Cross shape often confused with the Southern Cross, but larger and dimmer",
    ),
]


def get_prominent_constellations() -> list[Constellation]:
    """Get list of prominent constellations for naked-eye viewing."""
    return PROMINENT_CONSTELLATIONS


def get_famous_asterisms() -> list[Asterism]:
    """Get list of famous asterisms for naked-eye viewing."""
    return FAMOUS_ASTERISMS


def get_visible_constellations(
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
) -> list[tuple[Constellation, float, float]]:
    """
    Get constellations visible above horizon at given time.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)

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

    for constellation in PROMINENT_CONSTELLATIONS:
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


def get_visible_asterisms(
    latitude: float,
    longitude: float,
    observation_time: datetime | None = None,
    min_altitude_deg: float = 20.0,
) -> list[tuple[Asterism, float, float]]:
    """
    Get asterisms visible above horizon at given time.

    Args:
        latitude: Observer latitude in degrees
        longitude: Observer longitude in degrees
        observation_time: Time of observation (default: now)
        min_altitude_deg: Minimum altitude for visibility (default: 20°)

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

    for asterism in FAMOUS_ASTERISMS:
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


def populate_constellation_database(db_session: Session) -> None:
    """
    Populate database with constellation and asterism data.

    This should be called once to initialize the database with static data.

    Args:
        db_session: SQLAlchemy database session
    """
    from .models import AsterismModel, ConstellationModel

    logger.info("Populating constellation database...")

    # Clear existing data
    db_session.query(ConstellationModel).delete()
    db_session.query(AsterismModel).delete()

    # Add constellations
    for constellation in PROMINENT_CONSTELLATIONS:
        model = ConstellationModel(
            name=constellation.name,
            abbreviation=constellation.abbreviation,
            ra_hours=constellation.ra_hours,
            dec_degrees=constellation.dec_degrees,
            area_sq_deg=constellation.area_sq_deg,
            brightest_star=constellation.brightest_star,
            magnitude=constellation.magnitude,
            season=constellation.season,
            hemisphere=constellation.hemisphere,
            description=constellation.description,
        )
        db_session.add(model)

    # Add asterisms
    for asterism in FAMOUS_ASTERISMS:
        model = AsterismModel(
            name=asterism.name,
            alt_names=",".join(asterism.alt_names),
            ra_hours=asterism.ra_hours,
            dec_degrees=asterism.dec_degrees,
            size_degrees=asterism.size_degrees,
            parent_constellation=asterism.parent_constellation,
            season=asterism.season,
            hemisphere=asterism.hemisphere,
            member_stars=",".join(asterism.member_stars),
            description=asterism.description,
        )
        db_session.add(model)

    db_session.commit()
    logger.info(
        f"Added {len(PROMINENT_CONSTELLATIONS)} constellations and {len(FAMOUS_ASTERISMS)} asterisms to database"
    )
