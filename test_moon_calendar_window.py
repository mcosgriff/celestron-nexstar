#!/usr/bin/env python3
"""
Test script for Moon Calendar Window

Tests the complete moon calendar window with all features.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtWidgets import QApplication

from celestron_nexstar.gui.windows.moon_calendar_window import MoonCalendarWindow


def main():
    """Run test."""
    app = QApplication(sys.argv)

    print("=" * 80)
    print("Moon Calendar Window Test")
    print("=" * 80)
    print()
    print("Features to test:")
    print("  ✓ Month navigation (Previous/Next/Today buttons)")
    print("  ✓ Date picker for jumping to specific months")
    print("  ✓ Calendar grid showing moon phases")
    print("  ✓ Phase timeline with filtering")
    print("  ✓ Click calendar cells to open Moon Info Dialog")
    print("  ✓ Click timeline rows to open Moon Info Dialog")
    print("  ✓ Special events (supermoons, blue moons)")
    print("  ✓ Traditional moon names")
    print()
    print("=" * 80)

    window = MoonCalendarWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
