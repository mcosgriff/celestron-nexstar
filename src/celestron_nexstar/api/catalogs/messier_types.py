"""
Messier Object Type Mappings.

Maps abbreviated type codes from messier.min.geojson to human-readable names.
"""

from __future__ import annotations


__all__ = ["MESSIER_TYPE_MAP", "get_messier_type_name"]


# Mapping from messier.min.geojson type codes to human-readable names
MESSIER_TYPE_MAP: dict[str, str] = {
    # Clusters
    "gc": "Globular Cluster",
    "oc": "Open Cluster",
    # Nebulae
    "snr": "Supernova Remnant",
    "sfr": "Star Forming Region",
    "pn": "Planetary Nebula",
    "bn": "Bright Nebula",
    "en": "Emission Nebula",
    "rn": "Reflection Nebula",
    "dn": "Dark Nebula",
    "nb": "Nebula",
    # Galaxies
    "s": "Spiral Galaxy",
    "e": "Elliptical Galaxy",
    "i": "Irregular Galaxy",
    "gg": "Galaxy",
    # Other
    "pos": "Asterism",
    "patch": "Milky Way Patch",
}


def get_messier_type_name(type_code: str | None) -> str:
    """
    Get human-readable type name for a Messier object type code.

    Args:
        type_code: Abbreviated type code from messier.min.geojson

    Returns:
        Human-readable type name, or "Unknown" if not found

    Examples:
        >>> get_messier_type_name("gc")
        'Globular Cluster'
        >>> get_messier_type_name("snr")
        'Supernova Remnant'
        >>> get_messier_type_name("s")
        'Spiral Galaxy'
    """
    if not type_code:
        return "Unknown"

    return MESSIER_TYPE_MAP.get(type_code.lower(), "Unknown")
