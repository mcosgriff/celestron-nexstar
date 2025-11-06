# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Interactive Shell Features

- **Interactive tutorial system** with 10 comprehensive lessons covering shell basics, movement control, position tracking, catalogs, configuration, alignment, ephemeris management, and power user tips
- **Arrow key telescope control** for real-time movement using directional keys (↑↓←→)
- **Variable slew rate adjustment** with +/- keys (0-9 speed levels)
- **Emergency stop** functionality with ESC key for immediate halt of all movement
- **Demo mode** for tutorial lessons that don't require telescope connection
- **Interactive lesson menu** with options to run individual lessons, all lessons, or demo-only lessons

#### Position Tracking Enhancements

- **Configurable update intervals** (0.5 to 30 seconds) for position tracking refresh rate
- **Position history logging** with circular buffer (1000 entries) storing RA, Dec, Alt, Az with timestamps
- **Real-time velocity tracking** calculating angular velocity in degrees/sec for RA, Dec, Alt, Az components
- **Position export** to CSV and JSON formats with metadata
- **Collision detection alerts** with configurable threshold (0.1-20.0°/s) for unexpected movement
- **ASCII star chart visualization** in status bar with 16-point compass rose and altitude bar graph
- **Position history statistics** including drift calculations and duration tracking
- **Slewing detection** with visual indicators showing movement speed in status bar

#### Architecture Improvements

- **Modular CLI architecture** with separate modules for tracking, movement, and tutorial functionality
- `tracking.py` module (465 lines) extracted from main.py for position tracking logic
- `movement.py` module (99 lines) extracted from main.py for movement control logic
- `tutorial.py` module (269 lines) with comprehensive interactive learning system
- **Thread-safe implementations** with proper locking for background position tracking
- **Dependency injection pattern** using callable port getters for loose coupling

#### CLI/UX Improvements

- **Enhanced bottom toolbar** with real-time status display for position, movement state, slew rate, and tracking alerts
- **Color-coded status indicators** (green=stopped, red=moving) for visual feedback
- **Freshness indicators** showing position age ([live] vs [Ns ago])
- **Multiple simultaneous status displays** for position tracking, movement control, and alerts
- **Step-by-step tutorial confirmations** with Rich library panels and interactive prompts

#### Core Features (Previously Added)

- PEP 561 compliance with `py.typed` marker for type distribution
- Comprehensive `__all__` exports in all public API modules for clear public interfaces
- Logging infrastructure across all API modules (catalogs, observer, optics, ephemeris, ephemeris_manager, visibility)
- Real-time planetary ephemeris calculations using Skyfield
- Observer location management with geocoding support via geopy
- Prompt-toolkit-based interactive shell with rich formatting and key bindings
- Optical configuration management for telescopes and eyepieces
- Visibility filtering and calculations based on telescope capabilities
- Celestial object catalog system with fuzzy search capabilities
- Support for Messier, NGC, Caldwell, planetary, and planetary moon catalogs
- Comprehensive test suite with 86 unit tests and ~95% coverage on core modules

### Changed

- **Complete README overhaul** focusing on interactive shell as primary interface with comprehensive examples
- **Documentation consolidation** - removed redundant BACKGROUND_TRACKING.md, INTERACTIVE_SHELL.md, and TYPER_CLI_IMPLEMENTATION_PLAN.md files
- **CLI migration** from Typer to prompt-toolkit for true interactive shell experience with key bindings
- Migrated all Literal types to proper StrEnum classes for better type safety
- Replaced magic numbers with named constants in `constants.py` module
- Added `from __future__ import annotations` to all modules for forward compatibility
- Enhanced dataclasses with `frozen=True` and `slots=True` for immutability and performance
- Converted mutable list attributes to immutable tuples in dataclasses
- Updated imports in test files to reflect new package structure

### Fixed

- All 22 mypy type errors resolved with 100% type hint coverage
- Fixed coordinate conversion functions to use `DEGREES_PER_HOUR_ANGLE` constant
- Corrected attribute access from `obj.type` to `obj.object_type` in visibility calculations
- Fixed test import paths to use `celestron_nexstar.api.*` package structure
- Updated test mocks to use correct module paths

### Developer Experience

- Achieved 100% type coverage with mypy strict mode
- Added comprehensive logging for debugging file I/O and complex calculations
- Improved code organization with explicit public API exports
- Enhanced maintainability with immutable data structures

## [0.1.0] - Initial Development

### Added

- Initial Python API for Celestron NexStar 6SE telescope control
- Low-level serial protocol implementation
- High-level telescope control interface
- Support for Alt/Az and RA/Dec coordinate systems
- Tracking mode management
- Goto and slewing operations
- Coordinate conversion utilities
- Comprehensive unit tests for protocol and API layers

### Technical Details

- Python 3.14+ support
- Type-safe implementation with full mypy compliance
- Deal contracts for runtime verification
- Returns library for functional error handling
- Serial communication via pyserial

[Unreleased]: https://github.com/yourusername/celestron-nexstar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/celestron-nexstar/releases/tag/v0.1.0
