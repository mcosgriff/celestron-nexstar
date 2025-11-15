"""
Unit tests for observation/scoring.py

Tests observation quality scoring functions including light pollution,
moon separation, object type scoring, and nighttime detection.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.observation.observation_planner import ObservingConditions
from celestron_nexstar.api.observation.scoring import (
    calculate_light_pollution_score,
    calculate_moon_separation_score,
    calculate_object_type_score,
    is_nighttime,
)
from celestron_nexstar.api.observation.visibility import VisibilityInfo


class TestCalculateLightPollutionScore(unittest.TestCase):
    """Test suite for calculate_light_pollution_score function"""

    def test_class_1_excellent(self):
        """Test Bortle Class 1 (excellent dark sky)"""
        score = calculate_light_pollution_score(BortleClass.CLASS_1)
        self.assertEqual(score, 1.0)

    def test_class_2_typical_dark(self):
        """Test Bortle Class 2 (typical dark site)"""
        score = calculate_light_pollution_score(BortleClass.CLASS_2)
        self.assertEqual(score, 0.95)

    def test_class_3_rural(self):
        """Test Bortle Class 3 (rural sky)"""
        score = calculate_light_pollution_score(BortleClass.CLASS_3)
        self.assertEqual(score, 0.85)

    def test_class_5_suburban(self):
        """Test Bortle Class 5 (suburban sky)"""
        score = calculate_light_pollution_score(BortleClass.CLASS_5)
        self.assertEqual(score, 0.50)

    def test_class_9_inner_city(self):
        """Test Bortle Class 9 (inner-city sky)"""
        score = calculate_light_pollution_score(BortleClass.CLASS_9)
        self.assertEqual(score, 0.0)

    def test_all_classes_decreasing(self):
        """Test that scores decrease as Bortle class increases"""
        classes = [
            BortleClass.CLASS_1,
            BortleClass.CLASS_2,
            BortleClass.CLASS_3,
            BortleClass.CLASS_4,
            BortleClass.CLASS_5,
            BortleClass.CLASS_6,
            BortleClass.CLASS_7,
            BortleClass.CLASS_8,
            BortleClass.CLASS_9,
        ]
        scores = [calculate_light_pollution_score(bc) for bc in classes]
        for i in range(1, len(scores)):
            self.assertLessEqual(scores[i], scores[i - 1])


class TestCalculateMoonSeparationScore(unittest.TestCase):
    """Test suite for calculate_moon_separation_score function"""

    def test_separation_90_degrees_excellent(self):
        """Test separation >90 degrees (excellent, opposite sides)"""
        # With new moon (0% illumination), score should be 1.0
        score, sep = calculate_moon_separation_score(0.0, 0.0, 6.0, 0.0, 0.0)
        self.assertAlmostEqual(score, 1.0, places=1)
        self.assertAlmostEqual(sep, 90.0, places=1)

    def test_separation_60_degrees_good(self):
        """Test separation ~60 degrees (good)"""
        # With new moon to avoid brightness penalty
        score, sep = calculate_moon_separation_score(0.0, 0.0, 4.0, 0.0, 0.0)
        self.assertGreater(score, 0.7)
        self.assertLess(score, 1.0)

    def test_separation_30_degrees_fair(self):
        """Test separation ~30 degrees (fair)"""
        # With new moon to avoid brightness penalty
        score, sep = calculate_moon_separation_score(0.0, 0.0, 2.0, 0.0, 0.0)
        self.assertGreater(score, 0.4)
        self.assertLess(score, 0.7)

    def test_separation_15_degrees_poor(self):
        """Test separation ~15 degrees (poor)"""
        score, sep = calculate_moon_separation_score(0.0, 0.0, 1.0, 0.0, 0.5)
        self.assertGreater(score, 0.1)
        self.assertLess(score, 0.4)

    def test_separation_very_close_very_bad(self):
        """Test separation <15 degrees (very bad)"""
        score, sep = calculate_moon_separation_score(0.0, 0.0, 0.1, 0.0, 0.5)
        self.assertLess(score, 0.2)

    def test_new_moon_no_penalty(self):
        """Test that new moon (0% illumination) has minimal penalty"""
        score_new, _ = calculate_moon_separation_score(0.0, 0.0, 2.0, 0.0, 0.0)
        score_full, _ = calculate_moon_separation_score(0.0, 0.0, 2.0, 0.0, 1.0)
        self.assertGreater(score_new, score_full)

    def test_full_moon_maximum_penalty(self):
        """Test that full moon (100% illumination) has maximum penalty"""
        score_new, _ = calculate_moon_separation_score(0.0, 0.0, 2.0, 0.0, 0.0)
        score_full, _ = calculate_moon_separation_score(0.0, 0.0, 2.0, 0.0, 1.0)
        # Full moon should have lower score due to brightness penalty
        self.assertLess(score_full, score_new)


class TestCalculateObjectTypeScore(unittest.TestCase):
    """Test suite for calculate_object_type_score function"""

    def setUp(self):
        """Set up test fixtures"""
        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test",
            weather=MagicMock(),
            is_weather_suitable=True,
            light_pollution=LightPollutionData(
                bortle_class=BortleClass.CLASS_3,
                sqm_value=21.5,
                naked_eye_limiting_magnitude=6.5,
                milky_way_visible=True,
                airglow_visible=True,
                zodiacal_light_visible=True,
                description="Good",
                recommendations=("Good for observing",),
            ),
            limiting_magnitude=6.5,
            aperture_mm=150.0,
            moon_illumination=0.1,
            moon_altitude=10.0,
            moon_phase=MagicMock(),
            observing_quality_score=0.8,
            seeing_score=80.0,
            recommendations=("Good conditions",),
            warnings=(),
        )

        self.visibility = VisibilityInfo(
            object_name="Test",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=5.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )

    def test_planet_high_seeing_weight(self):
        """Test that planets weight seeing heavily"""
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        # High seeing conditions
        conditions_good_seeing = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 90.0}
        )
        score_good = calculate_object_type_score(planet, conditions_good_seeing, self.visibility, 0.8, None)

        # Low seeing conditions
        conditions_poor_seeing = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 30.0}
        )
        score_poor = calculate_object_type_score(planet, conditions_poor_seeing, self.visibility, 0.8, None)

        self.assertGreater(score_good, score_poor)

    def test_galaxy_light_pollution_sensitive(self):
        """Test that galaxies are sensitive to light pollution"""
        galaxy = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.7,
            dec_degrees=41.3,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )

        # Good light pollution (Bortle 2)
        lp_good = LightPollutionData(
            bortle_class=BortleClass.CLASS_2,
            sqm_value=22.0,
            naked_eye_limiting_magnitude=7.0,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Excellent",
            recommendations=("Excellent conditions",),
        )
        score_good = calculate_object_type_score(galaxy, self.conditions, self.visibility, 0.8, lp_good)

        # Poor light pollution (Bortle 7)
        lp_poor = LightPollutionData(
            bortle_class=BortleClass.CLASS_7,
            sqm_value=18.0,
            naked_eye_limiting_magnitude=4.0,
            milky_way_visible=False,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Poor",
            recommendations=("Poor conditions",),
        )
        score_poor = calculate_object_type_score(galaxy, self.conditions, self.visibility, 0.8, lp_poor)

        self.assertGreater(score_good, score_poor)

    def test_planet_light_pollution_insensitive(self):
        """Test that planets are not sensitive to light pollution"""
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        # Good light pollution
        lp_good = LightPollutionData(
            bortle_class=BortleClass.CLASS_2,
            sqm_value=22.0,
            naked_eye_limiting_magnitude=7.0,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Excellent",
            recommendations=("Excellent conditions",),
        )
        score_good = calculate_object_type_score(planet, self.conditions, self.visibility, 0.8, lp_good)

        # Poor light pollution
        lp_poor = LightPollutionData(
            bortle_class=BortleClass.CLASS_7,
            sqm_value=18.0,
            naked_eye_limiting_magnitude=4.0,
            milky_way_visible=False,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Poor",
            recommendations=("Poor conditions",),
        )
        score_poor = calculate_object_type_score(planet, self.conditions, self.visibility, 0.8, lp_poor)

        # Scores should be similar (planets not affected by light pollution)
        self.assertAlmostEqual(score_good, score_poor, places=2)

    def test_no_light_pollution_data(self):
        """Test scoring without light pollution data"""
        obj = CelestialObject(
            name="Test",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )

        score = calculate_object_type_score(obj, self.conditions, self.visibility, 0.8, None)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestIsNighttime(unittest.TestCase):
    """Test suite for is_nighttime function"""

    @patch("celestron_nexstar.api.astronomy.solar_system.get_sun_info")
    def test_nighttime_when_sun_below_horizon(self, mock_get_sun_info):
        """Test that nighttime is detected when sun is below horizon"""
        mock_sun_info = MagicMock()
        mock_sun_info.is_daytime = False
        mock_get_sun_info.return_value = mock_sun_info

        result = is_nighttime(datetime.now(UTC), 40.0, -100.0)
        self.assertTrue(result)

    @patch("celestron_nexstar.api.astronomy.solar_system.get_sun_info")
    def test_daytime_when_sun_above_horizon(self, mock_get_sun_info):
        """Test that daytime is detected when sun is above horizon"""
        mock_sun_info = MagicMock()
        mock_sun_info.is_daytime = True
        mock_get_sun_info.return_value = mock_sun_info

        result = is_nighttime(datetime.now(UTC), 40.0, -100.0)
        self.assertFalse(result)

    @patch("celestron_nexstar.api.astronomy.solar_system.get_sun_info")
    def test_fallback_when_sun_info_none(self, mock_get_sun_info):
        """Test fallback behavior when sun info is None"""
        mock_get_sun_info.return_value = None

        result = is_nighttime(datetime.now(UTC), 40.0, -100.0)
        # Should assume daytime if we can't determine
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
