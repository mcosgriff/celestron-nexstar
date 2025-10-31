# Telescope Data Types (`types.py`)

## Overview

This module defines the data structures and enumerations used throughout the telescope control library. These types provide a clear and consistent way to represent telescope states, coordinates, and configuration.

## Enumerations

### `TrackingMode`

Represents the telescope's tracking modes.

- `OFF`: No tracking.
- `ALT_AZ`: Alt-Az tracking for terrestrial or casual observing.
- `EQ_NORTH`: Equatorial tracking for the Northern Hemisphere.
- `EQ_SOUTH`: Equatorial tracking for the Southern Hemisphere.

### `AlignmentMode`

Represents the telescope's alignment modes.

- `NO_ALIGNMENT`: No alignment has been performed.
- `ONE_STAR`: Basic one-star alignment.
- `TWO_STAR`: Recommended two-star alignment.
- `THREE_STAR`: Three-star alignment for the best accuracy.

## Data Classes

### `EquatorialCoordinates`

Represents coordinates in the equatorial system (RA/Dec).

- `ra_hours` (float): Right Ascension in hours (0-24).
- `dec_degrees` (float): Declination in degrees (-90 to +90).

### `HorizontalCoordinates`

Represents coordinates in the horizontal system (Alt/Az).

- `azimuth` (float): Azimuth in degrees (0-360).
- `altitude` (float): Altitude in degrees (-90 to +90).

### `GeographicLocation`

Represents the observer's location on Earth.

- `latitude` (float): Latitude in degrees (-90 to +90).
- `longitude` (float): Longitude in degrees (-180 to +180).

### `TelescopeInfo`

Stores hardware information about the telescope.

- `model` (int): The model number of the telescope.
- `firmware_major` (int): The major version of the firmware.
- `firmware_minor` (int): The minor version of the firmware.

### `TelescopeTime`

Represents the date and time information from the telescope.

- `hour`, `minute`, `second` (int)
- `month`, `day`, `year` (int)
- `timezone` (int): Timezone offset from GMT.
- `daylight_savings` (int): Daylight savings flag (0 or 1).

### `TelescopeConfig`

Configuration for connecting to the telescope.

- `port` (str): The serial port path.
- `baudrate` (int): The communication speed (default 9600).
- `timeout` (float): Serial timeout in seconds.
- `auto_connect` (bool): Whether to connect automatically on initialization.
- `verbose` (bool): Enables verbose logging.
