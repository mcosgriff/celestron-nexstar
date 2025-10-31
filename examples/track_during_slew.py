"""
Real-World Example: Monitor Position During Slew

Shows how to track telescope position while it's slewing to a target.
Useful for displaying progress, calculating estimated time, etc.
"""

import time
import threading
from datetime import datetime
from tqdm import tqdm
from celestron_nexstar import NexStarTelescope
from celestron_nexstar.utils import angular_separation


class SlewMonitor:
    """
    Monitor telescope position during a slew operation.

    Provides real-time updates on:
    - Current position
    - Distance to target
    - Slew progress percentage
    - Estimated time remaining
    """

    def __init__(self, telescope: NexStarTelescope):
        self.telescope = telescope
        self.current_position = None
        self.target_ra = None
        self.target_dec = None
        self.start_position = None
        self.start_time = None
        self.running = False
        self._thread = None

    def start_slew(self, target_ra: float, target_dec: float):
        """
        Start slewing and monitoring.

        Args:
            target_ra: Target Right Ascension in hours
            target_dec: Target Declination in degrees
        """
        # Store target
        self.target_ra = target_ra
        self.target_dec = target_dec

        # Get starting position
        pos = self.telescope.get_position_ra_dec()
        self.start_position = pos
        self.current_position = pos
        self.start_time = datetime.now()

        # Calculate initial distance
        initial_distance = angular_separation(pos.ra_hours, pos.dec_degrees, target_ra, target_dec)

        print(f"\n{'=' * 70}")
        print(f"Starting slew to RA {target_ra:.4f}h, Dec {target_dec:+.4f}°")
        print(f"Current position: RA {pos.ra_hours:.4f}h, Dec {pos.dec_degrees:+.4f}°")
        print(f"Distance to target: {initial_distance:.2f}°")
        print(f"{'=' * 70}\n")

        # Start the slew
        self.telescope.goto_ra_dec(target_ra, target_dec)

        # Start monitoring
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        """Background monitoring loop."""
        # Calculate initial distance for progress bar
        initial_distance = angular_separation(
            self.start_position.ra_hours, self.start_position.dec_degrees, self.target_ra, self.target_dec
        )

        with tqdm(
            total=100,
            desc="Slewing to target",
            unit="%",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}, {postfix}]",
        ) as pbar:
            while self.running:
                try:
                    # Get current position
                    pos = self.telescope.get_position_ra_dec()
                    self.current_position = pos

                    # Calculate distances
                    distance_to_target = angular_separation(
                        pos.ra_hours, pos.dec_degrees, self.target_ra, self.target_dec
                    )

                    distance_traveled = angular_separation(
                        self.start_position.ra_hours, self.start_position.dec_degrees, pos.ra_hours, pos.dec_degrees
                    )

                    # Calculate progress
                    if initial_distance > 0:
                        progress = min(100, (distance_traveled / initial_distance) * 100)
                    else:
                        progress = 100

                    # Update progress bar
                    pbar.n = int(progress)
                    pbar.set_postfix(
                        {
                            "RA": f"{pos.ra_hours:.4f}h",
                            "Dec": f"{pos.dec_degrees:+.3f}°",
                            "Dist": f"{distance_to_target:.2f}°",
                        }
                    )
                    pbar.refresh()

                    # Check if slew is complete
                    if not self.telescope.is_slewing():
                        pbar.n = 100
                        pbar.refresh()
                        self._display_complete((datetime.now() - self.start_time).total_seconds(), distance_to_target)
                        self.running = False
                        break

                except Exception as e:
                    tqdm.write(f"Error in monitor: {e}")

                time.sleep(0.5)  # Update twice per second

    def _display_complete(self, elapsed, final_distance):
        """Display completion message."""
        print(f"\n{'=' * 70}")
        print(f"✓ Slew complete!")
        print(f"  Total time: {elapsed:.1f} seconds")
        print(f"  Final distance to target: {final_distance:.4f}°")
        print(f"{'=' * 70}\n")

    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_current_position(self):
        """Get latest position."""
        return self.current_position


# ============================================================================
# Example Usage
# ============================================================================


def example_monitor_slew():
    """Example: Monitor telescope during slew to multiple targets."""

    telescope = NexStarTelescope("/dev/ttyUSB0")
    telescope.connect()

    monitor = SlewMonitor(telescope)

    # Example targets (adjust for your location and time)
    targets = [
        ("Polaris", 2.5303, 89.2641),  # North Star
        ("Vega", 18.6156, 38.7836),  # Summer star
        ("Sirius", 6.7525, -16.7161),  # Brightest star
    ]

    for name, ra, dec in targets:
        print(f"\n{'*' * 70}")
        print(f"Slewing to {name}")
        print(f"{'*' * 70}")

        # Start slew with monitoring
        monitor.start_slew(ra, dec)

        # Wait for slew to complete
        while monitor.running:
            time.sleep(0.1)

        # Brief pause before next target
        time.sleep(2)

    telescope.disconnect()
    print("\nAll slews complete!")


def example_simple_tracking():
    """Simple example: Just track position during one slew."""

    telescope = NexStarTelescope("/dev/ttyUSB0")
    telescope.connect()

    monitor = SlewMonitor(telescope)

    # Slew to a target (example: Polaris)
    monitor.start_slew(2.5303, 89.2641)

    # Wait for completion
    while monitor.running:
        time.sleep(0.1)

    # Check final position
    final_pos = monitor.get_current_position()
    if final_pos:
        print(f"Final position: RA {final_pos.ra_hours:.4f}h, Dec {final_pos.dec_degrees:.4f}°")

    telescope.disconnect()


if __name__ == "__main__":
    print("Slew Monitoring Examples\n")
    print("1. Monitor slew to single target")
    print("2. Monitor slew to multiple targets")

    choice = input("\nChoose example (1 or 2): ").strip()

    if choice == "1":
        example_simple_tracking()
    elif choice == "2":
        example_monitor_slew()
    else:
        print("Invalid choice. Running example 1...")
        example_simple_tracking()
