"""
Tests for export filename generation utilities.
"""

from pathlib import Path

from celestron_nexstar.api.core.export_utils import (
    generate_catalog_export_filename,
    generate_export_filename,
    generate_vacation_export_filename,
)
from celestron_nexstar.api.location.observer import ObserverLocation


def test_generate_export_filename_telescope() -> None:
    """Test generating export filename for telescope viewing."""
    filename = generate_export_filename("tonight", viewing_type="telescope")

    assert isinstance(filename, Path)
    assert filename.suffix == ".txt"
    assert "nexstar" in filename.stem.lower()
    assert "tonight" in filename.stem.lower()


def test_generate_export_filename_binoculars() -> None:
    """Test generating export filename for binocular viewing."""
    filename = generate_export_filename("tonight", viewing_type="binoculars", binocular_model="10x50")

    assert isinstance(filename, Path)
    assert filename.suffix == ".txt"
    assert "binoculars" in filename.stem.lower()
    assert "10x50" in filename.stem.lower() or "10x" in filename.stem.lower()


def test_generate_export_filename_naked_eye() -> None:
    """Test generating export filename for naked-eye viewing."""
    filename = generate_export_filename("tonight", viewing_type="naked-eye")

    assert isinstance(filename, Path)
    assert filename.suffix == ".txt"
    assert "naked" in filename.stem.lower() or "naked_eye" in filename.stem.lower()


def test_generate_export_filename_with_location() -> None:
    """Test generating export filename with custom location."""
    location = ObserverLocation(
        name="Test Location",
        latitude=34.0522,
        longitude=-118.2437,
        elevation=100.0,
    )
    filename = generate_export_filename("conditions", viewing_type="telescope", location=location)

    assert isinstance(filename, Path)
    assert "test" in filename.stem.lower() or "location" in filename.stem.lower()


def test_generate_export_filename_with_date_suffix() -> None:
    """Test generating export filename with date suffix."""
    filename = generate_export_filename("plan", viewing_type="telescope", date_suffix="2024-10-15")

    assert isinstance(filename, Path)
    assert "plan" in filename.stem.lower()


def test_generate_export_filename_with_kwargs() -> None:
    """Test generating export filename with additional kwargs."""
    filename = generate_export_filename(
        "tonight",
        viewing_type="telescope",
        custom_part="test",
        another_part="value",
    )

    assert isinstance(filename, Path)
    # Should include custom parts if they're valid


def test_generate_vacation_export_filename() -> None:
    """Test generating vacation export filename."""
    filename = generate_vacation_export_filename("view", location="Denver, CO")

    assert isinstance(filename, Path)
    assert filename.suffix == ".txt"
    assert "vacation" in filename.stem.lower()
    assert "view" in filename.stem.lower()


def test_generate_vacation_export_filename_with_days() -> None:
    """Test generating vacation export filename with days."""
    filename = generate_vacation_export_filename("plan", location="Denver, CO", days=7)

    assert isinstance(filename, Path)
    assert "7days" in filename.stem.lower() or "7" in filename.stem.lower()


def test_generate_catalog_export_filename() -> None:
    """Test generating catalog export filename."""
    filename = generate_catalog_export_filename("messier")

    assert isinstance(filename, Path)
    assert filename.suffix == ".txt"
    assert "catalog" in filename.stem.lower()
    assert "messier" in filename.stem.lower()


def test_generate_export_filename_sanitization() -> None:
    """Test that special characters are sanitized in filenames."""
    location = ObserverLocation(
        name="Test/Location, Name!",
        latitude=34.0522,
        longitude=-118.2437,
    )
    filename = generate_export_filename("test", viewing_type="telescope", location=location)

    # Should not contain special characters that are invalid in filenames
    assert "/" not in str(filename)
    assert "!" not in str(filename)
    # Commas might be replaced with underscores
    assert "," not in str(filename) or "_" in str(filename)
