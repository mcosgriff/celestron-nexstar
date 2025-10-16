"""
Background Position Monitoring Examples

Demonstrates different approaches to monitoring telescope position in the background:
1. Threading approach - Simple background thread
2. Asyncio approach - Asynchronous monitoring
3. Callback approach - Event-driven updates
4. Queue-based approach - Producer-consumer pattern
"""

import time
import threading
import asyncio
from queue import Queue
from datetime import datetime
from typing import Callable, Optional
from celestron_nexstar import NexStarTelescope, EquatorialCoordinates, HorizontalCoordinates


# ============================================================================
# Approach 1: Threading - Simple Background Thread
# ============================================================================

class PositionMonitorThread:
    """
    Monitor telescope position in a background thread.

    Example:
        >>> telescope = NexStarTelescope('/dev/ttyUSB0')
        >>> telescope.connect()
        >>>
        >>> monitor = PositionMonitorThread(telescope, interval=1.0)
        >>> monitor.start()
        >>>
        >>> # Do other work...
        >>> time.sleep(10)
        >>>
        >>> # Get latest position
        >>> ra_dec = monitor.get_position_ra_dec()
        >>> print(f"RA: {ra_dec.ra_hours:.4f}h, Dec: {ra_dec.dec_degrees:.4f}°")
        >>>
        >>> monitor.stop()
        >>> telescope.disconnect()
    """

    def __init__(self, telescope: NexStarTelescope, interval: float = 1.0):
        """
        Initialize position monitor.

        Args:
            telescope: Connected telescope instance
            interval: Update interval in seconds (default 1.0)
        """
        self.telescope = telescope
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Cached positions
        self._position_ra_dec: Optional[EquatorialCoordinates] = None
        self._position_alt_az: Optional[HorizontalCoordinates] = None
        self._last_update: Optional[datetime] = None

    def start(self):
        """Start background monitoring."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Monitor is already running")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"Position monitoring started (interval: {self.interval}s)")

    def stop(self):
        """Stop background monitoring."""
        if self._thread is None or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=5.0)
        print("Position monitoring stopped")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            try:
                # Get positions from telescope
                ra_dec = self.telescope.get_position_ra_dec()
                alt_az = self.telescope.get_position_alt_az()

                # Update cached values (thread-safe)
                with self._lock:
                    self._position_ra_dec = ra_dec
                    self._position_alt_az = alt_az
                    self._last_update = datetime.now()

            except Exception as e:
                print(f"Error updating position: {e}")

            # Wait for next update (allow early exit)
            self._stop_event.wait(self.interval)

    def get_position_ra_dec(self) -> Optional[EquatorialCoordinates]:
        """Get latest RA/Dec position (cached)."""
        with self._lock:
            return self._position_ra_dec

    def get_position_alt_az(self) -> Optional[HorizontalCoordinates]:
        """Get latest Alt/Az position (cached)."""
        with self._lock:
            return self._position_alt_az

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last successful update."""
        with self._lock:
            return self._last_update

    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._thread is not None and self._thread.is_alive()


# ============================================================================
# Approach 2: Asyncio - Asynchronous Monitoring
# ============================================================================

