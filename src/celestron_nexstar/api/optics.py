"""
Optical Configuration and Calculations

Manages telescope and eyepiece specifications, calculates limiting magnitudes,
field of view, and object visibility based on optical parameters.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .constants import HUMAN_EYE_PUPIL_MM, MM_PER_INCH
from .enums import SkyBrightness


logger = logging.getLogger(__name__)


__all__ = [
    "COMMON_EYEPIECES",
    "EyepieceSpecs",
    "OpticalConfiguration",
    "TelescopeModel",
    "TelescopeSpecs",
    "calculate_dawes_limit_arcsec",
    "calculate_limiting_magnitude",
    "calculate_rayleigh_criterion_arcsec",
    "get_current_configuration",
    "get_telescope_specs",
    "is_object_resolvable",
    "set_current_configuration",
]


class TelescopeModel(str, Enum):
    """Supported telescope models."""

    NEXSTAR_4SE = "nexstar_4se"
    NEXSTAR_5SE = "nexstar_5se"
    NEXSTAR_6SE = "nexstar_6se"
    NEXSTAR_8SE = "nexstar_8se"

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        names = {
            TelescopeModel.NEXSTAR_4SE: "NexStar 4SE",
            TelescopeModel.NEXSTAR_5SE: "NexStar 5SE",
            TelescopeModel.NEXSTAR_6SE: "NexStar 6SE",
            TelescopeModel.NEXSTAR_8SE: "NexStar 8SE",
        }
        return names[self]


@dataclass(frozen=True, slots=True)
class TelescopeSpecs:
    """Telescope optical specifications."""

    model: TelescopeModel  # Telescope model enum
    aperture_mm: float  # Primary mirror/lens diameter in mm
    focal_length_mm: float  # Focal length in mm
    focal_ratio: float  # f-ratio (focal_length / aperture)
    obstruction_diameter_mm: float = 0.0  # Central obstruction diameter (0 for refractors)

    @property
    def aperture_inches(self) -> float:
        """Aperture in inches."""
        return self.aperture_mm / MM_PER_INCH

    @property
    def light_gathering_power(self) -> float:
        """
        Light gathering power relative to naked eye (7mm pupil).

        Returns:
            Factor by which telescope gathers more light than eye
        """
        return (self.aperture_mm / HUMAN_EYE_PUPIL_MM) ** 2

    @property
    def effective_aperture_mm(self) -> float:
        """
        Effective aperture accounting for central obstruction.

        For reflectors with secondary mirrors, the effective light-gathering
        area is reduced by the obstruction.
        """
        if self.obstruction_diameter_mm == 0:
            return self.aperture_mm

        # Calculate effective area
        main_area = math.pi * (self.aperture_mm / 2) ** 2
        obstruction_area = math.pi * (self.obstruction_diameter_mm / 2) ** 2
        effective_area = main_area - obstruction_area

        # Convert back to equivalent diameter
        return 2 * math.sqrt(effective_area / math.pi)

    @property
    def display_name(self) -> str:
        """Human-readable model name."""
        return self.model.display_name


# Telescope specifications database keyed by model enum
TELESCOPE_SPECS: dict[TelescopeModel, TelescopeSpecs] = {
    TelescopeModel.NEXSTAR_4SE: TelescopeSpecs(
        model=TelescopeModel.NEXSTAR_4SE,
        aperture_mm=102,
        focal_length_mm=1325,
        focal_ratio=13.0,
        obstruction_diameter_mm=35,
    ),
    TelescopeModel.NEXSTAR_5SE: TelescopeSpecs(
        model=TelescopeModel.NEXSTAR_5SE,
        aperture_mm=125,
        focal_length_mm=1250,
        focal_ratio=10.0,
        obstruction_diameter_mm=43,
    ),
    TelescopeModel.NEXSTAR_6SE: TelescopeSpecs(
        model=TelescopeModel.NEXSTAR_6SE,
        aperture_mm=150,
        focal_length_mm=1500,
        focal_ratio=10.0,
        obstruction_diameter_mm=52,  # Schmidt-Cassegrain secondary
    ),
    TelescopeModel.NEXSTAR_8SE: TelescopeSpecs(
        model=TelescopeModel.NEXSTAR_8SE,
        aperture_mm=203,
        focal_length_mm=2032,
        focal_ratio=10.0,
        obstruction_diameter_mm=70,
    ),
}


def get_telescope_specs(model: TelescopeModel) -> TelescopeSpecs:
    """
    Get specifications for a telescope model.

    Args:
        model: Telescope model enum

    Returns:
        Telescope specifications
    """
    return TELESCOPE_SPECS[model]


@dataclass
class EyepieceSpecs:
    """Eyepiece specifications."""

    focal_length_mm: float  # Eyepiece focal length
    apparent_fov_deg: float = 50.0  # Apparent field of view (degrees)
    name: str | None = None  # Optional eyepiece name/model

    def magnification(self, telescope: TelescopeSpecs) -> float:
        """
        Calculate magnification with this eyepiece on given telescope.

        Args:
            telescope: Telescope specifications

        Returns:
            Magnification factor
        """
        return telescope.focal_length_mm / self.focal_length_mm

    def exit_pupil_mm(self, telescope: TelescopeSpecs) -> float:
        """
        Calculate exit pupil diameter.

        The exit pupil is the diameter of the light beam exiting the eyepiece.
        For comfortable viewing, it should be ≤ eye's pupil diameter (7mm dark adapted).

        Args:
            telescope: Telescope specifications

        Returns:
            Exit pupil diameter in mm
        """
        return telescope.aperture_mm / self.magnification(telescope)

    def true_fov_deg(self, telescope: TelescopeSpecs) -> float:
        """
        Calculate true field of view in the sky.

        Args:
            telescope: Telescope specifications

        Returns:
            True field of view in degrees
        """
        return self.apparent_fov_deg / self.magnification(telescope)

    def true_fov_arcmin(self, telescope: TelescopeSpecs) -> float:
        """Calculate true field of view in arcminutes."""
        return self.true_fov_deg(telescope) * 60.0


# Common eyepieces for NexStar SE series telescopes
# Includes standard Plössl and wide-angle options commonly used
COMMON_EYEPIECES: dict[str, EyepieceSpecs] = {
    # Plössl eyepieces (50° FOV) - Standard included eyepieces
    "40mm_plossl": EyepieceSpecs(
        focal_length_mm=40,
        apparent_fov_deg=50,
        name="40mm Plössl",
    ),
    "32mm_plossl": EyepieceSpecs(
        focal_length_mm=32,
        apparent_fov_deg=50,
        name="32mm Plössl",
    ),
    "25mm_plossl": EyepieceSpecs(
        focal_length_mm=25,
        apparent_fov_deg=50,
        name="25mm Plössl (standard)",
    ),
    "20mm_plossl": EyepieceSpecs(
        focal_length_mm=20,
        apparent_fov_deg=50,
        name="20mm Plössl",
    ),
    "15mm_plossl": EyepieceSpecs(
        focal_length_mm=15,
        apparent_fov_deg=50,
        name="15mm Plössl",
    ),
    "12mm_plossl": EyepieceSpecs(
        focal_length_mm=12,
        apparent_fov_deg=50,
        name="12mm Plössl",
    ),
    "10mm_plossl": EyepieceSpecs(
        focal_length_mm=10,
        apparent_fov_deg=50,
        name="10mm Plössl",
    ),
    "8mm_plossl": EyepieceSpecs(
        focal_length_mm=8,
        apparent_fov_deg=50,
        name="8mm Plössl",
    ),
    "6mm_plossl": EyepieceSpecs(
        focal_length_mm=6,
        apparent_fov_deg=50,
        name="6mm Plössl",
    ),
    # Wide-angle eyepieces (68-82° FOV) - Popular upgrades
    "25mm_ultrawide": EyepieceSpecs(
        focal_length_mm=25,
        apparent_fov_deg=82,
        name="25mm Ultra-Wide (82°)",
    ),
    "20mm_ultrawide": EyepieceSpecs(
        focal_length_mm=20,
        apparent_fov_deg=82,
        name="20mm Ultra-Wide (82°)",
    ),
    "15mm_ultrawide": EyepieceSpecs(
        focal_length_mm=15,
        apparent_fov_deg=82,
        name="15mm Ultra-Wide (82°)",
    ),
    "10mm_ultrawide": EyepieceSpecs(
        focal_length_mm=10,
        apparent_fov_deg=82,
        name="10mm Ultra-Wide (82°)",
    ),
    "9mm_ultrawide": EyepieceSpecs(
        focal_length_mm=9,
        apparent_fov_deg=82,
        name="9mm Ultra-Wide (82°)",
    ),
    "8mm_ultrawide": EyepieceSpecs(
        focal_length_mm=8,
        apparent_fov_deg=82,
        name="8mm Ultra-Wide (82°)",
    ),
    # Medium wide-angle eyepieces (68° FOV)
    "24mm_wide": EyepieceSpecs(
        focal_length_mm=24,
        apparent_fov_deg=68,
        name="24mm Wide (68°)",
    ),
    "18mm_wide": EyepieceSpecs(
        focal_length_mm=18,
        apparent_fov_deg=68,
        name="18mm Wide (68°)",
    ),
    "13mm_wide": EyepieceSpecs(
        focal_length_mm=13,
        apparent_fov_deg=68,
        name="13mm Wide (68°)",
    ),
    "11mm_wide": EyepieceSpecs(
        focal_length_mm=11,
        apparent_fov_deg=68,
        name="11mm Wide (68°)",
    ),
    "7mm_wide": EyepieceSpecs(
        focal_length_mm=7,
        apparent_fov_deg=68,
        name="7mm Wide (68°)",
    ),
}


@dataclass
class OpticalConfiguration:
    """Complete optical configuration (telescope + eyepiece)."""

    telescope: TelescopeSpecs
    eyepiece: EyepieceSpecs

    @property
    def magnification(self) -> float:
        """Current magnification."""
        return self.eyepiece.magnification(self.telescope)

    @property
    def exit_pupil_mm(self) -> float:
        """Current exit pupil."""
        return self.eyepiece.exit_pupil_mm(self.telescope)

    @property
    def true_fov_deg(self) -> float:
        """Current true field of view in degrees."""
        return self.eyepiece.true_fov_deg(self.telescope)

    @property
    def true_fov_arcmin(self) -> float:
        """Current true field of view in arcminutes."""
        return self.eyepiece.true_fov_arcmin(self.telescope)


def calculate_limiting_magnitude(
    aperture_mm: float,
    sky_brightness: SkyBrightness = SkyBrightness.GOOD,
    exit_pupil_mm: float | None = None,
) -> float:
    """
    Calculate limiting magnitude for given conditions.

    Uses the formula: m_lim = 5 * log10(aperture_mm) + K
    where K depends on sky conditions and observing parameters.

    Args:
        aperture_mm: Telescope aperture in millimeters
        sky_brightness: Sky quality
            - excellent: Dark sky site (Bortle 1-2)
            - good: Rural sky (Bortle 3-4)
            - fair: Suburban sky (Bortle 5-6)
            - poor: Urban sky (Bortle 7-8)
            - urban: City center (Bortle 9)
        exit_pupil_mm: Exit pupil diameter. If None, assumes optimal value

    Returns:
        Limiting magnitude (dimmer = higher number)
    """
    # Base formula constant varies with conditions
    base_constants = {
        SkyBrightness.EXCELLENT: 7.5,  # Perfect dark sky
        SkyBrightness.GOOD: 7.0,  # Good rural sky
        SkyBrightness.FAIR: 6.5,  # Suburban
        SkyBrightness.POOR: 6.0,  # Urban
        SkyBrightness.URBAN: 5.5,  # City
    }

    k_base = base_constants[sky_brightness]

    # Calculate base limiting magnitude
    limiting_mag = 5 * math.log10(aperture_mm) + k_base

    # Adjust for exit pupil if very small (high magnification reduces visibility)
    if exit_pupil_mm is not None and exit_pupil_mm < 0.5:
        # Very high magnification makes faint objects harder to see
        penalty = (0.5 - exit_pupil_mm) * 2.0
        limiting_mag -= penalty

    return round(limiting_mag, 1)


def calculate_dawes_limit_arcsec(aperture_mm: float) -> float:
    """
    Calculate Dawes' limit for optical resolution.

    Dawes' limit is the theoretical angular resolution for separating
    double stars under ideal conditions.

    Formula: Resolution (arcsec) = 116 / aperture (mm)

    Args:
        aperture_mm: Telescope aperture in millimeters

    Returns:
        Angular resolution in arcseconds
    """
    return 116.0 / aperture_mm


def calculate_rayleigh_criterion_arcsec(aperture_mm: float, wavelength_nm: float = 550) -> float:
    """
    Calculate Rayleigh criterion for optical resolution.

    The Rayleigh criterion defines the minimum angular separation at which
    two point sources can be distinguished.

    Formula: θ = 1.22 * λ / D (in radians)

    Args:
        aperture_mm: Telescope aperture in millimeters
        wavelength_nm: Wavelength of light in nanometers (default: 550nm, green)

    Returns:
        Angular resolution in arcseconds
    """
    # Convert to same units (meters)
    aperture_m = aperture_mm / 1000.0
    wavelength_m = wavelength_nm / 1e9

    # Calculate in radians
    theta_rad = 1.22 * wavelength_m / aperture_m

    # Convert to arcseconds
    theta_arcsec = theta_rad * 206265.0

    return round(theta_arcsec, 2)


def is_object_resolvable(
    angular_size_arcsec: float,
    aperture_mm: float,
    magnification: float | None = None,
) -> bool:
    """
    Determine if an object's features are resolvable with given optics.

    Args:
        angular_size_arcsec: Object's angular size in arcseconds
        aperture_mm: Telescope aperture in millimeters
        magnification: Magnification being used (optional)

    Returns:
        True if object should be resolvable
    """
    dawes_limit = calculate_dawes_limit_arcsec(aperture_mm)

    # Object needs to be larger than resolution limit
    if angular_size_arcsec < dawes_limit:
        return False

    # If magnification specified, check if it's sufficient to see detail
    if magnification is not None:
        # Rule of thumb: need ~1 arcmin per mm of exit pupil to see detail clearly
        # This translates to needing sufficient magnification
        min_mag_needed = angular_size_arcsec / 120.0  # Rough heuristic
        if magnification < min_mag_needed:
            return False

    return True


# Global current configuration
_current_config: OpticalConfiguration | None = None


def get_config_path() -> Path:
    """Get path to optical configuration file."""
    config_dir = Path.home() / ".config" / "celestron-nexstar"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "optical_config.json"


def save_configuration(config: OpticalConfiguration) -> None:
    """
    Save optical configuration to file.

    Args:
        config: Optical configuration to save
    """
    config_path = get_config_path()
    logger.info(
        f"Saving optical configuration: {config.telescope.display_name} with {config.eyepiece.name or f'{config.eyepiece.focal_length_mm}mm eyepiece'}"
    )

    data = {
        "telescope_model": config.telescope.model.value,  # Save enum value
        "eyepiece": {
            "focal_length_mm": config.eyepiece.focal_length_mm,
            "apparent_fov_deg": config.eyepiece.apparent_fov_deg,
            "name": config.eyepiece.name,
        },
    }

    with config_path.open("w") as f:
        json.dump(data, f, indent=2)

    logger.debug(f"Configuration saved to {config_path}")


def load_configuration() -> OpticalConfiguration | None:
    """
    Load optical configuration from file.

    Returns:
        Saved configuration, or None if not configured
    """
    config_path = get_config_path()

    if not config_path.exists():
        return None

    try:
        with config_path.open("r") as f:
            data = json.load(f)

        # Load telescope by model enum
        model = TelescopeModel(data["telescope_model"])
        telescope = get_telescope_specs(model)

        # Load eyepiece
        eyepiece = EyepieceSpecs(**data["eyepiece"])

        return OpticalConfiguration(telescope=telescope, eyepiece=eyepiece)

    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # If config is corrupted, return None
        return None


def get_current_configuration() -> OpticalConfiguration:
    """
    Get current optical configuration.

    Returns cached configuration if set, otherwise loads from file.
    If no saved config, returns default (NexStar 6SE + 25mm Plössl).

    Returns:
        Current optical configuration
    """
    global _current_config

    if _current_config is None:
        _current_config = load_configuration()

    if _current_config is None:
        # Default to NexStar 6SE with 25mm eyepiece
        _current_config = OpticalConfiguration(
            telescope=get_telescope_specs(TelescopeModel.NEXSTAR_6SE),
            eyepiece=COMMON_EYEPIECES["25mm_plossl"],
        )

    return _current_config


def set_current_configuration(config: OpticalConfiguration, save: bool = True) -> None:
    """
    Set current optical configuration.

    Args:
        config: New optical configuration
        save: Whether to save to config file (default: True)
    """
    global _current_config
    _current_config = config

    if save:
        save_configuration(config)


def clear_current_configuration() -> None:
    """Clear cached configuration (will reload from file on next access)."""
    global _current_config
    _current_config = None
