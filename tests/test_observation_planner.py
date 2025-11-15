"""
Unit tests for observation_planner.py

Tests observation session planning and recommendations.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase, SkyBrightness
from celestron_nexstar.api.core.exceptions import LocationNotSetError
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.api.location.weather import WeatherData
from celestron_nexstar.api.observation.observation_planner import (
    ObservingConditions,
    ObservingTarget,
    ObservationPlanner,
    RecommendedObject,
    get_tonight_plan,
)
from celestron_nexstar.api.location.observer import ObserverLocation


class TestObservingTarget(unittest.TestCase):
    """Test suite for ObservingTarget enum"""

    def test_enum_values(self):
        """Test ObservingTarget enum values"""
        self.assertEqual(ObservingTarget.PLANETS, "planets")
        self.assertEqual(ObservingTarget.MOON, "moon")
        self.assertEqual(ObservingTarget.DEEP_SKY, "deep_sky")
        self.assertEqual(ObservingTarget.DOUBLE_STARS, "double_stars")
        self.assertEqual(ObservingTarget.VARIABLE_STARS, "variable_stars")
        self.assertEqual(ObservingTarget.MESSIER, "messier")


class TestObservingConditions(unittest.TestCase):
    """Test suite for ObservingConditions dataclass"""

    def test_creation(self):
        """Test creating ObservingConditions"""
        weather = WeatherData(temperature_c=20.0, cloud_cover_percent=10.0)
        light_pollution = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )

        conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=weather,
            is_weather_suitable=True,
            light_pollution=light_pollution,
            limiting_magnitude=6.5,
            aperture_mm=150.0,
            moon_illumination=0.1,
            moon_altitude=10.0,
            moon_phase=MoonPhase.NEW_MOON,
            observing_quality_score=0.9,
            seeing_score=80.0,
            recommendations=("Good conditions",),
            warnings=(),
        )

        self.assertEqual(conditions.latitude, 40.0)
        self.assertEqual(conditions.longitude, -100.0)
        self.assertTrue(conditions.is_weather_suitable)
        self.assertEqual(conditions.observing_quality_score, 0.9)


class TestRecommendedObject(unittest.TestCase):
    """Test suite for RecommendedObject dataclass"""

    def test_creation(self):
        """Test creating RecommendedObject"""
        obj = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )

        recommended = RecommendedObject(
            obj=obj,
            altitude=45.0,
            azimuth=180.0,
            best_viewing_time=datetime.now(UTC),
            visible_duration_hours=8.0,
            apparent_magnitude=3.4,
            observability_score=0.9,
            visibility_probability=0.95,
            priority=1,
            reason="Excellent visibility",
            viewing_tips=("Use low power eyepiece",),
            moon_separation_deg=90.0,
        )

        self.assertEqual(recommended.obj, obj)
        self.assertEqual(recommended.altitude, 45.0)
        self.assertEqual(recommended.priority, 1)
        self.assertEqual(recommended.moon_separation_deg, 90.0)


class TestObservationPlanner(unittest.TestCase):
    """Test suite for ObservationPlanner class"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

    def test_get_tonight_conditions_function_exists(self):
        """Test that get_tonight_conditions function exists"""
        self.assertTrue(hasattr(self.planner, "get_tonight_conditions"))
        self.assertTrue(callable(self.planner.get_tonight_conditions))

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    def test_get_tonight_conditions_no_location(self, mock_get_location):
        """Test error when no location is set"""
        mock_get_location.return_value = None

        with self.assertRaises(LocationNotSetError) as context:
            self.planner.get_tonight_conditions()

        self.assertIn("No location set", str(context.exception))

    def test_get_recommended_objects_function_exists(self):
        """Test that get_recommended_objects function exists"""
        self.assertTrue(hasattr(self.planner, "get_recommended_objects"))
        self.assertTrue(callable(self.planner.get_recommended_objects))


class TestGetTonightPlan(unittest.TestCase):
    """Test suite for get_tonight_plan function"""

    @patch.object(ObservationPlanner, "get_tonight_conditions")
    def test_get_tonight_plan(self, mock_get_tonight_conditions):
        """Test get_tonight_plan function"""
        from celestron_nexstar.api.observation.observation_planner import ObservingConditions

        # Mock the conditions and recommendations
        weather = WeatherData(temperature_c=20.0, cloud_cover_percent=10.0)
        light_pollution = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )

        conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=51.4769,
            longitude=-0.0005,
            location_name="Test Location",
            weather=weather,
            is_weather_suitable=True,
            light_pollution=light_pollution,
            limiting_magnitude=6.5,
            aperture_mm=150.0,
            moon_illumination=0.1,
            moon_altitude=10.0,
            moon_phase=MoonPhase.NEW_MOON,
            observing_quality_score=0.9,
            seeing_score=80.0,
            recommendations=("Good conditions",),
            warnings=(),
        )

        mock_get_tonight_conditions.return_value = conditions

        # Mock get_recommended_objects
        with patch.object(ObservationPlanner, "get_recommended_objects", return_value=[]):
            result = get_tonight_plan()

            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)
            self.assertIsInstance(result[0], ObservingConditions)
            self.assertIsInstance(result[1], list)
            self.assertEqual(result[0], conditions)
            self.assertEqual(result[1], [])


if __name__ == "__main__":
    unittest.main()
