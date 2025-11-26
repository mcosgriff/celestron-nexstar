"""
Unit tests for visibility.py

Tests visibility calculations, atmospheric extinction, and object filtering.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.observation.optics import EyepieceSpecs, OpticalConfiguration, TelescopeModel, TelescopeSpecs
from celestron_nexstar.api.observation.visibility import (
    VisibilityInfo,
    assess_visibility,
    calculate_atmospheric_extinction,
    calculate_parent_separation,
    filter_visible_objects,
    get_object_altitude_azimuth,
)


class TestCalculateAtmosphericExtinction(unittest.TestCase):
    """Test suite for calculate_atmospheric_extinction function"""

    def test_extinction_at_zenith(self):
        """Test extinction at zenith (should be minimal)"""
        extinction = calculate_atmospheric_extinction(90.0)
        self.assertAlmostEqual(extinction, 0.0, places=2)

    def test_extinction_below_horizon(self):
        """Test extinction below horizon (should be infinite)"""
        extinction = calculate_atmospheric_extinction(0.0)
        self.assertEqual(extinction, float("inf"))

    def test_extinction_negative_altitude(self):
        """Test extinction for negative altitude (below horizon)"""
        extinction = calculate_atmospheric_extinction(-10.0)
        self.assertEqual(extinction, float("inf"))

    def test_extinction_at_45_degrees(self):
        """Test extinction at 45 degrees altitude"""
        extinction = calculate_atmospheric_extinction(45.0)
        self.assertGreater(extinction, 0.0)
        self.assertLess(extinction, 1.0)  # Should be reasonable

    def test_extinction_at_30_degrees(self):
        """Test extinction at 30 degrees altitude"""
        extinction = calculate_atmospheric_extinction(30.0)
        self.assertGreater(extinction, 0.0)
        # Should be more than at 45 degrees
        extinction_45 = calculate_atmospheric_extinction(45.0)
        self.assertGreater(extinction, extinction_45)

    def test_extinction_at_10_degrees(self):
        """Test extinction at 10 degrees (low altitude)"""
        extinction = calculate_atmospheric_extinction(10.0)
        self.assertGreater(extinction, 0.0)
        # Should be significant at low altitude
        self.assertGreater(extinction, 0.1)

    def test_extinction_increases_with_lower_altitude(self):
        """Test that extinction increases as altitude decreases"""
        altitudes = [90, 60, 45, 30, 20, 15, 10]
        extinctions = [calculate_atmospheric_extinction(alt) for alt in altitudes]
        # Should be monotonically increasing (except zenith)
        for i in range(1, len(extinctions) - 1):
            self.assertGreater(extinctions[i], extinctions[i - 1])

    def test_extinction_low_altitude_rozenberg_formula(self):
        """Test extinction at very low altitude using Rozenberg formula (<10 degrees)"""
        # Test altitudes below 10 degrees which use Rozenberg formula
        extinction_5 = calculate_atmospheric_extinction(5.0)
        extinction_8 = calculate_atmospheric_extinction(8.0)
        extinction_9 = calculate_atmospheric_extinction(9.0)

        # All should be positive and significant
        self.assertGreater(extinction_5, 0.0)
        self.assertGreater(extinction_8, 0.0)
        self.assertGreater(extinction_9, 0.0)

        # Lower altitude should have more extinction
        self.assertGreater(extinction_5, extinction_8)
        self.assertGreater(extinction_8, extinction_9)


class TestGetObjectAltitudeAzimuth(unittest.TestCase):
    """Test suite for get_object_altitude_azimuth function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_obj = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )

    @patch("celestron_nexstar.api.observation.visibility.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.visibility.is_dynamic_object")
    @patch("celestron_nexstar.api.observation.visibility.get_observer_location")
    def test_get_object_altitude_azimuth_fixed_object(self, mock_get_location, mock_is_dynamic, mock_ra_dec_to_alt_az):
        """Test getting altitude/azimuth for a fixed object"""
        mock_get_location.return_value = MagicMock(latitude=40.0, longitude=-100.0)
        mock_is_dynamic.return_value = False
        mock_ra_dec_to_alt_az.return_value = (45.0, 180.0)

        alt, az = get_object_altitude_azimuth(self.test_obj)

        self.assertEqual(alt, 45.0)
        self.assertEqual(az, 180.0)
        mock_is_dynamic.assert_called_once_with(self.test_obj.name)

    @patch("celestron_nexstar.api.observation.visibility.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.visibility.get_planetary_position")
    @patch("celestron_nexstar.api.observation.visibility.is_dynamic_object")
    @patch("celestron_nexstar.api.observation.visibility.get_observer_location")
    def test_get_object_altitude_azimuth_dynamic_object(
        self, mock_get_location, mock_is_dynamic, mock_get_position, mock_ra_dec_to_alt_az
    ):
        """Test getting altitude/azimuth for a dynamic object"""
        mock_get_location.return_value = MagicMock(latitude=40.0, longitude=-100.0)
        mock_is_dynamic.return_value = True
        mock_get_position.return_value = (12.0, 20.0)  # RA, Dec
        mock_ra_dec_to_alt_az.return_value = (30.0, 90.0)

        dynamic_obj = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=0.0,
            dec_degrees=0.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        alt, az = get_object_altitude_azimuth(dynamic_obj)

        self.assertEqual(alt, 30.0)
        self.assertEqual(az, 90.0)
        mock_get_position.assert_called_once()

    @patch("celestron_nexstar.api.observation.visibility.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.visibility.is_dynamic_object")
    def test_get_object_altitude_azimuth_with_explicit_location(self, mock_is_dynamic, mock_ra_dec_to_alt_az):
        """Test getting altitude/azimuth with explicit observer location"""
        mock_is_dynamic.return_value = False
        mock_ra_dec_to_alt_az.return_value = (50.0, 270.0)

        alt, az = get_object_altitude_azimuth(self.test_obj, observer_lat=35.0, observer_lon=-120.0)

        self.assertEqual(alt, 50.0)
        self.assertEqual(az, 270.0)

    @patch("celestron_nexstar.api.observation.visibility.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.visibility.is_dynamic_object")
    def test_get_object_altitude_azimuth_with_datetime(self, mock_is_dynamic, mock_ra_dec_to_alt_az):
        """Test getting altitude/azimuth with explicit datetime"""
        mock_is_dynamic.return_value = False
        mock_ra_dec_to_alt_az.return_value = (60.0, 0.0)

        test_dt = datetime(2024, 6, 15, 20, 0, tzinfo=UTC)
        alt, az = get_object_altitude_azimuth(self.test_obj, dt=test_dt)

        self.assertEqual(alt, 60.0)
        self.assertEqual(az, 0.0)


