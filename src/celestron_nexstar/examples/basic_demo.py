"""
Basic demonstration of Celestron NexStar telescope control

This script demonstrates basic telescope operations including:
- Connecting to the telescope
- Getting current position
- Getting telescope information
- Basic movement commands
"""

import time
from celestron_nexstar import NexStarTelescope, TrackingMode


def main():
    """Main demo function"""
    print("=== Celestron NexStar 6SE Basic Demo ===\n")

    # Create telescope instance
    # Update port for your system:
    # - macOS: /dev/tty.usbserial-XXXXX
    # - Linux: /dev/ttyUSB0
    # - Windows: COM3
    telescope = NexStarTelescope(port='/dev/tty.usbserial-1420', baudrate=9600)

    try:
        # Connect to telescope
        print("Connecting to telescope...")
        if not telescope.connect():
            print("Failed to connect! Check port and connection.")
            return 1

        # Get telescope information
        version = telescope.get_version()
        print(f"Firmware Version: {version[0]}.{version[1]}")

        model = telescope.get_model()
        print(f"Model Number: {model}")

        # Get current position
        ra, dec = telescope.get_position_ra_dec()
        print(f"\nCurrent Position (RA/Dec):")
        print(f"  RA: {ra:.4f} hours")
        print(f"  Dec: {dec:.4f}°")

        az, alt = telescope.get_position_alt_az()
        print(f"\nCurrent Position (Alt/Az):")
        print(f"  Azimuth: {az:.2f}°")
        print(f"  Altitude: {alt:.2f}°")

        # Get tracking mode
        tracking = telescope.get_tracking_mode()
        print(f"\nTracking Mode: {tracking.name}")

        # Get location
        lat, lon = telescope.get_location()
        print(f"\nLocation:")
        print(f"  Latitude: {lat:.4f}°")
        print(f"  Longitude: {lon:.4f}°")

        print("\nDemo complete!")
        return 0

    except Exception as e:
        print(f"\nError: {e}")
        return 1

    finally:
        # Always disconnect
        if telescope.serial_conn:
            telescope.disconnect()


if __name__ == "__main__":
    exit(main())
