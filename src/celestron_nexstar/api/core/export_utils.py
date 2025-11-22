"""
Export utilities for generating standardized filenames.

This module provides utilities for generating consistent export filenames
across CLI and GUI applications.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from celestron_nexstar.api.location.observer import ObserverLocation, get_observer_location
from celestron_nexstar.api.observation.optics import load_configuration


def generate_export_filename(
    command: str,
    viewing_type: str = "telescope",
    binocular_model: str | None = None,
    location: ObserverLocation | None = None,
    date_suffix: str = "",
    **kwargs: str,
) -> Path:
    """
    Generate standardized export filename based on command, equipment, location, and date.

    Args:
        command: Command name (e.g., "tonight", "conditions", "planets")
        viewing_type: Type of viewing equipment ("telescope", "binoculars", "naked-eye")
        binocular_model: Binocular model string (e.g., "10x50") - only used if viewing_type is "binoculars"
        location: Observer location (if None, will fetch from config)
        date_suffix: Optional date suffix to append
        **kwargs: Additional keyword arguments for custom filename parts

    Returns:
        Path object with generated filename

    Examples:
        >>> filename = generate_export_filename("tonight", viewing_type="telescope")
        >>> # Returns: nexstar_6se_los_angeles_2024-10-14_tonight.txt

        >>> filename = generate_export_filename("tonight", viewing_type="binoculars", binocular_model="10x50")
        >>> # Returns: binoculars_10x50_los_angeles_2024-10-14_tonight.txt

        >>> filename = generate_export_filename("planets", viewing_type="naked-eye")
        >>> # Returns: naked_eye_los_angeles_2024-10-14_planets.txt
    """
    # Get location if not provided
    if location is None:
        try:
            location = get_observer_location()
        except Exception:
            location = None

    # Get location name (shortened, sanitized)
    if location and location.name:
        location_short = location.name.lower()
        # Replace spaces and special characters with underscores
        location_short = location_short.replace(" ", "_").replace(",", "_").replace(".", "_")
        # Remove other special characters that are invalid in filenames
        location_short = re.sub(r"[^\w\s-]", "", location_short)
        location_short = re.sub(r"[-\s]+", "_", location_short)
        # Remove common suffixes and limit length
        location_short = location_short.replace("_(default)", "").replace("_observatory", "")
        location_short = location_short[:20]  # Limit length
    else:
        location_short = "unknown"

    # Get date
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Generate filename based on viewing type
    if viewing_type == "telescope":
        config = load_configuration()
        if config:
            telescope_name = config.telescope.model.value.replace("nexstar_", "").replace("_", "")
        else:
            telescope_name = "no_telescope"
        filename = f"nexstar_{telescope_name}_{location_short}_{date_str}_{command}"
    elif viewing_type == "binoculars":
        model_safe = (binocular_model or "10x50").replace("x", "x").replace("/", "_").lower()
        filename = f"binoculars_{model_safe}_{location_short}_{date_str}_{command}"
    else:  # naked-eye
        filename = f"naked_eye_{location_short}_{date_str}_{command}"

    # Add date suffix if provided
    if date_suffix:
        filename += f"_{date_suffix.lstrip('_')}"

    # Add any additional kwargs as filename parts
    if kwargs:
        extra_parts = []
        for _key, value in sorted(kwargs.items()):
            if value:
                # Sanitize value for filename
                sanitized = re.sub(r"[^\w\s-]", "", str(value))
                sanitized = re.sub(r"[-\s]+", "-", sanitized)
                sanitized = sanitized[:30]  # Limit length
                if sanitized:
                    extra_parts.append(sanitized)
        if extra_parts:
            filename += "_" + "_".join(extra_parts)

    return Path(f"{filename}.txt")


def generate_vacation_export_filename(
    command: str,
    location: str | None = None,
    days: int | None = None,
    date_suffix: str = "",
) -> Path:
    """
    Generate export filename for vacation planning commands.

    Args:
        command: Command name (e.g., "view", "plan", "dark-sites")
        location: Vacation location string
        days: Number of days (optional)
        date_suffix: Optional date suffix to append

    Returns:
        Path object with generated filename

    Examples:
        >>> filename = generate_vacation_export_filename("view", location="Denver, CO")
        >>> # Returns: nexstar_vacation_2024-10-14_view_Denver-CO.txt
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    parts = [f"nexstar_vacation_{date_str}", command]

    if location:
        # Sanitize location for filename (remove special chars, limit length)
        sanitized = re.sub(r"[^\w\s-]", "", location)
        sanitized = re.sub(r"[-\s]+", "-", sanitized)
        sanitized = sanitized[:30]  # Limit length
        if sanitized:
            parts.append(sanitized)

    if days is not None:
        parts.append(f"{days}days")

    if date_suffix:
        parts.append(date_suffix.lstrip("_"))

    filename = "_".join(parts) + ".txt"
    return Path(filename)


def generate_catalog_export_filename(catalog: str) -> Path:
    """
    Generate export filename for catalog listing commands.

    Args:
        catalog: Catalog name (e.g., "messier", "bright_stars")

    Returns:
        Path object with generated filename

    Examples:
        >>> filename = generate_catalog_export_filename("messier")
        >>> # Returns: nexstar_catalog_messier_2024-10-14.txt
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"nexstar_catalog_{catalog}_{date_str}.txt"
    return Path(filename)
