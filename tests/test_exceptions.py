"""
Unit tests for exceptions module.

Tests all custom exception classes used throughout the API.
"""

import unittest

from celestron_nexstar.api.exceptions import (
    CommandError,
    InvalidCoordinateError,
    NexStarError,
    NotConnectedError,
    TelescopeConnectionError,
    TelescopeTimeoutError,
)


class TestNexStarError(unittest.TestCase):
    """Test suite for NexStarError base exception"""

    def test_nexstar_error_is_exception(self):
        """Test that NexStarError is an Exception"""
        self.assertTrue(issubclass(NexStarError, Exception))

    def test_nexstar_error_instantiation(self):
        """Test creating a NexStarError instance"""
        error = NexStarError("Test error message")
        self.assertEqual(str(error), "Test error message")
        self.assertIsInstance(error, Exception)

    def test_nexstar_error_with_no_message(self):
        """Test creating a NexStarError with no message"""
        error = NexStarError()
        self.assertEqual(str(error), "")


class TestTelescopeConnectionError(unittest.TestCase):
    """Test suite for TelescopeConnectionError"""

    def test_inherits_from_nexstar_error(self):
        """Test that TelescopeConnectionError inherits from NexStarError"""
        self.assertTrue(issubclass(TelescopeConnectionError, NexStarError))

    def test_instantiation(self):
        """Test creating a TelescopeConnectionError instance"""
        error = TelescopeConnectionError("Connection failed")
        self.assertEqual(str(error), "Connection failed")
        self.assertIsInstance(error, NexStarError)
        self.assertIsInstance(error, Exception)

    def test_with_detailed_message(self):
        """Test TelescopeConnectionError with detailed message"""
        error = TelescopeConnectionError("Port /dev/ttyUSB0 not found")
        self.assertEqual(str(error), "Port /dev/ttyUSB0 not found")


class TestTelescopeTimeoutError(unittest.TestCase):
    """Test suite for TelescopeTimeoutError"""

    def test_inherits_from_nexstar_error(self):
        """Test that TelescopeTimeoutError inherits from NexStarError"""
        self.assertTrue(issubclass(TelescopeTimeoutError, NexStarError))

    def test_instantiation(self):
        """Test creating a TelescopeTimeoutError instance"""
        error = TelescopeTimeoutError("Command timed out")
        self.assertEqual(str(error), "Command timed out")
        self.assertIsInstance(error, NexStarError)
        self.assertIsInstance(error, Exception)

    def test_with_timeout_duration(self):
        """Test TelescopeTimeoutError with timeout duration"""
        error = TelescopeTimeoutError("No response after 2.0 seconds")
        self.assertEqual(str(error), "No response after 2.0 seconds")


class TestInvalidCoordinateError(unittest.TestCase):
    """Test suite for InvalidCoordinateError"""

    def test_inherits_from_nexstar_error(self):
        """Test that InvalidCoordinateError inherits from NexStarError"""
        self.assertTrue(issubclass(InvalidCoordinateError, NexStarError))

    def test_instantiation(self):
        """Test creating an InvalidCoordinateError instance"""
        error = InvalidCoordinateError("RA out of range")
        self.assertEqual(str(error), "RA out of range")
        self.assertIsInstance(error, NexStarError)
        self.assertIsInstance(error, Exception)

    def test_with_coordinate_details(self):
        """Test InvalidCoordinateError with coordinate details"""
        error = InvalidCoordinateError("RA must be between 0 and 24 hours")
        self.assertEqual(str(error), "RA must be between 0 and 24 hours")


class TestCommandError(unittest.TestCase):
    """Test suite for CommandError"""

    def test_inherits_from_nexstar_error(self):
        """Test that CommandError inherits from NexStarError"""
        self.assertTrue(issubclass(CommandError, NexStarError))

    def test_instantiation(self):
        """Test creating a CommandError instance"""
        error = CommandError("Invalid command response")
        self.assertEqual(str(error), "Invalid command response")
        self.assertIsInstance(error, NexStarError)
        self.assertIsInstance(error, Exception)

    def test_with_command_details(self):
        """Test CommandError with command details"""
        error = CommandError("Command 'K' returned unexpected value")
        self.assertEqual(str(error), "Command 'K' returned unexpected value")


class TestNotConnectedError(unittest.TestCase):
    """Test suite for NotConnectedError"""

    def test_inherits_from_nexstar_error(self):
        """Test that NotConnectedError inherits from NexStarError"""
        self.assertTrue(issubclass(NotConnectedError, NexStarError))

    def test_instantiation(self):
        """Test creating a NotConnectedError instance"""
        error = NotConnectedError("Telescope not connected")
        self.assertEqual(str(error), "Telescope not connected")
        self.assertIsInstance(error, NexStarError)
        self.assertIsInstance(error, Exception)

    def test_default_message(self):
        """Test NotConnectedError with default message"""
        error = NotConnectedError()
        self.assertEqual(str(error), "")


class TestExceptionHierarchy(unittest.TestCase):
    """Test exception hierarchy and inheritance"""

    def test_all_exceptions_inherit_from_nexstar_error(self):
        """Test that all custom exceptions inherit from NexStarError"""
        exceptions = [
            TelescopeConnectionError,
            TelescopeTimeoutError,
            InvalidCoordinateError,
            CommandError,
            NotConnectedError,
        ]

        for exc_class in exceptions:
            with self.subTest(exc_class=exc_class):
                self.assertTrue(issubclass(exc_class, NexStarError))
                self.assertTrue(issubclass(exc_class, Exception))

    def test_exception_catching(self):
        """Test that catching NexStarError catches all subclasses"""
        exceptions = [
            TelescopeConnectionError("Connection failed"),
            TelescopeTimeoutError("Timeout"),
            InvalidCoordinateError("Invalid coord"),
            CommandError("Command failed"),
            NotConnectedError("Not connected"),
        ]

        for exc in exceptions:
            with self.subTest(exc=exc):
                try:
                    raise exc
                except NexStarError:
                    # Should catch all subclasses
                    pass
                except Exception:
                    self.fail(f"{type(exc).__name__} should be caught by NexStarError")

    def test_exception_attributes(self):
        """Test that exceptions preserve message attributes"""
        message = "Custom error message"
        error = TelescopeConnectionError(message)
        self.assertEqual(error.args[0], message)
        self.assertEqual(str(error), message)


if __name__ == "__main__":
    unittest.main()
