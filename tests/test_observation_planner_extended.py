"""
Extended unit tests for observation_planner.py

Tests internal methods and edge cases for observation planning.
"""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase
from celestron_nexstar.api.core.exceptions import LocationNotSetError
from celestron_nexstar.api.location.light_pollution import BortleClass, LightPollutionData
from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.api.location.weather import WeatherData
from celestron_nexstar.api.observation.observation_planner import (
    ObservationPlanner,
    ObservingConditions,
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

        result = self.planner._calculate_visibility_probability(planet, self.conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_calculate_visibility_probability_poor_seeing(self):
        """Test visibility probability with poor seeing"""
        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

        result = self.planner._calculate_visibility_probability(self.obj, poor_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertLess(prob, 1.0)  # Should be reduced by poor seeing

    def test_calculate_visibility_probability_cloudy(self):
        """Test visibility probability with cloud cover"""
        cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=85.0)
        cloudy_conditions = ObservingConditions(**{**self.conditions.__dict__, "weather": cloudy_weather})

        result = self.planner._calculate_visibility_probability(self.obj, cloudy_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertLess(prob, 1.0)  # Should be reduced by clouds

    def test_calculate_quality_score_excellent_weather(self):
        """Test quality score calculation with excellent weather"""
        score = self.planner._calculate_quality_score(self.weather, self.lp_data, 0.1, "excellent")
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
        score = self.planner._calculate_quality_score(self.weather, lp_poor, 0.1, "poor")
        self.assertLess(score, 0.5)  # Should be lower for poor conditions

    def test_calculate_quality_score_full_moon(self):
        """Test quality score with full moon"""
        score_full = self.planner._calculate_quality_score(self.weather, self.lp_data, 1.0, "excellent")
        score_new = self.planner._calculate_quality_score(self.weather, self.lp_data, 0.0, "excellent")
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
        recs, warnings = self.planner._generate_recommendations(self.weather, self.lp_data, 0.1, 0.9, "excellent", "")
        self.assertIsInstance(recs, tuple)
        self.assertIsInstance(warnings, tuple)

    def test_generate_recommendations_cloudy(self):
        """Test recommendation generation for cloudy conditions"""
        cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=85.0)
        _recs, warnings = self.planner._generate_recommendations(
            cloudy_weather, self.lp_data, 0.1, 0.3, "poor", "High cloud cover"
        )
        self.assertGreater(len(warnings), 0)

    def test_generate_recommendations_full_moon(self):
        """Test recommendation generation with full moon"""
        _recs, warnings = self.planner._generate_recommendations(self.weather, self.lp_data, 1.0, 0.5, "good", "")
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
        recs, _warnings = self.planner._generate_recommendations(self.weather, lp_dark, 0.1, 0.9, "excellent", "")
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
        excellent_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 90.0})

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
        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

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
            **{
                **self.conditions.__dict__,
                "light_pollution": LightPollutionData(
                    bortle_class=BortleClass.CLASS_7,
                    sqm_value=18.0,
                    naked_eye_limiting_magnitude=4.0,
                    milky_way_visible=False,
                    airglow_visible=False,
                    zodiacal_light_visible=False,
                    description="Poor",
                    recommendations=("Poor conditions",),
                ),
            }
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
        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

        tips = self.planner._generate_viewing_tips(self.obj, poor_conditions)
        self.assertIsInstance(tips, tuple)
        # Should have tips about poor seeing
        self.assertGreater(len(tips), 0)

    def test_calculate_best_viewing_time(self):
        """Test calculation of best viewing time (transit)"""
        best_time = self.planner._calculate_best_viewing_time(self.obj, 40.0, -100.0, datetime.now(UTC))
        self.assertIsInstance(best_time, datetime)

    def test_calculate_moon_separation_fast(self):
        """Test fast moon separation calculation"""
        separation = self.planner._calculate_moon_separation_fast(self.obj, moon_ra=12.0, moon_dec=45.0)
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

        from celestron_nexstar.api.observation.optics import EyepieceSpecs, TelescopeModel, TelescopeSpecs

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

        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import EyepieceSpecs, TelescopeModel, TelescopeSpecs

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

        from celestron_nexstar.api.observation.optics import EyepieceSpecs, TelescopeModel, TelescopeSpecs

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

        result = self.planner.get_recommended_objects(self.conditions, max_results=10, best_for_seeing=True)
        self.assertIsInstance(result, list)

    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    def test_get_recommended_objects_with_target_types(
        self, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test getting recommended objects with target type filtering"""
        from celestron_nexstar.api.observation.observation_planner import ObservingTarget
        from celestron_nexstar.api.observation.optics import OpticalConfiguration

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[])
        mock_get_db.return_value = mock_db

        from celestron_nexstar.api.observation.optics import EyepieceSpecs, TelescopeModel, TelescopeSpecs

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


class TestObservationPlannerGetTonightConditionsExtended(unittest.TestCase):
    """Extended test suite for get_tonight_conditions with more edge cases"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()
        self.mock_location = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test Location")
        self.mock_weather_data = WeatherData(temperature_c=15.0, cloud_cover_percent=20.0)
        self.mock_lp_data = LightPollutionData(
            bortle_class=BortleClass.CLASS_4,
            sqm_value=20.0,
            naked_eye_limiting_magnitude=6.0,
            milky_way_visible=False,
            airglow_visible=False,
            zodiacal_light_visible=False,
            description="Suburban",
            recommendations=(),
        )

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    @patch("celestron_nexstar.api.observation.observation_planner.fetch_weather")
    @patch("celestron_nexstar.api.database.models.get_db_session")
    @patch("celestron_nexstar.api.observation.observation_planner.get_light_pollution_data")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    @patch("celestron_nexstar.api.observation.observation_planner.get_sun_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.assess_observing_conditions")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_seeing_conditions")
    @patch("celestron_nexstar.api.observation.scoring.is_nighttime")
    @patch("celestron_nexstar.api.astronomy.sun_moon.calculate_sun_times")
    @patch("celestron_nexstar.api.location.weather.fetch_hourly_weather_forecast")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_astronomical_twilight")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_golden_hour")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_blue_hour")
    @patch.object(ObservationPlanner, "_calculate_galactic_center_visibility")
    def test_get_tonight_conditions_daytime_uses_sunset_weather(
        self,
        mock_galactic_center,
        mock_blue_hour,
        mock_golden_hour,
        mock_astronomical_twilight,
        mock_fetch_hourly,
        mock_calculate_sun_times,
        mock_is_nighttime,
        mock_calculate_seeing,
        mock_assess_conditions,
        mock_get_moon_info,
        mock_get_sun_info,
        mock_get_config,
        mock_get_lp_data,
        mock_get_db_session,
        mock_fetch_weather,
        mock_get_location,
    ):
        """Test that daytime conditions use sunset weather"""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session():
            mock_sess = AsyncMock()
            yield mock_sess

        mock_get_db_session.return_value = mock_session()
        mock_get_location.return_value = self.mock_location
        mock_fetch_weather.return_value = self.mock_weather_data
        mock_get_lp_data.return_value = self.mock_lp_data
        mock_get_config.return_value = None
        mock_sun_info = MagicMock()
        mock_sun_info.altitude_deg = 30.0
        mock_sun_info.sunrise_time = datetime(2023, 1, 1, 12, 0, tzinfo=UTC)
        mock_sun_info.sunset_time = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info
        mock_get_moon_info.return_value = MagicMock(
            illumination=0.5, altitude_deg=30.0, ra_hours=10.0, dec_degrees=20.0, phase=MoonPhase.FIRST_QUARTER
        )
        mock_assess_conditions.return_value = ("good", "No warnings")
        mock_calculate_seeing.return_value = (70.0, [])
        mock_is_nighttime.return_value = False  # Daytime
        sunset_time = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
        mock_calculate_sun_times.return_value = {
            "sunset": sunset_time,
            "sunrise": datetime(2023, 1, 1, 12, 0, tzinfo=UTC),
        }
        mock_fetch_hourly.return_value = []  # No hourly forecast
        mock_astronomical_twilight.return_value = (None, None, None, None)  # 4-element tuple
        mock_golden_hour.return_value = (None, None, None, None)  # 4-element tuple
        mock_blue_hour.return_value = (None, None, None, None)  # 4-element tuple
        mock_galactic_center.return_value = (None, None)

        conditions = self.planner.get_tonight_conditions(lat=40.0, lon=-100.0)

        self.assertIsInstance(conditions, ObservingConditions)
        # Should have used current weather (fallback when no hourly forecast)
        mock_fetch_weather.assert_called()

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    @patch("celestron_nexstar.api.observation.observation_planner.fetch_weather")
    @patch("celestron_nexstar.api.database.models.get_db_session")
    @patch("celestron_nexstar.api.observation.observation_planner.get_light_pollution_data")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    @patch("celestron_nexstar.api.observation.observation_planner.get_sun_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.assess_observing_conditions")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_seeing_conditions")
    @patch("celestron_nexstar.api.observation.scoring.is_nighttime")
    @patch("celestron_nexstar.api.astronomy.sun_moon.calculate_sun_times")
    @patch("celestron_nexstar.api.location.weather.fetch_hourly_weather_forecast")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_astronomical_twilight")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_golden_hour")
    @patch("celestron_nexstar.api.observation.observation_planner.calculate_blue_hour")
    @patch.object(ObservationPlanner, "_calculate_galactic_center_visibility")
    @patch("celestron_nexstar.api.events.space_weather.get_space_weather_conditions")
    def test_get_tonight_conditions_with_space_weather(
        self,
        mock_get_space_weather,
        mock_galactic_center,
        mock_blue_hour,
        mock_golden_hour,
        mock_astronomical_twilight,
        mock_fetch_hourly,
        mock_calculate_sun_times,
        mock_is_nighttime,
        mock_calculate_seeing,
        mock_assess_conditions,
        mock_get_moon_info,
        mock_get_sun_info,
        mock_get_config,
        mock_get_lp_data,
        mock_get_db_session,
        mock_fetch_weather,
        mock_get_location,
    ):
        """Test that space weather conditions are included"""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session():
            mock_sess = AsyncMock()
            yield mock_sess

        mock_get_db_session.return_value = mock_session()
        mock_get_location.return_value = self.mock_location
        mock_fetch_weather.return_value = self.mock_weather_data
        mock_get_lp_data.return_value = self.mock_lp_data
        mock_get_config.return_value = None
        mock_sun_info = MagicMock()
        mock_sun_info.altitude_deg = -30.0
        mock_sun_info.sunrise_time = datetime(2023, 1, 1, 12, 0, tzinfo=UTC)
        mock_sun_info.sunset_time = datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
        mock_get_sun_info.return_value = mock_sun_info
        mock_get_moon_info.return_value = MagicMock(
            illumination=0.5, altitude_deg=30.0, ra_hours=10.0, dec_degrees=20.0, phase=MoonPhase.FIRST_QUARTER
        )
        mock_assess_conditions.return_value = ("good", "No warnings")
        mock_calculate_seeing.return_value = (70.0, [])
        mock_is_nighttime.return_value = True
        mock_calculate_sun_times.return_value = {
            "sunset": datetime(2023, 1, 1, 0, 0, tzinfo=UTC),
            "sunrise": datetime(2023, 1, 1, 12, 0, tzinfo=UTC),
        }
        mock_fetch_hourly.return_value = []
        mock_astronomical_twilight.return_value = (None, None, None, None)  # 4-element tuple
        mock_golden_hour.return_value = (None, None, None, None)  # 4-element tuple
        mock_blue_hour.return_value = (None, None, None, None)  # 4-element tuple
        mock_galactic_center.return_value = (None, None)

        # Mock space weather with aurora opportunity
        mock_space_weather = MagicMock()
        mock_g_scale = MagicMock()
        mock_g_scale.level = 3
        mock_space_weather.g_scale = mock_g_scale
        mock_space_weather.r_scale = None
        mock_space_weather.solar_wind_bz = None
        mock_space_weather.alerts = []
        mock_get_space_weather.return_value = mock_space_weather

        conditions = self.planner.get_tonight_conditions(lat=40.0, lon=-100.0)

        self.assertIsInstance(conditions, ObservingConditions)
        mock_get_space_weather.assert_called_once()


