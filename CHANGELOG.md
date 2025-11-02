# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- PEP 561 compliance with `py.typed` marker for type distribution
- Comprehensive `__all__` exports in all public API modules for clear public interfaces
- Logging infrastructure across all API modules (catalogs, observer, optics, ephemeris, ephemeris_manager, visibility)
- Real-time planetary ephemeris calculations using Skyfield
- Observer location management with geocoding support via geopy
- Typer-based CLI with rich formatting and interactive features
- Optical configuration management for telescopes and eyepieces
- Visibility filtering and calculations based on telescope capabilities
- Celestial object catalog system with fuzzy search capabilities
- Support for Messier, NGC, Caldwell, and planetary catalogs
- Comprehensive test suite with 157 passing tests

### Changed

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
