"""
Unit tests for optical configuration and calculations.
Tests telescope specs, eyepiece specs, limiting magnitude, and resolution calculations.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.enums import SkyBrightness
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
    load_configuration,
    save_configuration,
    set_current_configuration,
)


class TestTelescopeModel(unittest.TestCase):
    """Test suite for TelescopeModel enum."""

    def test_telescope_model_values(self):
        """Test telescope model enum values."""
        self.assertEqual(TelescopeModel.NEXSTAR_4SE.value, "nexstar_4se")
        self.assertEqual(TelescopeModel.NEXSTAR_5SE.value, "nexstar_5se")
        self.assertEqual(TelescopeModel.NEXSTAR_6SE.value, "nexstar_6se")
        self.assertEqual(TelescopeModel.NEXSTAR_8SE.value, "nexstar_8se")

    def test_telescope_model_display_names(self):
        """Test telescope model display names."""
        self.assertEqual(TelescopeModel.NEXSTAR_4SE.display_name, "NexStar 4SE")
        self.assertEqual(TelescopeModel.NEXSTAR_5SE.display_name, "NexStar 5SE")
        self.assertEqual(TelescopeModel.NEXSTAR_6SE.display_name, "NexStar 6SE")
        self.assertEqual(TelescopeModel.NEXSTAR_8SE.display_name, "NexStar 8SE")


class TestTelescopeSpecs(unittest.TestCase):
    """Test suite for TelescopeSpecs dataclass."""

    def test_telescope_specs_creation(self):
        """Test creating telescope specs."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
            obstruction_diameter_mm=52,
        )
        self.assertEqual(specs.model, TelescopeModel.NEXSTAR_6SE)
        self.assertEqual(specs.aperture_mm, 150)
        self.assertEqual(specs.focal_length_mm, 1500)
        self.assertEqual(specs.focal_ratio, 10.0)
        self.assertEqual(specs.obstruction_diameter_mm, 52)

    def test_telescope_specs_aperture_inches(self):
        """Test aperture conversion to inches."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
        )
        self.assertAlmostEqual(specs.aperture_inches, 5.9055, places=4)

    def test_telescope_specs_light_gathering_power(self):
        """Test light gathering power calculation."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
        )
        # (150 / 7)^2 = ~459
        self.assertAlmostEqual(specs.light_gathering_power, 459.18, places=2)

    def test_telescope_specs_effective_aperture_no_obstruction(self):
        """Test effective aperture with no obstruction (refractor)."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
            obstruction_diameter_mm=0,
        )
        self.assertEqual(specs.effective_aperture_mm, 150)

    def test_telescope_specs_effective_aperture_with_obstruction(self):
        """Test effective aperture with central obstruction."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
            obstruction_diameter_mm=52,
        )
        # Should be less than 150 due to obstruction
        self.assertLess(specs.effective_aperture_mm, 150)
        self.assertGreater(specs.effective_aperture_mm, 140)

    def test_telescope_specs_display_name(self):
        """Test telescope specs display name."""
        specs = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
        )
        self.assertEqual(specs.display_name, "NexStar 6SE")


class TestTelescopeDatabase(unittest.TestCase):
    """Test suite for telescope specifications database."""

    def test_all_models_have_specs(self):
        """Test that all telescope models have specs defined."""
        for model in TelescopeModel:
            self.assertIn(model, TELESCOPE_SPECS)

    def test_get_telescope_specs(self):
        """Test getting telescope specs by model."""
        specs = get_telescope_specs(TelescopeModel.NEXSTAR_6SE)
        self.assertEqual(specs.model, TelescopeModel.NEXSTAR_6SE)
        self.assertEqual(specs.aperture_mm, 150)
        self.assertEqual(specs.focal_length_mm, 1500)

    def test_telescope_specs_6se(self):
        """Test NexStar 6SE specifications."""
        specs = TELESCOPE_SPECS[TelescopeModel.NEXSTAR_6SE]
        self.assertEqual(specs.aperture_mm, 150)
        self.assertEqual(specs.focal_length_mm, 1500)
        self.assertEqual(specs.focal_ratio, 10.0)
        self.assertEqual(specs.obstruction_diameter_mm, 52)

    def test_telescope_specs_8se(self):
        """Test NexStar 8SE specifications."""
        specs = TELESCOPE_SPECS[TelescopeModel.NEXSTAR_8SE]
        self.assertEqual(specs.aperture_mm, 203)
        self.assertEqual(specs.focal_length_mm, 2032)
        self.assertEqual(specs.focal_ratio, 10.0)
        self.assertEqual(specs.obstruction_diameter_mm, 70)


