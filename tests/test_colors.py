"""
Unit tests for observation/colors.py

Tests color mapping functions for observing conditions.
"""

import unittest

from celestron_nexstar.api.observation.colors import (
    get_darkness_color,
    get_humidity_color,
    get_temperature_color,
    get_wind_color,
)


class TestGetDarknessColor(unittest.TestCase):
    """Test suite for get_darkness_color function"""

    def test_none_returns_daytime(self):
        """Test that None magnitude returns daytime color"""
        color, label = get_darkness_color(None)
        self.assertEqual(color, "white")
        self.assertEqual(label, "Day")

    def test_very_dark_sky(self):
        """Test very dark sky (magnitude >= 6.5)"""
        color, label = get_darkness_color(6.5)
        self.assertEqual(color, "#000000")
        self.assertEqual(label, "6.5")

    def test_dark_sky_6_0(self):
        """Test dark sky (magnitude 6.0)"""
        color, label = get_darkness_color(6.0)
        self.assertEqual(color, "#000010")
        self.assertEqual(label, "6.0")

    def test_moderate_darkness(self):
        """Test moderate darkness (magnitude 4.0)"""
        color, label = get_darkness_color(4.0)
        self.assertEqual(color, "#000080")
        self.assertEqual(label, "4.0")

    def test_bright_sky(self):
        """Test bright sky (magnitude 0.0)"""
        color, label = get_darkness_color(0.0)
        self.assertEqual(color, "#40E0E0")
        self.assertEqual(label, "0")

    def test_very_bright_sky(self):
        """Test very bright sky (magnitude -4.0)"""
        color, label = get_darkness_color(-4.0)
        self.assertEqual(color, "#FFFFC0")
        self.assertEqual(label, "-4")

    def test_extremely_bright_sky(self):
        """Test extremely bright sky (magnitude < -4.0)"""
        color, label = get_darkness_color(-5.0)
        self.assertEqual(color, "white")
        self.assertEqual(label, "Day")


class TestGetWindColor(unittest.TestCase):
    """Test suite for get_wind_color function"""

    def test_none_returns_dim(self):
        """Test that None wind returns dim color"""
        color, label = get_wind_color(None)
        self.assertEqual(color, "dim")
        self.assertEqual(label, "-")

    def test_calm_wind(self):
        """Test calm wind (< 6 mph)"""
        color, label = get_wind_color(5.0)
        self.assertEqual(color, "#004080")
        self.assertEqual(label, "0-5 mph")

    def test_light_wind(self):
        """Test light wind (6-11 mph)"""
        color, label = get_wind_color(8.0)
        self.assertEqual(color, "#2060A0")
        self.assertEqual(label, "6-11 mph")

    def test_moderate_wind(self):
        """Test moderate wind (12-16 mph)"""
        color, label = get_wind_color(14.0)
        self.assertEqual(color, "#4080C0")
        self.assertEqual(label, "12-16 mph")

    def test_strong_wind(self):
        """Test strong wind (17-28 mph)"""
        color, label = get_wind_color(20.0)
        self.assertEqual(color, "#80C0E0")
        self.assertEqual(label, "17-28 mph")

    def test_very_strong_wind(self):
        """Test very strong wind (29-45 mph)"""
        color, label = get_wind_color(35.0)
        self.assertEqual(color, "#E0E0E0")
        self.assertEqual(label, "29-45 mph")

    def test_extreme_wind(self):
        """Test extreme wind (> 45 mph)"""
        color, label = get_wind_color(50.0)
        self.assertEqual(color, "white")
        self.assertEqual(label, ">45 mph")


class TestGetHumidityColor(unittest.TestCase):
    """Test suite for get_humidity_color function"""

    def test_none_returns_dim(self):
        """Test that None humidity returns dim color"""
        color, label = get_humidity_color(None)
        self.assertEqual(color, "dim")
        self.assertEqual(label, "-")

    def test_very_low_humidity(self):
        """Test very low humidity (< 25%)"""
        color, label = get_humidity_color(20.0)
        self.assertEqual(color, "#0000FF")
        self.assertEqual(label, "<25%")

    def test_low_humidity(self):
        """Test low humidity (25-30%)"""
        color, label = get_humidity_color(27.0)
        self.assertEqual(color, "#0022FF")
        self.assertEqual(label, "25-30%")

    def test_moderate_humidity(self):
        """Test moderate humidity (50-55%)"""
        color, label = get_humidity_color(52.0)
        self.assertEqual(color, "#00FFFF")
        self.assertEqual(label, "50-55%")

    def test_high_humidity(self):
        """Test high humidity (70-75%)"""
        color, label = get_humidity_color(72.0)
        self.assertEqual(color, "#FFFF00")
        self.assertEqual(label, "70-75%")

    def test_very_high_humidity(self):
        """Test very high humidity (85-90%)"""
        color, label = get_humidity_color(87.0)
        self.assertEqual(color, "#FF0000")
        self.assertEqual(label, "85-90%")

    def test_extreme_humidity(self):
        """Test extreme humidity (95-100%)"""
        color, label = get_humidity_color(98.0)
        self.assertEqual(color, "#800000")
        self.assertEqual(label, "95-100%")


