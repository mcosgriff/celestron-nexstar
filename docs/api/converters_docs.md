# Coordinate Converters (`converters.py`)

## Overview

This module provides a `CoordinateConverter` class with static methods for various coordinate conversions required for telescope operations. These methods handle conversions between different units (e.g., hours to degrees) and formats (e.g., signed to unsigned) used by the telescope's protocol.

## `CoordinateConverter` Class

This class contains static methods for all conversion tasks.

### Right Ascension (RA) Conversions

- **`ra_hours_to_degrees(ra_hours: float)`**: Converts RA from hours (0-24) to degrees (0-360).
- **`ra_degrees_to_hours(ra_degrees: float)`**: Converts RA from degrees (0-360) to hours (0-24).

### Declination (Dec) Conversions

- **`dec_to_unsigned(dec_degrees: float)`**: Converts Dec from a signed format (-90 to +90) to an unsigned format (0-360). The telescope protocol represents negative declinations as values greater than 180 degrees.
- **`dec_to_signed(dec_degrees: float)`**: Converts Dec from an unsigned format (0-360) back to a signed format (-90 to +90).

### Altitude Conversions

- **`altitude_to_unsigned(altitude: float)`**: Converts altitude from a signed format (-90 to +90) to an unsigned format (0-360).
- **`altitude_to_signed(altitude: float)`**: Converts altitude from an unsigned format (0-360) back to a signed format (-90 to +90).

### Geographic Location Conversions

- **`location_to_unsigned(coordinate: float)`**: Converts a geographic coordinate (latitude or longitude) from signed (-180 to +180) to unsigned (0-360) format.
- **`location_to_signed(coordinate: float)`**: Converts a geographic coordinate from unsigned (0-360) to signed (-180 to +180) format.