class TestEyepieceSpecs(unittest.TestCase):
    """Test suite for EyepieceSpecs dataclass."""

    def setUp(self):
        """Set up test fixtures."""
        self.telescope = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150,
            focal_length_mm=1500,
            focal_ratio=10.0,
        )

    def test_eyepiece_specs_creation(self):
        """Test creating eyepiece specs."""
        eyepiece = EyepieceSpecs(
            focal_length_mm=25,
            apparent_fov_deg=50,
            name="25mm Plössl",
        )
        self.assertEqual(eyepiece.focal_length_mm, 25)
        self.assertEqual(eyepiece.apparent_fov_deg, 50)
        self.assertEqual(eyepiece.name, "25mm Plössl")

    def test_eyepiece_specs_defaults(self):
        """Test eyepiece specs with default values."""
        eyepiece = EyepieceSpecs(focal_length_mm=25)
        self.assertEqual(eyepiece.apparent_fov_deg, 50.0)
        self.assertIsNone(eyepiece.name)

    def test_eyepiece_magnification(self):
        """Test magnification calculation."""
        eyepiece = EyepieceSpecs(focal_length_mm=25)
        # 1500 / 25 = 60x
        self.assertEqual(eyepiece.magnification(self.telescope), 60.0)

    def test_eyepiece_exit_pupil(self):
        """Test exit pupil calculation."""
        eyepiece = EyepieceSpecs(focal_length_mm=25)
        # 150 / 60 = 2.5mm
        self.assertEqual(eyepiece.exit_pupil_mm(self.telescope), 2.5)

    def test_eyepiece_true_fov_deg(self):
        """Test true field of view in degrees."""
        eyepiece = EyepieceSpecs(focal_length_mm=25, apparent_fov_deg=50)
        # 50 / 60 = 0.833 degrees
        self.assertAlmostEqual(eyepiece.true_fov_deg(self.telescope), 0.833, places=3)

    def test_eyepiece_true_fov_arcmin(self):
        """Test true field of view in arcminutes."""
        eyepiece = EyepieceSpecs(focal_length_mm=25, apparent_fov_deg=50)
        # 0.833 * 60 = 50 arcmin
        self.assertAlmostEqual(eyepiece.true_fov_arcmin(self.telescope), 50.0, places=1)


class TestCommonEyepieces(unittest.TestCase):
    """Test suite for common eyepieces database."""

    def test_common_eyepieces_defined(self):
        """Test that common eyepieces are defined."""
        self.assertIn("25mm_plossl", COMMON_EYEPIECES)
        self.assertIn("10mm_plossl", COMMON_EYEPIECES)
        self.assertIn("32mm_plossl", COMMON_EYEPIECES)

    def test_common_eyepiece_25mm_plossl(self):
        """Test 25mm Plössl eyepiece specs."""
        eyepiece = COMMON_EYEPIECES["25mm_plossl"]
        self.assertEqual(eyepiece.focal_length_mm, 25)
        self.assertEqual(eyepiece.apparent_fov_deg, 50)
        self.assertIn("25mm", eyepiece.name)


class TestOpticalConfiguration(unittest.TestCase):
    """Test suite for OpticalConfiguration dataclass."""

    def setUp(self):
        """Set up test fixtures."""
        self.telescope = get_telescope_specs(TelescopeModel.NEXSTAR_6SE)
        self.eyepiece = COMMON_EYEPIECES["25mm_plossl"]
        self.config = OpticalConfiguration(
            telescope=self.telescope,
            eyepiece=self.eyepiece,
        )

    def test_optical_configuration_creation(self):
        """Test creating an optical configuration."""
        self.assertEqual(self.config.telescope, self.telescope)
        self.assertEqual(self.config.eyepiece, self.eyepiece)

    def test_optical_configuration_magnification(self):
        """Test configuration magnification property."""
        # 1500 / 25 = 60x
        self.assertEqual(self.config.magnification, 60.0)

    def test_optical_configuration_exit_pupil(self):
        """Test configuration exit pupil property."""
        # 150 / 60 = 2.5mm
        self.assertEqual(self.config.exit_pupil_mm, 2.5)

    def test_optical_configuration_true_fov_deg(self):
        """Test configuration true FOV in degrees."""
        self.assertAlmostEqual(self.config.true_fov_deg, 0.833, places=3)

    def test_optical_configuration_true_fov_arcmin(self):
        """Test configuration true FOV in arcminutes."""
        self.assertAlmostEqual(self.config.true_fov_arcmin, 50.0, places=1)


