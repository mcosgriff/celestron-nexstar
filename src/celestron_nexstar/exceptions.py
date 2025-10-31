"""
Custom exception classes for Celestron NexStar telescope control.

This module defines specific exceptions for different types of errors
that can occur during telescope operations.
"""


class NexStarError(Exception):
    """
    Base exception for all NexStar telescope errors.

    All custom exceptions in this library inherit from this base class,
    making it easy to catch all telescope-related errors.
    """

    pass


class TelescopeConnectionError(NexStarError):
    """
    Raised when connection to the telescope fails.

    This can occur when:
    - Serial port cannot be opened
    - Port does not exist
    - Port is already in use by another application
    - USB cable is disconnected
    """

    pass


class TelescopeTimeoutError(NexStarError):
    """
    Raised when a telescope command times out.

    This indicates the telescope did not respond within the expected
    time window, which may mean:
    - Telescope is not powered on
    - Communication cable is faulty
    - Telescope is busy with another operation
    """

    pass


class InvalidCoordinateError(NexStarError):
    """
    Raised when coordinates are out of valid range.

    This occurs when attempting to use coordinates that are:
    - RA outside 0-24 hours range
    - Dec outside -90 to +90 degrees range
    - Azimuth outside 0-360 degrees range
    - Altitude outside -90 to +90 degrees range
    """

    pass


class CommandError(NexStarError):
    """
    Raised when a telescope command fails or returns an unexpected response.

    This can occur when:
    - Command returns invalid data format
    - Telescope reports an error condition
    - Response cannot be parsed
    """

    pass


class NotConnectedError(NexStarError):
    """
    Raised when attempting to send commands while not connected.

    This occurs when trying to control the telescope before calling
    connect() or after disconnect().
    """

    pass