class TestGetTemperatureColor(unittest.TestCase):
    """Test suite for get_temperature_color function"""

    def test_none_returns_dim(self):
        """Test that None temperature returns dim color"""
        color, label = get_temperature_color(None)
        self.assertEqual(color, "dim")
        self.assertEqual(label, "-")

    def test_extreme_cold(self):
        """Test extreme cold (< -40°F)"""
        color, label = get_temperature_color(-50.0)
        self.assertEqual(color, "#FF00FF")
        self.assertEqual(label, "< -40°F")

    def test_very_cold(self):
        """Test very cold (-30 to -21°F)"""
        color, label = get_temperature_color(-25.0)
        self.assertEqual(color, "#0022FF")
        self.assertEqual(label, "-30--21°F")

    def test_cold(self):
        """Test cold (14-23°F)"""
        color, label = get_temperature_color(18.0)
        self.assertEqual(color, "#00FFAA")
        self.assertEqual(label, "14-23°F")

    def test_moderate(self):
        """Test moderate temperature (50-59°F)"""
        color, label = get_temperature_color(55.0)
        self.assertEqual(color, "#FFFF00")
        self.assertEqual(label, "50-59°F")

    def test_warm(self):
        """Test warm temperature (68-77°F)"""
        color, label = get_temperature_color(72.0)
        self.assertEqual(color, "#FF8800")
        self.assertEqual(label, "68-77°F")

    def test_hot(self):
        """Test hot temperature (86-95°F)"""
        color, label = get_temperature_color(90.0)
        self.assertEqual(color, "#FF0000")
        self.assertEqual(label, "86-95°F")

    def test_extreme_heat(self):
        """Test extreme heat (> 113°F)"""
        color, label = get_temperature_color(120.0)
        self.assertEqual(color, "#808080")
        self.assertEqual(label, ">113°F")


class TestGetDarknessColorEdgeCases(unittest.TestCase):
    """Test suite for edge cases in get_darkness_color function"""

    def test_boundary_values(self):
        """Test boundary values between ranges"""
        # Test exact boundary values
        color_6_5, _ = get_darkness_color(6.5)
        color_6_0, _ = get_darkness_color(6.0)
        color_5_5, _ = get_darkness_color(5.5)
        color_5_0, _ = get_darkness_color(5.0)
        color_4_5, _ = get_darkness_color(4.5)
        color_4_0, _ = get_darkness_color(4.0)
        color_3_5, _ = get_darkness_color(3.5)
        color_3_0, _ = get_darkness_color(3.0)
        color_2_0, _ = get_darkness_color(2.0)
        color_1_0, _ = get_darkness_color(1.0)
        color_0_0, _ = get_darkness_color(0.0)
        color_neg1, _ = get_darkness_color(-1.0)
        color_neg2, _ = get_darkness_color(-2.0)
        color_neg3, _ = get_darkness_color(-3.0)
        color_neg4, _ = get_darkness_color(-4.0)

        # Verify all return valid colors
        self.assertIsInstance(color_6_5, str)
        self.assertIsInstance(color_6_0, str)
        self.assertIsInstance(color_5_5, str)
        self.assertIsInstance(color_5_0, str)
        self.assertIsInstance(color_4_5, str)
        self.assertIsInstance(color_4_0, str)
        self.assertIsInstance(color_3_5, str)
        self.assertIsInstance(color_3_0, str)
        self.assertIsInstance(color_2_0, str)
        self.assertIsInstance(color_1_0, str)
        self.assertIsInstance(color_0_0, str)
        self.assertIsInstance(color_neg1, str)
        self.assertIsInstance(color_neg2, str)
        self.assertIsInstance(color_neg3, str)
        self.assertIsInstance(color_neg4, str)

    def test_values_between_boundaries(self):
        """Test values between boundaries"""
        # Test values between boundaries
        color_6_25, _ = get_darkness_color(6.25)  # Between 6.0 and 6.5
        color_5_25, _ = get_darkness_color(5.25)  # Between 5.0 and 5.5
        color_3_25, _ = get_darkness_color(3.25)  # Between 3.0 and 3.5
        color_1_5, _ = get_darkness_color(1.5)  # Between 1.0 and 2.0
        color_neg0_5, _ = get_darkness_color(-0.5)  # Between 0.0 and -1.0
        color_neg2_5, _ = get_darkness_color(-2.5)  # Between -2.0 and -3.0

        # Verify all return valid colors
        self.assertIsInstance(color_6_25, str)
        self.assertIsInstance(color_5_25, str)
        self.assertIsInstance(color_3_25, str)
        self.assertIsInstance(color_1_5, str)
        self.assertIsInstance(color_neg0_5, str)
        self.assertIsInstance(color_neg2_5, str)


