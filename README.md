# Celestron NexStar Telescope Control

[![CI](https://github.com/mcosgriff/celestron-nexstar/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mcosgriff/celestron-nexstar/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mcosgriff/celestron-nexstar/branch/main/graph/badge.svg)](https://codecov.io/gh/mcosgriff/celestron-nexstar)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

A modern, feature-rich **interactive shell** for controlling Celestron NexStar telescopes. Control your telescope with arrow keys, monitor position in real-time, and explore the night sky through an intuitive command-line interface.

## ✨ Why This Project?

This isn't just another telescope control library—it's a complete **interactive observing companion** designed for real-world stargazing sessions:

- **🎮 Video-game-like control**: Use arrow keys to move your telescope in real-time
- **📊 Live position tracking**: See your telescope's position update every 0.5 seconds in the status bar
- **🎓 Built-in tutorial**: Interactive lessons guide you from beginner to power user
- **🗺️ Rich catalogs**: Explore thousands of stars, deep sky objects, constellations, and 28 planetary moons
- **📈 Advanced tracking**: History logging, collision detection, velocity tracking, and CSV/JSON export
- **⚙️ Smart configuration**: Save locations, telescope specs, and download ephemeris data offline

## 🚀 Quick Start

### Installation

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/mcosgriff/celestron-nexstar.git
cd celestron-nexstar
uv sync --all-extras
```

### Launch the Interactive Shell

```bash
uv run nexstar shell
```

### Take the Tutorial

New to the shell? Start with the interactive tutorial:

```bash
# In the shell, type:
tutorial

# Or run a specific lesson:
tutorial 1

# Demo mode (no telescope required):
tutorial demo
```

The tutorial covers everything from basic navigation to advanced tracking features!

## 🎯 Key Features

### Interactive Shell Experience

The shell is the heart of this project, designed for real observing sessions:

#### Real-Time Telescope Control

- **Arrow Keys** (↑↓←→): Always move telescope in real-time (no mode switching!)
- **Speed Control**: Press `+` to increase speed, `-` to decrease (0=slowest to 9=fastest, default 5)
- **Emergency Stop**: Press `ESC` to immediately halt all movement
- **Visual Feedback**: Status bar shows movement state and current speed (e.g., "Speed:5/9")
- **Command History**: Press `Ctrl+P` (previous) or `Ctrl+N` (next) to navigate history

#### Background Position Tracking

- Live position updates in status bar (RA/Dec/Alt/Az)
- Automatic start after alignment
- Configurable update intervals (0.5-30s)
- Position history with 1000-entry circular buffer
- Real-time velocity and slew speed calculation
- Collision detection with configurable alerts
- CSV/JSON export for analysis

#### Advanced Visualizations

- ASCII star chart showing compass direction and altitude
- Multiple status indicators (position, movement, tracking)
- Color-coded alerts (green=stopped, red=moving)
- Freshness indicators ([live] vs [Ns ago])

### Celestial Object Catalogs

Browse and search extensive catalogs from the [celestial_data](https://github.com/dieghernan/celestial_data) repository:

- **Stars**: Thousands of stars with proper names (magnitude limits: 6, 8, 14)
  - Includes common star names matched from comprehensive star name database
  - Bayer and Flamsteed designations
- **Deep Sky Objects**: Galaxies, nebulae, and star clusters
  - Multiple magnitude limits (6, 14, 20) for different telescope capabilities
  - Bright DSO catalog for easy observing
- **Messier Objects**: All 110 Messier objects
- **Constellations**: All 88 IAU constellations with boundaries and metadata
- **Asterisms**: Famous star patterns (Big Dipper, Summer Triangle, etc.)
- **Local Group**: Local Group galaxies and Milky Way halo objects
  - Includes globular clusters (like 47 Tucanae) and dwarf galaxies
- **Planets**: All major planets with accurate positions
- **Planetary Moons**: 28 moons including:
  - Jupiter's Galilean moons (Io, Europa, Ganymede, Callisto)
  - Saturn's moons (Titan, Rhea, Iapetus, Dione, Tethys, Enceladus, Mimas, Hyperion)
  - Uranus moons (Titania, Oberon, Ariel, Umbriel, Miranda)
  - Neptune's Triton
  - Mars moons (Phobos, Deimos)

### Intelligent Features

- **Fuzzy search**: Find objects quickly (`catalog search andromeda`)
- **Visibility filtering**: Filter by telescope capabilities and sky conditions
- **Interactive object type selection**: Choose from all object types or filter by specific type (planets, deep_sky, messier, etc.)
- **Automatic location detection**: Detect your location using system services or IP geolocation (`location detect`)
- **Geocoding**: Set location by address (`location set-observer "New York, NY"`)
- **Offline ephemeris**: Download JPL data for field use without internet
- **Dynamic ephemeris sync**: Automatically fetch and sync ephemeris file metadata from NASA JPL's NAIF servers
- **Optical calculations**: Magnification, FOV, limiting magnitude, resolution
- **Celestial events tracking**: Aurora, eclipses, meteor showers, comets, ISS, and more
- **Space events calendar**: Planetary Society calendar with viewing location recommendations
- **Vacation planning**: Plan astronomy viewing for any destination
- **Backlash control**: Comprehensive tools for optimizing mount backlash and GoTo approach settings

### Multi-Night Planning & Clear Sky Charts

Production-ready observation planning with intelligent, object-type specific recommendations:

- **Week Comparison**: Compare conditions across 7 nights at a glance
- **Best Night Calculator**: Find optimal night for specific objects with smart scoring
  - **Object-Type Optimization**: Planets prioritize seeing, galaxies prioritize dark skies
  - **Moon-Object Separation**: Calculates angular distance between target and moon
  - **Light Pollution Integration**: Applies Bortle scale penalties based on object sensitivity
  - **Location Assessment**: Shows your sky quality and warns about visibility limits
  - Example: Galaxy observing from Bortle 6 location receives appropriate penalty/warning
- **Clear Sky Chart**: Detailed hourly forecast grid with customizable conditions
  - Filter by nighttime hours only
  - Highlight hours meeting quality thresholds (clouds, seeing, darkness)
  - Export data to CSV/JSON for analysis
  - Customizable condition display (clouds, seeing, darkness, wind, humidity, temp)
- **Smart Scoring**: Weights conditions by object type (planets ≠ galaxies ≠ nebulae)

### Celestial Events & Space Calendar

Comprehensive tracking and prediction of celestial events:

- **Aurora Borealis**: Real-time visibility, short-term forecasts, and long-term probabilistic predictions
- **Eclipses**: Lunar and solar eclipse predictions with visibility calculations
- **Planetary Events**: Conjunctions and oppositions with optimal viewing times
- **Meteor Showers**: Enhanced predictions with moon phase impact analysis
- **Comets**: Bright comet tracking and visibility forecasts
- **ISS & Satellites**: Pass predictions for International Space Station and bright satellites
- **Zodiacal Light**: Optimal viewing windows for zodiacal light and gegenschein
- **Variable Stars**: Eclipses, maxima, and minima predictions
- **Space Events Calendar**: Planetary Society calendar with viewing location recommendations

**Usage:**

```bash
nexstar aurora tonight                    # Check aurora visibility
nexstar eclipse next                     # Find next eclipse
nexstar meteors best                     # Best meteor viewing windows
nexstar iss passes                       # ISS pass predictions
nexstar events upcoming                  # Space events calendar
nexstar events viewing "Geminid"         # Find best viewing location
```

### Vacation Planning

Plan astronomy viewing for vacation destinations:

- **Viewing Conditions**: Check light pollution and sky quality at any location
- **Dark Sky Sites**: Find nearby International Dark Sky Places
- **Comprehensive Plans**: Viewing conditions, dark sites, aurora, eclipses, meteor showers, and comets
- **Date Range Support**: Plan for specific vacation periods

**Usage:**

```bash
nexstar vacation view "Fairbanks, AK"
nexstar vacation dark-sites "Moab, UT" --max-distance 200
nexstar vacation plan "Denver, CO" --start-date 2025-12-15 --end-date 2025-12-22
```

### Export Functionality

Export viewing guides and plans to text files for printing or offline reference:

- **Auto-Generated Filenames**: Commands automatically create descriptive filenames
  - Format: `{equipment}_{location}_{date}_{command}.txt`
  - Example: `nexstar_6se_los_angeles_2024-11-15_tonight.txt`
- **Custom Filenames**: Specify your own export path with `--export-path`
- **Supported Commands**: All viewing, planning, and event commands support export
  - Telescope viewing: `conditions`, `objects`, `imaging`, `tonight`, `plan`
  - Multi-night: `week`, `best-night`
  - Binocular viewing: `tonight`
  - Naked-eye viewing: `tonight`
  - Celestial events: `aurora`, `eclipse`, `planets`, `meteors`, `comets`, `iss`, etc.
  - Space events: `events upcoming`, `events viewing`
  - Vacation planning: `vacation view`, `vacation dark-sites`, `vacation plan`
- **Print-Ready**: Plain text with ASCII tables, perfect for printing

**Usage:**

```bash
nexstar telescope tonight --export                              # Auto-generate filename
nexstar telescope conditions --export --export-path conditions.txt  # Custom filename
nexstar binoculars tonight --export                            # Binocular guide
nexstar multi-night best-night M31 --export                    # Best night analysis
nexstar aurora tonight --export                                # Aurora forecast
nexstar vacation plan "Denver, CO" --export                    # Vacation plan
```

See the [CLI documentation](docs/CLI.md) for detailed usage and examples.

## 📚 Interactive Shell Guide

### Tutorial System

The shell includes 10 comprehensive lessons:

1. **Shell Basics**: Navigation, tab completion, command history (Ctrl+P/Ctrl+N)
2. **Movement Control**: Arrow keys (always active), speed adjustment, emergency stop
3. **Position Tracking**: Start/stop, intervals, statistics
4. **Advanced Tracking**: Export, collision detection, visualization
5. **Celestial Catalogs**: Browse, search, object information
6. **Configuration**: Telescope setup, location management
7. **Telescope Control**: Connect, position queries, goto commands
8. **Alignment**: Calibration for improved accuracy
9. **Ephemeris**: Download planetary data for offline use
10. **Tips & Tricks**: Power user features and shortcuts

**Tutorial Commands:**

```bash
tutorial          # Show lesson menu
tutorial 5        # Run lesson 5 (Celestial Catalogs)
tutorial demo     # Run demo lessons (no telescope needed)
tutorial all      # Run all lessons in sequence
```

### Essential Commands

#### Movement & Control

```bash
# Arrow keys ↑↓←→ ALWAYS move telescope (press and hold)
# Press +/- to adjust slew speed (0=slowest to 9=fastest, default 5)
# Press ESC to stop all movement
# Use Ctrl+P / Ctrl+N to navigate command history

# Traditional commands also available:
goto object --name Jupiter
goto ra-dec --ra 5.5 --dec 22.5
move fixed up --rate 5
move stop
```

#### Position Tracking

```bash
tracking start              # Start background tracking
tracking interval 1.0       # Set update interval (seconds)
tracking history --last 10  # View recent positions
tracking stats              # Show statistics (drift, velocity)
tracking export pos.csv     # Export to CSV
tracking alert-threshold 5  # Set collision alert (deg/s)
tracking chart on           # Enable ASCII star chart
```

### Catalogs & Objects

```bash
catalog catalogs                      # List all catalogs
catalog list --catalog messier        # Browse Messier objects
catalog search "ring nebula"          # Fuzzy search
catalog info M57                      # Detailed information
```

#### Configuration

```bash
optics config --telescope nexstar_6se --eyepiece 25
location set --lat 34.05 --lon -118.24 --name "LA"
location geocode "Griffith Observatory, Los Angeles"
location detect                                                  # Automatically detect your location
location set-observer "New York, NY"                            # Set observer location for calculations
location detect --no-save                                       # Detect location without saving
ephemeris download recommended  # DE421 + Jupiter moons (Skyfield's default recommendation)
ephemeris download standard      # ~20MB, includes planets + Jupiter/Saturn moons
```

#### Alignment & Tracking

```bash
align sync --ra 5.5 --dec 22.5  # Sync to known position
track set --mode alt_az          # Set tracking mode
track get                        # Get current mode
```

#### Mount Settings & Backlash Control

```bash
mount backlash-info              # Learn about backlash control
mount backlash-recommendations   # Get recommended settings
mount backlash-calibrate         # Interactive calibration guide
mount backlash-test --axis azimuth --direction positive  # Test settings
mount goto-approach-info         # Learn about GoTo Approach settings
```

**Multi-Night Planning** (outside shell)

```bash
nexstar multi-night week                                        # Compare next 7 nights
nexstar multi-night best-night M31 --days 7                     # Find best night for M31 (galaxy-optimized)
nexstar multi-night best-night Jupiter --days 14                # Find best night for Jupiter (planet-optimized)
nexstar multi-night best-night "Ring Nebula" --days 7           # Nebula-optimized with light pollution warning
nexstar multi-night clear-sky --nighttime-only                  # Detailed hourly forecast
nexstar multi-night clear-sky --highlight-good -c clouds,seeing -e data.csv  # Advanced usage
```

**Celestial Events** (outside shell)

```bash
nexstar aurora tonight                                          # Check aurora visibility
nexstar aurora when --days 14                                   # When will aurora be visible
nexstar eclipse next                                            # Find next eclipse
nexstar planets conjunctions                                    # Planetary conjunctions
nexstar meteors best                                            # Best meteor viewing windows
nexstar comets visible                                          # Visible comets
nexstar iss passes                                              # ISS pass predictions
nexstar events upcoming --days 120                              # Space events calendar
nexstar events viewing "Geminid"                                # Best viewing location
```

**Vacation Planning** (outside shell)

```bash
nexstar vacation view "Fairbanks, AK"                 # Viewing conditions
nexstar vacation dark-sites "Moab, UT"                 # Find dark sky sites
nexstar vacation plan "Denver, CO" --days 7            # Comprehensive plan
nexstar vacation plan "Moab, UT" --start-date 2025-12-15 --end-date 2025-12-22
```

**Export Viewing Plans** (print-friendly text files)

```bash
nexstar telescope tonight --export                              # Auto-generate filename
nexstar telescope conditions --export --export-path conditions.txt  # Custom filename
nexstar binoculars tonight --export                            # Binocular viewing guide
nexstar naked-eye tonight --export                             # Naked-eye stargazing guide
nexstar multi-night week --export                              # Week comparison
nexstar multi-night best-night M31 --export                    # Best night analysis
nexstar aurora tonight --export                                # Aurora forecast
nexstar vacation plan "Denver, CO" --export                   # Vacation plan
```

### Database Initialization

```bash
nexstar data setup                                              # First-time database setup (creates schema, imports data)
nexstar data migrate                                            # Apply pending database migrations
nexstar data migrate --dry-run                                  # Preview migrations without applying
nexstar data init-static                                        # Initialize offline data
nexstar data sync-ephemeris                                     # Sync ephemeris file metadata from NAIF
nexstar data sync-ephemeris --list                             # Preview available ephemeris files
nexstar data stats                                              # Show database statistics
```

**Cached Data:**

The application caches downloaded data files to avoid re-downloading on subsequent runs:

- **Celestial Data Cache**: `~/.cache/celestron-nexstar/celestial-data/`
  - Stores GeoJSON files from the celestial_data repository (stars, DSOs, Messier objects, constellations, asterisms, etc.)
  - Files are automatically downloaded on first use and reused for faster imports
- **Light Pollution Cache**: `~/.cache/celestron-nexstar/light-pollution/`
  - Stores World Atlas light pollution PNG images
  - Processed during `nexstar data setup` and reused for faster subsequent setups

**Cache Management:**

```bash
nexstar data clear-cache                                        # Delete all cached files
nexstar data setup --refresh-cache                              # Clear cache and re-download everything during setup
```

Use `--refresh-cache` if you want to ensure you have the latest data from remote sources, or if you're experiencing issues with corrupted cache files.

**Database Migrations:**

The database schema is managed using Alembic migrations. When you update the software, you may need to apply database migrations:

```bash
# Check and apply any pending migrations
nexstar data migrate

# Preview what would be migrated (without applying)
nexstar data migrate --dry-run
```

Migrations are automatically applied during `nexstar data setup`, but if you're updating an existing installation, run `nexstar data migrate` to ensure your database schema is up to date.

### Shell Tips

- **Tab Completion**: Press TAB to complete commands and see options
- **Command History**: Use ↑/↓ arrows to navigate previous commands
- **Help System**: Type `help` for full command reference
- **Quick Exit**: Type `exit`, `quit`, or press Ctrl+D
- **Clear Screen**: Type `clear`
- **Status Bar**: Bottom toolbar shows real-time telescope state

## 🔧 Hardware Setup

### Connection

Connect your Celestron NexStar telescope via USB or WiFi:

**Serial Connection (USB):**

- **macOS**: `/dev/tty.usbserial-XXXXX` (check with `ls /dev/tty.usbserial*`)
- **Linux**: `/dev/ttyUSB0` (may need: `sudo usermod -a -G dialout $USER`)
- **Windows**: `COM3`, `COM4`, etc. (check Device Manager)

**TCP/IP Connection (WiFi - SkyPortal WiFi Adapter):**

Control your telescope wirelessly using the Celestron SkyPortal WiFi Adapter:

1. **Connect the adapter** to your telescope's hand control port
2. **Set adapter to WLAN mode** (creates its own WiFi network)
3. **Connect your computer** to the adapter's WiFi network (typically named "Celestron-XXXX")
4. **Connect via TCP/IP**:

```bash
# Default settings (192.168.4.1:4030)
nexstar connect --tcp

# Custom host/port
nexstar connect --tcp --host 192.168.4.1 --tcp-port 4030

# Test connection
nexstar test --tcp
```

The adapter uses the same NexStar protocol over TCP/IP, so all telescope commands work identically to serial connections.

### Location Setup

Your location is needed for accurate astronomical calculations. You can set it in several ways:

**Automatic Detection (Recommended):**

```bash
nexstar location detect
```

This command will:

1. Try to use system location services (GPS, if available and permitted)
   - **Linux**: Uses GeoClue2 (requires `dbus-python` and geoclue2 service)
   - **macOS**: Uses CoreLocation (requires PyObjC)
   - **Windows**: Uses Windows Location API (requires `winrt`)
2. Fall back to IP-based geolocation (less accurate, but works everywhere)

The command will prompt you for permission before accessing location services, similar to how web browsers request location access.

**Manual Setup:**

```bash
# By city/address (geocoded automatically)
nexstar location set-observer "New York, NY"

# By coordinates
nexstar location set-observer --lat 40.7128 --lon -74.0060 --name "New York"

# View current location
nexstar location get-observer
```

**Note:** The observer location is separate from the telescope's internal location setting. The observer location is used for CLI calculations (planetary positions, visibility, etc.), while the telescope location is used for the telescope's internal tracking calculations.

### First-Time Setup

```bash
# Start the shell
uv run nexstar shell

# Follow the setup wizard or configure manually:
optics config --telescope nexstar_6se --eyepiece 25

# Set your location (choose one method):
location detect                                                  # Automatically detect location (recommended)
# OR
location set-observer "Your City, State"                        # Geocode from address
# OR
location set-observer --lat 34.05 --lon -118.24                 # Manual coordinates

# Initialize database and download ephemeris
nexstar data setup                                               # First-time database setup
nexstar data sync-ephemeris                                     # Sync ephemeris file metadata
ephemeris download recommended                                  # Download recommended set (DE421 + Jupiter moons)

# Take the tutorial to learn all features
tutorial
```

## 📖 Documentation

### Position Tracking Features

The shell's background position tracking is a powerful observing companion:

**Core Features:**

- Runs in background thread (non-blocking)
- Updates UI every 0.5s, polls telescope every 2s (configurable)
- Automatic start after `align` commands
- Thread-safe with proper locking
- Smart error handling (auto-stop after 3 consecutive errors)

**Position History:**

- Circular buffer stores last 1000 positions
- Each entry: timestamp, RA, Dec, Alt, Az
- Filter by time or count
- Statistics: duration, drift, velocity

**Velocity Tracking:**

- Real-time calculation of angular velocity
- Components: RA (hours/s), Dec, Alt, Az (deg/s), Total (deg/s)
- Slewing detection (>0.1°/s threshold)
- Displayed in status bar during movement

**Export Capabilities:**

- CSV format: timestamp, coordinates (5 columns)
- JSON format: structured data with metadata
- Export count, time range, drift statistics
- Continues tracking during export

**Collision Detection:**

- Configurable threshold (0.1-20.0°/s, default 5.0)
- Visual alerts: ⚠ in status bar
- Alert cooldown (5 seconds)
- Logs unexpected movements in history

**ASCII Star Chart:**

- 16-point compass rose (N, NNE, NE, ENE, E, etc.)
- Altitude bar graph using Unicode blocks (▁▂▃▄▅▆▇█)
- Toggle on/off: `tracking chart on`
- Compact display in status bar

### Movement Control

**Interactive Control (Preferred):**

- **Arrow Keys (↑↓←→)**: Always move the telescope - no mode switching needed!
  - Press and hold to move in any direction
  - No Enter key needed - instant response
  - Works anytime, even while typing (just clear text first with Ctrl+U if needed)
- **Speed Adjustment**: `+` to increase, `-` to decrease
  - Speed range: 0 (slowest) to 9 (fastest)
  - Default: 5 (medium speed)
  - Status bar shows current speed (e.g., "Speed:5/9")
- **Emergency Stop**: Press `ESC` to immediately halt all movement
- **Command History**: Use `Ctrl+P` (previous) and `Ctrl+N` (next) to navigate history
  - Standard emacs-style keybindings
  - Works anytime without interfering with movement

**Programmatic Control:**

```bash
move fixed up --rate 5 --duration 2.0    # Move for 2 seconds
move fixed right --rate 7                 # Move until stopped
move stop --axis both                     # Stop all motion
```

### Python API

For developers who want to use the library programmatically:

```python
from celestron_nexstar import NexStarTelescope, TrackingMode

with NexStarTelescope(port='/dev/ttyUSB0') as telescope:
    # Get position
    ra, dec = telescope.get_position_ra_dec()

    # Slew to coordinates
    telescope.goto_ra_dec(5.5, 22.5)

    # Enable tracking
    telescope.set_tracking_mode(TrackingMode.ALT_AZ)
```

See `examples/` directory for more code samples.

## 🧪 Testing

```bash
# Run all tests with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_nexstar_api.py -v

# Generate HTML coverage report
uv run pytest --cov=src/celestron_nexstar --cov-report=html
open htmlcov/index.html
```

**Test Coverage:**

- 86 comprehensive unit tests
- ~95% coverage on core modules
- Includes connection, movement, coordinates, calculations

## 🛠️ Development

### Pre-commit Hooks

Before committing your code, run the pre-commit hooks to ensure code quality:

```bash
# Install pre-commit (if not already installed)
uv pip install pre-commit

# Install the git hooks
pre-commit install

# Run hooks on all files (recommended before first commit)
pre-commit run --all-files

# Hooks will run automatically on git commit, but you can also run manually:
pre-commit run
```

**What the hooks check:**

- **Code formatting**: Ruff automatically formats Python code
- **Linting**: Ruff checks for code quality issues
- **Type checking**: Mypy validates type annotations
- **Markdown linting**: Ensures documentation follows markdown best practices
- **YAML/TOML validation**: Checks configuration file syntax
- **Trailing whitespace**: Removes unnecessary whitespace
- **End of file**: Ensures files end with newlines
- **Debug statements**: Prevents accidental `pdb`/`breakpoint` commits
- **Merge conflicts**: Detects unresolved conflict markers

**Note:** The hooks will automatically fix many issues (like formatting and whitespace). If there are unfixable errors, the commit will be blocked until you fix them manually.

## ⚠️ Safety Notes

1. **Clear path**: Ensure telescope has room to move before goto commands
2. **Solar safety**: Never point at the Sun without proper solar filters
3. **Cable management**: Watch for cable wrap during extended slews
4. **Mechanical limits**: Use caution near mount stops
5. **Emergency stop**: ESC key immediately stops all movement

## 🐛 Troubleshooting

### Connection Issues

- Verify USB cable is connected
- Check no other software is using the port
- On Linux, ensure user has serial port permissions: `sudo usermod -a -G dialout $USER` (logout/login required)

### Location Detection Issues

**Automatic detection not working:**

- **System services unavailable**: If system location services aren't available, the command will automatically fall back to IP-based geolocation
- **Permission denied**: On Linux, ensure GeoClue2 is running and your application has location permissions
  - Check GeoClue2 status: `systemctl --user status geoclue`
  - Grant permissions via your desktop environment's privacy settings
- **IP geolocation inaccurate**: IP-based location is approximate (city-level). For better accuracy, use manual coordinates or system location services
- **Manual setup**: If automatic detection fails, you can always set your location manually:

  ```bash
  nexstar location set-observer "Your City, State"
  # OR
  nexstar location set-observer --lat YOUR_LAT --lon YOUR_LON
  ```

### Database Migration Issues

**Migrations not applying:**

- Ensure you're using the latest version of the software
- Check database file permissions: `ls -l ~/.config/celestron-nexstar/catalogs.db`
- Try running migrations manually: `nexstar data migrate`
- If migrations fail, you may need to rebuild the database: `nexstar data rebuild` (this will re-import all data)

**Database schema out of date:**

- Run `nexstar data migrate` to apply pending migrations
- Check migration status: `nexstar data migrate --dry-run`
- If issues persist, see the [Database Initialization](#database-initialization) section above

### Cache Issues

**Corrupted or outdated cache files:**

- Clear all cached files: `nexstar data clear-cache`
- Force re-download during setup: `nexstar data setup --refresh-cache`
- Cache locations:
  - Celestial data: `~/.cache/celestron-nexstar/celestial-data/`
  - Light pollution: `~/.cache/celestron-nexstar/light-pollution/`

**Download failures:**

- Check internet connection
- Verify cache directory permissions: `ls -ld ~/.cache/celestron-nexstar/`
- Clear cache and retry: `nexstar data clear-cache && nexstar data setup --refresh-cache`

### Movement Issues

- Press ESC to stop if telescope is moving unexpectedly
- Check tracking mode is appropriate for setup
- Verify coordinates are within valid ranges
- Ensure telescope is not at mechanical limit

### Backlash and GoTo Accuracy Issues

**Poor GoTo centering or tracking drift:**

- Check backlash settings: `nexstar mount backlash-info`
- Get recommended settings: `nexstar mount backlash-recommendations`
- Calibrate backlash: `nexstar mount backlash-calibrate`
- Test settings: `nexstar mount backlash-test --axis azimuth --direction positive`
- Verify GoTo Approach settings: `nexstar mount goto-approach-info`
- Re-calibrate after adding/removing accessories (cameras, eyepieces)

**Reference:** See the [Celestron knowledge base article](https://www.celestron.com/blogs/knowledgebase/controlling-backlash-in-your-mount) for detailed information.

### Position Tracking Not Working

- Tracking auto-starts after `align` commands
- Manually start: `tracking start`
- Check telescope is connected
- Verify port is set correctly

## 🎯 Project Philosophy

This project prioritizes the **interactive observing experience**:

1. **Shell-first design**: The CLI is not an afterthought—it's the primary interface
2. **Real-time feedback**: See everything happening as it happens
3. **Learn by doing**: Interactive tutorial teaches through practice
4. **Field-ready**: Offline ephemeris, saved configurations, quick commands
5. **Safety-conscious**: Emergency stops, collision detection, clear warnings

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- Additional telescope models (currently optimized for NexStar series)
- Enhanced planetarium software integration
- Mobile app using the Python API
- Additional tutorials or documentation
- Test coverage improvements

## 📜 License

MIT License - feel free to use, modify, and distribute.

## 🙏 Acknowledgments

- Built on the Celestron NexStar serial protocol
- Uses Skyfield for astronomical calculations
- Tutorial system inspired by interactive learning tools

### Data Sources

This project uses comprehensive celestial data from the [celestial_data](https://github.com/dieghernan/celestial_data) repository, which provides:

- **Stars**: Comprehensive star catalogs with proper names, magnitudes, and designations
- **Deep Sky Objects**: Galaxies, nebulae, and star clusters with detailed metadata
- **Constellations**: All 88 IAU constellations with boundaries
- **Asterisms**: Famous star patterns and groupings
- **Local Group**: Local Group galaxies and Milky Way halo objects

Data files are automatically downloaded from the repository and cached locally in `~/.cache/celestron-nexstar/celestial-data/` for faster subsequent imports. Use `nexstar data clear-cache` to clear cached files or `nexstar data setup --refresh-cache` to force re-download.

**Citation:**

Please cite the celestial_data dataset as:

> Frohn O, Hernangómez D (2023). "Celestial Data." doi:10.5281/zenodo.7561601 https://doi.org/10.5281/zenodo.7561601, https://dieghernan.github.io/celestial_data/.

## 📞 Contact

For issues, questions, or contributions, please open an issue on GitHub.

---

### Happy Observing! 🌟🔭

_Start with `tutorial` and you'll be controlling your telescope like a pro in minutes!_
