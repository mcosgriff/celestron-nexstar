"""
Worker functions for CPU-intensive visibility calculations.

These functions are designed to run in separate processes using ProcessPoolExecutor
to avoid Python's Global Interpreter Lock (GIL) limitations.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure logging for worker processes (each process needs its own setup)
def _setup_worker_logging() -> None:
    """Set up logging for worker processes."""
    if logging.getLogger().handlers:
        # Already configured
        return

    # Get log file path (same as main process)
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    log_file = config_dir / "nexstar-gui.log"

    # Configure logging format with process and thread IDs
    log_format = "%(asctime)s [%(levelname)-8s] [PID:%(process)d TID:%(thread)d] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)-8s [PID:%(process)d TID:%(thread)d] %(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)


def calculate_object_visibility(
    obj_data: dict[str, Any],
    conditions_data: dict[str, Any],
    config_data: dict[str, Any],
    location_data: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Calculate visibility information for a single celestial object.

    This function is designed to be run in a separate process to avoid GIL limitations.
    All inputs must be serializable (dicts, not complex objects).

    Args:
        obj_data: Dictionary with object data (name, ra_hours, dec_degrees, magnitude, etc.)
        conditions_data: Dictionary with observation conditions (timestamp, latitude, longitude, etc.)
        config_data: Dictionary with telescope configuration (aperture_mm, focal_length_mm, etc.)
        location_data: Dictionary with observer location (latitude, longitude)

    Returns:
        Dictionary with visibility results, or None on error
    """
    import os

    # Set up logging in this worker process (spawned processes don't inherit logging config)
    _setup_worker_logging()

    # Log to verify we're in a separate process
    logger.info(f"Worker processing {obj_data.get('name', 'unknown')} in PID {os.getpid()}")

    try:
        # Import inside function so each process gets its own imports
        from celestron_nexstar.api.catalogs.catalogs import CelestialObject
        from celestron_nexstar.api.core.enums import CelestialObjectType, SkyBrightness
        from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
        from celestron_nexstar.api.observation.optics import OpticsConfiguration, Telescope, Eyepiece
        from celestron_nexstar.api.observation.visibility import assess_visibility, get_object_altitude_azimuth

        # Reconstruct CelestialObject from dict
        obj = CelestialObject(
            name=obj_data["name"],
            common_name=obj_data.get("common_name"),
            catalog=obj_data["catalog"],
            ra_hours=obj_data["ra_hours"],
            dec_degrees=obj_data["dec_degrees"],
            magnitude=obj_data.get("magnitude"),
            object_type=CelestialObjectType(obj_data["object_type"]),
            description=obj_data.get("description"),
            constellation=obj_data.get("constellation"),
        )

        # Reconstruct timestamp
        timestamp = datetime.fromisoformat(conditions_data["timestamp"])

        # Reconstruct configuration
        telescope = Telescope(
            display_name=config_data["telescope"]["display_name"],
            aperture_mm=config_data["telescope"]["aperture_mm"],
            focal_length_mm=config_data["telescope"]["focal_length_mm"],
            central_obstruction_mm=config_data["telescope"].get("central_obstruction_mm", 0.0),
        )
        eyepiece = Eyepiece(
            display_name=config_data["eyepiece"]["display_name"],
            focal_length_mm=config_data["eyepiece"]["focal_length_mm"],
            apparent_fov_degrees=config_data["eyepiece"]["apparent_fov_degrees"],
        )
        config = OpticsConfiguration(telescope=telescope, eyepiece=eyepiece)

        # Get sky brightness
        sky_brightness = SkyBrightness(conditions_data["sky_brightness"])

        # Create planner (note: this creates a new database connection in this process)
        planner = ObservationPlanner()

        # Reconstruct conditions from planner
        # We can't pickle the full Conditions object, so we'll use planner to get it fresh
        conditions = planner.get_tonight_conditions()

        # Perform visibility calculations
        vis_info = assess_visibility(
            obj,
            config=config,
            sky_brightness=sky_brightness,
            min_altitude_deg=0.0,
            observer_lat=location_data["latitude"],
            observer_lon=location_data["longitude"],
            dt=timestamp,
        )

        # Calculate visibility probability
        visibility_prob_result = planner._calculate_visibility_probability(obj, conditions, vis_info)
        if isinstance(visibility_prob_result, tuple):
            visibility_prob = visibility_prob_result[0]
        else:
            visibility_prob = visibility_prob_result or 0.0

        # Calculate priority
        priority = planner._determine_priority(obj, conditions, vis_info) if vis_info.is_visible else 5

        # Calculate reason
        reason = " / ".join(vis_info.reasons) if vis_info.reasons else "Not currently visible"

        # Calculate best viewing time and position at that time
        best_time = planner._calculate_best_viewing_time(
            obj, location_data["latitude"], location_data["longitude"], timestamp
        )
        transit_alt, transit_az = get_object_altitude_azimuth(
            obj, location_data["latitude"], location_data["longitude"], best_time
        )

        # Return results as dict (must be serializable)
        return {
            "name": obj.name,
            "altitude": transit_alt,
            "azimuth": transit_az,
            "best_viewing_time": best_time.isoformat(),
            "apparent_magnitude": obj.magnitude or 0.0,
            "observability_score": vis_info.observability_score,
            "visibility_probability": visibility_prob,
            "priority": priority,
            "reason": reason,
        }

    except Exception as e:
        logger.error(f"Error calculating visibility for {obj_data.get('name', 'unknown')}: {e}", exc_info=True)
        return None