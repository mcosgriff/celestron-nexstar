"""
Extended unit tests for observation_planner.py

Tests internal methods and edge cases for observation planning.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase, SkyBrightness
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.api.location.weather import WeatherData
from celestron_nexstar.api.observation.observation_planner import (
    ObservingConditions,
    ObservationPlanner,
    RecommendedObject,
)
from celestron_nexstar.api.observation.visibility import VisibilityInfo


class TestObservationPlannerInternalMethods(unittest.TestCase):
    """Test suite for ObservationPlanner internal methods"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

        self.weather = WeatherData(temperature_c=20.0, cloud_cover_percent=10.0)
        self.lp_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )

        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=self.weather,
            is_weather_suitable=True,
            light_pollution=self.lp_data,
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

        self.obj = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )

        self.vis_info = VisibilityInfo(
            object_name="M31",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )

    def test_calculate_visibility_probability_planet(self):
        """Test visibility probability calculation for planets"""
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        prob = self.planner._calculate_visibility_probability(planet, self.conditions, self.vis_info)
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_calculate_visibility_probability_poor_seeing(self):
        """Test visibility probability with poor seeing"""
        poor_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 30.0}
        )

        prob = self.planner._calculate_visibility_probability(self.obj, poor_conditions, self.vis_info)
        self.assertLess(prob, 1.0)  # Should be reduced by poor seeing

    def test_calculate_visibility_probability_cloudy(self):
        """Test visibility probability with cloud cover"""
        cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=85.0)
        cloudy_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "weather": cloudy_weather}
        )

        prob = self.planner._calculate_visibility_probability(self.obj, cloudy_conditions, self.vis_info)
        self.assertLess(prob, 1.0)  # Should be reduced by clouds

    def test_calculate_quality_score_excellent_weather(self):
        """Test quality score calculation with excellent weather"""
        score = self.planner._calculate_quality_score(
            self.weather, self.lp_data, 0.1, "excellent"
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertGreater(score, 0.5)  # Should be high for excellent conditions

    def test_calculate_quality_score_poor_weather(self):
        """Test quality score calculation with poor weather"""
        # Use worse light pollution for truly poor conditions
        lp_poor = LightPollutionData(
            bortle_class=BortleClass.CLASS_8,
            sqm_value=18.0,
            naked_eye_limiting_magnitude=4.0,
            milky_way_visible=False,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Poor",
            recommendations=("Poor conditions",),
        )
        score = self.planner._calculate_quality_score(
            self.weather, lp_poor, 0.1, "poor"
        )
        self.assertLess(score, 0.5)  # Should be lower for poor conditions

    def test_calculate_quality_score_full_moon(self):
        """Test quality score with full moon"""
        score_full = self.planner._calculate_quality_score(
            self.weather, self.lp_data, 1.0, "excellent"
        )
        score_new = self.planner._calculate_quality_score(
            self.weather, self.lp_data, 0.0, "excellent"
        )
        self.assertLess(score_full, score_new)  # Full moon should reduce score

    def test_calculate_quality_score_light_pollution(self):
        """Test quality score with different light pollution levels"""
        lp_dark = LightPollutionData(
            bortle_class=BortleClass.CLASS_2,
            sqm_value=22.0,
            naked_eye_limiting_magnitude=7.0,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Excellent",
            recommendations=("Excellent conditions",),
        )
        lp_bright = LightPollutionData(
            bortle_class=BortleClass.CLASS_8,
            sqm_value=18.0,
            naked_eye_limiting_magnitude=4.0,
            milky_way_visible=False,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Poor",
            recommendations=("Poor conditions",),
        )

        score_dark = self.planner._calculate_quality_score(self.weather, lp_dark, 0.1, "excellent")
        score_bright = self.planner._calculate_quality_score(self.weather, lp_bright, 0.1, "excellent")
        self.assertGreater(score_dark, score_bright)

    def test_generate_recommendations_clear_skies(self):
        """Test recommendation generation for clear skies"""
        recs, warnings = self.planner._generate_recommendations(
            self.weather, self.lp_data, 0.1, 0.9, "excellent", ""
        )
        self.assertIsInstance(recs, tuple)
        self.assertIsInstance(warnings, tuple)

    def test_generate_recommendations_cloudy(self):
        """Test recommendation generation for cloudy conditions"""
        cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=85.0)
        recs, warnings = self.planner._generate_recommendations(
            cloudy_weather, self.lp_data, 0.1, 0.3, "poor", "High cloud cover"
        )
        self.assertGreater(len(warnings), 0)

    def test_generate_recommendations_full_moon(self):
        """Test recommendation generation with full moon"""
        recs, warnings = self.planner._generate_recommendations(
            self.weather, self.lp_data, 1.0, 0.5, "good", ""
        )
        # Should have warning about bright moon
        self.assertGreater(len(warnings), 0)

    def test_generate_recommendations_dark_skies(self):
        """Test recommendation generation for dark skies"""
        lp_dark = LightPollutionData(
            bortle_class=BortleClass.CLASS_2,
            sqm_value=22.0,
            naked_eye_limiting_magnitude=7.0,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Excellent",
            recommendations=("Excellent conditions",),
        )
        recs, warnings = self.planner._generate_recommendations(
            self.weather, lp_dark, 0.1, 0.9, "excellent", ""
        )
        # Should recommend faint objects
        self.assertGreater(len(recs), 0)

    def test_score_object_visible(self):
        """Test scoring a visible object"""
        rec = self.planner._score_object(self.obj, self.conditions, self.vis_info, moon_ra=12.0, moon_dec=45.0)
        self.assertIsNotNone(rec)
        self.assertIsInstance(rec, RecommendedObject)
        self.assertEqual(rec.obj, self.obj)

    def test_score_object_not_visible(self):
        """Test scoring a non-visible object"""
        not_visible = VisibilityInfo(
            object_name="M31",
            altitude_deg=5.0,
            azimuth_deg=180.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=False,
            observability_score=0.1,
            reasons=("Too low",),
        )

        rec = self.planner._score_object(self.obj, self.conditions, not_visible, moon_ra=12.0, moon_dec=45.0)
        self.assertIsNone(rec)

    def test_determine_priority_excellent_seeing(self):
        """Test priority determination with excellent seeing"""
        excellent_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 90.0}
        )

        # Faint galaxy should get priority 1 with excellent seeing
        faint_galaxy = CelestialObject(
            name="Faint Galaxy",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=12.0,
            object_type=CelestialObjectType.GALAXY,
            catalog="test",
        )
        priority = self.planner._determine_priority(faint_galaxy, excellent_conditions, self.vis_info)
        self.assertEqual(priority, 1)

    def test_determine_priority_poor_seeing(self):
        """Test priority determination with poor seeing"""
        poor_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 30.0}
        )

        # Planet should get priority 1 with poor seeing
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )
        priority = self.planner._determine_priority(planet, poor_conditions, self.vis_info)
        self.assertEqual(priority, 1)

    def test_determine_priority_bright_star(self):
        """Test priority determination for bright stars"""
        bright_star = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )
        priority = self.planner._determine_priority(bright_star, self.conditions, self.vis_info)
        self.assertLessEqual(priority, 3)  # Should be priority 2 or 3

    def test_determine_priority_messier(self):
        """Test priority determination for Messier objects"""
        # M42 is bright and in dark skies, so it gets priority 2, not 4
        messier_obj = CelestialObject(
            name="M42",
            common_name="Orion Nebula",
            ra_hours=5.588,
            dec_degrees=-5.389,
            magnitude=4.0,
            object_type=CelestialObjectType.NEBULA,
            catalog="messier",
        )
        priority = self.planner._determine_priority(messier_obj, self.conditions, self.vis_info)
        # M42 is bright (mag 4.0) in dark skies (Bortle 3), so gets priority 2
        self.assertEqual(priority, 2)

    def test_determine_priority_messier_faint(self):
        """Test priority determination for faint Messier objects"""
        # Use a faint Messier object that doesn't match earlier conditions
        messier_obj = CelestialObject(
            name="M101",
            common_name="Pinwheel Galaxy",
            ra_hours=14.0,
            dec_degrees=54.0,
            magnitude=7.9,  # Faint, but still < 8
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )
        # Use poor light pollution so it doesn't match "bright objects in dark skies"
        poor_lp_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "light_pollution": LightPollutionData(
                bortle_class=BortleClass.CLASS_7,
                sqm_value=18.0,
                naked_eye_limiting_magnitude=4.0,
                milky_way_visible=False,
                airglow_visible=False,
                zodiacal_light_visible=False,
                description="Poor",
                recommendations=("Poor conditions",),
            )}
        )
        priority = self.planner._determine_priority(messier_obj, poor_lp_conditions, self.vis_info)
        # Should get priority 4 for Messier objects that don't match earlier conditions
        self.assertEqual(priority, 4)

    def test_generate_viewing_tips_planet(self):
        """Test viewing tips generation for planets"""
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        tips = self.planner._generate_viewing_tips(planet, self.conditions)
        self.assertIsInstance(tips, tuple)
        self.assertGreater(len(tips), 0)

    def test_generate_viewing_tips_galaxy(self):
        """Test viewing tips generation for galaxies"""
        tips = self.planner._generate_viewing_tips(self.obj, self.conditions)
        self.assertIsInstance(tips, tuple)

    def test_generate_viewing_tips_poor_seeing(self):
        """Test viewing tips with poor seeing"""
        poor_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 30.0}
        )

        tips = self.planner._generate_viewing_tips(self.obj, poor_conditions)
        self.assertIsInstance(tips, tuple)
        # Should have tips about poor seeing
        self.assertGreater(len(tips), 0)

    def test_calculate_best_viewing_time(self):
        """Test calculation of best viewing time (transit)"""
        best_time = self.planner._calculate_best_viewing_time(
            self.obj, 40.0, -100.0, datetime.now(UTC)
        )
        self.assertIsInstance(best_time, datetime)

    def test_calculate_moon_separation_fast(self):
        """Test fast moon separation calculation"""
        separation = self.planner._calculate_moon_separation_fast(
            self.obj, moon_ra=12.0, moon_dec=45.0
        )
        self.assertIsNotNone(separation)
        self.assertGreaterEqual(separation, 0.0)
        self.assertLessEqual(separation, 180.0)

    def test_calculate_moon_separation_fast_none(self):
        """Test fast moon separation with None moon position"""
        separation = self.planner._calculate_moon_separation_fast(self.obj, moon_ra=None, moon_dec=None)
        self.assertIsNone(separation)

    def test_calculate_moon_separation(self):
        """Test moon separation calculation"""
        with patch("celestron_nexstar.api.observation.observation_planner.get_moon_info") as mock_moon:
            mock_moon_info = MagicMock()
            mock_moon_info.ra_hours = 12.0
            mock_moon_info.dec_degrees = 45.0
            mock_moon.return_value = mock_moon_info

            separation = self.planner._calculate_moon_separation(self.obj, self.conditions)
            self.assertIsNotNone(separation)
            self.assertGreaterEqual(separation, 0.0)
            self.assertLessEqual(separation, 180.0)

    def test_calculate_moon_separation_no_moon_info(self):
        """Test moon separation when moon info is unavailable"""
        with patch("celestron_nexstar.api.observation.observation_planner.get_moon_info", return_value=None):
            separation = self.planner._calculate_moon_separation(self.obj, self.conditions)
            self.assertIsNone(separation)


