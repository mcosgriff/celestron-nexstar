"""
Unit tests for observation/filtering.py

Tests object filtering and sorting functions.
"""

import unittest

from celestron_nexstar.api.catalogs.catalogs import CelestialObject
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.observation.filtering import (
    filter_and_sort_objects,
    filter_objects,
    sort_objects,
)
from celestron_nexstar.api.observation.visibility import VisibilityInfo


class TestFilterObjects(unittest.TestCase):
    """Test suite for filter_objects function"""

    def setUp(self):
        """Set up test fixtures"""
        self.obj1 = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
            constellation="Lyra",
        )
        self.obj2 = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
            constellation="Andromeda",
        )
        self.obj3 = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        self.vis1 = VisibilityInfo(
            object_name="Vega",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=0.03,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )
        self.vis2 = VisibilityInfo(
            object_name="M31",
            altitude_deg=30.0,
            azimuth_deg=90.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.7,
            reasons=("Moderate altitude",),
        )
        self.vis3 = VisibilityInfo(
            object_name="Jupiter",
            altitude_deg=60.0,
            azimuth_deg=270.0,
            magnitude=-2.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.95,
            reasons=("Excellent altitude",),
        )

        self.objects = [
            (self.obj1, self.vis1),
            (self.obj2, self.vis2),
            (self.obj3, self.vis3),
        ]

    def test_filter_by_search_query_name(self):
        """Test filtering by search query matching name"""
        filtered = filter_objects(self.objects, search_query="Vega")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].name, "Vega")

    def test_filter_by_search_query_common_name(self):
        """Test filtering by search query matching common_name"""
        filtered = filter_objects(self.objects, search_query="Andromeda")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].common_name, "Andromeda Galaxy")

    def test_filter_by_search_query_case_insensitive(self):
        """Test that search query is case-insensitive"""
        filtered = filter_objects(self.objects, search_query="vega")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].name, "Vega")

    def test_filter_by_search_query_no_match(self):
        """Test filtering with no matching search query"""
        filtered = filter_objects(self.objects, search_query="Nonexistent")
        self.assertEqual(len(filtered), 0)

    def test_filter_by_object_type(self):
        """Test filtering by object type"""
        filtered = filter_objects(self.objects, object_type="star")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].object_type, CelestialObjectType.STAR)

    def test_filter_by_magnitude_min(self):
        """Test filtering by minimum magnitude"""
        filtered = filter_objects(self.objects, magnitude_min=0.0)
        # Should include Vega (0.03) and M31 (3.4), exclude Jupiter (-2.0)
        self.assertEqual(len(filtered), 2)
        names = {obj.name for obj, _ in filtered}
        self.assertIn("Vega", names)
        self.assertIn("M31", names)

    def test_filter_by_magnitude_max(self):
        """Test filtering by maximum magnitude"""
        filtered = filter_objects(self.objects, magnitude_max=1.0)
        # Should include Vega (0.03) and Jupiter (-2.0), exclude M31 (3.4)
        self.assertEqual(len(filtered), 2)
        names = {obj.name for obj, _ in filtered}
        self.assertIn("Vega", names)
        self.assertIn("Jupiter", names)

    def test_filter_by_magnitude_range(self):
        """Test filtering by magnitude range"""
        filtered = filter_objects(self.objects, magnitude_min=0.0, magnitude_max=5.0)
        # Should include Vega (0.03) and M31 (3.4), exclude Jupiter (-2.0)
        self.assertEqual(len(filtered), 2)

    def test_filter_by_constellation(self):
        """Test filtering by constellation"""
        filtered = filter_objects(self.objects, constellation="Lyra")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].constellation, "Lyra")

    def test_filter_by_constellation_case_insensitive(self):
        """Test that constellation filter is case-insensitive"""
        filtered = filter_objects(self.objects, constellation="lyra")
        self.assertEqual(len(filtered), 1)

    def test_filter_combines_multiple_criteria(self):
        """Test filtering with multiple criteria"""
        filtered = filter_objects(
            self.objects, search_query="Vega", object_type="star", magnitude_max=1.0
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].name, "Vega")

    def test_filter_empty_list(self):
        """Test filtering empty list"""
        filtered = filter_objects([], search_query="Vega")
        self.assertEqual(len(filtered), 0)

    def test_filter_none_magnitude_excluded(self):
        """Test that objects with None magnitude are excluded from magnitude filters"""
        obj_none_mag = CelestialObject(
            name="Test",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=None,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        vis_none = VisibilityInfo(
            object_name="Test",
            altitude_deg=45.0,
            azimuth_deg=180.0,
            magnitude=None,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("Good altitude",),
        )
        objects_with_none = self.objects + [(obj_none_mag, vis_none)]

        filtered = filter_objects(objects_with_none, magnitude_min=0.0)
        # Should not include object with None magnitude
        self.assertEqual(len(filtered), 2)


class TestSortObjects(unittest.TestCase):
    """Test suite for sort_objects function"""

    def setUp(self):
        """Set up test fixtures"""
        self.obj1 = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )
        self.obj2 = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )
        self.obj3 = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        self.vis1 = VisibilityInfo(
            object_name="Vega",
            altitude_deg=30.0,
            azimuth_deg=180.0,
            magnitude=0.03,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.7,
            reasons=("Moderate altitude",),
        )
        self.vis2 = VisibilityInfo(
            object_name="M31",
            altitude_deg=60.0,
            azimuth_deg=90.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("High altitude",),
        )
        self.vis3 = VisibilityInfo(
            object_name="Jupiter",
            altitude_deg=45.0,
            azimuth_deg=270.0,
            magnitude=-2.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.8,
            reasons=("Good altitude",),
        )

        self.objects = [
            (self.obj1, self.vis1),  # Altitude 30
            (self.obj2, self.vis2),  # Altitude 60
            (self.obj3, self.vis3),  # Altitude 45
        ]

    def test_sort_by_altitude_ascending(self):
        """Test sorting by altitude (ascending)"""
        sorted_objs = sort_objects(self.objects, sort_by="altitude", reverse=False)
        altitudes = [vis.altitude_deg for _, vis in sorted_objs]
        self.assertEqual(altitudes, [30.0, 45.0, 60.0])

    def test_sort_by_altitude_descending(self):
        """Test sorting by altitude (descending)"""
        sorted_objs = sort_objects(self.objects, sort_by="altitude", reverse=True)
        altitudes = [vis.altitude_deg for _, vis in sorted_objs]
        self.assertEqual(altitudes, [60.0, 45.0, 30.0])

    def test_sort_by_magnitude_ascending(self):
        """Test sorting by magnitude (ascending, brighter first)"""
        sorted_objs = sort_objects(self.objects, sort_by="magnitude", reverse=False)
        magnitudes = [obj.magnitude for obj, _ in sorted_objs]
        self.assertEqual(magnitudes, [-2.0, 0.03, 3.4])

    def test_sort_by_magnitude_descending(self):
        """Test sorting by magnitude (descending, fainter first)"""
        sorted_objs = sort_objects(self.objects, sort_by="magnitude", reverse=True)
        magnitudes = [obj.magnitude for obj, _ in sorted_objs]
        self.assertEqual(magnitudes, [3.4, 0.03, -2.0])

    def test_sort_by_name(self):
        """Test sorting by name alphabetically"""
        sorted_objs = sort_objects(self.objects, sort_by="name", reverse=False)
        names = [obj.name for obj, _ in sorted_objs]
        self.assertEqual(names, ["Jupiter", "M31", "Vega"])

    def test_sort_by_type(self):
        """Test sorting by type, then by name"""
        sorted_objs = sort_objects(self.objects, sort_by="type", reverse=False)
        types = [obj.object_type.value for obj, _ in sorted_objs]
        # Should be sorted by type value, then name
        self.assertEqual(types, ["galaxy", "planet", "star"])

    def test_sort_empty_list(self):
        """Test sorting empty list"""
        sorted_objs = sort_objects([], sort_by="altitude")
        self.assertEqual(len(sorted_objs), 0)

    def test_sort_with_none_altitude(self):
        """Test sorting with None altitude values"""
        vis_none = VisibilityInfo(
            object_name="Unknown",
            altitude_deg=None,
            azimuth_deg=180.0,
            magnitude=5.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.5,
            reasons=("Unknown altitude",),
        )
        obj_none = CelestialObject(
            name="Unknown",
            common_name=None,
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=5.0,
            object_type=CelestialObjectType.STAR,
            catalog="test",
        )
        objects_with_none = self.objects + [(obj_none, vis_none)]

        sorted_objs = sort_objects(objects_with_none, sort_by="altitude", reverse=False)
        # None altitude should be at the beginning (sorted as -999)
        self.assertEqual(sorted_objs[0][0].name, "Unknown")


