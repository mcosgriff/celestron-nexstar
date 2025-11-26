"""
Unit tests for planning_utils.py

Tests planning utilities for observation sessions including visibility timelines,
checklists, difficulty ratings, moon phase impact, and more.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType, MoonPhase
from celestron_nexstar.api.observation.planning_utils import (
    DifficultyLevel,
    ObjectVisibilityTimeline,
    compare_equipment,
    generate_observation_checklist,
    generate_quick_reference,
    generate_session_log_template,
    get_moon_phase_impact,
    get_object_difficulty,
    get_object_visibility_timeline,
    get_time_based_recommendations,
    get_transit_times,
)


class TestDifficultyLevel(unittest.TestCase):
    """Test suite for DifficultyLevel enum"""

    def test_difficulty_level_values(self):
        """Test DifficultyLevel enum values"""
        self.assertEqual(DifficultyLevel.BEGINNER, "beginner")
        self.assertEqual(DifficultyLevel.INTERMEDIATE, "intermediate")
        self.assertEqual(DifficultyLevel.ADVANCED, "advanced")
        self.assertEqual(DifficultyLevel.EXPERT, "expert")


class TestObjectVisibilityTimeline(unittest.TestCase):
    """Test suite for ObjectVisibilityTimeline dataclass"""

    def test_creation(self):
        """Test creating ObjectVisibilityTimeline"""
        timeline = ObjectVisibilityTimeline(
            object_name="M31",
            rise_time=datetime.now(UTC),
            transit_time=datetime.now(UTC),
            set_time=datetime.now(UTC),
            max_altitude=45.0,
            is_circumpolar=False,
            is_always_visible=False,
            is_never_visible=False,
        )
        self.assertEqual(timeline.object_name, "M31")
        self.assertEqual(timeline.max_altitude, 45.0)
        self.assertFalse(timeline.is_circumpolar)

    def test_frozen(self):
        """Test that ObjectVisibilityTimeline is frozen (immutable)"""
        timeline = ObjectVisibilityTimeline(
            object_name="M31",
            rise_time=None,
            transit_time=None,
            set_time=None,
            max_altitude=45.0,
            is_circumpolar=False,
            is_always_visible=False,
            is_never_visible=False,
        )
        with self.assertRaises(Exception):  # dataclass frozen raises FrozenInstanceError
            timeline.object_name = "M42"


class TestGetObjectDifficulty(unittest.TestCase):
    """Test suite for get_object_difficulty function"""

    def test_planet_difficulty(self):
        """Test difficulty for planets"""
        obj = CelestialObject(
            name="Jupiter",
            common_name=None,
            catalog="planet",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.PLANET,
            magnitude=2.0,
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_bright_star_difficulty(self):
        """Test difficulty for bright stars"""
        obj = CelestialObject(
            name="Vega",
            common_name=None,
            catalog="star",
            ra_hours=18.0,
            dec_degrees=38.0,
            object_type=CelestialObjectType.STAR,
            magnitude=2.0,  # < 3.0 is beginner
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_faint_star_difficulty(self):
        """Test difficulty for faint stars"""
        obj = CelestialObject(
            name="Faint Star",
            common_name=None,
            catalog="star",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.STAR,
            magnitude=5.0,  # >= 3.0, falls to default logic
        )
        difficulty = get_object_difficulty(obj)
        # Default logic: < 4.0 = beginner, < 7.0 = intermediate
        self.assertEqual(difficulty, DifficultyLevel.INTERMEDIATE)

    def test_bright_galaxy_difficulty(self):
        """Test difficulty for bright galaxies"""
        obj = CelestialObject(
            name="M31",
            common_name=None,
            catalog="messier",
            ra_hours=0.7,
            dec_degrees=41.3,
            object_type=CelestialObjectType.GALAXY,
            magnitude=5.0,  # < 6.0 is beginner
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_intermediate_galaxy_difficulty(self):
        """Test difficulty for intermediate galaxies"""
        obj = CelestialObject(
            name="M51",
            common_name=None,
            catalog="messier",
            ra_hours=13.5,
            dec_degrees=47.2,
            object_type=CelestialObjectType.GALAXY,
            magnitude=8.0,  # < 9.0 is intermediate
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.INTERMEDIATE)

    def test_advanced_galaxy_difficulty(self):
        """Test difficulty for advanced galaxies"""
        obj = CelestialObject(
            name="Faint Galaxy",
            common_name=None,
            catalog="ngc",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.GALAXY,
            magnitude=11.0,  # < 12.0 is advanced
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.ADVANCED)

    def test_expert_galaxy_difficulty(self):
        """Test difficulty for expert galaxies"""
        obj = CelestialObject(
            name="Very Faint Galaxy",
            common_name=None,
            catalog="ngc",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.GALAXY,
            magnitude=13.0,  # >= 12.0 is expert
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.EXPERT)

    def test_nebula_difficulty(self):
        """Test difficulty for nebulae"""
        obj = CelestialObject(
            name="M42",
            common_name=None,
            catalog="messier",
            ra_hours=5.6,
            dec_degrees=-5.4,
            object_type=CelestialObjectType.NEBULA,
            magnitude=5.0,  # < 6.0 is beginner
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_cluster_difficulty(self):
        """Test difficulty for star clusters"""
        obj = CelestialObject(
            name="M13",
            common_name=None,
            catalog="messier",
            ra_hours=16.7,
            dec_degrees=36.5,
            object_type=CelestialObjectType.CLUSTER,
            magnitude=5.0,  # < 6.0 is beginner
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_double_star_difficulty(self):
        """Test difficulty for double stars"""
        obj = CelestialObject(
            name="Albireo",
            common_name=None,
            catalog="star",
            ra_hours=19.8,
            dec_degrees=27.9,
            object_type=CelestialObjectType.DOUBLE_STAR,
            magnitude=4.0,  # < 5.0 is intermediate
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.INTERMEDIATE)

    def test_faint_double_star_difficulty(self):
        """Test difficulty for faint double stars"""
        obj = CelestialObject(
            name="Faint Double",
            common_name=None,
            catalog="star",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.DOUBLE_STAR,
            magnitude=6.0,  # >= 5.0 is advanced
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.ADVANCED)

    def test_no_magnitude_difficulty(self):
        """Test difficulty when magnitude is None"""
        obj = CelestialObject(
            name="Unknown",
            common_name=None,
            catalog="unknown",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.STAR,
            magnitude=None,
        )
        difficulty = get_object_difficulty(obj)
        # Should default to expert for very faint objects
        self.assertEqual(difficulty, DifficultyLevel.EXPERT)

    def test_default_difficulty_bright(self):
        """Test default difficulty for bright objects"""
        obj = CelestialObject(
            name="Bright Object",
            common_name=None,
            catalog="unknown",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.ASTERISM,
            magnitude=2.0,
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.BEGINNER)

    def test_default_difficulty_intermediate(self):
        """Test default difficulty for intermediate objects"""
        obj = CelestialObject(
            name="Intermediate Object",
            common_name=None,
            catalog="unknown",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.ASTERISM,
            magnitude=5.0,
        )
        difficulty = get_object_difficulty(obj)
        self.assertEqual(difficulty, DifficultyLevel.INTERMEDIATE)


class TestGetMoonPhaseImpact(unittest.TestCase):
    """Test suite for get_moon_phase_impact function"""

    def test_planet_impact(self):
        """Test moon phase impact on planets"""
        impact = get_moon_phase_impact(CelestialObjectType.PLANET, MoonPhase.FULL_MOON, 1.0)
        self.assertEqual(impact["impact_level"], "minimal")
        self.assertTrue(impact["recommended"])
        self.assertIn("Planets are bright enough", impact["notes"][0])

    def test_star_impact_bright_moon(self):
        """Test moon phase impact on stars with bright moon"""
        impact = get_moon_phase_impact(CelestialObjectType.STAR, MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "moderate")
        self.assertTrue(impact["recommended"])

    def test_star_impact_dark_moon(self):
        """Test moon phase impact on stars with dark moon"""
        impact = get_moon_phase_impact(CelestialObjectType.STAR, MoonPhase.NEW_MOON, 0.1)
        self.assertEqual(impact["impact_level"], "minimal")

    def test_galaxy_impact_bright_moon(self):
        """Test moon phase impact on galaxies with bright moon"""
        impact = get_moon_phase_impact(CelestialObjectType.GALAXY, MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "severe")
        self.assertFalse(impact["recommended"])
        self.assertIn("Avoid observing", impact["notes"][0])

    def test_galaxy_impact_dark_moon(self):
        """Test moon phase impact on galaxies with dark moon"""
        impact = get_moon_phase_impact(CelestialObjectType.GALAXY, MoonPhase.NEW_MOON, 0.1)
        self.assertEqual(impact["impact_level"], "minimal")
        self.assertTrue(impact["recommended"])

    def test_nebula_impact_bright_moon(self):
        """Test moon phase impact on nebulae with bright moon"""
        impact = get_moon_phase_impact(CelestialObjectType.NEBULA, MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "severe")
        self.assertFalse(impact["recommended"])

    def test_cluster_impact_bright_moon(self):
        """Test moon phase impact on clusters with bright moon"""
        impact = get_moon_phase_impact(CelestialObjectType.CLUSTER, MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "moderate")
        self.assertTrue(impact["recommended"])

    def test_cluster_impact_dark_moon(self):
        """Test moon phase impact on clusters with dark moon"""
        impact = get_moon_phase_impact(CelestialObjectType.CLUSTER, MoonPhase.NEW_MOON, 0.1)
        self.assertEqual(impact["impact_level"], "minimal")

    def test_string_object_type(self):
        """Test with string object type"""
        impact = get_moon_phase_impact("galaxy", MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "severe")

    def test_invalid_string_object_type(self):
        """Test with invalid string object type (defaults to star)"""
        impact = get_moon_phase_impact("invalid_type", MoonPhase.FULL_MOON, 0.9)
        self.assertEqual(impact["impact_level"], "moderate")

    def test_no_moon_phase(self):
        """Test with no moon phase provided"""
        impact = get_moon_phase_impact(CelestialObjectType.STAR, None, None)
        self.assertEqual(impact["impact_level"], "minimal")

    def test_no_moon_illumination(self):
        """Test with no moon illumination provided"""
        impact = get_moon_phase_impact(CelestialObjectType.STAR, MoonPhase.FULL_MOON, None)
        # Should default to 0.5 if moon_phase is provided, which is NOT > 0.5, so minimal
        self.assertEqual(impact["impact_level"], "minimal")


class TestGenerateObservationChecklist(unittest.TestCase):
    """Test suite for generate_observation_checklist function"""

    def test_telescope_checklist(self):
        """Test telescope checklist generation"""
        checklist = generate_observation_checklist(equipment_type="telescope")
        self.assertIn("Set up telescope mount", checklist)
        self.assertIn("Perform star alignment", checklist)
        self.assertIn("Check battery/power", checklist)

    def test_binoculars_checklist(self):
        """Test binoculars checklist generation"""
        checklist = generate_observation_checklist(equipment_type="binoculars")
        self.assertIn("Check binocular focus", checklist)
        self.assertIn("Clean lenses", checklist)
        self.assertNotIn("Perform star alignment", checklist)

    def test_naked_eye_checklist(self):
        """Test naked-eye checklist generation"""
        checklist = generate_observation_checklist(equipment_type="naked_eye")
        self.assertIn("Allow 20-30 minutes for dark adaptation", checklist)
        self.assertIn("Find dark location away from lights", checklist)
        self.assertNotIn("Set up telescope mount", checklist)

    def test_checklist_includes_weather(self):
        """Test that checklist includes weather items"""
        checklist = generate_observation_checklist(include_weather=True)
        self.assertIn("Check weather forecast", checklist)
        self.assertIn("Check cloud cover", checklist)

    def test_checklist_excludes_weather(self):
        """Test that checklist excludes weather items when requested"""
        checklist = generate_observation_checklist(include_weather=False)
        self.assertNotIn("Check weather forecast", checklist)

    def test_checklist_includes_setup(self):
        """Test that checklist includes setup items"""
        checklist = generate_observation_checklist(include_setup=True)
        self.assertIn("Set up telescope mount", checklist)

    def test_checklist_excludes_setup(self):
        """Test that checklist excludes setup items when requested"""
        checklist = generate_observation_checklist(equipment_type="telescope", include_setup=False)
        self.assertNotIn("Set up telescope mount", checklist)

    def test_checklist_common_items(self):
        """Test that checklist includes common items"""
        checklist = generate_observation_checklist()
        self.assertIn("Dress appropriately for temperature", checklist)
        self.assertIn("Bring water and snacks", checklist)
        self.assertIn("Notify someone of your location", checklist)


class TestCompareEquipment(unittest.TestCase):
    """Test suite for compare_equipment function"""

    def test_compare_equipment_default(self):
        """Test equipment comparison with default types"""
        result = compare_equipment("M31")
        self.assertIn("naked_eye", result)
        self.assertIn("binoculars", result)
        self.assertIn("telescope", result)

    def test_compare_equipment_custom_types(self):
        """Test equipment comparison with custom types"""
        result = compare_equipment("M31", equipment_types=["telescope"])
        self.assertIn("telescope", result)
        self.assertNotIn("naked_eye", result)

    def test_compare_equipment_structure(self):
        """Test equipment comparison result structure"""
        result = compare_equipment("M31")
        for _equipment, data in result.items():
            self.assertIn("visible", data)
            self.assertIn("notes", data)


class TestGenerateQuickReference(unittest.TestCase):
    """Test suite for generate_quick_reference function"""

    def test_generate_quick_reference(self):
        """Test quick reference generation"""
        objects = [
            CelestialObject(
                name="M31",
                common_name=None,
                catalog="messier",
                ra_hours=0.7,
                dec_degrees=41.3,
                object_type=CelestialObjectType.GALAXY,
                magnitude=3.4,
            ),
            CelestialObject(
                name="Jupiter",
                common_name=None,
                catalog="planet",
                ra_hours=10.0,
                dec_degrees=20.0,
                object_type=CelestialObjectType.PLANET,
                magnitude=-2.0,
            ),
        ]
        reference = generate_quick_reference(objects)
        self.assertIsInstance(reference, str)
        self.assertIn("QUICK REFERENCE CARD", reference)
        self.assertIn("M31", reference)
        self.assertIn("Jupiter", reference)

    def test_generate_quick_reference_empty(self):
        """Test quick reference with empty list"""
        reference = generate_quick_reference([])
        self.assertIsInstance(reference, str)
        self.assertIn("QUICK REFERENCE CARD", reference)

    def test_generate_quick_reference_limit(self):
        """Test quick reference limits to 20 objects"""
        objects = [
            CelestialObject(
                name=f"Object{i}",
                common_name=None,
                catalog="test",
                ra_hours=10.0,
                dec_degrees=20.0,
                object_type=CelestialObjectType.STAR,
                magnitude=5.0,
            )
            for i in range(25)
        ]
        reference = generate_quick_reference(objects)
        # Should only show first 20
        self.assertIn("Object0", reference)
        self.assertIn("Object19", reference)
        self.assertNotIn("Object20", reference)


class TestGenerateSessionLogTemplate(unittest.TestCase):
    """Test suite for generate_session_log_template function"""

    def test_generate_log_template(self):
        """Test session log template generation"""
        template = generate_session_log_template()
        self.assertIn("OBSERVATION SESSION LOG", template)
        self.assertIn("Date:", template)
        self.assertIn("Location:", template)
        self.assertIn("CONDITIONS:", template)
        self.assertIn("EQUIPMENT:", template)
        self.assertIn("OBSERVATIONS:", template)

    def test_generate_log_template_with_date(self):
        """Test session log template with specific date"""
        date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        template = generate_session_log_template(date=date)
        self.assertIn("2024-01-15", template)

    def test_generate_log_template_with_location(self):
        """Test session log template with location"""
        template = generate_session_log_template(location="Test Observatory")
        self.assertIn("Test Observatory", template)

    def test_generate_log_template_default_location(self):
        """Test session log template with default location"""
        template = generate_session_log_template(location=None)
        self.assertIn("TBD", template)


class TestGetTimeBasedRecommendations(unittest.TestCase):
    """Test suite for get_time_based_recommendations function"""

    def test_get_time_based_recommendations(self):
        """Test time-based recommendations"""
        import asyncio

        time_slots = [
            datetime(2024, 1, 15, 20, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 15, 22, 0, 0, tzinfo=UTC),
        ]
        result = asyncio.run(get_time_based_recommendations(time_slots))
        self.assertEqual(len(result), 2)
        for time_slot in time_slots:
            self.assertIn(time_slot, result)

    def test_get_time_based_recommendations_equipment_types(self):
        """Test time-based recommendations with different equipment types"""
        import asyncio

        time_slots = [datetime(2024, 1, 15, 20, 0, 0, tzinfo=UTC)]
        for eq_type in ["telescope", "binoculars", "naked_eye"]:
            result = asyncio.run(get_time_based_recommendations(time_slots, equipment_type=eq_type))
            self.assertIn(time_slots[0], result)


class TestGetObjectVisibilityTimeline(unittest.TestCase):
    """Test suite for get_object_visibility_timeline function"""

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.planning_utils.calculate_lst")
    @patch("celestron_nexstar.api.observation.planning_utils.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.planning_utils.is_dynamic_object")
    def test_get_timeline_fixed_object(self, mock_dynamic, mock_ra_dec, mock_lst, mock_alt_az, mock_location):
        """Test timeline for fixed object"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_dynamic.return_value = False
        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_lst.return_value = 12.0
        mock_ra_dec.return_value = (45.0, 0.0)  # altitude, azimuth
        mock_alt_az.side_effect = [
            (30.0, 180.0),  # Initial check
            (45.0, 0.0),  # Transit
            (30.0, 180.0),  # Later check
        ]

        obj = CelestialObject(
            name="M31",
            common_name=None,
            catalog="messier",
            ra_hours=0.7,
            dec_degrees=41.3,
            object_type=CelestialObjectType.GALAXY,
            magnitude=3.4,
        )

        timeline = get_object_visibility_timeline(obj)
        self.assertEqual(timeline.object_name, "M31")

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_planetary_position")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.planning_utils.calculate_lst")
    @patch("celestron_nexstar.api.observation.planning_utils.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.planning_utils.is_dynamic_object")
    def test_get_timeline_dynamic_object(
        self, mock_dynamic, mock_ra_dec, mock_lst, mock_alt_az, mock_planet_pos, mock_location
    ):
        """Test timeline for dynamic object (planet)"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_dynamic.return_value = True
        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_planet_pos.return_value = (10.0, 20.0)  # RA, Dec
        mock_lst.return_value = 12.0
        mock_ra_dec.return_value = (45.0, 0.0)  # altitude, azimuth
        mock_alt_az.side_effect = [
            (30.0, 180.0),  # Initial check
            (45.0, 0.0),  # Transit
            (30.0, 180.0),  # Later check
        ]

        obj = CelestialObject(
            name="Jupiter",
            common_name=None,
            catalog="planet",
            ra_hours=10.0,
            dec_degrees=20.0,
            object_type=CelestialObjectType.PLANET,
            magnitude=-2.0,
        )

        timeline = get_object_visibility_timeline(obj)
        self.assertEqual(timeline.object_name, "Jupiter")

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.planning_utils.calculate_lst")
    @patch("celestron_nexstar.api.observation.planning_utils.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.planning_utils.is_dynamic_object")
    def test_get_timeline_circumpolar(self, mock_dynamic, mock_ra_dec, mock_lst, mock_alt_az, mock_location):
        """Test timeline for circumpolar object"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_dynamic.return_value = False
        # High latitude observer, object near pole
        mock_location.return_value = ObserverLocation(latitude=80.0, longitude=-100.0)
        mock_lst.return_value = 12.0
        mock_ra_dec.return_value = (85.0, 0.0)  # altitude, azimuth
        # Always above horizon
        mock_alt_az.side_effect = [
            (85.0, 180.0),  # Initial check
            (85.0, 0.0),  # Transit
            (85.0, 180.0),  # Later check
        ]

        obj = CelestialObject(
            name="Polaris",
            common_name=None,
            catalog="star",
            ra_hours=2.5,
            dec_degrees=89.0,  # Very close to north pole
            object_type=CelestialObjectType.STAR,
            magnitude=2.0,
        )

        timeline = get_object_visibility_timeline(obj)
        self.assertTrue(timeline.is_circumpolar)
        self.assertTrue(timeline.is_always_visible)

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_altitude_azimuth")
    @patch("celestron_nexstar.api.observation.planning_utils.calculate_lst")
    @patch("celestron_nexstar.api.observation.planning_utils.ra_dec_to_alt_az")
    @patch("celestron_nexstar.api.observation.planning_utils.is_dynamic_object")
    def test_get_timeline_never_visible(self, mock_dynamic, mock_ra_dec, mock_lst, mock_alt_az, mock_location):
        """Test timeline for object never visible"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_dynamic.return_value = False
        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_lst.return_value = 12.0
        # Transit altitude is below horizon
        mock_ra_dec.return_value = (-10.0, 0.0)  # Below horizon at transit
        # All altitude checks return negative (below horizon)
        mock_alt_az.side_effect = [
            (-5.0, 180.0),  # Initial check - below horizon
            (-10.0, 0.0),  # Transit - below horizon (max altitude is negative)
            (-5.0, 180.0),  # Later check - below horizon
            (-5.0, 180.0),  # Additional checks for rise/set
            (-5.0, 180.0),
        ]

        obj = CelestialObject(
            name="Southern Object",
            common_name=None,
            catalog="test",
            ra_hours=12.0,
            dec_degrees=-80.0,  # Very far south
            object_type=CelestialObjectType.STAR,
            magnitude=5.0,
        )

        timeline = get_object_visibility_timeline(obj)
        # Object is never visible if max altitude is negative
        self.assertTrue(timeline.is_never_visible or timeline.max_altitude < 0)


class TestGetTransitTimes(unittest.TestCase):
    """Test suite for get_transit_times function"""

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_visibility_timeline")
    def test_get_transit_times(self, mock_timeline, mock_location):
        """Test getting transit times for multiple objects"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)

        transit_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_timeline.return_value = ObjectVisibilityTimeline(
            object_name="M31",
            rise_time=None,
            transit_time=transit_time,
            set_time=None,
            max_altitude=45.0,
            is_circumpolar=False,
            is_always_visible=False,
            is_never_visible=False,
        )

        objects = [
            CelestialObject(
                name="M31",
                common_name=None,
                catalog="messier",
                ra_hours=0.7,
                dec_degrees=41.3,
                object_type=CelestialObjectType.GALAXY,
                magnitude=3.4,
            )
        ]

        result = get_transit_times(objects)
        self.assertIn("M31", result)
        self.assertEqual(result["M31"], transit_time)

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_visibility_timeline")
    def test_get_transit_times_no_transit(self, mock_timeline, mock_location):
        """Test getting transit times when object has no transit"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_timeline.return_value = ObjectVisibilityTimeline(
            object_name="M31",
            rise_time=None,
            transit_time=None,  # No transit
            set_time=None,
            max_altitude=-10.0,
            is_circumpolar=False,
            is_always_visible=False,
            is_never_visible=True,
        )

        objects = [
            CelestialObject(
                name="M31",
                common_name=None,
                catalog="messier",
                ra_hours=0.7,
                dec_degrees=41.3,
                object_type=CelestialObjectType.GALAXY,
                magnitude=3.4,
            )
        ]

        result = get_transit_times(objects)
        self.assertNotIn("M31", result)

    @patch("celestron_nexstar.api.observation.planning_utils.get_observer_location")
    @patch("celestron_nexstar.api.observation.planning_utils.get_object_visibility_timeline")
    def test_get_transit_times_exception(self, mock_timeline, mock_location):
        """Test getting transit times when exception occurs"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_location.return_value = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_timeline.side_effect = Exception("Calculation error")

        objects = [
            CelestialObject(
                name="M31",
                common_name=None,
                catalog="messier",
                ra_hours=0.7,
                dec_degrees=41.3,
                object_type=CelestialObjectType.GALAXY,
                magnitude=3.4,
            )
        ]

        result = get_transit_times(objects)
        # Should return empty dict when exception occurs
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
