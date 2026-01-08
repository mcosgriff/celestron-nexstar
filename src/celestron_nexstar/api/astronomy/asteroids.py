"""
Asteroid Visibility Calculations

Functions for computing asteroid positions and visibility from orbital elements.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from celestron_nexstar.api.location.observer import ObserverLocation


logger = logging.getLogger(__name__)


__all__ = [
    "Asteroid",
    "AsteroidVisibility",
    "get_known_asteroids",
    "get_upcoming_oppositions",
    "get_visible_asteroids",
]


@dataclass
class Asteroid:
    """Represents an asteroid with its orbital elements."""

    designation: str
    name: str | None
    asteroid_type: str

    # Orbital elements
    semi_major_axis_au: float
    eccentricity: float
    inclination_deg: float
    ascending_node_deg: float
    arg_perihelion_deg: float
    mean_anomaly_deg: float
    epoch: datetime

    # Photometric
    absolute_magnitude_h: float
    slope_g: float | None
    diameter_km: float | None
    albedo: float | None

    # Derived
    perihelion_au: float | None
    aphelion_au: float | None
    orbital_period_years: float | None

    # Metadata
    notes: str | None
    source: str

    @property
    def display_name(self) -> str:
        """Get display name (name if available, else designation)."""
        if self.name:
            return f"{self.name} ({self.designation})"
        return self.designation


@dataclass
class AsteroidVisibility:
    """Visibility information for an asteroid at a specific time."""

    asteroid: Asteroid
    date: datetime
    magnitude: float
    is_visible: bool
    altitude: float
    azimuth: float
    ra_hours: float | None
    dec_degrees: float | None
    elongation_deg: float | None
    helio_distance_au: float | None
    geo_distance_au: float | None
    phase_angle_deg: float | None
    propagation_method: str  # "keplerian" or "estimated"
    notes: str


def get_known_asteroids(db_session: Session) -> list[Asteroid]:
    """
    Get all known asteroids from the database.

    Args:
        db_session: Database session

    Returns:
        List of Asteroid objects
    """
    from sqlalchemy import select

    from celestron_nexstar.api.database.models import AsteroidModel

    asteroids = db_session.execute(select(AsteroidModel).order_by(AsteroidModel.absolute_magnitude_h)).scalars().all()

    return [
        Asteroid(
            designation=a.designation,
            name=a.name,
            asteroid_type=a.asteroid_type,
            semi_major_axis_au=a.semi_major_axis_au,
            eccentricity=a.eccentricity,
            inclination_deg=a.inclination_deg,
            ascending_node_deg=a.ascending_node_deg,
            arg_perihelion_deg=a.arg_perihelion_deg,
            mean_anomaly_deg=a.mean_anomaly_deg,
            epoch=a.epoch,
            absolute_magnitude_h=a.absolute_magnitude_h,
            slope_g=a.slope_g,
            diameter_km=a.diameter_km,
            albedo=a.albedo,
            perihelion_au=a.perihelion_au,
            aphelion_au=a.aphelion_au,
            orbital_period_years=a.orbital_period_years,
            notes=a.notes,
            source=a.source,
        )
        for a in asteroids
    ]


def _compute_from_spk(
    spk_path: Path,
    observer_lat: float,
    observer_lon: float,
    dt: datetime,
) -> dict | None:
    """Compute asteroid position from SPK file using Skyfield."""
    try:
        from skyfield.api import Loader

        from celestron_nexstar.api.core.utils import angular_separation, ra_dec_to_alt_az
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        load = Loader(str(spk_path.parent))
        ts = get_skyfield_timescale()
        t = ts.from_datetime(dt)

        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        # Load asteroid kernel
        asteroid_kernel = load.open(str(spk_path))

        # Find the SPICE ID for the asteroid (usually negative for small bodies)
        target = None
        for segment in asteroid_kernel.segments:
            target = segment.target
            break

        if target is None:
            logger.warning(f"Could not find target in SPK {spk_path}")
            return None

        sun = eph["sun"]
        earth = eph["earth"]

        # Position from SPK (this is barycentric or heliocentric depending on kernel)
        from skyfield.jpllib import SpiceKernel

        if isinstance(asteroid_kernel, SpiceKernel):
            asteroid = asteroid_kernel[target]
        else:
            return None

        # Get position relative to Earth
        astrometric = earth.at(t).observe(asteroid)
        ra, dec, distance = astrometric.radec()

        ra_hours = ra.hours
        dec_degrees = dec.degrees
        geo_dist = distance.au

        # Get altitude/azimuth
        azimuth, altitude = ra_dec_to_alt_az(ra_hours, dec_degrees, observer_lat, observer_lon, dt)

        # Heliocentric distance
        helio_astrometric = sun.at(t).observe(asteroid)
        _, _, helio_distance = helio_astrometric.radec()
        helio_dist = helio_distance.au

        # Sun position for elongation
        sun_astrometric = earth.at(t).observe(sun)
        sun_ra, sun_dec, _ = sun_astrometric.radec()
        elongation = angular_separation(ra_hours, dec_degrees, sun_ra.hours, sun_dec.degrees)

        # Phase angle
        earth_sun_dist = 1.0
        cos_phase = (helio_dist**2 + geo_dist**2 - earth_sun_dist**2) / (2 * helio_dist * geo_dist)
        cos_phase = max(-1.0, min(1.0, cos_phase))
        phase_angle = math.degrees(math.acos(cos_phase))

        return {
            "ra_hours": ra_hours,
            "dec_degrees": dec_degrees,
            "altitude": altitude,
            "azimuth": azimuth,
            "helio_dist": helio_dist,
            "geo_dist": geo_dist,
            "elongation": elongation,
            "phase_angle": phase_angle,
            "method": "spk",
        }

    except Exception as e:
        logger.debug(f"Error computing from SPK {spk_path}: {e}")
        return None


def _compute_asteroid_position(
    asteroid: Asteroid,
    observer_lat: float,
    observer_lon: float,
    dt: datetime,
) -> dict | None:
    """
    Compute asteroid position using SPK (if available) or Keplerian propagation.

    Returns dict with ra_hours, dec_degrees, altitude, azimuth, helio_dist, geo_dist, elongation, phase_angle
    or None if calculation fails.
    """
    # First try SPK if available
    try:
        from celestron_nexstar.api.solar_system.horizons_spk import load_asteroid_spk

        is_available, spk_path = load_asteroid_spk(asteroid.designation)
        if is_available and spk_path:
            result = _compute_from_spk(spk_path, observer_lat, observer_lon, dt)
            if result:
                return result
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"SPK calculation failed for {asteroid.designation}: {e}")

    # Fall back to Keplerian propagation
    try:
        from celestron_nexstar.api.core.utils import angular_separation, ra_dec_to_alt_az
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        # Ensure UTC
        dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)

        # Days since epoch
        epoch = asteroid.epoch
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=UTC)
        delta_days = (dt - epoch).total_seconds() / 86400.0

        # Orbital elements
        a = asteroid.semi_major_axis_au
        e = asteroid.eccentricity
        i = math.radians(asteroid.inclination_deg)
        omega = math.radians(asteroid.ascending_node_deg)
        w = math.radians(asteroid.arg_perihelion_deg)
        mean_anomaly_0 = math.radians(asteroid.mean_anomaly_deg)

        # Mean motion (rad/day)
        n = math.sqrt(1.0 / (a**3)) * (2 * math.pi / 365.25)

        # Mean anomaly at target time
        mean_anomaly = mean_anomaly_0 + n * delta_days
        mean_anomaly = mean_anomaly % (2 * math.pi)

        # Solve Kepler's equation for eccentric anomaly
        eccentric_anomaly = mean_anomaly
        for _ in range(50):
            delta_e = (mean_anomaly - eccentric_anomaly + e * math.sin(eccentric_anomaly)) / (
                1 - e * math.cos(eccentric_anomaly)
            )
            eccentric_anomaly += delta_e
            if abs(delta_e) < 1e-10:
                break

        # True anomaly
        nu = 2 * math.atan2(
            math.sqrt(1 + e) * math.sin(eccentric_anomaly / 2),
            math.sqrt(1 - e) * math.cos(eccentric_anomaly / 2),
        )

        # Heliocentric distance
        r = a * (1 - e * math.cos(eccentric_anomaly))

        # Position in orbital plane
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)

        # Transform to heliocentric ecliptic coordinates
        cos_omega, sin_omega = math.cos(omega), math.sin(omega)
        cos_w, sin_w = math.cos(w), math.sin(w)
        cos_i, sin_i = math.cos(i), math.sin(i)

        x_ecl = (cos_omega * cos_w - sin_omega * sin_w * cos_i) * x_orb + (
            -cos_omega * sin_w - sin_omega * cos_w * cos_i
        ) * y_orb
        y_ecl = (sin_omega * cos_w + cos_omega * sin_w * cos_i) * x_orb + (
            -sin_omega * sin_w + cos_omega * cos_w * cos_i
        ) * y_orb
        z_ecl = sin_w * sin_i * x_orb + cos_w * sin_i * y_orb

        # Get Earth position
        ts = get_skyfield_timescale()
        t = ts.from_datetime(dt)

        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        earth = eph["earth"]
        sun = eph["sun"]

        # Earth position in ecliptic coordinates (heliocentric)
        earth_pos = earth.at(t).position.au
        sun_pos = sun.at(t).position.au
        earth_helio = earth_pos - sun_pos

        # Convert Earth from equatorial to ecliptic
        obliquity = math.radians(23.4393)
        cos_obl, sin_obl = math.cos(obliquity), math.sin(obliquity)

        earth_x = earth_helio[0]
        earth_y = earth_helio[1] * cos_obl + earth_helio[2] * sin_obl
        earth_z = -earth_helio[1] * sin_obl + earth_helio[2] * cos_obl

        # Geocentric position of asteroid (ecliptic)
        dx = x_ecl - earth_x
        dy = y_ecl - earth_y
        dz = z_ecl - earth_z

        geo_dist = math.sqrt(dx**2 + dy**2 + dz**2)

        # Convert to equatorial
        dx_eq = dx
        dy_eq = dy * cos_obl - dz * sin_obl
        dz_eq = dy * sin_obl + dz * cos_obl

        # RA/Dec
        ra = math.atan2(dy_eq, dx_eq)
        if ra < 0:
            ra += 2 * math.pi
        dec = math.asin(dz_eq / geo_dist)

        ra_hours = math.degrees(ra) / 15.0
        dec_degrees = math.degrees(dec)

        # Alt/Az
        azimuth, altitude = ra_dec_to_alt_az(ra_hours, dec_degrees, observer_lat, observer_lon, dt)

        # Sun position for elongation
        sun_astrometric = earth.at(t).observe(sun)
        sun_ra, sun_dec, _ = sun_astrometric.radec()
        elongation = angular_separation(ra_hours, dec_degrees, sun_ra.hours, sun_dec.degrees)

        # Phase angle
        helio_dist = r
        earth_sun_dist = 1.0  # Earth-Sun distance approx
        cos_phase = (helio_dist**2 + geo_dist**2 - earth_sun_dist**2) / (2 * helio_dist * geo_dist)
        cos_phase = max(-1.0, min(1.0, cos_phase))
        phase_angle = math.degrees(math.acos(cos_phase))

        return {
            "ra_hours": ra_hours,
            "dec_degrees": dec_degrees,
            "altitude": altitude,
            "azimuth": azimuth,
            "helio_dist": helio_dist,
            "geo_dist": geo_dist,
            "elongation": elongation,
            "phase_angle": phase_angle,
            "method": "keplerian",
        }

    except Exception as e:
        logger.debug(f"Error computing position for {asteroid.designation}: {e}")
        return None


def _compute_asteroid_magnitude(
    asteroid: Asteroid,
    helio_dist: float,
    geo_dist: float,
    phase_angle: float,
) -> float:
    """
    Compute asteroid apparent magnitude using H-G system.

    m = H + 5·log₁₀(r·Δ) - 2.5·log₁₀((1-G)·Φ₁ + G·Φ₂)

    Where Φ₁, Φ₂ are phase functions.
    """
    absolute_magnitude = asteroid.absolute_magnitude_h
    slope_g = asteroid.slope_g if asteroid.slope_g is not None else 0.15

    # Simplified H-G magnitude formula
    # Phase functions (Bowell approximation)
    phase_rad = math.radians(phase_angle)

    a1 = 3.332
    a2 = 1.862
    b1 = 0.631
    b2 = 1.218

    phi1 = math.exp(-a1 * (math.tan(phase_rad / 2)) ** b1)
    phi2 = math.exp(-a2 * (math.tan(phase_rad / 2)) ** b2)

    # Avoid log of zero
    phase_term = (1 - slope_g) * phi1 + slope_g * phi2
    if phase_term <= 0:
        phase_term = 0.001

    magnitude = absolute_magnitude + 5 * math.log10(helio_dist * geo_dist) - 2.5 * math.log10(phase_term)

    return magnitude


def get_visible_asteroids(
    db_session: Session,
    location: ObserverLocation,
    dt: datetime | None = None,
    max_magnitude: float = 12.0,
    min_altitude: float = 15.0,
) -> list[AsteroidVisibility]:
    """
    Get asteroids visible from observer location at given time.

    Args:
        db_session: Database session
        location: Observer location
        dt: Observation time (default: now)
        max_magnitude: Maximum apparent magnitude to include
        min_altitude: Minimum altitude above horizon

    Returns:
        List of visible asteroids sorted by magnitude
    """
    if dt is None:
        dt = datetime.now(UTC)

    asteroids = get_known_asteroids(db_session)
    visible = []

    for asteroid in asteroids:
        pos = _compute_asteroid_position(asteroid, location.latitude, location.longitude, dt)

        if pos is None:
            continue

        magnitude = _compute_asteroid_magnitude(
            asteroid,
            pos["helio_dist"],
            pos["geo_dist"],
            pos["phase_angle"],
        )

        if magnitude > max_magnitude:
            continue

        is_visible = pos["altitude"] >= min_altitude

        notes = []
        if asteroid.asteroid_type == "neo":
            notes.append("Near-Earth Object")
        elif asteroid.asteroid_type == "dwarf_planet":
            notes.append("Dwarf planet")
        elif asteroid.asteroid_type == "trojan":
            notes.append("Jupiter Trojan")
        elif asteroid.asteroid_type == "centaur":
            notes.append("Centaur")

        if pos["elongation"] < 30:
            notes.append("Close to Sun")
        elif pos["elongation"] > 150:
            notes.append("Near opposition")

        visible.append(
            AsteroidVisibility(
                asteroid=asteroid,
                date=dt,
                magnitude=magnitude,
                is_visible=is_visible,
                altitude=pos["altitude"],
                azimuth=pos["azimuth"],
                ra_hours=pos["ra_hours"],
                dec_degrees=pos["dec_degrees"],
                elongation_deg=pos["elongation"],
                helio_distance_au=pos["helio_dist"],
                geo_distance_au=pos["geo_dist"],
                phase_angle_deg=pos["phase_angle"],
                propagation_method=pos.get("method", "keplerian"),
                notes=", ".join(notes) if notes else "",
            )
        )

    # Sort by magnitude (brightest first)
    visible.sort(key=lambda v: v.magnitude)

    return visible


def get_upcoming_oppositions(
    db_session: Session,
    location: ObserverLocation,
    months_ahead: int = 12,
) -> list[AsteroidVisibility]:
    """
    Find asteroids with upcoming oppositions.

    Opposition occurs when elongation is ~180° (opposite the Sun).

    Args:
        db_session: Database session
        location: Observer location
        months_ahead: Number of months to search

    Returns:
        List of asteroids at their opposition dates
    """
    now = datetime.now(UTC)
    asteroids = get_known_asteroids(db_session)
    oppositions = []

    # Sample weekly to find oppositions
    for asteroid in asteroids:
        best_elongation = 0.0
        best_date = now
        best_pos = None

        for week in range(int(months_ahead * 4.3)):
            check_date = now + timedelta(weeks=week)
            pos = _compute_asteroid_position(asteroid, location.latitude, location.longitude, check_date)

            if pos is None:
                continue

            if pos["elongation"] > best_elongation:
                best_elongation = pos["elongation"]
                best_date = check_date
                best_pos = pos

        # Only include if elongation > 150° (near opposition)
        if best_pos and best_elongation > 150:
            magnitude = _compute_asteroid_magnitude(
                asteroid,
                best_pos["helio_dist"],
                best_pos["geo_dist"],
                best_pos["phase_angle"],
            )

            # Only include reasonably bright objects
            if magnitude <= 12.0:
                oppositions.append(
                    AsteroidVisibility(
                        asteroid=asteroid,
                        date=best_date,
                        magnitude=magnitude,
                        is_visible=best_pos["altitude"] > 0,
                        altitude=best_pos["altitude"],
                        azimuth=best_pos["azimuth"],
                        ra_hours=best_pos["ra_hours"],
                        dec_degrees=best_pos["dec_degrees"],
                        elongation_deg=best_elongation,
                        helio_distance_au=best_pos["helio_dist"],
                        geo_distance_au=best_pos["geo_dist"],
                        phase_angle_deg=best_pos["phase_angle"],
                        propagation_method=best_pos.get("method", "keplerian"),
                        notes="Opposition",
                    )
                )

    # Sort by date
    oppositions.sort(key=lambda v: v.date)

    return oppositions
