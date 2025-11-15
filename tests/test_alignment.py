"""
Unit tests for alignment.py

Tests telescope alignment methods including SkyAlign.
"""

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.observation.visibility import VisibilityInfo
from celestron_nexstar.api.telescope.alignment import (
    SkyAlignGroup,
    SkyAlignObject,
    _calculate_conditions_score,
    _calculate_separation_score,
    _check_collinear,
    get_bright_objects_for_skyalign,
    suggest_skyalign_objects,
)


class TestSkyAlignObject(unittest.TestCase):
    """Test suite for SkyAlignObject dataclass"""

    def test_creation(self):
        """Test creating a SkyAlignObject"""
        obj = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="star",
        )
        visibility = VisibilityInfo(
            object_name="Vega",
            is_visible=True,
            magnitude=0.03,
            altitude_deg=45.0,
            azimuth_deg=180.0,
            limiting_magnitude=6.0,
            reasons=("Visible",),
            observability_score=0.9,
        )
        sky_align_obj = SkyAlignObject(obj=obj, visibility=visibility, display_name="Vega")
        self.assertEqual(sky_align_obj.obj, obj)
        self.assertEqual(sky_align_obj.visibility, visibility)
        self.assertEqual(sky_align_obj.display_name, "Vega")


class TestSkyAlignGroup(unittest.TestCase):
    """Test suite for SkyAlignGroup dataclass"""

    def test_creation(self):
        """Test creating a SkyAlignGroup"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        obj2 = CelestialObject(name="Star2", common_name="Star2", ra_hours=1, dec_degrees=0, magnitude=1.5, object_type=CelestialObjectType.STAR, catalog="star")
        obj3 = CelestialObject(name="Star3", common_name="Star3", ra_hours=2, dec_degrees=0, magnitude=2.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=180.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj2, visibility=vis, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj3, visibility=vis, display_name="Star3")

        group = SkyAlignGroup(
            objects=(align_obj1, align_obj2, align_obj3),
            min_separation_deg=30.0,
            avg_observability_score=0.8,
            separation_score=0.7,
            conditions_score=0.9,
        )
        self.assertEqual(len(group.objects), 3)
        self.assertEqual(group.min_separation_deg, 30.0)
        self.assertEqual(group.avg_observability_score, 0.8)


class TestCalculateSeparationScore(unittest.TestCase):
    """Test suite for _calculate_separation_score function"""

    def test_calculate_separation_score(self):
        """Test separation score calculation"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        obj2 = CelestialObject(name="Star2", common_name="Star2", ra_hours=1, dec_degrees=0, magnitude=1.5, object_type=CelestialObjectType.STAR, catalog="star")
        obj3 = CelestialObject(name="Star3", common_name="Star3", ra_hours=2, dec_degrees=0, magnitude=2.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis1 = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis2 = VisibilityInfo(object_name="Star2", is_visible=True, magnitude=1.5, altitude_deg=45.0, azimuth_deg=60.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis3 = VisibilityInfo(object_name="Star3", is_visible=True, magnitude=2.0, altitude_deg=45.0, azimuth_deg=120.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis1, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj2, visibility=vis2, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj3, visibility=vis3, display_name="Star3")

        min_sep, sep_score = _calculate_separation_score(align_obj1, align_obj2, align_obj3)

        self.assertIsInstance(min_sep, float)
        self.assertGreater(min_sep, 0)
        self.assertIsInstance(sep_score, float)
        self.assertGreaterEqual(sep_score, 0.0)
        self.assertLessEqual(sep_score, 1.0)


class TestCheckCollinear(unittest.TestCase):
    """Test suite for _check_collinear function"""

    def test_not_collinear(self):
        """Test non-collinear objects"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        obj2 = CelestialObject(name="Star2", common_name="Star2", ra_hours=1, dec_degrees=0, magnitude=1.5, object_type=CelestialObjectType.STAR, catalog="star")
        obj3 = CelestialObject(name="Star3", common_name="Star3", ra_hours=0, dec_degrees=1, magnitude=2.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis1 = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis2 = VisibilityInfo(object_name="Star2", is_visible=True, magnitude=1.5, altitude_deg=45.0, azimuth_deg=60.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis3 = VisibilityInfo(object_name="Star3", is_visible=True, magnitude=2.0, altitude_deg=45.0, azimuth_deg=120.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis1, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj2, visibility=vis2, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj3, visibility=vis3, display_name="Star3")

        result = _check_collinear(align_obj1, align_obj2, align_obj3)
        self.assertIsInstance(result, bool)

    def test_collinear(self):
        """Test collinear objects"""
        # Objects in a line (same azimuth, different altitudes)
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        obj2 = CelestialObject(name="Star2", common_name="Star2", ra_hours=1, dec_degrees=0, magnitude=1.5, object_type=CelestialObjectType.STAR, catalog="star")
        obj3 = CelestialObject(name="Star3", common_name="Star3", ra_hours=2, dec_degrees=0, magnitude=2.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis1 = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=30.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis2 = VisibilityInfo(object_name="Star2", is_visible=True, magnitude=1.5, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis3 = VisibilityInfo(object_name="Star3", is_visible=True, magnitude=2.0, altitude_deg=60.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis1, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj2, visibility=vis2, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj3, visibility=vis3, display_name="Star3")

        result = _check_collinear(align_obj1, align_obj2, align_obj3, threshold_deg=10.0)
        self.assertIsInstance(result, bool)


class TestCalculateConditionsScore(unittest.TestCase):
    """Test suite for _calculate_conditions_score function"""

    def test_calculate_conditions_score_no_conditions(self):
        """Test conditions score with no condition data"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star3")

        score = _calculate_conditions_score(align_obj1, align_obj2, align_obj3)
        self.assertEqual(score, 1.0)  # Default score when no conditions provided

    def test_calculate_conditions_score_cloudy(self):
        """Test conditions score with cloud cover"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star3")

        score = _calculate_conditions_score(align_obj1, align_obj2, align_obj3, cloud_cover_percent=90.0)
        self.assertLess(score, 1.0)  # Should be reduced by cloud cover
        self.assertGreaterEqual(score, 0.0)

    def test_calculate_conditions_score_moon_interference(self):
        """Test conditions score with moon interference"""
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj1, visibility=vis, display_name="Star3")

        score = _calculate_conditions_score(
            align_obj1, align_obj2, align_obj3, moon_ra_hours=0.0, moon_dec_degrees=0.0, moon_illumination=1.0
        )
        self.assertLess(score, 1.0)  # Should be reduced by bright moon
        self.assertGreaterEqual(score, 0.0)


class TestGetBrightObjectsForSkyalign(unittest.TestCase):
    """Test suite for get_bright_objects_for_skyalign function"""

    @patch("celestron_nexstar.api.telescope.alignment.get_observer_location")
    @patch("celestron_nexstar.api.telescope.alignment.get_database")
    @patch("celestron_nexstar.api.telescope.alignment.assess_visibility")
    @patch("celestron_nexstar.api.telescope.alignment.get_planet_magnitude")
    @patch("celestron_nexstar.api.telescope.alignment.get_planetary_position")
    def test_get_bright_objects_for_skyalign(
        self, mock_get_planetary, mock_get_magnitude, mock_assess, mock_get_db, mock_get_location
    ):
        """Test getting bright objects for SkyAlign"""
        # Mock observer location
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_location = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_get_location.return_value = mock_location

        # Mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Mock stars
        star = CelestialObject(
            name="Vega", common_name="Vega", ra_hours=18.615, dec_degrees=38.784, magnitude=0.03, object_type=CelestialObjectType.STAR, catalog="star"
        )
        mock_db.filter_objects = AsyncMock(return_value=[star])

        # Mock visibility
        vis = VisibilityInfo(object_name="Vega", is_visible=True, magnitude=0.03, altitude_deg=45.0, azimuth_deg=180.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.9)
        mock_assess.return_value = vis

        # Mock planetary positions
        mock_get_magnitude.return_value = -2.0
        mock_get_planetary.return_value = (12.0, 0.0)

        result = get_bright_objects_for_skyalign(observer_lat=40.0, observer_lon=-100.0)

        self.assertIsInstance(result, list)
        # Should have objects if database returns stars

    @patch("celestron_nexstar.api.telescope.alignment.get_observer_location")
    def test_get_bright_objects_for_skyalign_default_location(self, mock_get_location):
        """Test getting bright objects with default location"""
        from celestron_nexstar.api.location.observer import ObserverLocation

        mock_location = ObserverLocation(latitude=40.0, longitude=-100.0)
        mock_get_location.return_value = mock_location

        with patch("celestron_nexstar.api.telescope.alignment.get_database") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db
            mock_db.filter_objects = AsyncMock(return_value=[])

            result = get_bright_objects_for_skyalign()

            self.assertIsInstance(result, list)


class TestSuggestSkyalignObjects(unittest.TestCase):
    """Test suite for suggest_skyalign_objects function"""

    @patch("celestron_nexstar.api.telescope.alignment.get_bright_objects_for_skyalign")
    def test_suggest_skyalign_objects_not_enough(self, mock_get_bright):
        """Test when not enough objects available"""
        mock_get_bright.return_value = []  # No objects

        result = suggest_skyalign_objects(observer_lat=40.0, observer_lon=-100.0)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    @patch("celestron_nexstar.api.telescope.alignment.get_bright_objects_for_skyalign")
    def test_suggest_skyalign_objects_success(self, mock_get_bright):
        """Test successful suggestion of SkyAlign objects"""
        # Create mock objects
        obj1 = CelestialObject(name="Star1", common_name="Star1", ra_hours=0, dec_degrees=0, magnitude=1.0, object_type=CelestialObjectType.STAR, catalog="star")
        obj2 = CelestialObject(name="Star2", common_name="Star2", ra_hours=1, dec_degrees=0, magnitude=1.5, object_type=CelestialObjectType.STAR, catalog="star")
        obj3 = CelestialObject(name="Star3", common_name="Star3", ra_hours=2, dec_degrees=0, magnitude=2.0, object_type=CelestialObjectType.STAR, catalog="star")
        vis1 = VisibilityInfo(object_name="Star1", is_visible=True, magnitude=1.0, altitude_deg=45.0, azimuth_deg=0.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.9)
        vis2 = VisibilityInfo(object_name="Star2", is_visible=True, magnitude=1.5, altitude_deg=45.0, azimuth_deg=60.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.8)
        vis3 = VisibilityInfo(object_name="Star3", is_visible=True, magnitude=2.0, altitude_deg=45.0, azimuth_deg=120.0, limiting_magnitude=6.0, reasons=("Visible",), observability_score=0.85)
        align_obj1 = SkyAlignObject(obj=obj1, visibility=vis1, display_name="Star1")
        align_obj2 = SkyAlignObject(obj=obj2, visibility=vis2, display_name="Star2")
        align_obj3 = SkyAlignObject(obj=obj3, visibility=vis3, display_name="Star3")

        mock_get_bright.return_value = [align_obj1, align_obj2, align_obj3]

        result = suggest_skyalign_objects(observer_lat=40.0, observer_lon=-100.0, max_groups=5)

        self.assertIsInstance(result, list)
        # Should have groups if objects are well-separated


if __name__ == "__main__":
    unittest.main()
