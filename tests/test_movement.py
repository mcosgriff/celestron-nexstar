"""
Unit tests for movement.py

Tests MovementController for interactive telescope control.
"""

import unittest
from unittest.mock import MagicMock, patch

from celestron_nexstar.api.telescope.movement import MovementController


class TestMovementController(unittest.TestCase):
    """Test suite for MovementController class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_get_port = MagicMock(return_value="/dev/ttyUSB0")
        self.controller = MovementController(self.mock_get_port)

    def test_initialization(self):
        """Test controller initialization"""
        self.assertEqual(self.controller.slew_rate, 5)
        self.assertIsNone(self.controller.active_direction)
        self.assertFalse(self.controller.moving)

    def test_get_rate(self):
        """Test getting slew rate"""
        self.assertEqual(self.controller.get_rate(), 5)

    def test_increase_rate(self):
        """Test increasing slew rate"""
        self.controller.increase_rate()
        self.assertEqual(self.controller.get_rate(), 6)
        # Test max rate
        self.controller.slew_rate = 9
        self.controller.increase_rate()
        self.assertEqual(self.controller.get_rate(), 9)  # Should not exceed 9

    def test_decrease_rate(self):
        """Test decreasing slew rate"""
        self.controller.decrease_rate()
        self.assertEqual(self.controller.get_rate(), 4)
        # Test min rate
        self.controller.slew_rate = 0
        self.controller.decrease_rate()
        self.assertEqual(self.controller.get_rate(), 0)  # Should not go below 0

    def test_is_moving(self):
        """Test checking if moving"""
        self.assertFalse(self.controller.is_moving())
        self.controller.moving = True
        self.assertTrue(self.controller.is_moving())

    def test_get_direction(self):
        """Test getting movement direction"""
        self.assertIsNone(self.controller.get_direction())
        self.controller.active_direction = "up"
        self.assertEqual(self.controller.get_direction(), "up")

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_start_move_success(self, mock_telescope_class):
        """Test starting movement successfully"""
        mock_telescope = MagicMock()
        mock_telescope.__enter__ = MagicMock(return_value=mock_telescope)
        mock_telescope.__exit__ = MagicMock(return_value=None)
        mock_telescope_class.return_value = mock_telescope

        self.controller.start_move("up")

        mock_telescope.move_fixed.assert_called_once_with("up", 5)
        self.assertTrue(self.controller.moving)
        self.assertEqual(self.controller.active_direction, "up")

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_start_move_same_direction(self, mock_telescope_class):
        """Test starting move when already moving in same direction"""
        self.controller.moving = True
        self.controller.active_direction = "up"

        self.controller.start_move("up")

        # Should not call telescope again
        mock_telescope_class.assert_not_called()

    def test_start_move_no_port(self):
        """Test starting move when no port available"""
        self.mock_get_port.return_value = None

        self.controller.start_move("up")

        self.assertFalse(self.controller.moving)

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_start_move_exception(self, mock_telescope_class):
        """Test starting move when exception occurs"""
        mock_telescope = MagicMock()
        mock_telescope.__enter__ = MagicMock(side_effect=Exception("Connection error"))
        mock_telescope.__exit__ = MagicMock(return_value=None)
        mock_telescope_class.return_value = mock_telescope

        # Should not raise exception
        self.controller.start_move("up")

        self.assertFalse(self.controller.moving)

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_stop_move_success(self, mock_telescope_class):
        """Test stopping movement successfully"""
        self.controller.moving = True
        self.controller.active_direction = "up"

        mock_telescope = MagicMock()
        mock_telescope.__enter__ = MagicMock(return_value=mock_telescope)
        mock_telescope.__exit__ = MagicMock(return_value=None)
        mock_telescope_class.return_value = mock_telescope

        self.controller.stop_move()

        mock_telescope.stop_motion.assert_called_once_with("both")
        self.assertFalse(self.controller.moving)
        self.assertIsNone(self.controller.active_direction)

    def test_stop_move_not_moving(self):
        """Test stopping when not moving"""
        self.controller.stop_move()
        # Should not raise exception
        self.assertFalse(self.controller.moving)

    def test_stop_move_no_port(self):
        """Test stopping when no port available"""
        self.controller.moving = True
        self.mock_get_port.return_value = None

        self.controller.stop_move()

        # Should still be marked as moving since we couldn't stop
        self.assertTrue(self.controller.moving)

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_stop_move_exception(self, mock_telescope_class):
        """Test stopping move when exception occurs"""
        self.controller.moving = True
        mock_telescope = MagicMock()
        mock_telescope.__enter__ = MagicMock(side_effect=Exception("Connection error"))
        mock_telescope.__exit__ = MagicMock(return_value=None)
        mock_telescope_class.return_value = mock_telescope

        # Should not raise exception
        self.controller.stop_move()

        # Should still be marked as moving since we couldn't stop
        self.assertTrue(self.controller.moving)

    @patch("celestron_nexstar.api.telescope.telescope.NexStarTelescope")
    def test_different_directions(self, mock_telescope_class):
        """Test moving in different directions"""
        mock_telescope = MagicMock()
        mock_telescope.__enter__ = MagicMock(return_value=mock_telescope)
        mock_telescope.__exit__ = MagicMock(return_value=None)
        mock_telescope_class.return_value = mock_telescope

        for direction in ["up", "down", "left", "right"]:
            self.controller.start_move(direction)
            mock_telescope.move_fixed.assert_called_with(direction, 5)
            self.assertEqual(self.controller.active_direction, direction)


if __name__ == "__main__":
    unittest.main()