class TestObservationPlannerGetRecommendedObjects(unittest.TestCase):
    """Test suite for get_recommended_objects method"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

        self.weather = WeatherData(temperature_c=20.0, cloud_cover_percent=10.0)
        self.lp_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_3,
            sqm_value=21.5,
            naked_eye_limiting_magnitude=6.5,
            milky_way_visible=True,
            airglow_visible=True,
            zodiacal_light_visible=True,
            description="Good",
            recommendations=("Good for observing",),
        )

        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=self.weather,
            is_weather_suitable=True,
            light_pollution=self.lp_data,
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

    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    def test_get_recommended_objects_excellent_seeing(
        self, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test getting recommended objects with excellent seeing"""
        from celestron_nexstar.api.observation.optics import OpticalConfiguration

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import TelescopeModel, TelescopeSpecs, EyepieceSpecs
        mock_telescope = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150.0,
            focal_length_mm=1500.0,
            focal_ratio=10.0,
        )
        mock_eyepiece = EyepieceSpecs(
            focal_length_mm=25.0,
            apparent_fov_deg=50.0,
        )
        mock_config = OpticalConfiguration(
            telescope=mock_telescope,
            eyepiece=mock_eyepiece,
        )
        mock_get_config.return_value = mock_config

        mock_filter_visible.return_value = []

        result = self.planner.get_recommended_objects(self.conditions, max_results=10)
        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    def test_get_recommended_objects_poor_seeing(
        self, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test getting recommended objects with poor seeing"""
        from celestron_nexstar.api.observation.optics import OpticalConfiguration

        poor_conditions = ObservingConditions(
            **{**self.conditions.__dict__, "seeing_score": 30.0}
        )

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import TelescopeModel, TelescopeSpecs, EyepieceSpecs
        mock_telescope = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150.0,
            focal_length_mm=1500.0,
            focal_ratio=10.0,
        )
        mock_eyepiece = EyepieceSpecs(
            focal_length_mm=25.0,
            apparent_fov_deg=50.0,
        )
        mock_config = OpticalConfiguration(
            telescope=mock_telescope,
            eyepiece=mock_eyepiece,
        )
        mock_get_config.return_value = mock_config

        mock_filter_visible.return_value = []

        result = self.planner.get_recommended_objects(poor_conditions, max_results=10)
        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    def test_get_recommended_objects_best_for_seeing(
        self, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test getting recommended objects filtered for best seeing"""
        from celestron_nexstar.api.observation.optics import OpticalConfiguration

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import TelescopeModel, TelescopeSpecs, EyepieceSpecs
        mock_telescope = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150.0,
            focal_length_mm=1500.0,
            focal_ratio=10.0,
        )
        mock_eyepiece = EyepieceSpecs(
            focal_length_mm=25.0,
            apparent_fov_deg=50.0,
        )
        mock_config = OpticalConfiguration(
            telescope=mock_telescope,
            eyepiece=mock_eyepiece,
        )
        mock_get_config.return_value = mock_config

        mock_filter_visible.return_value = []

        result = self.planner.get_recommended_objects(
            self.conditions, max_results=10, best_for_seeing=True
        )
        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    def test_get_recommended_objects_with_target_types(
        self, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test getting recommended objects with target type filtering"""
        from celestron_nexstar.api.observation.optics import OpticalConfiguration
        from celestron_nexstar.api.observation.observation_planner import ObservingTarget

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import TelescopeModel, TelescopeSpecs, EyepieceSpecs
        mock_telescope = TelescopeSpecs(
            model=TelescopeModel.NEXSTAR_6SE,
            aperture_mm=150.0,
            focal_length_mm=1500.0,
            focal_ratio=10.0,
        )
        mock_eyepiece = EyepieceSpecs(
            focal_length_mm=25.0,
            apparent_fov_deg=50.0,
        )
        mock_config = OpticalConfiguration(
            telescope=mock_telescope,
            eyepiece=mock_eyepiece,
        )
        mock_get_config.return_value = mock_config

        mock_filter_visible.return_value = []

        result = self.planner.get_recommended_objects(
            self.conditions, target_types=[ObservingTarget.PLANETS], max_results=10
        )
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
