"""
Keplerian Orbit Propagation for Comets

Provides functions to compute comet positions from orbital elements
using two-body Keplerian mechanics with Skyfield for coordinate transforms.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from celestron_nexstar.api.astronomy.comets import Comet


logger = logging.getLogger(__name__)


__all__ = [
    "CometPosition",
    "compute_comet_magnitude",
    "compute_comet_position",
    "solve_kepler",
]


@dataclass
class CometPosition:
    """Position of a comet at a specific time."""

    ra_hours: float  # Right ascension in hours (0-24)
    dec_degrees: float  # Declination in degrees (-90 to +90)
    altitude_deg: float  # Altitude above horizon in degrees
    azimuth_deg: float  # Azimuth in degrees (0-360)
    helio_distance_au: float  # Distance from Sun in AU
    geo_distance_au: float  # Distance from Earth in AU
    elongation_deg: float  # Angular separation from Sun in degrees
    phase_angle_deg: float  # Sun-comet-Earth angle in degrees


def solve_kepler(mean_anomaly: float, eccentricity: float, tol: float = 1e-10, max_iter: int = 100) -> float:
    """
    Solve Kepler's equation for eccentric/hyperbolic anomaly.

    For elliptical orbits (e < 1): M = E - e * sin(E)
    For parabolic orbits (e ≈ 1): Uses Barker's equation
    For hyperbolic orbits (e > 1): M = e * sinh(H) - H

    Args:
        mean_anomaly: Mean anomaly in radians
        eccentricity: Orbital eccentricity
        tol: Convergence tolerance
        max_iter: Maximum iterations

    Returns:
        Eccentric anomaly (E) for elliptic, or hyperbolic anomaly (H) for hyperbolic orbits
    """
    M = mean_anomaly
    e = eccentricity

    if e < 1.0:
        # Elliptic orbit - Newton-Raphson for E
        E = M if e < 0.8 else math.pi
        for _ in range(max_iter):
            f = E - e * math.sin(E) - M
            f_prime = 1 - e * math.cos(E)
            delta = f / f_prime
            E -= delta
            if abs(delta) < tol:
                break
        return E
    elif abs(e - 1.0) < 1e-6:
        # Near-parabolic - use parabolic approximation (Barker's equation)
        # tan(ν/2) = D, M = D + D³/3
        # Cubic equation: D³ + 3D - 3M = 0
        W = 3.0 * M
        s = (W + math.sqrt(W * W + 1)) ** (1.0 / 3.0) if W >= 0 else -((abs(W) + math.sqrt(W * W + 1)) ** (1.0 / 3.0))
        D = s - 1.0 / s
        # Convert D (tan(ν/2)) to parabolic eccentric anomaly
        return 2.0 * math.atan(D)
    else:
        # Hyperbolic orbit - Newton-Raphson for H
        H = M
        for _ in range(max_iter):
            f = e * math.sinh(H) - H - M
            f_prime = e * math.cosh(H) - 1
            delta = f / f_prime
            H -= delta
            if abs(delta) < tol:
                break
        return H


def _compute_true_anomaly(eccentric_anomaly: float, eccentricity: float) -> float:
    """
    Compute true anomaly from eccentric/hyperbolic anomaly.

    Args:
        eccentric_anomaly: Eccentric (E) or hyperbolic (H) anomaly in radians
        eccentricity: Orbital eccentricity

    Returns:
        True anomaly in radians
    """
    e = eccentricity
    if e < 1.0:
        # Elliptic: tan(ν/2) = sqrt((1+e)/(1-e)) * tan(E/2)
        E = eccentric_anomaly
        factor = math.sqrt((1 + e) / (1 - e))
        return 2.0 * math.atan(factor * math.tan(E / 2.0))
    elif abs(e - 1.0) < 1e-6:
        # Parabolic: ν = eccentric_anomaly (already computed as 2*atan(D))
        return eccentric_anomaly
    else:
        # Hyperbolic: tan(ν/2) = sqrt((e+1)/(e-1)) * tanh(H/2)
        H = eccentric_anomaly
        factor = math.sqrt((e + 1) / (e - 1))
        return 2.0 * math.atan(factor * math.tanh(H / 2.0))


def _compute_radius(true_anomaly: float, perihelion_distance: float, eccentricity: float) -> float:
    """
    Compute heliocentric distance from true anomaly.

    r = q * (1 + e) / (1 + e * cos(ν))   for parabolic (e=1): r = 2q / (1 + cos(ν))

    Args:
        true_anomaly: True anomaly in radians
        perihelion_distance: Perihelion distance in AU
        eccentricity: Orbital eccentricity

    Returns:
        Heliocentric distance in AU
    """
    q = perihelion_distance
    e = eccentricity
    nu = true_anomaly

    if abs(e - 1.0) < 1e-6:
        # Parabolic
        return 2.0 * q / (1.0 + math.cos(nu))
    else:
        # General conic
        return q * (1.0 + e) / (1.0 + e * math.cos(nu))


def _orbital_to_heliocentric(
    true_anomaly: float,
    radius: float,
    arg_perihelion_rad: float,
    ascending_node_rad: float,
    inclination_rad: float,
) -> tuple[float, float, float]:
    """
    Convert orbital elements to heliocentric ecliptic coordinates.

    Args:
        true_anomaly: True anomaly in radians
        radius: Heliocentric distance in AU
        arg_perihelion_rad: Argument of perihelion in radians
        ascending_node_rad: Longitude of ascending node in radians
        inclination_rad: Orbital inclination in radians

    Returns:
        Tuple of (x, y, z) in heliocentric ecliptic coordinates (AU)
    """
    nu = true_anomaly
    r = radius
    omega = arg_perihelion_rad  # Argument of perihelion
    Omega = ascending_node_rad  # Longitude of ascending node
    i = inclination_rad  # Inclination

    # Position in orbital plane
    u = omega + nu  # Argument of latitude

    # Transform to heliocentric ecliptic
    cos_u = math.cos(u)
    sin_u = math.sin(u)
    cos_Omega = math.cos(Omega)
    sin_Omega = math.sin(Omega)
    cos_i = math.cos(i)
    sin_i = math.sin(i)

    x = r * (cos_Omega * cos_u - sin_Omega * sin_u * cos_i)
    y = r * (sin_Omega * cos_u + cos_Omega * sin_u * cos_i)
    z = r * (sin_u * sin_i)

    return x, y, z


def _get_earth_position(ts: Any, eph: Any, t: Any) -> tuple[float, float, float]:
    """
    Get Earth's heliocentric ecliptic position at time t.

    Args:
        ts: Skyfield timescale
        eph: Skyfield ephemeris
        t: Skyfield time

    Returns:
        Tuple of (x, y, z) in heliocentric ecliptic coordinates (AU)
    """
    sun = eph["sun"]
    earth = eph["earth"]

    # Get Earth's position relative to Sun
    earth_pos = sun.at(t).observe(earth)

    # Skyfield returns ICRS (equatorial); convert to ecliptic
    from skyfield.framelib import ecliptic_frame

    ecliptic_pos = earth_pos.frame_xyz(ecliptic_frame)
    x, y, z = ecliptic_pos.au

    return float(x), float(y), float(z)


def _ecliptic_to_equatorial(x: float, y: float, z: float, obliquity_rad: float) -> tuple[float, float, float]:
    """
    Convert ecliptic coordinates to equatorial coordinates.

    Args:
        x, y, z: Ecliptic coordinates
        obliquity_rad: Obliquity of the ecliptic in radians

    Returns:
        Tuple of (x_eq, y_eq, z_eq) in equatorial coordinates
    """
    cos_eps = math.cos(obliquity_rad)
    sin_eps = math.sin(obliquity_rad)

    x_eq = x
    y_eq = y * cos_eps - z * sin_eps
    z_eq = y * sin_eps + z * cos_eps

    return x_eq, y_eq, z_eq


def _cartesian_to_spherical(x: float, y: float, z: float) -> tuple[float, float, float]:
    """
    Convert Cartesian to spherical coordinates (RA/Dec).

    Args:
        x, y, z: Cartesian coordinates

    Returns:
        Tuple of (ra_hours, dec_degrees, distance)
    """
    r = math.sqrt(x * x + y * y + z * z)
    if r < 1e-15:
        return 0.0, 0.0, 0.0

    dec_rad = math.asin(z / r)
    ra_rad = math.atan2(y, x)

    # Normalize RA to 0-2π
    if ra_rad < 0:
        ra_rad += 2 * math.pi

    ra_hours = math.degrees(ra_rad) / 15.0  # Convert to hours
    dec_degrees = math.degrees(dec_rad)

    return ra_hours, dec_degrees, r


def compute_comet_position(
    comet: Comet,
    observer_lat: float,
    observer_lon: float,
    dt: datetime | None = None,
) -> CometPosition | None:
    """
    Compute comet position using Keplerian propagation.

    Uses the comet's orbital elements to compute its position at the given time,
    then transforms to observer-centric coordinates.

    Args:
        comet: Comet with orbital elements
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        dt: Datetime to compute position for (default: now UTC)

    Returns:
        CometPosition with RA/Dec, Alt/Az, distances, or None if cannot compute
    """
    # Check if we have required orbital elements
    if (
        comet.eccentricity is None
        or comet.inclination_deg is None
        or comet.arg_perihelion_deg is None
        or comet.ascending_node_deg is None
        or comet.perihelion_time is None
    ):
        logger.debug(f"Comet {comet.name} missing orbital elements, cannot propagate")
        return None

    # Ensure we have perihelion distance
    q = comet.perihelion_distance_au
    if q is None or q <= 0:
        logger.debug(f"Comet {comet.name} missing perihelion distance")
        return None

    try:
        from celestron_nexstar.api.ephemeris.skyfield_utils import (
            get_skyfield_ephemeris,
            get_skyfield_timescale,
        )

        ts = get_skyfield_timescale()

        # Load ephemeris for Earth position
        try:
            eph = get_skyfield_ephemeris("de421.bsp")
        except FileNotFoundError:
            eph = get_skyfield_ephemeris("de440s.bsp")

        # Handle datetime
        if dt is None:
            dt = datetime.now(UTC)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        t = ts.from_datetime(dt)

        # Get orbital elements in radians
        e = comet.eccentricity
        i_rad = math.radians(comet.inclination_deg)
        omega_rad = math.radians(comet.arg_perihelion_deg)
        Omega_rad = math.radians(comet.ascending_node_deg)

        # Compute time since perihelion
        T = comet.perihelion_time
        T = T.replace(tzinfo=UTC) if T.tzinfo is None else T.astimezone(UTC)

        delta_t = (dt - T).total_seconds() / 86400.0  # Days since perihelion

        # Compute mean motion (n) in radians/day
        # For elliptic orbits: n = sqrt(GM/a³) where GM = k² (Gaussian gravitational constant)
        # k ≈ 0.01720209895 AU^(3/2) / day
        k = 0.01720209895

        if e < 1.0:
            # Elliptic: compute semi-major axis from q and e
            a = q / (1.0 - e)
            n = k / (a**1.5)  # radians/day
            M = n * delta_t  # Mean anomaly
        elif abs(e - 1.0) < 1e-6:
            # Parabolic: use different formulation
            # M = k * (t - T) / (2 * q^1.5)
            # Actually for parabolic, we directly compute true anomaly
            M = k * delta_t / (2.0 * q**1.5)
        else:
            # Hyperbolic: n = k * sqrt(-1/a³) where a = q / (1 - e) < 0
            a = q / (1.0 - e)  # Negative for hyperbolic
            n = k / ((-a) ** 1.5)
            M = n * delta_t

        # Solve Kepler's equation
        E = solve_kepler(M, e)

        # Compute true anomaly
        nu = _compute_true_anomaly(E, e)

        # Compute heliocentric distance
        r = _compute_radius(nu, q, e)

        # Convert to heliocentric ecliptic coordinates
        x_ecl, y_ecl, z_ecl = _orbital_to_heliocentric(nu, r, omega_rad, Omega_rad, i_rad)

        # Get Earth's position
        x_earth, y_earth, z_earth = _get_earth_position(ts, eph, t)

        # Geocentric ecliptic position
        dx = x_ecl - x_earth
        dy = y_ecl - y_earth
        dz = z_ecl - z_earth

        # Geocentric distance
        delta = math.sqrt(dx * dx + dy * dy + dz * dz)

        # Convert ecliptic to equatorial
        # Obliquity for J2000: 23.4392911 degrees
        obliquity = math.radians(23.4392911)
        x_eq, y_eq, z_eq = _ecliptic_to_equatorial(dx, dy, dz, obliquity)

        # Convert to RA/Dec
        ra_hours, dec_degrees, _ = _cartesian_to_spherical(x_eq, y_eq, z_eq)

        # Compute elongation (angle from Sun)
        # Get Sun's position from Earth
        sun = eph["sun"]
        earth = eph["earth"]
        sun_astrometric = earth.at(t).observe(sun)
        sun_ra, sun_dec, _ = sun_astrometric.radec()

        # Angular separation
        from celestron_nexstar.api.core.utils import angular_separation

        elongation = angular_separation(ra_hours, dec_degrees, sun_ra.hours, sun_dec.degrees)

        # Compute phase angle (Sun-Comet-Earth angle)
        # Using law of cosines: cos(phase) = (r² + Δ² - R²) / (2rΔ)
        # where R is Earth-Sun distance
        R = math.sqrt(x_earth * x_earth + y_earth * y_earth + z_earth * z_earth)
        cos_phase = (r * r + delta * delta - R * R) / (2 * r * delta) if r * delta > 0 else 0
        cos_phase = max(-1.0, min(1.0, cos_phase))
        phase_angle = math.degrees(math.acos(cos_phase))

        # Convert RA/Dec to Alt/Az for observer
        from celestron_nexstar.api.core.utils import ra_dec_to_alt_az

        azimuth, altitude = ra_dec_to_alt_az(ra_hours, dec_degrees, observer_lat, observer_lon, dt)

        return CometPosition(
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
            altitude_deg=altitude,
            azimuth_deg=azimuth,
            helio_distance_au=r,
            geo_distance_au=delta,
            elongation_deg=elongation,
            phase_angle_deg=phase_angle,
        )

    except Exception as e:
        logger.warning(f"Error computing position for comet {comet.name}: {e}")
        return None


def compute_comet_magnitude(
    comet: Comet,
    helio_distance_au: float,
    geo_distance_au: float,
) -> float:
    """
    Compute comet apparent magnitude using H/G photometric model.

    Uses the formula: m = H + 5*log10(Δ) + k*log10(r)
    where H is absolute magnitude, k is slope parameter, Δ is geocentric
    distance, and r is heliocentric distance.

    Falls back to peak_magnitude if H/k not available.

    Args:
        comet: Comet with photometric parameters
        helio_distance_au: Heliocentric distance in AU
        geo_distance_au: Geocentric distance in AU

    Returns:
        Apparent magnitude
    """
    r = helio_distance_au
    delta = geo_distance_au

    if r <= 0 or delta <= 0:
        return comet.peak_magnitude

    # Check if we have H and k (slope_g)
    H = comet.absolute_magnitude_h
    k = comet.slope_g

    if H is not None:
        # Use H/k photometric model
        # Default k to 4.0 if not specified (typical for comets)
        if k is None:
            k = 4.0

        # m = H + 5*log10(Δ) + 2.5*k*log10(r)
        # Note: Some sources use k directly, others use 2.5*k
        # MPC typically uses: m = H + 5*log10(Δ) + k*log10(r)
        magnitude = H + 5.0 * math.log10(delta) + k * math.log10(r)
        return magnitude
    else:
        # Fallback to simple model based on perihelion
        return comet.peak_magnitude


def find_best_visibility_window(
    comet: Comet,
    observer_lat: float,
    observer_lon: float,
    start_date: datetime | None = None,
    days_window: int = 180,
    sample_interval_days: int = 7,
    max_magnitude: float = 10.0,
    min_altitude_deg: float = 15.0,
    min_elongation_deg: float = 20.0,
) -> list[tuple[datetime, CometPosition, float]]:
    """
    Find the best visibility windows for a comet.

    Samples the comet's position over a time window and returns dates when
    the comet is visible (above horizon, adequate elongation, bright enough).

    Args:
        comet: Comet to analyze
        observer_lat: Observer latitude in degrees
        observer_lon: Observer longitude in degrees
        start_date: Start of search window (default: now)
        days_window: Number of days to search
        sample_interval_days: Days between samples
        max_magnitude: Maximum (dimmest) magnitude to include
        min_altitude_deg: Minimum altitude above horizon
        min_elongation_deg: Minimum elongation from Sun

    Returns:
        List of (datetime, CometPosition, magnitude) tuples for visible dates,
        sorted by brightness (brightest first)
    """
    if start_date is None:
        start_date = datetime.now(UTC)
    elif start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=UTC)

    results: list[tuple[datetime, CometPosition, float]] = []

    current = start_date
    end_date = start_date + timedelta(days=days_window)

    while current <= end_date:
        pos = compute_comet_position(comet, observer_lat, observer_lon, current)

        if pos is not None:
            mag = compute_comet_magnitude(comet, pos.helio_distance_au, pos.geo_distance_au)

            # Check visibility criteria
            if (
                mag <= max_magnitude
                and pos.altitude_deg >= min_altitude_deg
                and pos.elongation_deg >= min_elongation_deg
            ):
                results.append((current, pos, mag))

        current += timedelta(days=sample_interval_days)

    # Sort by magnitude (brightest first)
    results.sort(key=lambda x: x[2])

    return results
