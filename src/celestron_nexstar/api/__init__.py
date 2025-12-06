"""
Celestron NexStar API - Business Logic Layer

This package contains all the core business logic for the Celestron NexStar
telescope control library, separated from CLI presentation concerns.

The API is organized into logical subpackages:
- database: Database models and operations
- astronomy: Astronomical objects and events
- catalogs: Catalog management
- telescope: Telescope control
- observation: Observation planning
- location: Location and environment
- events: Special events
- ephemeris: Ephemeris calculations
- core: Core utilities and types
"""

# Import deal for contract decorators (@deal.pre, @deal.post, etc.)
# NOTE: We do NOT call deal.activate() because it installs an import hook that is
# incompatible with Python 3.13 and breaks many modules (duckdb, starplot, numpy, astropy, etc.)
# The contract decorators will still work for runtime validation without the import hook.
# The import hook is only needed for module-level contracts (deal.module_load), which we don't use.
import deal  # noqa: F401


__all__ = [
    # Package is organized into subpackages - import directly from them:
    # from celestron_nexstar.api.database import ...
    # from celestron_nexstar.api.astronomy import ...
    # from celestron_nexstar.api.catalogs import ...
    # etc.
]