class TestFilterAndSortObjects(unittest.TestCase):
    """Test suite for filter_and_sort_objects function"""

    def setUp(self):
        """Set up test fixtures"""
        self.obj1 = CelestialObject(
            name="Vega",
            common_name="Vega",
            ra_hours=18.615,
            dec_degrees=38.784,
            magnitude=0.03,
            object_type=CelestialObjectType.STAR,
            catalog="bright_stars",
        )
        self.obj2 = CelestialObject(
            name="M31",
            common_name="Andromeda Galaxy",
            ra_hours=0.711,
            dec_degrees=41.269,
            magnitude=3.4,
            object_type=CelestialObjectType.GALAXY,
            catalog="messier",
        )
        self.obj3 = CelestialObject(
            name="Jupiter",
            common_name="Jupiter",
            ra_hours=10.0,
            dec_degrees=20.0,
            magnitude=-2.0,
            object_type=CelestialObjectType.PLANET,
            catalog="planets",
        )

        self.vis1 = VisibilityInfo(
            object_name="Vega",
            altitude_deg=30.0,
            azimuth_deg=180.0,
            magnitude=0.03,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.7,
            reasons=("Moderate altitude",),
        )
        self.vis2 = VisibilityInfo(
            object_name="M31",
            altitude_deg=60.0,
            azimuth_deg=90.0,
            magnitude=3.4,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.9,
            reasons=("High altitude",),
        )
        self.vis3 = VisibilityInfo(
            object_name="Jupiter",
            altitude_deg=45.0,
            azimuth_deg=270.0,
            magnitude=-2.0,
            limiting_magnitude=6.5,
            is_visible=True,
            observability_score=0.8,
            reasons=("Good altitude",),
        )

        self.objects = [
            (self.obj1, self.vis1),
            (self.obj2, self.vis2),
            (self.obj3, self.vis3),
        ]

    def test_filter_and_sort(self):
        """Test filtering and sorting together"""
        result = filter_and_sort_objects(
            self.objects, search_query="Vega", sort_by="altitude", sort_reverse=True
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].name, "Vega")

    def test_filter_and_sort_with_limit(self):
        """Test filtering, sorting, and limiting"""
        result = filter_and_sort_objects(
            self.objects, sort_by="altitude", sort_reverse=True, limit=2
        )
        self.assertEqual(len(result), 2)
        # Should be sorted by altitude descending
        self.assertEqual(result[0][1].altitude_deg, 60.0)
        self.assertEqual(result[1][1].altitude_deg, 45.0)

    def test_limit_zero(self):
        """Test that limit=0 returns empty list"""
        result = filter_and_sort_objects(self.objects, limit=0)
        self.assertEqual(len(result), 0)

    def test_limit_none(self):
        """Test that limit=None returns all objects"""
        result = filter_and_sort_objects(self.objects, limit=None)
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
