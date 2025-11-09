"""
Compass Direction Utilities

Converts azimuth angles to compass directions and formats sky positions
for human-readable observing instructions.
"""

from __future__ import annotations


__all__ = [
    "azimuth_to_compass_8point",
    "azimuth_to_compass_16point",
    "format_altitude_description",
    "format_sky_position",
]


def azimuth_to_compass_8point(azimuth_deg: float) -> str:
    """
    Convert azimuth angle to 8-point compass direction.

    Args:
        azimuth_deg: Azimuth in degrees (0° = North, 90° = East, 180° = South, 270° = West)

    Returns:
        Compass direction: N, NE, E, SE, S, SW, W, or NW

    Examples:
        >>> azimuth_to_compass_8point(0)
        'N'
        >>> azimuth_to_compass_8point(45)
        'NE'
        >>> azimuth_to_compass_8point(180)
        'S'
    """
    # Normalize to 0-360 range
    azimuth_deg = azimuth_deg % 360

    # Define compass points with their angular ranges
    # Each point covers 45 degrees, centered on the cardinal/intercardinal direction
    compass_points = [
        (22.5, "N"),
        (67.5, "NE"),
        (112.5, "E"),
        (157.5, "SE"),
        (202.5, "S"),
        (247.5, "SW"),
        (292.5, "W"),
        (337.5, "NW"),
        (360.0, "N"),  # Wrap around
    ]

    for angle_limit, direction in compass_points:
        if azimuth_deg < angle_limit:
            return direction

    return "N"  # Fallback (shouldn't reach here)


def azimuth_to_compass_16point(azimuth_deg: float) -> str:
    """
    Convert azimuth angle to 16-point compass direction.

    Provides finer directional precision with points like NNE, ENE, etc.

    Args:
        azimuth_deg: Azimuth in degrees (0° = North, 90° = East)

    Returns:
        Compass direction: N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, or NNW

    Examples:
        >>> azimuth_to_compass_16point(22.5)
        'NNE'
        >>> azimuth_to_compass_16point(67.5)
        'ENE'
    """
    # Normalize to 0-360 range
    azimuth_deg = azimuth_deg % 360

    # Define 16 compass points, each covering 22.5 degrees
    compass_points = [
        (11.25, "N"),
        (33.75, "NNE"),
        (56.25, "NE"),
        (78.75, "ENE"),
        (101.25, "E"),
        (123.75, "ESE"),
        (146.25, "SE"),
        (168.75, "SSE"),
        (191.25, "S"),
        (213.75, "SSW"),
        (236.25, "SW"),
        (258.75, "WSW"),
        (281.25, "W"),
        (303.75, "WNW"),
        (326.25, "NW"),
        (348.75, "NNW"),
        (360.0, "N"),  # Wrap around
    ]

    for angle_limit, direction in compass_points:
        if azimuth_deg < angle_limit:
            return direction

    return "N"  # Fallback


def format_altitude_description(altitude_deg: float) -> str:
    """
    Convert altitude angle to descriptive text.

    Args:
        altitude_deg: Altitude in degrees (0° = horizon, 90° = zenith)

    Returns:
        Human-readable description of altitude

    Examples:
        >>> format_altitude_description(5)
        'just above the horizon'
        >>> format_altitude_description(45)
        'halfway up the sky'
        >>> format_altitude_description(85)
        'nearly overhead'
    """
    if altitude_deg < 0:
        return "below the horizon"
    elif altitude_deg < 10:
        return "just above the horizon"
    elif altitude_deg < 20:
        return "low in the sky"
    elif altitude_deg < 40:
        return "about one-third up the sky"
    elif altitude_deg < 50:
        return "halfway up the sky"
    elif altitude_deg < 70:
        return "high in the sky"
    elif altitude_deg < 80:
        return "very high in the sky"
    else:
        return "nearly overhead"


def format_sky_position(
    azimuth_deg: float,
    altitude_deg: float,
    use_16point: bool = False,
    include_degrees: bool = True,
) -> str:
    """
    Format complete sky position with compass direction and altitude.

    Args:
        azimuth_deg: Azimuth in degrees (0° = North, 90° = East)
        altitude_deg: Altitude in degrees (0° = horizon, 90° = zenith)
        use_16point: Use 16-point compass (more precise) instead of 8-point
        include_degrees: Include numeric degrees in output

    Returns:
        Human-readable sky position description

    Examples:
        >>> format_sky_position(45, 30)
        'Look NE at 45°, 30° above horizon'
        >>> format_sky_position(180, 60, use_16point=True, include_degrees=False)
        'Look S, high in the sky'
    """
    # Get compass direction
    direction = azimuth_to_compass_16point(azimuth_deg) if use_16point else azimuth_to_compass_8point(azimuth_deg)

    # Get altitude description
    alt_desc = format_altitude_description(altitude_deg)

    # Format output
    if include_degrees:
        return f"Look {direction} at {azimuth_deg:.0f}°, {altitude_deg:.0f}° above horizon"
    else:
        return f"Look {direction}, {alt_desc}"


def format_object_path(
    rise_azimuth_deg: float,
    max_azimuth_deg: float,
    max_altitude_deg: float,
    set_azimuth_deg: float,
) -> str:
    """
    Format the path an object takes across the sky.

    Useful for describing satellite passes, meteor shower radiants, etc.

    Args:
        rise_azimuth_deg: Azimuth where object rises
        max_azimuth_deg: Azimuth at maximum altitude
        max_altitude_deg: Maximum altitude reached
        set_azimuth_deg: Azimuth where object sets

    Returns:
        Human-readable path description

    Example:
        >>> format_object_path(225, 180, 60, 135)
        'Rises SW, peaks S at 60° high, sets SE'
    """
    rise_dir = azimuth_to_compass_8point(rise_azimuth_deg)
    max_dir = azimuth_to_compass_8point(max_azimuth_deg)
    set_dir = azimuth_to_compass_8point(set_azimuth_deg)

    return f"Rises {rise_dir}, peaks {max_dir} at {max_altitude_deg:.0f}° high, sets {set_dir}"
