# NexStar Telescope Control (`telescope.py`)

## Overview

This module provides a high-level, user-friendly interface for controlling Celestron NexStar telescopes. It abstracts the low-level serial commands found in `protocol.py` into convenient methods for common telescope operations, such as connecting, moving, and retrieving position data.

## `NexStarTelescope` Class

This is the main class for interacting with the telescope. It handles the connection, sends commands, and processes responses.

### Initialization

To begin, create an instance of the `NexStarTelescope` class. You can provide a configuration object or simply the serial port as a string.

```python
from celestron_nexstar.telescope import NexStarTelescope, TelescopeConfig

# Simple initialization with port string
# Replace '/dev/tty.usbmodem14201' with your serial port
telescope = NexStarTelescope('/dev/tty.usbmodem14201')

# Or with a full configuration object
config = TelescopeConfig(port='/dev/tty.usbmodem14201', baudrate=9600, verbose=True)
telescope = NexStarTelescope(config)
```

### Connection Management

The class can be used as a context manager to automatically handle connection and disconnection.

```python
with NexStarTelescope('/dev/tty.usbmodem14201') as telescope:
    # Telescope is connected within this block
    position = telescope.get_position_ra_dec()
    print(position)
# Telescope is automatically disconnected here
```

#### `connect()`
Establishes a connection to the telescope.

- **Returns**: `True` if the connection is successful.
- **Raises**: `TelescopeConnectionError` if the connection fails.

#### `disconnect()`
Closes the connection to the telescope.

### Telescope Information

#### `get_info()`
Retrieves hardware information about the telescope.

- **Returns**: A `TelescopeInfo` object containing the model and firmware version.

```python
info = telescope.get_info()
print(f"Model: {info.model}, Firmware: {info.firmware_major}.{info.firmware_minor}")
```

### Positioning and Slewing

#### `get_position_ra_dec()`
Gets the current Right Ascension (RA) and Declination (Dec) of the telescope.

- **Returns**: An `EquatorialCoordinates` object with `ra_hours` and `dec_degrees`.

#### `get_position_alt_az()`
Gets the current Altitude (Alt) and Azimuth (Az) of the telescope.

- **Returns**: A `HorizontalCoordinates` object with `azimuth` and `altitude` in degrees.

#### `goto_ra_dec(ra_hours: float, dec_degrees: float)`
Slews the telescope to the specified RA and Dec coordinates.

- **Arguments**:
  - `ra_hours` (float): Right Ascension in hours (0-24).
  - `dec_degrees` (float): Declination in degrees (-90 to +90).
- **Returns**: `True` if the command is successful.

#### `goto_alt_az(azimuth: float, altitude: float)`
Slews the telescope to the specified Alt and Az coordinates.

- **Arguments**:
  - `azimuth` (float): Azimuth in degrees (0-360).
  - `altitude` (float): Altitude in degrees (-90 to +90).
- **Returns**: `True` if the command is successful.

#### `sync_ra_dec(ra_hours: float, dec_degrees: float)`
Syncs the telescope's internal position to the given RA and Dec. This is useful for alignment.

- **Returns**: `True` if the command is successful.

#### `is_slewing()`
Checks if the telescope is currently moving to a target.

- **Returns**: `True` if the telescope is slewing.

#### `cancel_goto()`
Stops the current slew operation.

- **Returns**: `True` if the command is successful.

### Manual Movement

#### `move_fixed(direction: str, rate: int = 9)`
Moves the telescope in a fixed direction at a specified rate.

- **Arguments**:
  - `direction` (str): 'up', 'down', 'left', or 'right'.
  - `rate` (int): Speed from 0 (slowest) to 9 (fastest).
- **Returns**: `True` if the command is successful.

#### `stop_motion(axis: str = 'both')`
Stops the telescope's movement.

- **Arguments**:
  - `axis` (str): 'az', 'alt', or 'both'.
- **Returns**: `True` if the command is successful.

### Tracking

#### `get_tracking_mode()`
Gets the current tracking mode of the telescope.

- **Returns**: A `TrackingMode` enum value (e.g., `TrackingMode.ALT_AZ`, `TrackingMode.EQ_NORTH`).

#### `set_tracking_mode(mode: TrackingMode)`
Sets the tracking mode.

- **Arguments**:
  - `mode` (TrackingMode): The desired tracking mode.
- **Returns**: `True` if the command is successful.

### Location and Time

#### `get_location()`
Gets the observer's geographical location from the telescope.

- **Returns**: A `GeographicLocation` object.

#### `set_location(latitude: float, longitude: float)`
Sets the observer's location.

- **Arguments**:
  - `latitude` (float): Latitude in degrees (-90 to +90).
  - `longitude` (float): Longitude in degrees (-180 to +180).
- **Returns**: `True` if the command is successful.

#### `get_time()`
Gets the current time from the telescope.

- **Returns**: A `TelescopeTime` object.

#### `set_time(...)`
Sets the time on the telescope.

- **Returns**: `True` if the command is successful.
