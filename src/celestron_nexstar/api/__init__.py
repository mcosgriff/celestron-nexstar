"""
Celestron NexStar API - Business Logic Layer

This package contains all the core business logic for the Celestron NexStar
telescope control library, separated from CLI presentation concerns.
"""

import deal

# Activate deal contracts for runtime validation
# Contracts are checked during development/testing
# Can be disabled in production for performance if needed
deal.activate()

# Main telescope class
# Celestial object catalogs
from celestron_nexstar.api.catalogs import (
    ALL_CATALOGS,
    CelestialObject,
    get_all_catalogs_dict,
    get_all_objects,
    get_available_catalogs,
    get_catalog,
    get_object_by_name,
    search_objects,
)

# Coordinate converters (internal helper class)
from celestron_nexstar.api.converters import CoordinateConverter

# Ephemeris calculations
from celestron_nexstar.api.ephemeris import (
    PLANET_NAMES,
    get_planet_magnitude,
    get_planetary_position,
    is_dynamic_object,
)

# Ephemeris file management
from celestron_nexstar.api.ephemeris_manager import (
    EPHEMERIS_FILES,
    EPHEMERIS_SETS,
    EphemerisFileInfo,
    delete_file,
    download_file,
    download_set,
    get_ephemeris_directory,
    get_file_size,
    get_installed_files,
    get_set_info,
    get_total_size,
    is_file_installed,
    verify_file,
)

# Exceptions
from celestron_nexstar.api.exceptions import (
    CommandError,
    InvalidCoordinateError,
    NexStarError,
    NotConnectedError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
)

# Import utilities
from celestron_nexstar.api.importers import (
    map_openngc_type,
    parse_catalog_number,
    parse_ra_dec,
)

# Light pollution
from celestron_nexstar.api.light_pollution import (
    BortleClass,
    LightPollutionData,
    get_light_pollution_data,
    get_light_pollution_data_batch,
    sqm_to_bortle,
)

# Movement and tracking
from celestron_nexstar.api.movement import MovementController

# Observer location management
from celestron_nexstar.api.observer import (
    DEFAULT_LOCATION,
    ObserverLocation,
    clear_observer_location,
    geocode_location,
    get_config_path,
    get_observer_location,
    load_location,
    save_location,
    set_observer_location,
)

# Optical configuration and calculations
from celestron_nexstar.api.optics import (
    COMMON_EYEPIECES,
    TELESCOPE_SPECS,
    EyepieceSpecs,
    OpticalConfiguration,
    TelescopeModel,
    TelescopeSpecs,
    calculate_dawes_limit_arcsec,
    calculate_limiting_magnitude,
    calculate_rayleigh_criterion_arcsec,
    clear_current_configuration,
    get_current_configuration,
    get_telescope_specs,
    is_object_resolvable,
    set_current_configuration,
)
from celestron_nexstar.api.telescope import NexStarTelescope
from celestron_nexstar.api.tracking import PositionTracker

# Type definitions
from celestron_nexstar.api.types import (
    AlignmentMode,
    EquatorialCoordinates,
    GeographicLocation,
    HorizontalCoordinates,
    TelescopeConfig,
    TelescopeInfo,
    TelescopeTime,
    TrackingMode,
)

# Coordinate conversion utilities
from celestron_nexstar.api.utils import (
    alt_az_to_ra_dec,
    angular_separation,
    calculate_julian_date,
    calculate_lst,
    dec_to_degrees,
    degrees_to_dms,
    format_dec,
    format_position,
    format_ra,
    hours_to_hms,
    ra_dec_to_alt_az,
    ra_to_hours,
)

# Visibility filtering
from celestron_nexstar.api.visibility import (
    VisibilityInfo,
    assess_visibility,
    calculate_atmospheric_extinction,
    calculate_parent_separation,
    filter_visible_objects,
    get_object_altitude_azimuth,
)

# Weather API
from celestron_nexstar.api.weather import (
    HourlySeeingForecast,
    WeatherData,
    assess_observing_conditions,
    fetch_weather,
    get_weather_api_key,
)


__all__ = [
    "ALL_CATALOGS",
    "COMMON_EYEPIECES",
    "DEFAULT_LOCATION",
    # Ephemeris file management
    "EPHEMERIS_FILES",
    "EPHEMERIS_SETS",
    # Ephemeris
    "PLANET_NAMES",
    "TELESCOPE_SPECS",
    "AlignmentMode",
    # Light pollution
    "BortleClass",
    # Catalogs
    "CelestialObject",
    "CommandError",
    # Coordinate converter class
    "CoordinateConverter",
    "EphemerisFileInfo",
    "EquatorialCoordinates",
    "EyepieceSpecs",
    "GeographicLocation",
    "HorizontalCoordinates",
    # Weather
    "HourlySeeingForecast",
    "InvalidCoordinateError",
    "LightPollutionData",
    # Movement and tracking
    "MovementController",
    # Exceptions
    "NexStarError",
    # Main telescope class
    "NexStarTelescope",
    "NotConnectedError",
    # Observer location
    "ObserverLocation",
    "OpticalConfiguration",
    "PositionTracker",
    "TelescopeConfig",
    "TelescopeConnectionError",
    "TelescopeInfo",
    # Optics
    "TelescopeModel",
    "TelescopeSpecs",
    "TelescopeTime",
    "TelescopeTimeoutError",
    # Type definitions
    "TrackingMode",
    # Visibility
    "VisibilityInfo",
    "WeatherData",
    "alt_az_to_ra_dec",
    "angular_separation",
    "assess_observing_conditions",
    "assess_visibility",
    "calculate_atmospheric_extinction",
    "calculate_dawes_limit_arcsec",
    "calculate_julian_date",
    "calculate_limiting_magnitude",
    "calculate_lst",
    "calculate_parent_separation",
    "calculate_rayleigh_criterion_arcsec",
    "clear_current_configuration",
    "clear_observer_location",
    "dec_to_degrees",
    "degrees_to_dms",
    "delete_file",
    "download_file",
    "download_set",
    "fetch_weather",
    "filter_visible_objects",
    "format_dec",
    "format_position",
    "format_ra",
    "geocode_location",
    "get_all_catalogs_dict",
    "get_all_objects",
    "get_available_catalogs",
    "get_catalog",
    "get_config_path",
    "get_current_configuration",
    "get_ephemeris_directory",
    "get_file_size",
    "get_installed_files",
    "get_light_pollution_data",
    "get_light_pollution_data_batch",
    "get_object_altitude_azimuth",
    "get_object_by_name",
    "get_observer_location",
    "get_planet_magnitude",
    "get_planetary_position",
    "get_set_info",
    "get_telescope_specs",
    "get_total_size",
    "get_weather_api_key",
    "hours_to_hms",
    "is_dynamic_object",
    "is_file_installed",
    "is_object_resolvable",
    "load_location",
    # Importers
    "map_openngc_type",
    "parse_catalog_number",
    "parse_ra_dec",
    "ra_dec_to_alt_az",
    # Coordinate conversions
    "ra_to_hours",
    "save_location",
    "search_objects",
    "set_current_configuration",
    "set_observer_location",
    "sqm_to_bortle",
    "verify_file",
]
