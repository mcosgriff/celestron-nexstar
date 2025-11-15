"""
Color Mapping Functions for Observing Conditions

Functions for mapping observing condition values to colors for display.
These functions match the color schemes used by Clear Sky Chart and are
designed to be reusable across CLI, TUI, and other interfaces.
"""

from __future__ import annotations


def get_darkness_color(magnitude: float | None) -> tuple[str, str]:
    """
    Get color for darkness/limiting magnitude.

    Uses a 15-level gradient matching Clear Sky Chart colors.
    Darker skies (higher magnitude) are shown in darker colors.

    Args:
        magnitude: Limiting magnitude at zenith (None for daytime)

    Returns:
        Tuple of (color_name_or_hex, label_string)
    """
    if magnitude is None:
        return ("white", "Day")
    elif magnitude >= 6.5:
        return ("#000000", "6.5")
    elif magnitude >= 6.0:
        return ("#000010", "6.0")
    elif magnitude >= 5.5:
        return ("#000020", "5.5")
    elif magnitude >= 5.0:
        return ("#000040", "5.0")
    elif magnitude >= 4.5:
        return ("#000060", "4.5")
    elif magnitude >= 4.0:
        return ("#000080", "4.0")
    elif magnitude >= 3.5:
        return ("#0000A0", "3.5")
    elif magnitude >= 3.0:
        return ("#0000C0", "3.0")
    elif magnitude >= 2.0:
        return ("#0080C0", "2.0")
    elif magnitude >= 1.0:
        return ("#00C0C0", "1.0")
    elif magnitude >= 0.0:
        return ("#40E0E0", "0")
    elif magnitude >= -1.0:
        return ("#80E0E0", "-1")
    elif magnitude >= -2.0:
        return ("#C0E0C0", "-2")
    elif magnitude >= -3.0:
        return ("#FFFF80", "-3")
    elif magnitude >= -4.0:
        return ("#FFFFC0", "-4")
    else:
        return ("white", "Day")


def get_wind_color(wind_mph: float | None) -> tuple[str, str]:
    """
    Get color for wind speed.

    Uses a 6-level gradient matching Clear Sky Chart colors.
    Lower wind speeds are better for observing.

    Args:
        wind_mph: Wind speed in miles per hour (None if unavailable)

    Returns:
        Tuple of (color_name_or_hex, label_string)
    """
    if wind_mph is None:
        return ("dim", "-")
    elif wind_mph > 45:
        return ("white", ">45 mph")
    elif wind_mph >= 29:
        return ("#E0E0E0", "29-45 mph")
    elif wind_mph >= 17:
        return ("#80C0E0", "17-28 mph")
    elif wind_mph >= 12:
        return ("#4080C0", "12-16 mph")
    elif wind_mph >= 6:
        return ("#2060A0", "6-11 mph")
    else:
        return ("#004080", "0-5 mph")


def get_humidity_color(humidity_percent: float | None) -> tuple[str, str]:
    """
    Get color for humidity.

    Uses a 16-level gradient matching Clear Sky Chart colors.
    Lower humidity is better for transparency.

    Args:
        humidity_percent: Humidity percentage (0-100, None if unavailable)

    Returns:
        Tuple of (color_name_or_hex, label_string)
    """
    if humidity_percent is None:
        return ("dim", "-")
    elif humidity_percent >= 95:
        return ("#800000", "95-100%")
    elif humidity_percent >= 90:
        return ("#A00000", "90-95%")
    elif humidity_percent >= 85:
        return ("#FF0000", "85-90%")
    elif humidity_percent >= 80:
        return ("#FF4400", "80-85%")
    elif humidity_percent >= 75:
        return ("#FF8800", "75-80%")
    elif humidity_percent >= 70:
        return ("#FFFF00", "70-75%")
    elif humidity_percent >= 65:
        return ("#80FF00", "65-70%")
    elif humidity_percent >= 60:
        return ("#00FF00", "60-65%")
    elif humidity_percent >= 55:
        return ("#00FF80", "55-60%")
    elif humidity_percent >= 50:
        return ("#00FFFF", "50-55%")
    elif humidity_percent >= 45:
        return ("#00AAFF", "45-50%")
    elif humidity_percent >= 40:
        return ("#0080FF", "40-45%")
    elif humidity_percent >= 35:
        return ("#0066FF", "35-40%")
    elif humidity_percent >= 30:
        return ("#0044FF", "30-35%")
    elif humidity_percent >= 25:
        return ("#0022FF", "25-30%")
    else:
        return ("#0000FF", "<25%")


def get_temperature_color(temperature_f: float | None) -> tuple[str, str]:
    """
    Get color for temperature.

    Uses a 19-level gradient matching Clear Sky Chart colors.
    Temperature affects comfort and equipment performance.

    Args:
        temperature_f: Temperature in Fahrenheit (None if unavailable)

    Returns:
        Tuple of (color_name_or_hex, label_string)
    """
    if temperature_f is None:
        return ("dim", "-")
    elif temperature_f > 113:
        return ("#808080", ">113°F")
    elif temperature_f >= 104:
        return ("#800000", "104-113°F")
    elif temperature_f >= 95:
        return ("#A00000", "95-104°F")
    elif temperature_f >= 86:
        return ("#FF0000", "86-95°F")
    elif temperature_f >= 77:
        return ("#FF4400", "77-86°F")
    elif temperature_f >= 68:
        return ("#FF8800", "68-77°F")
    elif temperature_f >= 59:
        return ("#FFAA00", "59-68°F")
    elif temperature_f >= 50:
        return ("#FFFF00", "50-59°F")
    elif temperature_f >= 41:
        return ("#80FF00", "41-50°F")
    elif temperature_f >= 32:
        return ("#00FF80", "32-41°F")
    elif temperature_f >= 23:
        return ("white", "23-32°F")
    elif temperature_f >= 14:
        return ("#00FFAA", "14-23°F")
    elif temperature_f >= 5:
        return ("#00FFFF", "5-14°F")
    elif temperature_f >= -3:
        return ("#0080FF", "-3-5°F")
    elif temperature_f >= -12:
        return ("#0066FF", "-12--3°F")
    elif temperature_f >= -21:
        return ("#0044FF", "-21--12°F")
    elif temperature_f >= -30:
        return ("#0022FF", "-30--21°F")
    elif temperature_f >= -40:
        return ("#0000FF", "-40--31°F")
    else:
        return ("#FF00FF", "< -40°F")
