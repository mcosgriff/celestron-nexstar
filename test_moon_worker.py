#!/usr/bin/env python3
"""
Test script for MoonDataWorker

Tests the moon data calculation worker with sample month data.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtCore import QCoreApplication

from celestron_nexstar.api.location.observer import ObserverLocation
from celestron_nexstar.gui.workers.moon_workers import MoonDataWorker


def test_moon_worker():
    """Test the MoonDataWorker with sample data."""
    app = QCoreApplication(sys.argv)

    # Create sample observer location (Los Angeles)
    location = ObserverLocation(
        latitude=34.0522,
        longitude=-118.2437,
        elevation=285,  # Feet above sea level
        name="Los Angeles",
    )

    # Test for January 2025
    year = 2025
    month = 1

    print(f"\n{'='*80}")
    print(f"Testing MoonDataWorker for {year}-{month:02d}")
    print(f"Location: {location.name} ({location.latitude}°, {location.longitude}°)")
    print(f"{'='*80}\n")

    # Create worker
    worker = MoonDataWorker(year, month, location, months_ahead=3)

    # Track completion
    completed = False
    moon_data_result = None
    phase_events_result = None

    def on_data_ready(moon_data, phase_events):
        """Handle data ready signal."""
        nonlocal completed, moon_data_result, phase_events_result
        moon_data_result = moon_data
        phase_events_result = phase_events
        completed = True
        app.quit()

    def on_error(error_msg):
        """Handle error signal."""
        print(f"\n❌ ERROR: {error_msg}\n")
        app.quit()

    def on_progress(current, total):
        """Handle progress signal."""
        percent = (current / total) * 100
        print(f"Progress: {current}/{total} days ({percent:.1f}%)")

    # Connect signals
    worker.data_ready.connect(on_data_ready)
    worker.error_occurred.connect(on_error)
    worker.progress_updated.connect(on_progress)

    # Start worker
    print("Starting worker thread...")
    worker.start()

    # Run event loop
    app.exec()

    # Display results
    if completed and moon_data_result and phase_events_result:
        print(f"\n{'='*80}")
        print("RESULTS")
        print(f"{'='*80}\n")

        print(f"✓ Calculated moon data for {len(moon_data_result)} days")
        print(f"✓ Found {len(phase_events_result)} major phase events\n")

        # Show sample days
        print("Sample Moon Data (first 5 days):")
        print(f"{'Date':<12} {'Phase':<20} {'Illum %':<10} {'Distance (km)':<15} {'Major':<8}")
        print("-" * 80)

        for i, (date_str, day_data) in enumerate(sorted(moon_data_result.items())[:5]):
            print(
                f"{date_str:<12} "
                f"{day_data.phase_name.value:<20} "
                f"{day_data.illumination*100:>6.1f}%   "
                f"{day_data.distance_km:>10.0f} km   "
                f"{'✓' if day_data.is_major_phase else ' ':<8}"
            )

        # Show major phase events
        print(f"\nMajor Phase Events (showing first 10 of {len(phase_events_result)}):")
        print(
            f"{'Date':<12} {'Phase':<20} {'Traditional Name':<25} "
            f"{'Supermoon':<12} {'Blue Moon':<10}"
        )
        print("-" * 90)

        for event in phase_events_result[:10]:
            supermoon = "🌕 Yes" if event.is_supermoon else ""
            blue_moon = "🔵 Yes" if event.is_blue_moon else ""
            traditional = event.traditional_name or ""

            print(
                f"{event.date.strftime('%Y-%m-%d'):<12} "
                f"{event.phase.value:<20} "
                f"{traditional:<25} "
                f"{supermoon:<12} "
                f"{blue_moon:<10}"
            )

        # Summary statistics
        full_moons = sum(1 for e in phase_events_result if e.phase.value == "Full Moon")
        new_moons = sum(1 for e in phase_events_result if e.phase.value == "New Moon")
        supermoons = sum(1 for e in phase_events_result if e.is_supermoon)
        blue_moons = sum(1 for e in phase_events_result if e.is_blue_moon)

        print(f"\n{'='*80}")
        print("SUMMARY STATISTICS")
        print(f"{'='*80}")
        print(f"  Full Moons: {full_moons}")
        print(f"  New Moons: {new_moons}")
        print(f"  Supermoons: {supermoons}")
        print(f"  Blue Moons: {blue_moons}")
        print(f"{'='*80}\n")

        # Find any traditional names
        named_moons = [
            e for e in phase_events_result if e.traditional_name and e.traditional_name != "Blue Moon"
        ]
        if named_moons:
            print("Traditional Full Moon Names:")
            for event in named_moons:
                print(f"  - {event.date.strftime('%Y-%m-%d')}: {event.traditional_name}")
            print()

        return True
    else:
        print("\n❌ Worker did not complete successfully\n")
        return False


if __name__ == "__main__":
    try:
        success = test_moon_worker()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
