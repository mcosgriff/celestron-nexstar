# Celestron NexStar Telescope Control

[![CI](https://github.com/mcosgriff/celestron-nexstar/actions/workflows/ci.yml/badge.svg)](https://github.com/mcosgriff/celestron-nexstar/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mcosgriff/celestron-nexstar/branch/main/graph/badge.svg)](https://codecov.io/gh/mcosgriff/celestron-nexstar)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

A comprehensive command-line interface (CLI) and Python API for controlling Celestron NexStar telescopes with advanced features for planetary moon tracking, intelligent visibility filtering, and field-ready ephemeris management.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Hardware Setup](#hardware-setup)
- [Quick Start (CLI)](#quick-start-cli)
- [CLI Reference](#cli-reference)
  - [Configuration Commands](#configuration-commands)
  - [Catalog Commands](#catalog-commands)
  - [Ephemeris Management](#ephemeris-management)
  - [Observer Location](#observer-location)
  - [Telescope Control](#telescope-control)
- [Python API Reference](#python-api-reference)
  - [NexStarTelescope Class](#nexstartelescope-class)
  - [Utility Functions](#utility-functions)
- [Coordinate Systems](#coordinate-systems)
- [Tracking Modes](#tracking-modes)
- [Compatibility Notes](#compatibility-notes)
- [Safety Notes](#safety-notes)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [License](#license)
- [Contributing](#contributing)
- [Resources](#resources)

## Features

### CLI Features

- **Optical Configuration**: Configure telescope and eyepiece specs to calculate magnification, field of view, limiting magnitude, and resolution
- **Celestial Object Catalogs**: Browse and search 100+ deep sky objects, planets, and 28 planetary moons (Galilean moons, Titan, Uranus moons, Triton, and more)
- **Ephemeris Management**: Download JPL ephemeris files for offline field use with real-time planetary moon positions
- **Intelligent Visibility Filtering**: Filter objects based on telescope capabilities, altitude, atmospheric conditions, and moon-planet separation
- **Observer Location Management**: Save and geocode observer locations for accurate coordinate conversions
- **Telescope Control**: Full serial communication for position tracking, goto commands, alignment, and tracking modes

### Python API Features

- Full NexStar serial protocol implementation
- Position tracking (RA/Dec and Alt/Az) with coordinate conversions
- Goto commands for automatic slewing to celestial coordinates
- Manual movement controls with adjustable rates
- Tracking mode configuration (Alt-Az, Equatorial North/South)
- Location and time management for accurate calculations
- Alignment and sync capabilities for improved accuracy
- Comprehensive astronomical calculations (LST, angular separation, coordinate transforms)
- Context manager support for automatic connection handling

## Requirements

- Python 3.9+ (tested up to Python 3.14)
- PySerial library (for serial communication)
- tqdm library (for progress bars in examples)
- Celestron NexStar 6SE telescope with USB connection

## Installation

### Using uv (Recommended)

```zsh
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the package and dependencies
uv sync --all-extras

# Run examples (no demo script currently)
uv run python examples/simple_position_tracking.py
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
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_nexstar_api.py
```

### Code Coverage

```zsh
# Generate coverage report in terminal
uv run pytest --cov=src/celestron_nexstar --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=src/celestron_nexstar --cov-report=html

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

## Quick Start (CLI)

The CLI is the recommended way to use the telescope control system. Here are common workflows:

### Initial Setup (One-Time Configuration)

```bash
# Configure your telescope and eyepiece
uv run nexstar optics config --telescope nexstar_6se --eyepiece 25

# Set your observing location (Los Angeles example)
uv run nexstar location set --lat 34.05 --lon -118.24 --name "Los Angeles"

# Or use geocoding to find coordinates
uv run nexstar location geocode "Griffith Observatory, Los Angeles"

# Download ephemeris files for offline use (downloads ~20MB)
uv run nexstar ephemeris download standard
```

### Exploring Celestial Objects

```bash
# List all available catalogs
uv run nexstar catalog catalogs

# View planets
uv run nexstar catalog list --catalog planets

# View Jupiter's moons
uv run nexstar catalog list --catalog jupiter-moons

# Search for specific objects
uv run nexstar catalog search "andromeda"

# Get detailed information about an object
uv run nexstar catalog info "M31"
```

### Telescope Control

```bash
# Connect to telescope and get position
uv run nexstar connect --port /dev/ttyUSB0

# Get current telescope position
uv run nexstar position

# Slew to an object from the catalog
uv run nexstar goto --object "Jupiter"

# Or slew to specific coordinates
uv run nexstar goto --ra 5.5 --dec 22.5

# Set tracking mode
uv run nexstar track --mode alt_az

# Check telescope information
uv run nexstar connect --info
```

### Managing Ephemeris Files

```bash
# List available ephemeris files
uv run nexstar ephemeris list --all

# Get information about a specific file
uv run nexstar ephemeris info jup365

# Download a specific ephemeris set
uv run nexstar ephemeris download complete  # Planets + Jupiter/Saturn/Uranus moons

# Verify downloaded files
uv run nexstar ephemeris verify

# View all available sets
uv run nexstar ephemeris sets
```

For Python API usage, see the [Python API Reference](#python-api-reference) section below.

## CLI Reference

All CLI commands start with `nexstar` (or `uv run nexstar` in development). Use `--help` on any command to see detailed usage.

### Configuration Commands

#### Optics Configuration

Configure telescope and eyepiece specifications for accurate calculations:

```bash
# Configure telescope and eyepiece together
nexstar optics config --telescope nexstar_6se --eyepiece 25

# Change just the eyepiece
nexstar optics set-eyepiece 10

# View current configuration
nexstar optics show

# List available telescopes
nexstar optics telescopes

# List common eyepieces
nexstar optics eyepieces

# Calculate limiting magnitude for sky conditions
nexstar optics limiting-mag --sky excellent
```

### Catalog Commands

Browse and search celestial object catalogs:

```bash
# List all available catalogs
nexstar catalog catalogs

# List objects in a specific catalog
nexstar catalog list --catalog messier
nexstar catalog list --catalog planets
nexstar catalog list --catalog jupiter-moons
nexstar catalog list --catalog saturn-moons

# Search across all catalogs
nexstar catalog search "nebula"
nexstar catalog search "Titan"

# Get detailed information about an object
nexstar catalog info "M31"
nexstar catalog info "Jupiter"
```

Available catalogs:

- `messier`: Messier objects (M1-M110)
- `ngc-popular`: Popular NGC objects
- `caldwell`: Caldwell catalog
- `planets`: Major planets (Mercury through Neptune)
- `jupiter-moons`: Galilean moons (Io, Europa, Ganymede, Callisto)
- `saturn-moons`: Saturn's moons (Titan, Rhea, Iapetus, Dione, Tethys, Enceladus, Mimas, Hyperion)
- `uranus-moons`: Uranus moons (Titania, Oberon, Ariel, Umbriel, Miranda)
- `neptune-moons`: Neptune's moon (Triton)
- `mars-moons`: Mars moons (Phobos, Deimos - very challenging)

### Ephemeris Management

Download and manage JPL ephemeris files for offline planetary calculations:

```bash
# List available ephemeris files
nexstar ephemeris list         # Show only installed files
nexstar ephemeris list --all   # Show all available files

# Get information about a specific file
nexstar ephemeris info de440s
nexstar ephemeris info jup365

# Download individual files
nexstar ephemeris download de421

# Download pre-configured sets
nexstar ephemeris download minimal    # DE421 + Jupiter moons (~25MB)
nexstar ephemeris download standard   # DE440s + Jupiter/Saturn moons (~20MB)
nexstar ephemeris download complete   # Adds Uranus/Neptune moons (~85MB)
nexstar ephemeris download full       # All files including Mars moons (~3.2GB)

# View available sets
nexstar ephemeris sets

# Verify downloaded files
nexstar ephemeris verify

# Delete files
nexstar ephemeris delete de421
```

Ephemeris files are stored in `~/.skyfield/` directory.

### Observer Location

Manage observer location for accurate coordinate calculations:

```bash
# Set location manually
nexstar location set --lat 34.05 --lon -118.24 --name "Los Angeles"

# Geocode an address (requires internet)
nexstar location geocode "Griffith Observatory, Los Angeles"
nexstar location geocode "New York, NY"

# View current location
nexstar location show

# Clear saved location
nexstar location clear
```

Location is saved to `~/.config/celestron-nexstar/location.json`.

### Telescope Control

Connect to and control the physical telescope:

```bash
# Connect to telescope (test connection)
nexstar connect --port /dev/ttyUSB0
nexstar connect --port COM3  # Windows

# Get telescope info
nexstar connect --info

# Get current position
nexstar position

# Slew to an object from catalog
nexstar goto --object "M31"
nexstar goto --object "Jupiter"

# Slew to specific coordinates
nexstar goto --ra 5.5 --dec 22.5

# Slew to alt/az coordinates
nexstar goto --alt 45 --az 180

# Cancel goto operation
nexstar goto --cancel

# Manual movement
nexstar move --direction north --rate 5
nexstar move --direction east --rate 9
nexstar move --stop

# Set tracking mode
nexstar track --mode off
nexstar track --mode alt_az
nexstar track --mode eq_north
nexstar track --mode eq_south

# Get current tracking mode
nexstar track --get

# Alignment
nexstar align --ra 5.5 --dec 22.5  # Sync to known position
```

## Python API Reference

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

### Python API Example

For those who want to use the Python API directly:

```python
from celestron_nexstar import NexStarTelescope, TrackingMode
from celestron_nexstar import ra_to_hours, dec_to_degrees

# Context manager automatically connects and disconnects
with NexStarTelescope(port='/dev/ttyUSB0') as telescope:
    # Get current position
    ra, dec = telescope.get_position_ra_dec()
    print(f"RA: {ra:.4f} hours, Dec: {dec:.4f}°")

    # Slew to coordinates (example: Polaris)
    polaris_ra = ra_to_hours(2, 31, 49)  # 2h 31m 49s
    polaris_dec = dec_to_degrees(89, 15, 51, '+')  # +89° 15' 51"
    telescope.goto_ra_dec(polaris_ra, polaris_dec)

    # Enable tracking
    telescope.set_tracking_mode(TrackingMode.ALT_AZ)
```

See `examples/` directory for more comprehensive examples.

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
