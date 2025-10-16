# Library Initialization (`__init__.py`)

## Overview

This file serves as the main entry point for the `celestron_nexstar` library. It imports the key classes, functions, and types from the various modules, making them directly accessible to users of the library.

## Exposed Components

The `__all__` variable in this file defines the public API of the library. The following components are exposed:

### Main Telescope Class
- **`NexStarTelescope`**: The primary class for interacting with the telescope.

### Type Definitions
- `TrackingMode`, `AlignmentMode`
- `EquatorialCoordinates`, `HorizontalCoordinates`
- `GeographicLocation`
- `TelescopeInfo`, `TelescopeTime`, `TelescopeConfig`

### Exceptions
- `NexStarError` (base exception)
- `TelescopeConnectionError`, `TelescopeTimeoutError`
- `InvalidCoordinateError`, `CommandError`, `NotConnectedError`

### Coordinate Conversion and Astronomical Utilities
- A suite of functions for converting, calculating, and formatting astronomical coordinates, such as `ra_to_hours`, `dec_to_degrees`, `calculate_lst`, and `alt_az_to_ra_dec`.

### Coordinate Converter Class
- **`CoordinateConverter`**: The internal helper class for coordinate conversions.