class TestGetWindColorEdgeCases(unittest.TestCase):
    """Test suite for edge cases in get_wind_color function"""

    def test_boundary_values(self):
        """Test boundary values between ranges"""
        # Test exact boundary values
        color_45, _ = get_wind_color(45.0)
        color_29, _ = get_wind_color(29.0)
        color_17, _ = get_wind_color(17.0)
        color_12, _ = get_wind_color(12.0)
        color_6, _ = get_wind_color(6.0)
        color_0, _ = get_wind_color(0.0)

        # Verify all return valid colors
        self.assertIsInstance(color_45, str)
        self.assertIsInstance(color_29, str)
        self.assertIsInstance(color_17, str)
        self.assertIsInstance(color_12, str)
        self.assertIsInstance(color_6, str)
        self.assertIsInstance(color_0, str)

    def test_values_between_boundaries(self):
        """Test values between boundaries"""
        color_37, _ = get_wind_color(37.0)  # Between 29 and 45
        color_22, _ = get_wind_color(22.0)  # Between 17 and 29
        color_14, _ = get_wind_color(14.0)  # Between 12 and 17
        color_8, _ = get_wind_color(8.0)  # Between 6 and 12
        color_3, _ = get_wind_color(3.0)  # Between 0 and 6

        # Verify all return valid colors
        self.assertIsInstance(color_37, str)
        self.assertIsInstance(color_22, str)
        self.assertIsInstance(color_14, str)
        self.assertIsInstance(color_8, str)
        self.assertIsInstance(color_3, str)


class TestGetHumidityColorEdgeCases(unittest.TestCase):
    """Test suite for edge cases in get_humidity_color function"""

    def test_boundary_values(self):
        """Test boundary values between ranges"""
        # Test exact boundary values
        color_95, _ = get_humidity_color(95.0)
        color_90, _ = get_humidity_color(90.0)
        color_85, _ = get_humidity_color(85.0)
        color_80, _ = get_humidity_color(80.0)
        color_75, _ = get_humidity_color(75.0)
        color_70, _ = get_humidity_color(70.0)
        color_65, _ = get_humidity_color(65.0)
        color_60, _ = get_humidity_color(60.0)
        color_55, _ = get_humidity_color(55.0)
        color_50, _ = get_humidity_color(50.0)
        color_45, _ = get_humidity_color(45.0)
        color_40, _ = get_humidity_color(40.0)
        color_35, _ = get_humidity_color(35.0)
        color_30, _ = get_humidity_color(30.0)
        color_25, _ = get_humidity_color(25.0)

        # Verify all return valid colors
        self.assertIsInstance(color_95, str)
        self.assertIsInstance(color_90, str)
        self.assertIsInstance(color_85, str)
        self.assertIsInstance(color_80, str)
        self.assertIsInstance(color_75, str)
        self.assertIsInstance(color_70, str)
        self.assertIsInstance(color_65, str)
        self.assertIsInstance(color_60, str)
        self.assertIsInstance(color_55, str)
        self.assertIsInstance(color_50, str)
        self.assertIsInstance(color_45, str)
        self.assertIsInstance(color_40, str)
        self.assertIsInstance(color_35, str)
        self.assertIsInstance(color_30, str)
        self.assertIsInstance(color_25, str)

    def test_values_between_boundaries(self):
        """Test values between boundaries"""
        color_92, _ = get_humidity_color(92.0)  # Between 90 and 95
        color_87, _ = get_humidity_color(87.0)  # Between 85 and 90
        color_77, _ = get_humidity_color(77.0)  # Between 75 and 80
        color_52, _ = get_humidity_color(52.0)  # Between 50 and 55
        color_37, _ = get_humidity_color(37.0)  # Between 35 and 40
        color_27, _ = get_humidity_color(27.0)  # Between 25 and 30

        # Verify all return valid colors
        self.assertIsInstance(color_92, str)
        self.assertIsInstance(color_87, str)
        self.assertIsInstance(color_77, str)
        self.assertIsInstance(color_52, str)
        self.assertIsInstance(color_37, str)
        self.assertIsInstance(color_27, str)