class TestLimitingMagnitude(unittest.TestCase):
    """Test suite for limiting magnitude calculations."""

    def test_limiting_magnitude_good_conditions(self):
        """Test limiting magnitude under good conditions."""
        # 150mm aperture, good sky
        mag = calculate_limiting_magnitude(150, SkyBrightness.GOOD)
        self.assertGreater(mag, 12.0)
        self.assertLess(mag, 18.0)

    def test_limiting_magnitude_excellent_conditions(self):
        """Test limiting magnitude under excellent conditions."""
        mag = calculate_limiting_magnitude(150, SkyBrightness.EXCELLENT)
        # Should be higher than good conditions
        mag_good = calculate_limiting_magnitude(150, SkyBrightness.GOOD)
        self.assertGreater(mag, mag_good)

    def test_limiting_magnitude_poor_conditions(self):
        """Test limiting magnitude under poor conditions."""
        mag = calculate_limiting_magnitude(150, SkyBrightness.POOR)
        # Should be lower than good conditions
        mag_good = calculate_limiting_magnitude(150, SkyBrightness.GOOD)
        self.assertLess(mag, mag_good)

    def test_limiting_magnitude_urban_conditions(self):
        """Test limiting magnitude under urban conditions."""
        mag = calculate_limiting_magnitude(150, SkyBrightness.URBAN)
        # Should be the lowest
        self.assertGreater(mag, 10.0)
        self.assertLess(mag, 18.0)

    def test_limiting_magnitude_with_high_magnification(self):
        """Test limiting magnitude with very small exit pupil (high mag)."""
        # Small exit pupil should reduce limiting magnitude
        mag_normal = calculate_limiting_magnitude(150, SkyBrightness.GOOD)
        mag_high_mag = calculate_limiting_magnitude(150, SkyBrightness.GOOD, exit_pupil_mm=0.3)
        self.assertLess(mag_high_mag, mag_normal)

    def test_limiting_magnitude_larger_aperture(self):
        """Test that larger aperture gives better limiting magnitude."""
        mag_150 = calculate_limiting_magnitude(150, SkyBrightness.GOOD)
        mag_203 = calculate_limiting_magnitude(203, SkyBrightness.GOOD)
        self.assertGreater(mag_203, mag_150)


class TestResolutionCalculations(unittest.TestCase):
    """Test suite for optical resolution calculations."""

    def test_dawes_limit_150mm(self):
        """Test Dawes limit for 150mm aperture."""
        limit = calculate_dawes_limit_arcsec(150)
        # 116 / 150 = 0.773 arcsec
        self.assertAlmostEqual(limit, 0.773, places=3)

    def test_dawes_limit_203mm(self):
        """Test Dawes limit for 203mm aperture."""
        limit = calculate_dawes_limit_arcsec(203)
        # 116 / 203 = 0.571 arcsec
        self.assertAlmostEqual(limit, 0.571, places=3)

    def test_rayleigh_criterion_150mm(self):
        """Test Rayleigh criterion for 150mm aperture."""
        limit = calculate_rayleigh_criterion_arcsec(150)
        # Should be around 0.9 arcsec for green light
        self.assertGreater(limit, 0.7)
        self.assertLess(limit, 1.1)

    def test_rayleigh_criterion_203mm(self):
        """Test Rayleigh criterion for 203mm aperture."""
        limit = calculate_rayleigh_criterion_arcsec(203)
        # Larger aperture should have better resolution (smaller angle)
        limit_150 = calculate_rayleigh_criterion_arcsec(150)
        self.assertLess(limit, limit_150)

    def test_rayleigh_criterion_different_wavelengths(self):
        """Test Rayleigh criterion with different wavelengths."""
        limit_green = calculate_rayleigh_criterion_arcsec(150, wavelength_nm=550)
        limit_red = calculate_rayleigh_criterion_arcsec(150, wavelength_nm=650)
        # Red light has longer wavelength, so worse resolution
        self.assertGreater(limit_red, limit_green)

    def test_is_object_resolvable_yes(self):
        """Test that large object is resolvable."""
        # Object 2 arcsec in size with 150mm aperture
        # Dawes limit is ~0.77 arcsec, so 2 arcsec should be resolvable
        self.assertTrue(is_object_resolvable(2.0, 150))

    def test_is_object_resolvable_no(self):
        """Test that small object is not resolvable."""
        # Object 0.5 arcsec in size with 150mm aperture
        # Dawes limit is ~0.77 arcsec, so 0.5 arcsec is not resolvable
        self.assertFalse(is_object_resolvable(0.5, 150))

    def test_is_object_resolvable_with_magnification(self):
        """Test resolvability considering magnification."""
        # Even if object is theoretically resolvable, need enough magnification
        result = is_object_resolvable(1.0, 150, magnification=5)
        # Low magnification might not show detail
        self.assertIsNotNone(result)