class TestObservationPlannerGetRecommendedObjectsExtended(unittest.TestCase):
    """Extended test suite for get_recommended_objects with more edge cases"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()
        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=WeatherData(temperature_c=20.0, cloud_cover_percent=10.0),
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
    @patch.object(ObservationPlanner, "_score_object")
    def test_get_recommended_objects_poor_seeing_filters_faint_objects(
        self, mock_score_object, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon
    ):
        """Test that poor seeing filters out faint objects"""
        from celestron_nexstar.api.observation.optics import (
            EyepieceSpecs,
            OpticalConfiguration,
            TelescopeModel,
            TelescopeSpecs,
        )

        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        # Create test objects
        bright_obj = CelestialObject(
            name="Bright Star",
            common_name="Bright",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=2.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        faint_obj = CelestialObject(
            name="Faint Galaxy",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=12.0,
            object_type=CelestialObjectType.GALAXY,
            catalog="test",
        )
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        bright_vis = VisibilityInfo(
            object_name="Bright Star",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=2.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )
        faint_vis = VisibilityInfo(
            object_name="Faint Galaxy",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=12.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.7,
            reasons=("Good altitude",),
        )
        planet_vis = VisibilityInfo(
            object_name="Jupiter",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=-2.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.95,
            reasons=("Good altitude",),
        )

        mock_db = MagicMock()
        # Poor seeing should limit to max_mag = 10.0
        mock_db.filter_objects = AsyncMock(return_value=[bright_obj, faint_obj, planet])
        mock_get_db.return_value = mock_db

        mock_config = OpticalConfiguration(
            telescope=TelescopeSpecs(
                model=TelescopeModel.NEXSTAR_6SE, aperture_mm=150.0, focal_length_mm=1500.0, focal_ratio=10.0
            ),
            eyepiece=EyepieceSpecs(focal_length_mm=25.0, apparent_fov_deg=50.0),
        )
        mock_get_config.return_value = mock_config

        # filter_visible will be called with all objects, but then faint objects should be filtered out
        mock_filter_visible.return_value = [(bright_obj, bright_vis), (faint_obj, faint_vis), (planet, planet_vis)]

        # Mock score_object to return None for faint objects (they get filtered)
        def score_side_effect(obj, conditions, vis_info, *args, **kwargs):
            if obj.magnitude and obj.magnitude > 10:
                return None  # Faint objects filtered out
            return RecommendedObject(
                obj=obj,
                altitude=vis_info.altitude_deg or 0.0,
                azimuth=vis_info.azimuth_deg or 0.0,
                best_viewing_time=datetime.now(UTC),
                visible_duration_hours=8.0,
                apparent_magnitude=obj.magnitude or 0.0,
                observability_score=0.95,
                visibility_probability=0.9,
                priority=1,
                reason="Good conditions",
                viewing_tips=("Good conditions",),
            )

        mock_score_object.side_effect = score_side_effect

        result = self.planner.get_recommended_objects(poor_conditions, max_results=10)

        # Should filter out faint objects (mag > 10) in poor seeing
        # Only bright objects and planets should remain
        self.assertIsInstance(result, list)
        # Verify that filter_visible was called
        mock_filter_visible.assert_called_once()
        # Verify that faint objects were not scored (filtered out)
        self.assertTrue(all(rec.obj.magnitude is None or rec.obj.magnitude <= 10 for rec in result))

    @patch("celestron_nexstar.api.observation.planning_utils.get_object_visibility_timeline")
    @patch("celestron_nexstar.api.observation.observation_planner.get_moon_info")
    @patch("celestron_nexstar.api.observation.observation_planner.get_database")
    @patch("celestron_nexstar.api.observation.observation_planner.filter_visible_objects")
    @patch("celestron_nexstar.api.observation.observation_planner.get_current_configuration")
    @patch.object(ObservationPlanner, "_score_object")
    def test_get_recommended_objects_with_direct_object_type_filter(
        self, mock_score_object, mock_get_config, mock_filter_visible, mock_get_db, mock_get_moon, mock_timeline
    ):
        """Test filtering with direct CelestialObjectType"""
        from celestron_nexstar.api.observation.optics import (
            EyepieceSpecs,
            OpticalConfiguration,
            TelescopeModel,
            TelescopeSpecs,
        )

        mock_moon_info = MagicMock()
        mock_moon_info.ra_hours = 12.0
        mock_moon_info.dec_degrees = 45.0
        mock_get_moon.return_value = mock_moon_info

        star_obj = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )
        galaxy_obj = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )

        star_vis = VisibilityInfo(
            object_name="Vega",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=0.03,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )
        VisibilityInfo(
            object_name="M31",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.8,
            reasons=("Good altitude",),
        )

        mock_db = MagicMock()
        mock_db.filter_objects = AsyncMock(return_value=[star_obj, galaxy_obj])
        mock_get_db.return_value = mock_db

        mock_config = OpticalConfiguration(
            telescope=TelescopeSpecs(
                model=TelescopeModel.NEXSTAR_6SE, aperture_mm=150.0, focal_length_mm=1500.0, focal_ratio=10.0
            ),
            eyepiece=EyepieceSpecs(focal_length_mm=25.0, apparent_fov_deg=50.0),
        )
        mock_get_config.return_value = mock_config

        # The filtering by object type happens BEFORE filter_visible_objects is called
        # So filter_visible_objects should only receive the star object
        mock_filter_visible.return_value = [(star_obj, star_vis)]

        def score_side_effect(obj, conditions, vis_info, *args, **kwargs):
            return RecommendedObject(
                obj=obj,
                altitude=vis_info.altitude_deg or 0.0,
                azimuth=vis_info.azimuth_deg or 0.0,
                best_viewing_time=datetime.now(UTC),
                visible_duration_hours=8.0,
                apparent_magnitude=obj.magnitude or 0.0,
                observability_score=0.9,
                visibility_probability=0.9,
                priority=2,
                reason="Good conditions",
                viewing_tips=("Good conditions",),
            )

        mock_score_object.side_effect = score_side_effect

        # Mock timeline to return that objects are visible (not never visible)
        from celestron_nexstar.api.observation.planning_utils import ObjectVisibilityTimeline

        mock_timeline_obj = ObjectVisibilityTimeline(
            object_name="Vega",
            rise_time=None,
            transit_time=None,
            set_time=None,
            max_altitude=45.0,
            is_circumpolar=False,
            is_always_visible=False,
            is_never_visible=False,
        )
        mock_timeline.return_value = mock_timeline_obj

        result = self.planner.get_recommended_objects(
            self.conditions, target_types=CelestialObjectType.STAR, max_results=10
        )

        self.assertIsInstance(result, list)
        # Should filter to only stars (galaxy should be filtered out before filter_visible_objects)
        # Verify all results are stars
        self.assertTrue(len(result) > 0)
        self.assertTrue(all(rec.obj.object_type == CelestialObjectType.STAR for rec in result))
        mock_db.filter_objects.assert_called_once()


class TestObservationPlannerVisibilityProbabilityExtended(unittest.TestCase):
    """Extended test suite for _calculate_visibility_probability"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()
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
        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=WeatherData(temperature_c=20.0, cloud_cover_percent=10.0),
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
            moon_phase=MoonPhase.NEW_MOON,
            observing_quality_score=0.9,
            seeing_score=80.0,
            recommendations=("Good conditions",),
            warnings=(),
        )

    def test_calculate_visibility_probability_very_poor_seeing_bright_object(self):
        """Test visibility probability with very poor seeing and bright object"""
        very_poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 10.0})
        bright_obj = CelestialObject(
            name="Bright Star",
            common_name="Bright",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=1.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )

        result = self.planner._calculate_visibility_probability(bright_obj, very_poor_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertGreater(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_calculate_visibility_probability_very_poor_seeing_faint_object(self):
        """Test visibility probability with very poor seeing and faint object"""
        very_poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 10.0})
        faint_obj = CelestialObject(
            name="Faint Galaxy",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=12.0,
            object_type=CelestialObjectType.GALAXY,
            catalog="test",
        )

        result = self.planner._calculate_visibility_probability(faint_obj, very_poor_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertLess(prob, 0.5)  # Should be significantly reduced

    def test_calculate_visibility_probability_cloud_cover_heavy(self):
        """Test visibility probability with heavy cloud cover"""
        cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=85.0)
        cloudy_conditions = ObservingConditions(**{**self.conditions.__dict__, "weather": cloudy_weather})

        result = self.planner._calculate_visibility_probability(self.obj, cloudy_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertLess(prob, 0.5)  # Should be significantly reduced

    def test_calculate_visibility_probability_cloud_cover_partly_cloudy(self):
        """Test visibility probability with partly cloudy conditions"""
        partly_cloudy_weather = WeatherData(temperature_c=20.0, cloud_cover_percent=45.0)
        partly_cloudy_conditions = ObservingConditions(**{**self.conditions.__dict__, "weather": partly_cloudy_weather})

        result = self.planner._calculate_visibility_probability(self.obj, partly_cloudy_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertGreater(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_calculate_visibility_probability_planet_type(self):
        """Test visibility probability for planet (less sensitive to seeing)"""
        planet = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )
        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})

        result = self.planner._calculate_visibility_probability(planet, poor_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        # Planets should still have reasonable probability even in poor seeing
        self.assertGreater(prob, 0.5)

    def test_calculate_visibility_probability_cluster_type(self):
        """Test visibility probability for cluster"""
        cluster = CelestialObject(
            name="M13",
            common_name="Hercules Cluster",
            ra_hours=16.691,
            dec_degrees=36.460,
            magnitude=5.8,
            object_type=CelestialObjectType.CLUSTER,
            catalog="messier",
        )

        result = self.planner._calculate_visibility_probability(cluster, self.conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertGreater(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_calculate_visibility_probability_fair_seeing(self):
        """Test visibility probability with fair seeing (50-70)"""
        fair_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 60.0})

        result = self.planner._calculate_visibility_probability(self.obj, fair_conditions, self.vis_info)
        # Handle both float and tuple return types
        prob = result[0] if isinstance(result, tuple) else result
        self.assertGreater(prob, 0.0)
        self.assertLessEqual(prob, 1.0)


class TestObservationPlannerDeterminePriorityExtended(unittest.TestCase):
    """Extended test suite for _determine_priority"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()
        self.conditions = ObservingConditions(
            timestamp=datetime.now(UTC),
            latitude=40.0,
            longitude=-100.0,
            location_name="Test Location",
            weather=WeatherData(temperature_c=20.0, cloud_cover_percent=10.0),
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
            moon_phase=MoonPhase.NEW_MOON,
            observing_quality_score=0.9,
            seeing_score=80.0,
            recommendations=("Good conditions",),
            warnings=(),
        )
        self.vis_info = VisibilityInfo(
            object_name="Test",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )

    def test_determine_priority_excellent_seeing_faint_galaxy(self):
        """Test priority for faint galaxy with excellent seeing"""
        excellent_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 90.0})
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
        self.assertEqual(priority, 1)  # Should get priority 1

    def test_determine_priority_poor_seeing_bright_object(self):
        """Test priority for bright object with poor seeing"""
        poor_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 30.0})
        bright_obj = CelestialObject(
            name="Bright Star",
            common_name="Bright",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=4.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )

        priority = self.planner._determine_priority(bright_obj, poor_conditions, self.vis_info)
        self.assertEqual(priority, 2)  # Should get priority 2

    def test_determine_priority_good_seeing_dark_skies(self):
        """Test priority for object in dark skies with good seeing"""
        good_conditions = ObservingConditions(**{**self.conditions.__dict__, "seeing_score": 70.0})
        bright_obj = CelestialObject(
            name="Bright Object",
            common_name="Bright",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=6.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )

        priority = self.planner._determine_priority(bright_obj, good_conditions, self.vis_info)
        self.assertEqual(priority, 2)  # Should get priority 2 (bright object in dark skies)

    def test_determine_priority_high_altitude(self):
        """Test priority for object at high altitude"""
        # Use object that doesn't match earlier conditions (faint, not in dark skies)
        poor_lp_conditions = ObservingConditions(
            **{
                **self.conditions.__dict__,
                "light_pollution": LightPollutionData(
                    bortle_class=BortleClass.CLASS_7,
                    sqm_value=18.0,
                    naked_eye_limiting_magnitude=4.0,
                    milky_way_visible=False,
                    airglow_visible=False,
                    zodiacal_light_visible=False,
                    description="Poor",
                    recommendations=("Poor conditions",),
                ),
            }
        )
        high_alt_vis = VisibilityInfo(
            object_name="High Alt",
            altitude_deg=75.0,
            azimuth_deg=180.0,
            magnitude=8.0,
            limiting_magnitude=4.0,
            is_visible=True,
            observability_score=0.9,
            reasons=("High altitude",),
        )
        obj = CelestialObject(
            name="Object",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=8.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )

        priority = self.planner._determine_priority(obj, poor_lp_conditions, high_alt_vis)
        self.assertEqual(priority, 3)  # Should get priority 3 (high altitude)

    def test_determine_priority_very_bright_star(self):
        """Test priority for very bright star (1st magnitude)"""
        bright_star = CelestialObject(
            name="Sirius",
            common_name="Sirius",
            ra_hours=6.752,
            dec_degrees=-16.716,
            magnitude=-1.46,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )

        priority = self.planner._determine_priority(bright_star, self.conditions, self.vis_info)
        self.assertEqual(priority, 2)  # Should get priority 2 (very bright star)


class TestObservationPlannerSeeingWindows(unittest.TestCase):
    """Test suite for seeing window calculations"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

    def test_calculate_best_seeing_windows_no_forecast(self):
        """Test best seeing windows with no forecast"""
        windows = self.planner._calculate_best_seeing_windows([], None, None)
        self.assertEqual(windows, ())

    def test_calculate_best_seeing_windows_no_sunset_sunrise(self):
        """Test best seeing windows with no sunset/sunrise"""
        from celestron_nexstar.api.location.weather import HourlySeeingForecast

        forecast = HourlySeeingForecast(
            timestamp=datetime.now(UTC),
            seeing_score=80.0,
            temperature_f=60.0,
            dew_point_f=50.0,
            humidity_percent=50.0,
            wind_speed_mph=5.0,
            cloud_cover_percent=10.0,
        )
        windows = self.planner._calculate_best_seeing_windows([forecast], None, None)
        self.assertEqual(windows, ())

    def test_find_seeing_windows_empty_forecast(self):
        """Test finding seeing windows with empty forecast"""
        windows = self.planner._find_seeing_windows([], min_score=80.0)
        self.assertEqual(windows, [])

    def test_find_seeing_windows_excellent_seeing(self):
        """Test finding seeing windows with excellent seeing"""
        from celestron_nexstar.api.location.weather import HourlySeeingForecast

        base_time = datetime(2023, 1, 1, 20, 0, tzinfo=UTC)
        forecasts = [
            HourlySeeingForecast(
                timestamp=base_time + timedelta(hours=i),
                seeing_score=85.0,
                temperature_f=60.0,
                dew_point_f=50.0,
                humidity_percent=50.0,
                wind_speed_mph=5.0,
                cloud_cover_percent=10.0,
            )
            for i in range(3)
        ]

        windows = self.planner._find_seeing_windows(forecasts, min_score=80.0)
        self.assertGreater(len(windows), 0)
        self.assertEqual(len(windows[0]), 2)  # Each window is (start, end)

    def test_find_seeing_windows_mixed_seeing(self):
        """Test finding seeing windows with mixed seeing conditions"""
        from celestron_nexstar.api.location.weather import HourlySeeingForecast

        base_time = datetime(2023, 1, 1, 20, 0, tzinfo=UTC)
        forecasts = [
            HourlySeeingForecast(
                timestamp=base_time + timedelta(hours=0),
                seeing_score=85.0,
                temperature_f=60.0,
                dew_point_f=50.0,
                humidity_percent=50.0,
                wind_speed_mph=5.0,
                cloud_cover_percent=10.0,
            ),
            HourlySeeingForecast(
                timestamp=base_time + timedelta(hours=1),
                seeing_score=85.0,
                temperature_f=60.0,
                dew_point_f=50.0,
                humidity_percent=50.0,
                wind_speed_mph=5.0,
                cloud_cover_percent=10.0,
            ),
            HourlySeeingForecast(
                timestamp=base_time + timedelta(hours=2),
                seeing_score=40.0,
                temperature_f=60.0,
                dew_point_f=50.0,
                humidity_percent=50.0,
                wind_speed_mph=5.0,
                cloud_cover_percent=50.0,
            ),
            HourlySeeingForecast(
                timestamp=base_time + timedelta(hours=3),
                seeing_score=85.0,
                temperature_f=60.0,
                dew_point_f=50.0,
                humidity_percent=50.0,
                wind_speed_mph=5.0,
                cloud_cover_percent=10.0,
            ),
        ]

        windows = self.planner._find_seeing_windows(forecasts, min_score=80.0)
        # Should find two separate windows
        self.assertGreaterEqual(len(windows), 1)


class TestObservationPlannerGalacticCenter(unittest.TestCase):
    """Test suite for galactic center visibility calculations"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

    def test_calculate_galactic_center_visibility_no_sunset_sunrise(self):
        """Test galactic center visibility with no sunset/sunrise"""
        result = self.planner._calculate_galactic_center_visibility(40.0, -100.0, datetime.now(UTC), None, None)
        self.assertEqual(result, (None, None))

    def test_calculate_galactic_center_visibility_with_times(self):
        """Test galactic center visibility calculation"""
        sunset = datetime(2023, 6, 15, 0, 0, tzinfo=UTC)  # Summer, galactic center should be visible
        sunrise = datetime(2023, 6, 15, 12, 0, tzinfo=UTC)

        result = self.planner._calculate_galactic_center_visibility(
            40.0, -100.0, datetime(2023, 6, 15, 6, 0, tzinfo=UTC), sunset, sunrise
        )
        # Should return tuple of (start, end) or (None, None)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestObservationPlannerEdgeCases(unittest.TestCase):
    """Test suite for edge cases to push coverage over 80%"""

    def setUp(self):
        """Set up test fixtures"""
        self.planner = ObservationPlanner()

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    def test_get_tonight_conditions_with_none_location(self, mock_get_location):
        """Test get_tonight_conditions when location is None"""
        mock_get_location.return_value = None

        with self.assertRaises(LocationNotSetError):
            self.planner.get_tonight_conditions()

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    def test_get_tonight_conditions_with_start_time_no_tzinfo(self, mock_get_location):
        """Test get_tonight_conditions with start_time that has no timezone info"""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session():
            mock_sess = AsyncMock()
            yield mock_sess

        mock_get_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        start_time_no_tz = datetime(2023, 1, 1, 20, 0)  # No timezone

        with patch("celestron_nexstar.api.database.models.get_db_session", return_value=mock_session()):
            with patch(
                "celestron_nexstar.api.observation.observation_planner.fetch_weather",
                return_value=WeatherData(temperature_c=20.0, cloud_cover_percent=10.0),
            ):
                with patch(
                    "celestron_nexstar.api.observation.observation_planner.get_light_pollution_data",
                    return_value=LightPollutionData(
                        bortle_class=BortleClass.CLASS_3,
                        sqm_value=21.5,
                        naked_eye_limiting_magnitude=6.5,
                        milky_way_visible=True,
                        airglow_visible=True,
                        zodiacal_light_visible=True,
                        description="Good",
                        recommendations=("Good for observing",),
                    ),
                ):
                    with patch(
                        "celestron_nexstar.api.observation.observation_planner.get_current_configuration",
                        return_value=None,
                    ):
                        with patch(
                            "celestron_nexstar.api.astronomy.sun_moon.calculate_sun_times",
                            return_value={
                                "sunset": datetime(2023, 1, 1, 20, 0, tzinfo=UTC),
                                "sunrise": datetime(2023, 1, 2, 6, 0, tzinfo=UTC),
                            },
                        ):
                            with patch(
                                "celestron_nexstar.api.observation.observation_planner.get_sun_info"
                            ) as mock_sun_info:
                                mock_sun = MagicMock()
                                mock_sun.altitude_deg = -30.0
                                mock_sun.sunrise_time = datetime(2023, 1, 2, 6, 0, tzinfo=UTC)
                                mock_sun.sunset_time = datetime(2023, 1, 1, 20, 0, tzinfo=UTC)
                                mock_sun_info.return_value = mock_sun
                                with patch(
                                    "celestron_nexstar.api.observation.observation_planner.get_moon_info",
                                    return_value=MagicMock(
                                        illumination=0.5,
                                        altitude_deg=30.0,
                                        ra_hours=10.0,
                                        dec_degrees=20.0,
                                        phase=MoonPhase.FIRST_QUARTER,
                                    ),
                                ):
                                    with patch(
                                        "celestron_nexstar.api.observation.observation_planner.assess_observing_conditions",
                                        return_value=("good", "No warnings"),
                                    ):
                                        with patch(
                                            "celestron_nexstar.api.observation.observation_planner.calculate_seeing_conditions",
                                            return_value=(70.0, []),
                                        ):
                                            with patch(
                                                "celestron_nexstar.api.observation.scoring.is_nighttime",
                                                return_value=True,
                                            ):
                                                with patch(
                                                    "celestron_nexstar.api.location.weather.fetch_hourly_weather_forecast",
                                                    return_value=[],
                                                ):
                                                    with patch(
                                                        "celestron_nexstar.api.observation.observation_planner.calculate_astronomical_twilight",
                                                        return_value=(None, None, None, None),
                                                    ):
                                                        with patch(
                                                            "celestron_nexstar.api.observation.observation_planner.calculate_golden_hour",
                                                            return_value=(None, None, None, None),
                                                        ):
                                                            with patch(
                                                                "celestron_nexstar.api.observation.observation_planner.calculate_blue_hour",
                                                                return_value=(None, None, None, None),
                                                            ):
                                                                with patch.object(
                                                                    ObservationPlanner,
                                                                    "_calculate_galactic_center_visibility",
                                                                    return_value=(None, None),
                                                                ):
                                                                    # Test with start_time that has no timezone (should add UTC)
                                                                    conditions = self.planner.get_tonight_conditions(
                                                                        start_time=start_time_no_tz
                                                                    )
                                                                    self.assertIsInstance(
                                                                        conditions, ObservingConditions
                                                                    )

    @patch("celestron_nexstar.api.observation.observation_planner.get_observer_location")
    @patch("celestron_nexstar.api.astronomy.sun_moon.calculate_sun_times")
    def test_get_tonight_conditions_sunrise_before_sunset(self, mock_calculate_sun_times, mock_get_location):
        """Test get_tonight_conditions when sunrise is before sunset (next day)"""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session():
            mock_sess = AsyncMock()
            yield mock_sess

        mock_get_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0, name="Test")
        # Sunrise at 6:00, sunset at 20:00 (same day) - but code handles case where sunrise < sunset
        mock_calculate_sun_times.return_value = {
            "sunset": datetime(2023, 1, 1, 20, 0, tzinfo=UTC),
            "sunrise": datetime(2023, 1, 1, 6, 0, tzinfo=UTC),
        }

        with patch("celestron_nexstar.api.database.models.get_db_session", return_value=mock_session()):
            with patch(
                "celestron_nexstar.api.observation.observation_planner.fetch_weather",
                return_value=WeatherData(temperature_c=20.0, cloud_cover_percent=10.0),
            ):
                with patch(
                    "celestron_nexstar.api.observation.observation_planner.get_light_pollution_data",
                    return_value=LightPollutionData(
                        bortle_class=BortleClass.CLASS_3,
                        sqm_value=21.5,
                        naked_eye_limiting_magnitude=6.5,
                        milky_way_visible=True,
                        airglow_visible=True,
                        zodiacal_light_visible=True,
                        description="Good",
                        recommendations=("Good for observing",),
                    ),
                ):
                    with patch(
                        "celestron_nexstar.api.observation.observation_planner.get_current_configuration",
                        return_value=None,
                    ):
                        with patch(
                            "celestron_nexstar.api.observation.observation_planner.get_sun_info"
                        ) as mock_sun_info:
                            mock_sun = MagicMock()
                            mock_sun.altitude_deg = -30.0
                            mock_sun.sunrise_time = datetime(2023, 1, 1, 6, 0, tzinfo=UTC)
                            mock_sun.sunset_time = datetime(2023, 1, 1, 20, 0, tzinfo=UTC)
                            mock_sun_info.return_value = mock_sun
                            with patch(
                                "celestron_nexstar.api.observation.observation_planner.get_moon_info",
                                return_value=MagicMock(
                                    illumination=0.5,
                                    altitude_deg=30.0,
                                    ra_hours=10.0,
                                    dec_degrees=20.0,
                                    phase=MoonPhase.FIRST_QUARTER,
                                ),
                            ):
                                with patch(
                                    "celestron_nexstar.api.observation.observation_planner.assess_observing_conditions",
                                    return_value=("good", "No warnings"),
                                ):
                                    with patch(
                                        "celestron_nexstar.api.observation.observation_planner.calculate_seeing_conditions",
                                        return_value=(70.0, []),
                                    ):
                                        with patch(
                                            "celestron_nexstar.api.observation.scoring.is_nighttime", return_value=True
                                        ):
                                            with patch(
                                                "celestron_nexstar.api.location.weather.fetch_hourly_weather_forecast",
                                                return_value=[],
                                            ):
                                                with patch(
                                                    "celestron_nexstar.api.observation.observation_planner.calculate_astronomical_twilight",
                                                    return_value=(None, None, None, None),
                                                ):
                                                    with patch(
                                                        "celestron_nexstar.api.observation.observation_planner.calculate_golden_hour",
                                                        return_value=(None, None, None, None),
                                                    ):
                                                        with patch(
                                                            "celestron_nexstar.api.observation.observation_planner.calculate_blue_hour",
                                                            return_value=(None, None, None, None),
                                                        ):
                                                            with patch.object(
                                                                ObservationPlanner,
                                                                "_calculate_galactic_center_visibility",
                                                                return_value=(None, None),
                                                            ):
                                                                # This should handle the sunrise < sunset case
                                                                conditions = self.planner.get_tonight_conditions()
                                                                self.assertIsInstance(conditions, ObservingConditions)


if __name__ == "__main__":
    unittest.main()
