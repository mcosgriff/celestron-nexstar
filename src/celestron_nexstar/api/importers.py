"""
Catalog Import Utilities

Business logic for parsing and importing catalog data from various sources.
"""

from __future__ import annotations

from .enums import CelestialObjectType


def parse_ra_dec(ra_str: str, dec_str: str) -> tuple[float, float] | None:
    """
    Parse RA/Dec from OpenNGC format.

    RA format: HH:MM:SS.ss
    Dec format: ±DD:MM:SS.s

    Returns:
        (ra_hours, dec_degrees) or None if invalid
    """
    try:
        # Parse RA (HH:MM:SS.ss → hours)
        ra_parts = ra_str.split(":")
        ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60 + float(ra_parts[2]) / 3600

        # Parse Dec (±DD:MM:SS.s → degrees)
        dec_sign = 1 if not dec_str.startswith("-") else -1
        dec_str_abs = dec_str.lstrip("+-")
        dec_parts = dec_str_abs.split(":")
        dec_degrees = dec_sign * (float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600)

        return ra_hours, dec_degrees

    except (ValueError, IndexError):
        return None


def map_openngc_type(type_str: str) -> CelestialObjectType:
    """
    Map OpenNGC type codes to CelestialObjectType.

    OpenNGC types:
        * or ** = Star
        *Ass = Association of stars
        OCl = Open cluster
        GCl = Globular cluster
        Cl+N = Cluster with nebulosity
        G = Galaxy
        GPair = Galaxy pair
        GTrpl = Galaxy triplet
        GGroup = Group of galaxies
        PN = Planetary nebula
        HII = HII ionized region
        DrkN = Dark nebula
        EmN = Emission nebula
        Neb = Generic nebula
        RfN = Reflection nebula
        SNR = Supernova remnant
        Nova = Nova star
    """
    type_map = {
        "*": CelestialObjectType.STAR,
        "**": CelestialObjectType.DOUBLE_STAR,
        "*Ass": CelestialObjectType.CLUSTER,
        "OCl": CelestialObjectType.CLUSTER,
        "GCl": CelestialObjectType.CLUSTER,
        "Cl+N": CelestialObjectType.CLUSTER,
        "G": CelestialObjectType.GALAXY,
        "GPair": CelestialObjectType.GALAXY,
        "GTrpl": CelestialObjectType.GALAXY,
        "GGroup": CelestialObjectType.GALAXY,
        "PN": CelestialObjectType.NEBULA,
        "HII": CelestialObjectType.NEBULA,
        "DrkN": CelestialObjectType.NEBULA,
        "EmN": CelestialObjectType.NEBULA,
        "Neb": CelestialObjectType.NEBULA,
        "RfN": CelestialObjectType.NEBULA,
        "SNR": CelestialObjectType.NEBULA,
        "Nova": CelestialObjectType.STAR,
    }

    return type_map.get(type_str, CelestialObjectType.NEBULA)  # Default to nebula


def parse_catalog_number(name: str, catalog: str) -> int | None:
    """
    Extract numeric catalog number from name.

    Examples:
        M31 → 31
        NGC 224 → 224
        IC 1101 → 1101
    """
    prefixes = ["M", "NGC", "IC", "C"]  # Messier, NGC, IC, Caldwell

    name_upper = name.upper().strip()

    for prefix in prefixes:
        if name_upper.startswith(prefix):
            # Extract numeric part
            num_str = name_upper[len(prefix) :].strip()
            try:
                return int(num_str)
            except ValueError:
                # Handle cases like "NGC 224A"
                digits = ""
                for char in num_str:
                    if char.isdigit():
                        digits += char
                    else:
                        break
                if digits:
                    return int(digits)

    return None