class TestConfigurationPersistence(unittest.TestCase):
    """Test suite for saving and loading optical configurations."""

    def setUp(self):
        """Set up test fixtures."""
        self.telescope = get_telescope_specs(TelescopeModel.NEXSTAR_6SE)
        self.eyepiece = COMMON_EYEPIECES["25mm_plossl"]
        self.config = OpticalConfiguration(
            telescope=self.telescope,
            eyepiece=self.eyepiece,
        )
        clear_current_configuration()

    def tearDown(self):
        """Clean up after each test."""
        clear_current_configuration()

    @patch("celestron_nexstar.api.optics.get_config_path")
    def test_save_configuration(self, mock_get_config_path):
        """Test saving optical configuration to file."""
        mock_path = MagicMock()
        mock_file = MagicMock()
        mock_path.open.return_value.__enter__.return_value = mock_file
        mock_get_config_path.return_value = mock_path

        save_configuration(self.config)

        mock_path.open.assert_called_once_with("w")

    @patch("celestron_nexstar.api.optics.get_config_path")
    def test_load_configuration_file_not_exists(self, mock_get_config_path):
        """Test loading configuration when file doesn't exist."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_config_path.return_value = mock_path

        config = load_configuration()

        self.assertIsNone(config)

    @patch("celestron_nexstar.api.optics.get_config_path")
    def test_load_configuration_success(self, mock_get_config_path):
        """Test successfully loading configuration from file."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        test_data = {
            "telescope_model": "nexstar_6se",
            "eyepiece": {
                "focal_length_mm": 25,
                "apparent_fov_deg": 50,
                "name": "25mm Plössl (standard)",
            },
        }

        mock_path.open.return_value.__enter__.return_value = MagicMock()
        mock_get_config_path.return_value = mock_path

        with patch("json.load", return_value=test_data):
            config = load_configuration()

        self.assertIsNotNone(config)
        self.assertEqual(config.telescope.model, TelescopeModel.NEXSTAR_6SE)
        self.assertEqual(config.eyepiece.focal_length_mm, 25)

    @patch("celestron_nexstar.api.optics.get_config_path")
    def test_load_configuration_corrupted_file(self, mock_get_config_path):
        """Test loading configuration with corrupted file."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.return_value.__enter__.return_value = MagicMock()
        mock_get_config_path.return_value = mock_path

        with patch("json.load", side_effect=json.JSONDecodeError("msg", "doc", 0)):
            config = load_configuration()

        self.assertIsNone(config)

    @patch("celestron_nexstar.api.optics.load_configuration")
    def test_get_current_configuration_from_file(self, mock_load):
        """Test getting current configuration loads from file."""
        mock_load.return_value = self.config

        config = get_current_configuration()

        self.assertEqual(config, self.config)
        mock_load.assert_called_once()

    @patch("celestron_nexstar.api.optics.load_configuration")
    def test_get_current_configuration_default(self, mock_load):
        """Test getting current configuration returns default if no saved config."""
        mock_load.return_value = None

        config = get_current_configuration()

        # Should return default configuration
        self.assertIsNotNone(config)
        self.assertEqual(config.telescope.model, TelescopeModel.NEXSTAR_6SE)
        self.assertEqual(config.eyepiece.focal_length_mm, 25)

    @patch("celestron_nexstar.api.optics.load_configuration")
    def test_get_current_configuration_cached(self, mock_load):
        """Test that configuration is cached."""
        mock_load.return_value = self.config

        # First call
        config1 = get_current_configuration()
        # Second call
        config2 = get_current_configuration()

        # Should only load once
        mock_load.assert_called_once()
        self.assertEqual(config1, config2)

    @patch("celestron_nexstar.api.optics.save_configuration")
    def test_set_current_configuration_with_save(self, mock_save):
        """Test setting current configuration with save=True."""
        set_current_configuration(self.config, save=True)

        mock_save.assert_called_once_with(self.config)

        # Verify it's now the current configuration
        current = get_current_configuration()
        self.assertEqual(current, self.config)

    @patch("celestron_nexstar.api.optics.save_configuration")
    def test_set_current_configuration_without_save(self, mock_save):
        """Test setting current configuration with save=False."""
        set_current_configuration(self.config, save=False)

        mock_save.assert_not_called()

        # Verify it's still the current configuration
        current = get_current_configuration()
        self.assertEqual(current, self.config)

    @patch("celestron_nexstar.api.optics.load_configuration")
    def test_clear_current_configuration(self, mock_load):
        """Test clearing cached configuration."""
        mock_load.return_value = self.config

        # Get configuration (caches it)
        get_current_configuration()
        mock_load.assert_called_once()

        # Clear the cache
        clear_current_configuration()

        # Get configuration again (should load from file again)
        get_current_configuration()
        self.assertEqual(mock_load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
