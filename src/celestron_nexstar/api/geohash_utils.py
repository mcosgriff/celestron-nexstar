"""
Geohash utilities for spatial indexing.

Geohash encodes geographic coordinates into short strings that can be used for
hierarchical spatial indexing and proximity searches. Points with similar geohashes
are geographically close together.

Reference: https://en.wikipedia.org/wiki/Geohash
"""

from __future__ import annotations


# Geohash base32 alphabet (excludes a, i, l, o to avoid confusion)
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(latitude: float, longitude: float, precision: int = 12) -> str:
    """
    Encode latitude and longitude into a geohash string.

    Args:
        latitude: Latitude in degrees (-90 to 90)
        longitude: Longitude in degrees (-180 to 180)
        precision: Number of characters in geohash (1-12, default: 12)
                  Each character adds ~5 bits of precision
                  - 1 char: ~5000km
                  - 5 chars: ~5km
                  - 7 chars: ~150m
                  - 9 chars: ~5m
                  - 12 chars: ~0.6cm

    Returns:
        Geohash string

    Example:
        >>> encode(48.8566, 2.3522, 7)
        'u09tvqr'
    """
    # Clamp coordinates to valid ranges
    lat = max(-90.0, min(90.0, latitude))
    lon = max(-180.0, min(180.0, longitude))

    # Even bits are longitude, odd bits are latitude
    bits = 0
    bit_count = 0
    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0

    geohash: list[str] = []

    while len(geohash) < precision:
        if bit_count % 2 == 0:  # Even bit: longitude
            mid = (lon_min + lon_max) / 2.0
            if lon >= mid:
                bits = bits * 2 + 1
                lon_min = mid
            else:
                bits = bits * 2
                lon_max = mid
        else:  # Odd bit: latitude
            mid = (lat_min + lat_max) / 2.0
            if lat >= mid:
                bits = bits * 2 + 1
                lat_min = mid
            else:
                bits = bits * 2
                lat_max = mid

        bit_count += 1

        # Every 5 bits, encode to base32 character
        if bit_count % 5 == 0:
            geohash.append(GEOHASH_ALPHABET[bits])
            bits = 0

    return "".join(geohash)


def decode(geohash: str) -> tuple[float, float, float, float]:
    """
    Decode a geohash string into latitude and longitude bounds.

    Args:
        geohash: Geohash string

    Returns:
        Tuple of (latitude, longitude, lat_error, lon_error)
        where errors are the precision of the bounding box

    Example:
        >>> decode('u09tvqr')
        (48.8566..., 2.3522..., 0.000686..., 0.001373...)
    """
    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0
    lat_err = 90.0
    lon_err = 180.0

    is_even = True

    for char in geohash:
        if char not in GEOHASH_ALPHABET:
            raise ValueError(f"Invalid geohash character: {char}")

        idx = GEOHASH_ALPHABET.index(char)

        # Decode 5 bits
        for mask in [16, 8, 4, 2, 1]:
            if is_even:  # Longitude bit
                lon_err /= 2.0
                if idx & mask:
                    lon_min = (lon_min + lon_max) / 2.0
                else:
                    lon_max = (lon_min + lon_max) / 2.0
            else:  # Latitude bit
                lat_err /= 2.0
                if idx & mask:
                    lat_min = (lat_min + lat_max) / 2.0
                else:
                    lat_max = (lat_min + lat_max) / 2.0
            is_even = not is_even

    # Return center point and errors
    lat = (lat_min + lat_max) / 2.0
    lon = (lon_min + lon_max) / 2.0

    return lat, lon, lat_err, lon_err


def neighbors(geohash: str) -> list[str]:
    """
    Get the 8 neighboring geohashes (north, south, east, west, and diagonals).

    Args:
        geohash: Geohash string

    Returns:
        List of 8 neighboring geohash strings
    """
    lat, lon, lat_err, lon_err = decode(geohash)

    # Calculate offsets for neighbors
    neighbors_list = []
    for dlat in [-lat_err, 0, lat_err]:
        for dlon in [-lon_err, 0, lon_err]:
            if dlat == 0 and dlon == 0:
                continue  # Skip center point
            neighbor_lat = lat + dlat
            neighbor_lon = lon + dlon
            # Clamp to valid ranges
            neighbor_lat = max(-90.0, min(90.0, neighbor_lat))
            neighbor_lon = max(-180.0, min(180.0, neighbor_lon))
            neighbors_list.append(encode(neighbor_lat, neighbor_lon, len(geohash)))

    return neighbors_list


def get_precision_for_radius(radius_km: float) -> int:
    """
    Get recommended geohash precision for a given search radius.

    Args:
        radius_km: Search radius in kilometers

    Returns:
        Recommended geohash precision (number of characters)

    Precision guide:
        - 1 char: ~5000km
        - 2 chars: ~1250km
        - 3 chars: ~156km
        - 4 chars: ~39km
        - 5 chars: ~5km
        - 6 chars: ~1.2km
        - 7 chars: ~150m
        - 8 chars: ~38m
        - 9 chars: ~5m
    """
    # Approximate precision based on radius
    # Each character reduces the area by ~32x
    if radius_km >= 5000:
        return 1
    elif radius_km >= 1250:
        return 2
    elif radius_km >= 156:
        return 3
    elif radius_km >= 39:
        return 4
    elif radius_km >= 5:
        return 5
    elif radius_km >= 1.2:
        return 6
    elif radius_km >= 0.15:
        return 7
    elif radius_km >= 0.038:
        return 8
    else:
        return 9


def get_neighbors_for_search(geohash: str, radius_km: float) -> list[str]:
    """
    Get geohash prefixes to search for points within a given radius.

    This includes the geohash itself and its neighbors at the appropriate precision.

    Args:
        geohash: Geohash string for the search center
        radius_km: Search radius in kilometers

    Returns:
        List of geohash prefixes to search
    """
    # Determine precision based on radius
    precision = get_precision_for_radius(radius_km)

    # Truncate geohash to desired precision
    search_geohash = geohash[:precision] if len(geohash) >= precision else geohash

    # Get neighbors at this precision
    neighbor_hashes = neighbors(search_geohash)

    # Include the center geohash
    search_hashes = [search_geohash, *neighbor_hashes]

    # Remove duplicates
    return list(dict.fromkeys(search_hashes))
