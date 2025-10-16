# Astronomical Utilities (`utils.py`)

## Overview

This module provides a collection of utility functions for astronomical calculations and coordinate conversions. These functions are essential for converting between different coordinate systems (e.g., Alt/Az to RA/Dec) and for formatting coordinates into human-readable strings.

## Coordinate Conversion Functions

- **`ra_to_degrees(hours, minutes, seconds)`**: Converts Right Ascension (RA) from H/M/S to decimal degrees.
- **`ra_to_hours(hours, minutes, seconds)`**: Converts RA from H/M/S to decimal hours.
- **`dec_to_degrees(degrees, minutes, seconds, sign)`**: Converts Declination (Dec) from D/M/S to decimal degrees.
- **`degrees_to_dms(degrees)`**: Converts decimal degrees to a tuple of (degrees, minutes, seconds, sign).
- **`hours_to_hms(hours)`**: Converts decimal hours to a tuple of (hours, minutes, seconds).

## Coordinate System Transformations

- **`alt_az_to_ra_dec(azimuth, altitude, latitude, longitude, utc_time)`**: Converts horizontal coordinates (Alt/Az) to equatorial coordinates (RA/Dec). This requires the observer's location and the current UTC time.
- **`ra_dec_to_alt_az(ra_hours, dec_degrees, latitude, longitude, utc_time)`**: Converts equatorial coordinates (RA/Dec) to horizontal coordinates (Alt/Az).

## Time and Angular Calculations

- **`calculate_lst(longitude, utc_time)`**: Calculates the Local Sidereal Time (LST) for a given longitude and UTC time.
- **`calculate_julian_date(dt)`**: Calculates the Julian Date from a `datetime` object.
- **`angular_separation(ra1, dec1, ra2, dec2)`**: Computes the angular separation in degrees between two celestial coordinates.

## Formatting Functions

- **`format_ra(hours, precision)`**: Formats RA in decimal hours into a readable string (e.g., "12h 34m 56.78s").
- **`format_dec(degrees, precision)`**: Formats Dec in decimal degrees into a readable string (e.g., "+45° 12' 34.5\"").
- **`format_position(ra_hours, dec_degrees)`**: Formats a full celestial position into a single readable string.
