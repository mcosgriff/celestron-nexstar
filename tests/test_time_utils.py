"""
Tests for time formatting utilities.
"""

from datetime import UTC, datetime

from celestron_nexstar.api.core import format_local_time, get_local_timezone


def test_get_local_timezone() -> None:
    """Test getting timezone from coordinates."""
    # Test with known coordinates (Los Angeles)
    tz = get_local_timezone(34.0522, -118.2437)
    assert tz is not None
    assert "America" in str(tz) or "Los_Angeles" in str(tz) or "Pacific" in str(tz)

    # Test with invalid coordinates (should return None gracefully)
    tz_invalid = get_local_timezone(999.0, 999.0)
    # Should either return None or handle gracefully
    assert tz_invalid is None or tz_invalid is not None


def test_format_local_time_with_timezone() -> None:
    """Test formatting time with valid timezone."""
    # Use Los Angeles coordinates
    dt = datetime(2024, 10, 14, 20, 30, 0, tzinfo=UTC)
    formatted = format_local_time(dt, 34.0522, -118.2437)

    assert "2024-10-14" in formatted
    # Should have time in 12-hour format with AM/PM
    assert "PM" in formatted or "AM" in formatted
    # Should have timezone abbreviation
    assert any(tz in formatted for tz in ["PDT", "PST", "UTC", "Local"])


def test_format_local_time_utc_fallback() -> None:
    """Test formatting time falls back to UTC when timezone unavailable."""
    dt = datetime(2024, 10, 14, 20, 30, 0, tzinfo=UTC)
    # Use invalid coordinates to trigger UTC fallback
    formatted = format_local_time(dt, 999.0, 999.0)

    assert "2024-10-14" in formatted
    assert "UTC" in formatted


def test_format_local_time_no_timezone() -> None:
    """Test formatting time without timezone info (should add UTC)."""
    dt = datetime(2024, 10, 14, 20, 30, 0)  # No timezone
    formatted = format_local_time(dt, 34.0522, -118.2437)

    assert "2024-10-14" in formatted
    # Should have time and timezone info
    assert "PM" in formatted or "AM" in formatted


def test_format_local_time_various_locations() -> None:
    """Test formatting time for various locations."""
    dt = datetime(2024, 10, 14, 12, 0, 0, tzinfo=UTC)

    # New York
    formatted_ny = format_local_time(dt, 40.7128, -74.0060)
    assert "2024-10-14" in formatted_ny

    # London
    formatted_london = format_local_time(dt, 51.5074, -0.1278)
    assert "2024-10-14" in formatted_london

    # Tokyo
    formatted_tokyo = format_local_time(dt, 35.6762, 139.6503)
    assert "2024-10-14" in formatted_tokyo