class TestCalculateParentSeparation(unittest.TestCase):
    """Test suite for calculate_parent_separation function"""

    @patch("celestron_nexstar.api.observation.visibility.angular_separation")
    @patch("celestron_nexstar.api.observation.visibility.get_planetary_position")
    def test_calculate_parent_separation_jupiter_moon(self, mock_get_position, mock_angular_separation):
        """Test calculating separation for a Jupiter moon"""
        mock_get_position.side_effect = [
            (12.0, 20.0),  # Io position
            (12.1, 20.1),  # Jupiter position
        ]
        mock_angular_separation.return_value = 0.1  # degrees

        separation = calculate_parent_separation("Io", observer_lat=40.0, observer_lon=-100.0)

        self.assertIsNotNone(separation)
        self.assertAlmostEqual(separation, 6.0, places=1)  # 0.1 degrees = 6 arcminutes

    @patch("celestron_nexstar.api.observation.visibility.angular_separation")
    @patch("celestron_nexstar.api.observation.visibility.get_planetary_position")
    def test_calculate_parent_separation_saturn_moon(self, mock_get_position, mock_angular_separation):
        """Test calculating separation for a Saturn moon"""
        mock_get_position.side_effect = [
            (15.0, 25.0),  # Titan position
            (15.05, 25.05),  # Saturn position
        ]
        mock_angular_separation.return_value = 0.05  # degrees

        separation = calculate_parent_separation("Titan", observer_lat=40.0, observer_lon=-100.0)

        self.assertIsNotNone(separation)
        self.assertAlmostEqual(separation, 3.0, places=1)  # 0.05 degrees = 3 arcminutes

    def test_calculate_parent_separation_not_a_moon(self):
        """Test calculating separation for non-moon object"""
        separation = calculate_parent_separation("Vega")
        self.assertIsNone(separation)

    def test_calculate_parent_separation_earth_moon(self):
        """Test calculating separation for Earth's Moon (should return None)"""
        separation = calculate_parent_separation("Moon")
        self.assertIsNone(separation)

    @patch("celestron_nexstar.api.observation.visibility.get_planetary_position")
    def test_calculate_parent_separation_error_handling(self, mock_get_position):
        """Test error handling when position calculation fails"""
        mock_get_position.side_effect = Exception("Ephemeris error")

        separation = calculate_parent_separation("Io")
        self.assertIsNone(separation)


