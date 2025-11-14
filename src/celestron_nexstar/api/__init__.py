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

# Activate deal contracts for runtime validation
import deal


deal.activate()

__all__ = [
    # Package is organized into subpackages - import directly from them:
    # from celestron_nexstar.api.database import ...
    # from celestron_nexstar.api.astronomy import ...
    # from celestron_nexstar.api.catalogs import ...
    # etc.
]