class AsyncPositionMonitor:
    """
    Asynchronous position monitoring using asyncio.

    Example:
        >>> import asyncio
        >>>
        >>> async def main():
        ...     telescope = NexStarTelescope('/dev/ttyUSB0')
        ...     telescope.connect()
        ...
        ...     monitor = AsyncPositionMonitor(telescope, interval=1.0)
        ...
        ...     # Start monitoring
        ...     task = asyncio.create_task(monitor.run())
        ...
        ...     # Do other async work...
        ...     await asyncio.sleep(10)
        ...
        ...     # Get current position
        ...     position = monitor.get_position_ra_dec()
        ...     print(f"RA: {position.ra_hours:.4f}h")
        ...
        ...     # Stop monitoring
        ...     monitor.stop()
        ...     await task
        ...
        ...     telescope.disconnect()
        >>>
        >>> asyncio.run(main())
    """

    def __init__(self, telescope: NexStarTelescope, interval: float = 1.0):
        """
        Initialize async position monitor.

        Args:
            telescope: Connected telescope instance
            interval: Update interval in seconds
        """
        self.telescope = telescope
        self.interval = interval
        self._running = False

        # Cached positions
        self._position_ra_dec: Optional[EquatorialCoordinates] = None
        self._position_alt_az: Optional[HorizontalCoordinates] = None
        self._last_update: Optional[datetime] = None

    async def run(self):
        """Run async monitoring loop."""
        self._running = True
        print(f"Async position monitoring started (interval: {self.interval}s)")

        while self._running:
            try:
                # Run blocking telescope calls in executor
                loop = asyncio.get_event_loop()
                ra_dec = await loop.run_in_executor(
                    None, self.telescope.get_position_ra_dec
                )
                alt_az = await loop.run_in_executor(
                    None, self.telescope.get_position_alt_az
                )

                # Update cached values
                self._position_ra_dec = ra_dec
                self._position_alt_az = alt_az
                self._last_update = datetime.now()

            except Exception as e:
                print(f"Error updating position: {e}")

            # Wait for next update
            await asyncio.sleep(self.interval)

        print("Async position monitoring stopped")

    def stop(self):
        """Stop async monitoring."""
        self._running = False

    def get_position_ra_dec(self) -> Optional[EquatorialCoordinates]:
        """Get latest RA/Dec position."""
        return self._position_ra_dec

    def get_position_alt_az(self) -> Optional[HorizontalCoordinates]:
        """Get latest Alt/Az position."""
        return self._position_alt_az

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last update."""
        return self._last_update


# ============================================================================
# Approach 3: Callback-Based Monitoring
# ============================================================================

class CallbackPositionMonitor:
    """
    Position monitor with callback support.

    Example:
        >>> def on_position_update(ra_dec, alt_az, timestamp):
        ...     print(f"[{timestamp}] RA: {ra_dec.ra_hours:.4f}h, "
        ...           f"Alt: {alt_az.altitude:.2f}°")
        >>>
        >>> telescope = NexStarTelescope('/dev/ttyUSB0')
        >>> telescope.connect()
        >>>
        >>> monitor = CallbackPositionMonitor(
        ...     telescope,
        ...     callback=on_position_update,
        ...     interval=1.0
        ... )
        >>> monitor.start()
        >>>
        >>> # Callbacks will be triggered automatically
        >>> time.sleep(10)
        >>>
        >>> monitor.stop()
        >>> telescope.disconnect()
    """

    def __init__(
        self,
        telescope: NexStarTelescope,
        callback: Callable[[EquatorialCoordinates, HorizontalCoordinates, datetime], None],
        interval: float = 1.0
    ):
        """
        Initialize callback-based monitor.

        Args:
            telescope: Connected telescope instance
            callback: Function to call on each update
            interval: Update interval in seconds
        """
        self.telescope = telescope
        self.callback = callback
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Start monitoring with callbacks."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Monitor is already running")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"Callback monitoring started (interval: {self.interval}s)")

    def stop(self):
        """Stop monitoring."""
        if self._thread is None or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=5.0)
        print("Callback monitoring stopped")

    def _monitor_loop(self):
        """Background loop that triggers callbacks."""
        while not self._stop_event.is_set():
            try:
                ra_dec = self.telescope.get_position_ra_dec()
                alt_az = self.telescope.get_position_alt_az()
                timestamp = datetime.now()

                # Trigger callback
                self.callback(ra_dec, alt_az, timestamp)

            except Exception as e:
                print(f"Error in monitoring loop: {e}")

            self._stop_event.wait(self.interval)


# ============================================================================
# Approach 4: Queue-Based Monitoring (Producer-Consumer)
# ============================================================================

class QueuePositionMonitor:
    """
    Queue-based position monitor (producer-consumer pattern).

    Example:
        >>> telescope = NexStarTelescope('/dev/ttyUSB0')
        >>> telescope.connect()
        >>>
        >>> monitor = QueuePositionMonitor(telescope, interval=1.0)
        >>> monitor.start()
        >>>
        >>> # Consumer: process position updates
        >>> for _ in range(10):
        ...     position_data = monitor.get_position(timeout=2.0)
        ...     if position_data:
        ...         ra_dec, alt_az, timestamp = position_data
        ...         print(f"RA: {ra_dec.ra_hours:.4f}h")
        >>>
        >>> monitor.stop()
        >>> telescope.disconnect()
    """

    def __init__(self, telescope: NexStarTelescope, interval: float = 1.0, maxsize: int = 10):
        """
        Initialize queue-based monitor.

        Args:
            telescope: Connected telescope instance
            interval: Update interval in seconds
            maxsize: Maximum queue size (0 = unlimited)
        """
        self.telescope = telescope
        self.interval = interval
        self.queue = Queue(maxsize=maxsize)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Start position monitoring."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Monitor is already running")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"Queue-based monitoring started (interval: {self.interval}s)")

    def stop(self):
        """Stop monitoring."""
        if self._thread is None or not self._thread.is_alive():
            return

        self._stop_event.set()
        self._thread.join(timeout=5.0)
        print("Queue-based monitoring stopped")

    def _monitor_loop(self):
        """Producer: continuously read positions and add to queue."""
        while not self._stop_event.is_set():
            try:
                ra_dec = self.telescope.get_position_ra_dec()
                alt_az = self.telescope.get_position_alt_az()
                timestamp = datetime.now()

                # Add to queue (non-blocking, drop oldest if full)
                try:
                    self.queue.put_nowait((ra_dec, alt_az, timestamp))
                except:
                    # Queue full, remove oldest and add new
                    try:
                        self.queue.get_nowait()
                        self.queue.put_nowait((ra_dec, alt_az, timestamp))
                    except:
                        pass

            except Exception as e:
                print(f"Error in producer loop: {e}")

            self._stop_event.wait(self.interval)

    def get_position(self, timeout: Optional[float] = None) -> Optional[tuple]:
        """
        Consumer: get next position from queue.

        Args:
            timeout: Maximum time to wait (None = block forever)

        Returns:
            Tuple of (ra_dec, alt_az, timestamp) or None if timeout
        """
        try:
            return self.queue.get(timeout=timeout)
        except:
            return None

    def queue_size(self) -> int:
        """Get current number of items in queue."""
        return self.queue.qsize()


# ============================================================================
# Example Usage
# ============================================================================

def example_threading():
    """Example using threading approach."""
    print("\n" + "="*70)
    print("Example 1: Threading Approach")
    print("="*70)

    telescope = NexStarTelescope('/dev/ttyUSB0')
    telescope.connect()

    # Start background monitoring
    monitor = PositionMonitorThread(telescope, interval=1.0)
    monitor.start()

    # Do other work while monitoring runs in background
    for i in range(5):
        time.sleep(1)

        # Get cached position (no delay!)
        ra_dec = monitor.get_position_ra_dec()
        alt_az = monitor.get_position_alt_az()
        last_update = monitor.get_last_update()

        if ra_dec and alt_az:
            print(f"[{i+1}] RA: {ra_dec.ra_hours:.4f}h, "
                  f"Dec: {ra_dec.dec_degrees:.4f}°, "
                  f"Alt: {alt_az.altitude:.2f}° "
                  f"(updated: {last_update.strftime('%H:%M:%S')})")

    monitor.stop()
    telescope.disconnect()


def example_callback():
    """Example using callback approach."""
    print("\n" + "="*70)
    print("Example 2: Callback Approach")
    print("="*70)

    def position_callback(ra_dec, alt_az, timestamp):
        """Called automatically on each update."""
        print(f"[{timestamp.strftime('%H:%M:%S')}] "
              f"RA: {ra_dec.ra_hours:.4f}h, "
              f"Az: {alt_az.azimuth:.2f}°")

    telescope = NexStarTelescope('/dev/ttyUSB0')
    telescope.connect()

    monitor = CallbackPositionMonitor(
        telescope,
        callback=position_callback,
        interval=1.0
    )
    monitor.start()

    # Callbacks happen automatically
    time.sleep(5)

    monitor.stop()
    telescope.disconnect()


def example_queue():
    """Example using queue-based approach."""
    print("\n" + "="*70)
    print("Example 3: Queue-Based Approach")
    print("="*70)

    telescope = NexStarTelescope('/dev/ttyUSB0')
    telescope.connect()

    monitor = QueuePositionMonitor(telescope, interval=1.0, maxsize=5)
    monitor.start()

    # Consumer: process positions from queue
    for i in range(5):
        position_data = monitor.get_position(timeout=2.0)

        if position_data:
            ra_dec, alt_az, timestamp = position_data
            print(f"[{i+1}] Received: RA {ra_dec.ra_hours:.4f}h, "
                  f"Alt {alt_az.altitude:.2f}° at {timestamp.strftime('%H:%M:%S')}")
            print(f"     Queue size: {monitor.queue_size()}")
        else:
            print(f"[{i+1}] Timeout waiting for position")

    monitor.stop()
    telescope.disconnect()


async def example_async():
    """Example using asyncio approach."""
    print("\n" + "="*70)
    print("Example 4: Asyncio Approach")
    print("="*70)

    telescope = NexStarTelescope('/dev/ttyUSB0')
    telescope.connect()

    monitor = AsyncPositionMonitor(telescope, interval=1.0)

    # Start monitoring task
    monitor_task = asyncio.create_task(monitor.run())

    # Do other async work
    for i in range(5):
        await asyncio.sleep(1)

        position = monitor.get_position_ra_dec()
        if position:
            print(f"[{i+1}] RA: {position.ra_hours:.4f}h, "
                  f"Dec: {position.dec_degrees:.4f}°")

    # Stop monitoring
    monitor.stop()
    await monitor_task

    telescope.disconnect()


if __name__ == '__main__':
    print("Background Position Monitoring Examples")
    print("Choose an example to run:")
    print("1. Threading approach")
    print("2. Callback approach")
    print("3. Queue-based approach")
    print("4. Asyncio approach")

    choice = input("\nEnter choice (1-4) or 'all': ").strip()

    if choice == '1':
        example_threading()
    elif choice == '2':
        example_callback()
    elif choice == '3':
        example_queue()
    elif choice == '4':
        asyncio.run(example_async())
    elif choice.lower() == 'all':
        example_threading()
        example_callback()
        example_queue()
        asyncio.run(example_async())
    else:
        print("Invalid choice")