class TestAssessVisibility(unittest.TestCase):
    """Test suite for assess_visibility function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_obj = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )
        self.test_config = OpticalConfiguration(
            telescope=TelescopeSpecs(
                model=TelescopeModel.NEXSTAR_8SE,
                aperture_mm=200.0,
                focal_length_mm=2032.0,
                focal_ratio=10.16,
            ),
            eyepiece=EyepieceSpecs(focal_length_mm=10.0, apparent_fov_deg=50.0),
        )

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_visible_object(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for a visible object"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (45.0, 180.0)  # Good altitude

        visibility = assess_visibility(self.test_obj)

        self.assertTrue(visibility.is_visible)
        self.assertEqual(visibility.object_name, "Vega")
        self.assertEqual(visibility.altitude_deg, 45.0)
        self.assertGreater(visibility.observability_score, 0.0)

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_below_horizon(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for object below horizon"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (-10.0, 180.0)  # Below horizon

        visibility = assess_visibility(self.test_obj)

        self.assertFalse(visibility.is_visible)
        self.assertEqual(visibility.observability_score, 0.0)
        self.assertIn("Below horizon", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_too_faint(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for object that's too faint"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 10.0  # Limiting magnitude
        mock_get_alt_az.return_value = (45.0, 180.0)

        faint_obj = CelestialObject(
            name="Faint Galaxy",
            common_name=None,
            ra_hours=12.0,
            dec_degrees=30.0,
            magnitude=15.0,  # Too faint
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )

        visibility = assess_visibility(faint_obj)

        self.assertFalse(visibility.is_visible)
        self.assertEqual(visibility.observability_score, 0.0)
        self.assertIn("Too faint", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_low_altitude(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for object at low altitude"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (10.0, 180.0)  # Low altitude

        visibility = assess_visibility(self.test_obj, min_altitude_deg=20.0)

        self.assertTrue(visibility.is_visible)  # Still visible but reduced score
        self.assertLess(visibility.observability_score, 1.0)
        self.assertIn("Low altitude", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_position_error(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility when position calculation fails"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.side_effect = Exception("Position error")

        visibility = assess_visibility(self.test_obj)

        self.assertFalse(visibility.is_visible)
        self.assertEqual(visibility.observability_score, 0.0)
        self.assertIn("Cannot calculate position", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.calculate_parent_separation")
    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_moon_too_close(
        self, mock_get_config, mock_calc_limiting, mock_get_alt_az, mock_calc_separation
    ):
        """Test assessing visibility for moon too close to parent planet"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (45.0, 180.0)
        mock_calc_separation.return_value = 0.5  # Very close, less than 1 arcminute

        moon_obj = CelestialObject(
            name="Io",
            common_name="Io",
            ra_hours=12.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.MOON,
            catalog="moons",
        )

        visibility = assess_visibility(moon_obj)

        self.assertFalse(visibility.is_visible)
        self.assertEqual(visibility.observability_score, 0.0)
        self.assertIn("Too close to parent", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.calculate_parent_separation")
    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_moon_good_separation(
        self, mock_get_config, mock_calc_limiting, mock_get_alt_az, mock_calc_separation
    ):
        """Test assessing visibility for moon with good separation"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (45.0, 180.0)
        mock_calc_separation.return_value = 10.0  # Good separation

        moon_obj = CelestialObject(
            name="Io",
            common_name="Io",
            ra_hours=12.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.MOON,
            catalog="moons",
        )

        visibility = assess_visibility(moon_obj)

        self.assertTrue(visibility.is_visible)
        self.assertIn("Good separation", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.calculate_parent_separation")
    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_moon_close_separation(
        self, mock_get_config, mock_calc_limiting, mock_get_alt_az, mock_calc_separation
    ):
        """Test assessing visibility for moon with close separation (1-5 arcmin)"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (45.0, 180.0)
        mock_calc_separation.return_value = 3.0  # Close but not too close

        moon_obj = CelestialObject(
            name="Io",
            common_name="Io",
            ra_hours=12.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.MOON,
            catalog="moons",
        )

        visibility = assess_visibility(moon_obj)

        self.assertTrue(visibility.is_visible)  # Still visible but reduced score
        self.assertLess(visibility.observability_score, 1.0)
        self.assertIn("Close to parent planet", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_near_detection_limit(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for object near detection limit"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (45.0, 180.0)

        # Object with magnitude close to limiting magnitude
        near_limit_obj = CelestialObject(
            name="Faint Object",
            common_name=None,
            ra_hours=12.0,
            dec_degrees=30.0,
            magnitude=11.5,  # Close to limit of 12.0
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )

        visibility = assess_visibility(near_limit_obj)

        self.assertTrue(visibility.is_visible)
        self.assertLess(visibility.observability_score, 1.0)
        self.assertIn("Near detection limit", str(visibility.reasons))

    @patch("celestron_nexstar.api.observation.visibility.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_assess_visibility_excellent_altitude(self, mock_get_config, mock_calc_limiting, mock_get_alt_az):
        """Test assessing visibility for object at excellent altitude (>60 degrees)"""
        mock_get_config.return_value = self.test_config
        mock_calc_limiting.return_value = 12.0
        mock_get_alt_az.return_value = (65.0, 180.0)  # Excellent altitude

        bright_obj = CelestialObject(
            name="Bright Star",
            common_name=None,
            ra_hours=12.0,
            dec_degrees=30.0,
            magnitude=5.0,  # Well within limit
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )

        visibility = assess_visibility(bright_obj)

        self.assertTrue(visibility.is_visible)
        self.assertGreater(visibility.observability_score, 0.8)
        self.assertIn("Excellent altitude", str(visibility.reasons))


class TestFilterVisibleObjects(unittest.TestCase):
    """Test suite for filter_visible_objects function"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_objects = [
            CelestialObject(
                name="Vega",
                common_name="Vega",
                ra_hours=18.615,
                dec_degrees=38.784,
                magnitude=0.03,
                object_type=CelestialObjectType.STAR,
                catalog="bright_stars",
            ),
            CelestialObject(
                name="Faint Star",
                common_name=None,
                ra_hours=12.0,
                dec_degrees=30.0,
                magnitude=15.0,  # Too faint
                object_type=CelestialObjectType.STAR,
                catalog="bright_stars",
            ),
        ]
        self.test_config = OpticalConfiguration(
            telescope=TelescopeSpecs(
                model=TelescopeModel.NEXSTAR_8SE,
                aperture_mm=200.0,
                focal_length_mm=2032.0,
                focal_ratio=10.16,
            ),
            eyepiece=EyepieceSpecs(focal_length_mm=10.0, apparent_fov_deg=50.0),
        )

    @patch("celestron_nexstar.api.observation.visibility.assess_visibility")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_filter_visible_objects_empty_list(self, mock_get_config, mock_assess):
        """Test filtering empty list"""
        result = filter_visible_objects([])
        self.assertEqual(result, [])

    @patch("celestron_nexstar.api.observation.visibility.assess_visibility")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_filter_visible_objects_filters_invisible(self, mock_get_config, mock_assess):
        """Test that filter_visible_objects filters out invisible objects"""
        mock_get_config.return_value = self.test_config

        # Mock visibility assessments
        visible_info = VisibilityInfo(
            object_name="Vega",
            is_visible=True,
            magnitude=0.03,
            altitude_deg=45.0,
            azimuth_deg=180.0,
            limiting_magnitude=12.0,
            reasons=("Visible",),
            observability_score=0.9,
        )
        invisible_info = VisibilityInfo(
            object_name="Faint Star",
            is_visible=False,
            magnitude=15.0,
            altitude_deg=45.0,
            azimuth_deg=180.0,
            limiting_magnitude=12.0,
            reasons=("Too faint",),
            observability_score=0.0,
        )

        mock_assess.side_effect = [visible_info, invisible_info]

        result = filter_visible_objects(self.test_objects)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].name, "Vega")

    @patch("celestron_nexstar.api.observation.visibility.assess_visibility")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    def test_filter_visible_objects_sorts_by_score(self, mock_get_config, mock_assess):
        """Test that filter_visible_objects sorts by observability score"""
        mock_get_config.return_value = self.test_config

        # Create multiple visible objects with different scores
        objects = [
            CelestialObject(
                name="Star1",
                common_name=None,
                ra_hours=10.0,
                dec_degrees=20.0,
                magnitude=5.0,
                object_type=CelestialObjectType.STAR,
                catalog="bright_stars",
            ),
            CelestialObject(
                name="Star2",
                common_name=None,
                ra_hours=11.0,
                dec_degrees=21.0,
                magnitude=4.0,
                object_type=CelestialObjectType.STAR,
                catalog="bright_stars",
            ),
        ]

        info1 = VisibilityInfo(
            object_name="Star1",
            is_visible=True,
            magnitude=5.0,
            altitude_deg=45.0,
            azimuth_deg=180.0,
            limiting_magnitude=12.0,
            reasons=("Visible",),
            observability_score=0.5,  # Lower score
        )
        info2 = VisibilityInfo(
            object_name="Star2",
            is_visible=True,
            magnitude=4.0,
            altitude_deg=60.0,
            azimuth_deg=180.0,
            limiting_magnitude=12.0,
            reasons=("Visible",),
            observability_score=0.9,  # Higher score
        )

        mock_assess.side_effect = [info1, info2]

        result = filter_visible_objects(objects)

        # Should be sorted by score (best first)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0].name, "Star2")  # Higher score first
        self.assertEqual(result[1][0].name, "Star1")

    @patch("celestron_nexstar.api.observation.visibility.is_dynamic_object")
    @patch("celestron_nexstar.api.observation.visibility.get_observer_location")
    @patch("celestron_nexstar.api.observation.visibility.get_current_configuration")
    @patch("celestron_nexstar.api.observation.visibility.calculate_limiting_magnitude")
    def test_filter_visible_objects_vectorized_path(
        self, mock_calc_limiting, mock_get_config, mock_get_location, mock_is_dynamic
    ):
        """Test that filter_visible_objects uses vectorized path for >10 objects"""
        mock_get_config.return_value = self.test_config
        mock_get_location.return_value = MagicMock(latitude=40.0, longitude=-100.0)
        mock_calc_limiting.return_value = 12.0
        mock_is_dynamic.return_value = False

        # Create more than 10 objects to trigger vectorized path
        # Use objects that will be visible (above horizon, bright enough)
        many_objects = [
            CelestialObject(
                name=f"Star{i}",
                common_name=None,
                ra_hours=10.0 + (i * 0.1),  # Spread out in RA
                dec_degrees=40.0 + (i * 0.1),  # Above horizon for lat 40
                magnitude=5.0,  # Bright enough
                object_type=CelestialObjectType.STAR,
                catalog="bright_stars",
            )
            for i in range(15)
        ]

        # Mock datetime to a specific time
        test_dt = datetime(2024, 6, 15, 20, 0, tzinfo=UTC)
        with patch("celestron_nexstar.api.observation.visibility.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_dt
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = filter_visible_objects(
                many_objects,
                observer_lat=40.0,
                observer_lon=-100.0,
                dt=test_dt,
                min_observability_score=0.0,  # Low threshold to include more objects
            )

            # Should have used vectorized path and returned some results
            self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
