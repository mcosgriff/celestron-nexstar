# Celestron NexStar 6SE Python API

A comprehensive Python API for controlling the Celestron NexStar 6SE Computerized Telescope via serial communication.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Hardware Setup](#hardware-setup)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
  - [NexStarTelescope Class](#nexstartelescope-class)
    - [Connection Methods](#connection-methods)
    - [Information Methods](#information-methods)
    - [Movement Methods](#movement-methods)
    - [Alignment Methods](#alignment-methods)
    - [Tracking Methods](#tracking-methods)
    - [Location and Time Methods](#location-and-time-methods)
  - [Utility Functions](#utility-functions-nexstar_utilspy)
    - [Coordinate Conversions](#coordinate-conversions)
    - [Astronomical Calculations](#astronomical-calculations)
    - [Formatting](#formatting)
- [Examples](#examples)
- [Context Manager Support](#context-manager-support)
- [NexStar Protocol](#nexstar-protocol)
- [Coordinate Systems](#coordinate-systems)
  - [Equatorial (RA/Dec)](#equatorial-radec)
  - [Horizontal (Alt/Az)](#horizontal-altaz)
- [Tracking Modes](#tracking-modes)
- [Compatibility Notes](#compatibility-notes)
  - [Celestron StarSense AutoAlign](#celestron-starsense-autoalign)
- [Safety Notes](#safety-notes)
- [Troubleshooting](#troubleshooting)
  - [Connection Issues](#connection-issues)
  - [Slew Issues](#slew-issues)
  - [Accuracy Issues](#accuracy-issues)
- [Documentation](#documentation)
- [License](#license)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)
- [Resources](#resources)
- [Contact](#contact)

## Features

- Full serial communication with NexStar telescopes
- Position tracking (RA/Dec and Alt/Az)
- Goto commands for automatic slewing
- Manual movement controls
- Tracking mode configuration
- Location and time management
- Alignment and sync capabilities
- Coordinate conversion utilities
- Astronomical calculations

## Requirements

- Python 3.9+ (tested up to Python 3.14)
- PySerial library
- Celestron NexStar 6SE telescope with USB connection

## Installation

### Using Poetry (Recommended)

```zsh
# Install Poetry if needed
curl -sSL https://install.python-poetry.org | python3 -

# Install the package and dependencies
poetry install

# Run the demo
poetry run nexstar-demo
```

### Using pip

```zsh
# Install from source
pip install .

# Or install in development mode
pip install -e .
```

For detailed installation instructions, see [INSTALL.md](docs/INSTALL.md).

## Running Tests

The project includes comprehensive unit tests with high code coverage.

### Run All Tests

```zsh
# Run all tests with coverage report
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run specific test file
poetry run pytest tests/test_nexstar_api.py
```

### Code Coverage

```zsh
# Generate coverage report in terminal
poetry run pytest --cov=src/celestron_nexstar --cov-report=term-missing

# Generate HTML coverage report
poetry run pytest --cov=src/celestron_nexstar --cov-report=html

# Open HTML report (macOS)
open htmlcov/index.html

# Open HTML report (Linux)
xdg-open htmlcov/index.html
```

### Test Output

The test suite includes 86 tests covering:
- Connection management and serial communication
- Telescope movement and positioning commands
- Coordinate conversion and transformations
- Astronomical calculations
- Error handling and edge cases

Current coverage statistics:
- **telescope.py**: ~95% coverage (high-level API)
- **utils.py**: ~96% coverage (coordinate conversions and calculations)
- **Overall**: 71% coverage

## Hardware Setup

Connect your telescope via USB cable and find your serial port:
- **macOS**: `/dev/tty.usbserial-XXXXX` (check with `ls /dev/tty.usbserial*`)
- **Linux**: `/dev/ttyUSB0` (may need: `sudo usermod -a -G dialout $USER`)
- **Windows**: `COM3`, `COM4`, etc. (check Device Manager)

## Quick Start

```python
from celestron_nexstar import NexStarTelescope, TrackingMode
from celestron_nexstar import ra_to_hours, dec_to_degrees

# Connect to telescope
telescope = NexStarTelescope(port='/dev/ttyUSB0')
telescope.connect()

# Get current position
ra, dec = telescope.get_position_ra_dec()
print(f"RA: {ra:.4f} hours, Dec: {dec:.4f}°")

# Slew to coordinates (example: Polaris)
polaris_ra = ra_to_hours(2, 31, 49)  # 2h 31m 49s
polaris_dec = dec_to_degrees(89, 15, 51, '+')  # +89° 15' 51"
telescope.goto_ra_dec(polaris_ra, polaris_dec)

# Wait for slew to complete
while telescope.is_slewing():
    print("Slewing...")
    time.sleep(1)

# Enable tracking
telescope.set_tracking_mode(TrackingMode.ALT_AZ)

# Disconnect
telescope.disconnect()
```

## API Reference

### NexStarTelescope Class

#### Connection Methods

- `connect()` - Establish connection to telescope
- `disconnect()` - Close connection
- `echo_test(char='x')` - Test connection with echo command

#### Information Methods

- `get_version()` - Get firmware version
- `get_model()` - Get telescope model number
- `get_position_ra_dec()` - Get current RA/Dec coordinates
- `get_position_alt_az()` - Get current Alt/Az coordinates

#### Movement Methods

- `goto_ra_dec(ra_hours, dec_degrees)` - Slew to RA/Dec coordinates
- `goto_alt_az(azimuth, altitude)` - Slew to Alt/Az coordinates
- `move_fixed(direction, rate)` - Move in direction at specified rate
- `stop_motion(axis='both')` - Stop telescope motion
- `is_slewing()` - Check if telescope is currently moving
- `cancel_goto()` - Cancel current goto operation

#### Alignment Methods

- `sync_ra_dec(ra_hours, dec_degrees)` - Sync telescope position to coordinates

#### Tracking Methods

- `get_tracking_mode()` - Get current tracking mode
- `set_tracking_mode(mode)` - Set tracking mode (OFF, ALT_AZ, EQ_NORTH, EQ_SOUTH)

#### Location and Time Methods

- `get_location()` - Get observer location (lat, lon)
- `set_location(latitude, longitude)` - Set observer location
- `get_time()` - Get date and time from telescope
- `set_time(hour, minute, second, month, day, year, ...)` - Set date and time

### Utility Functions (nexstar_utils.py)

#### Coordinate Conversions

- `ra_to_hours(hours, minutes, seconds)` - Convert RA to decimal hours
- `dec_to_degrees(degrees, minutes, seconds, sign)` - Convert Dec to decimal degrees
- `degrees_to_dms(degrees)` - Convert decimal degrees to DMS format
- `hours_to_hms(hours)` - Convert decimal hours to HMS format

#### Astronomical Calculations

- `alt_az_to_ra_dec(azimuth, altitude, latitude, longitude, utc_time)` - Convert Alt/Az to RA/Dec
- `ra_dec_to_alt_az(ra_hours, dec_degrees, latitude, longitude, utc_time)` - Convert RA/Dec to Alt/Az
- `calculate_lst(longitude, utc_time)` - Calculate Local Sidereal Time
- `angular_separation(ra1, dec1, ra2, dec2)` - Calculate angular distance between coordinates

#### Formatting

- `format_ra(hours)` - Format RA as readable string
- `format_dec(degrees)` - Format Dec as readable string
- `format_position(ra_hours, dec_degrees)` - Format complete position

## Examples

See `example_usage.py` for comprehensive examples including:

1. Basic connection and information retrieval
2. Slewing to celestial objects
3. Manual telescope movement
4. Setting tracking modes
5. Configuring location and time
6. Performing alignment
7. Alt/Az coordinate slewing
8. Canceling goto operations

To run examples:

```bash
python example_usage.py
```

Remember to update the serial port in the examples to match your system!

## Context Manager Support

The API supports Python's context manager protocol for automatic connection management:

```python
with NexStarTelescope(port='/dev/ttyUSB0') as telescope:
    ra, dec = telescope.get_position_ra_dec()
    print(f"Position: {ra}, {dec}")
# Automatically disconnects
```

## NexStar Protocol

This API implements the Celestron NexStar serial protocol for communication. Commands are sent as ASCII strings terminated with '#' character. The telescope uses a precise hexadecimal format for coordinates where:

- 0x00000000 = 0°
- 0x80000000 = 180°
- 0xFFFFFFFF = 360° (wraps to 0°)

## Coordinate Systems

### Equatorial (RA/Dec)
- **Right Ascension (RA)**: 0-24 hours (0° to 360°)
- **Declination (Dec)**: -90° to +90°

### Horizontal (Alt/Az)
- **Azimuth (Az)**: 0-360° (0° = North, 90° = East, 180° = South, 270° = West)
- **Altitude (Alt)**: -90° to +90° (0° = horizon, 90° = zenith)

## Tracking Modes

- `TrackingMode.OFF` - No tracking
- `TrackingMode.ALT_AZ` - Alt-Az tracking for terrestrial observing
- `TrackingMode.EQ_NORTH` - Equatorial tracking for Northern Hemisphere
- `TrackingMode.EQ_SOUTH` - Equatorial tracking for Southern Hemisphere

## Compatibility Notes

### Celestron StarSense AutoAlign

**This API does not support the Celestron StarSense AutoAlign accessory.** The StarSense AutoAlign system uses proprietary camera control commands and alignment protocols that are not part of the standard NexStar serial protocol documented by Celestron.

**What is supported:**
- Manual alignment via the `sync_ra_dec()` method
- Traditional star alignment workflows (manually center a known star, then sync)
- All standard telescope control functions (goto, tracking, positioning)

**What is NOT supported:**
- StarSense camera-based automatic alignment
- StarSense-specific commands and protocols
- Automated plate solving via StarSense hardware

If you need to use StarSense AutoAlign, use the telescope's hand controller. This API is designed for manual control and traditional alignment methods. Users interested in automated alignment could implement custom plate-solving solutions using this API's positioning commands with third-party software.

## Safety Notes

1. Always ensure the telescope has a clear path before issuing goto commands
2. Never point the telescope at the Sun without proper solar filters
3. Be aware of cable wrap limits during extended slews
4. Use manual movement commands carefully to avoid hitting mechanical stops
5. Verify coordinates before slewing to prevent damage

## Troubleshooting

### Connection Issues

- Verify USB cable is properly connected
- Check that no other software is using the serial port
- Try different baud rates if connection fails (default is 9600)
- On Linux, ensure user has permissions for serial port: `sudo usermod -a -G dialout $USER`

### Slew Issues

- Ensure telescope is properly aligned before slewing
- Check that tracking mode is appropriate for your setup
- Verify coordinates are within valid ranges
- Make sure telescope is not at a mechanical limit

### Accuracy Issues

- Perform proper alignment (at least 2-star alignment)
- Set correct location and time
- Allow telescope to cool to ambient temperature
- Check for mechanical issues (loose screws, etc.)

## Documentation

Complete documentation is available in the [docs/](docs/) directory:

- [Documentation Index](docs/INDEX.md) - Complete documentation overview
- [Installation Guide](docs/INSTALL.md) - Detailed installation instructions
- [Telescope API Documentation](docs/telescope_docs.md) - High-level telescope control
- [Protocol Documentation](docs/protocol_docs.md) - Low-level serial communication
- [Type Definitions](docs/types_docs.md) - Enums and dataclasses
- [Custom Exceptions](docs/exceptions_docs.md) - Exception hierarchy
- [Coordinate Converters](docs/converters_docs.md) - Coordinate conversion utilities
- [Astronomical Utilities](docs/utils_docs.md) - Calculations and formatting
- [Library Initialization](docs/init_docs.md) - Package exports
- [Usage Examples](docs/examples_docs.md) - Code examples

## License

This is an open-source project. Feel free to use, modify, and distribute as needed.

## Contributing

Contributions are welcome! Areas for improvement:

- Additional telescope models support
- More astronomical calculations
- GUI interface
- Planetarium software integration
- Enhanced error handling
- Additional test coverage for protocol.py layer

## Acknowledgments

Based on the Celestron NexStar serial protocol specification.

## Resources

- [Celestron NexStar Serial Protocol Documentation (PDF)](https://s3.amazonaws.com/celestron-site-support-files/support_files/1154108406_nexstarcommprot.pdf)
- [NexStar Programming Guide](https://www.nexstarsite.com/PCControl/ProgrammingNexStar.htm)
- [PySerial Documentation](https://pyserial.readthedocs.io/)
- Astronomical calculations based on Jean Meeus's "Astronomical Algorithms"

## Contact

For issues, questions, or contributions, please open an issue on the project repository.
