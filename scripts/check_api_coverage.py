#!/usr/bin/env python3
"""
Check that the api package has 100% test coverage.

This script runs tests with coverage checking for the celestron_nexstar.api package
and ensures coverage is at 100%.

Uses coverage.py directly with unittest to avoid pytest collection issues
with astropy/deal imports.
"""

import subprocess
import sys
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).parent.parent


def main() -> int:
    """Run tests with coverage checking for the api package."""
    # Test files to run (excluding test_utils.py due to astropy import issues)
    test_files = [
        "tests.test_constants",
        "tests.test_enums",
        "tests.test_exceptions",
        "tests.test_types",
        "tests.test_converters",
        "tests.test_geohash_utils",
        "tests.test_nexstar_protocol",
    ]

    # Modules we're checking coverage for (excluding utils.py due to astropy issue)
    modules_to_check = [
        "celestron_nexstar.api.constants",
        "celestron_nexstar.api.enums",
        "celestron_nexstar.api.exceptions",
        "celestron_nexstar.api.types",
        "celestron_nexstar.api.converters",
        "celestron_nexstar.api.geohash_utils",
        "celestron_nexstar.api.protocol",
    ]

    # Use coverage run with unittest to avoid pytest collection issues
    cmd = [
        "uv",
        "run",
        "coverage",
        "run",
        "--source",
        ",".join(modules_to_check),
        "-m",
        "unittest",
        *test_files,
    ]

    print("Running tests with coverage check for celestron_nexstar.api modules...")
    print(f"Command: {' '.join(cmd)}")
    print()
    print("Note: utils.py is excluded from this check due to astropy import issues with deal.")
    print("Once the astropy/deal compatibility issue is resolved, utils.py will be included.")
    print()

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print("\n❌ Tests failed!")
        return 1

    # Now check coverage
    report_cmd = [
        "uv",
        "run",
        "coverage",
        "report",
        "--show-missing",
        "--skip-covered",
        "--fail-under=100",
    ]

    print("\nChecking coverage...")
    result = subprocess.run(report_cmd, cwd=project_root)

    if result.returncode != 0:
        print("\n❌ Coverage check failed!")
        print("The tested api package modules must have 100% test coverage.")
        return 1

    print("\n✅ Coverage check passed!")
    print("All tested api package modules have 100% test coverage.")
    return 0

    if result.returncode != 0:
        print("\n❌ Coverage check failed!")
        print("The tested api package modules must have 100% test coverage.")
        return 1

    print("\n✅ Coverage check passed!")
    print("All tested api package modules have 100% test coverage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