class TestGetTemperatureColorEdgeCases(unittest.TestCase):
    """Test suite for edge cases in get_temperature_color function"""

    def test_boundary_values(self):
        """Test boundary values between ranges"""
        # Test exact boundary values
        color_113, _ = get_temperature_color(113.0)
        color_104, _ = get_temperature_color(104.0)
        color_95, _ = get_temperature_color(95.0)
        color_86, _ = get_temperature_color(86.0)
        color_77, _ = get_temperature_color(77.0)
        color_68, _ = get_temperature_color(68.0)
        color_59, _ = get_temperature_color(59.0)
        color_50, _ = get_temperature_color(50.0)
        color_41, _ = get_temperature_color(41.0)
        color_32, _ = get_temperature_color(32.0)
        color_23, _ = get_temperature_color(23.0)
        color_14, _ = get_temperature_color(14.0)
        color_5, _ = get_temperature_color(5.0)
        color_neg3, _ = get_temperature_color(-3.0)
        color_neg12, _ = get_temperature_color(-12.0)
        color_neg21, _ = get_temperature_color(-21.0)
        color_neg30, _ = get_temperature_color(-30.0)
        color_neg40, _ = get_temperature_color(-40.0)

        # Verify all return valid colors
        self.assertIsInstance(color_113, str)
        self.assertIsInstance(color_104, str)
        self.assertIsInstance(color_95, str)
        self.assertIsInstance(color_86, str)
        self.assertIsInstance(color_77, str)
        self.assertIsInstance(color_68, str)
        self.assertIsInstance(color_59, str)
        self.assertIsInstance(color_50, str)
        self.assertIsInstance(color_41, str)
        self.assertIsInstance(color_32, str)
        self.assertIsInstance(color_23, str)
        self.assertIsInstance(color_14, str)
        self.assertIsInstance(color_5, str)
        self.assertIsInstance(color_neg3, str)
        self.assertIsInstance(color_neg12, str)
        self.assertIsInstance(color_neg21, str)
        self.assertIsInstance(color_neg30, str)
        self.assertIsInstance(color_neg40, str)

    def test_values_between_boundaries(self):
        """Test values between boundaries"""
        color_108, _ = get_temperature_color(108.0)  # Between 104 and 113
        color_99, _ = get_temperature_color(99.0)  # Between 95 and 104
        color_81, _ = get_temperature_color(81.0)  # Between 77 and 86
        color_72, _ = get_temperature_color(72.0)  # Between 68 and 77
        color_54, _ = get_temperature_color(54.0)  # Between 50 and 59
        color_45, _ = get_temperature_color(45.0)  # Between 41 and 50
        color_36, _ = get_temperature_color(36.0)  # Between 32 and 41
        color_28, _ = get_temperature_color(28.0)  # Between 23 and 32
        color_18, _ = get_temperature_color(18.0)  # Between 14 and 23
        color_9, _ = get_temperature_color(9.0)  # Between 5 and 14
        color_neg1, _ = get_temperature_color(-1.0)  # Between -3 and 5
        color_neg7, _ = get_temperature_color(-7.0)  # Between -12 and -3
        color_neg16, _ = get_temperature_color(-16.0)  # Between -21 and -12
        color_neg25, _ = get_temperature_color(-25.0)  # Between -30 and -21
        color_neg35, _ = get_temperature_color(-35.0)  # Between -40 and -30

        # Verify all return valid colors
        self.assertIsInstance(color_108, str)
        self.assertIsInstance(color_99, str)
        self.assertIsInstance(color_81, str)
        self.assertIsInstance(color_72, str)
        self.assertIsInstance(color_54, str)
        self.assertIsInstance(color_45, str)
        self.assertIsInstance(color_36, str)
        self.assertIsInstance(color_28, str)
        self.assertIsInstance(color_18, str)
        self.assertIsInstance(color_9, str)
        self.assertIsInstance(color_neg1, str)
        self.assertIsInstance(color_neg7, str)
        self.assertIsInstance(color_neg16, str)
        self.assertIsInstance(color_neg25, str)
        self.assertIsInstance(color_neg35, str)


if __name__ == "__main__":
    unittest.main()
