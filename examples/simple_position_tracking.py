"""
Simple Background Position Tracking Example

A minimal example showing the easiest way to track telescope position
in the background while doing other work.
"""

import time
import threading
from tqdm import tqdm
from celestron_nexstar import NexStarTelescope


class SimplePositionTracker:
    """Simple background position tracker - just 50 lines of code!"""

    def __init__(self, telescope: NexStarTelescope, interval: float = 1.0):
        self.telescope = telescope
        self.interval = interval
        self.position = None
        self.running = False
        self._thread = None

    def start(self):
        """Start tracking in background."""
        self.running = True
        self._thread = threading.Thread(target=self._track, daemon=True)
        self._thread.start()
        print("✓ Position tracking started")

    def stop(self):
        """Stop tracking."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        print("✓ Position tracking stopped")

    def _track(self):
        """Background tracking loop."""
        while self.running:
            try:
                self.position = self.telescope.get_position_ra_dec()
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(self.interval)

    def get_position(self):
        """Get latest position (cached, instant!)."""
        return self.position


# ============================================================================
# Quick Start Example
# ============================================================================

def main():
    """Simple example showing background tracking."""

    # Connect to telescope
    telescope = NexStarTelescope('/dev/ttyUSB0')
    telescope.connect()

    # Start background tracking (updates every second)
    tracker = SimplePositionTracker(telescope, interval=1.0)
    tracker.start()

    print("\nTracking telescope position in background...")
    print("Doing other work while position updates automatically:\n")

    # Do your work here - position updates in background!
    with tqdm(total=10, desc="Tracking position", unit="update",
              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
        for i in range(10):
            # Simulate doing other work
            time.sleep(1)

            # Get current position (instant - no waiting!)
            pos = tracker.get_position()

            if pos:
                pbar.set_postfix({
                    'RA': f'{pos.ra_hours:.4f}h',
                    'Dec': f'{pos.dec_degrees:+.3f}°'
                })
            else:
                pbar.set_postfix({'status': 'Waiting...'})

            pbar.update(1)

    # Clean up
    tracker.stop()
    telescope.disconnect()


if __name__ == '__main__':
    main()
