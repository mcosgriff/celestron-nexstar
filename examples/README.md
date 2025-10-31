# Celestron NexStar Examples

This directory contains practical examples showing how to use the Celestron NexStar Python library.

## Background Position Monitoring Examples

### Simple Position Tracking

**File:** `simple_position_tracking.py`

The easiest way to track telescope position in the background. Perfect for beginners!

```python
tracker = SimplePositionTracker(telescope, interval=1.0)
tracker.start()

# Position updates automatically in background
for i in range(10):
    pos = tracker.get_position()  # Instant - no waiting!
    print(f"RA: {pos.ra_hours}h, Dec: {pos.dec_degrees}°")
    time.sleep(1)
```

**Features:**

- ✓ Minimal code (~50 lines)
- ✓ Easy to understand
- ✓ Automatic background updates
- ✓ Cached position (instant access)

---

### Advanced Background Monitoring

**File:** `background_position_monitor.py`

Comprehensive examples showing 4 different approaches:

#### 1. Threading Approach

Simple background thread with cached positions.

```python
monitor = PositionMonitorThread(telescope, interval=1.0)
monitor.start()

# Get cached position (thread-safe)
ra_dec = monitor.get_position_ra_dec()
alt_az = monitor.get_position_alt_az()
```

**Best for:** Simple background monitoring with cached access

#### 2. Asyncio Approach

Asynchronous monitoring using Python's asyncio.

```python
async def main():
    monitor = AsyncPositionMonitor(telescope, interval=1.0)
    task = asyncio.create_task(monitor.run())

    # Do async work...
    position = monitor.get_position_ra_dec()
```

**Best for:** Integration with async applications

#### 3. Callback Approach

Event-driven updates with callbacks.

```python
def on_update(ra_dec, alt_az, timestamp):
    print(f"Position updated: {ra_dec.ra_hours}h")

monitor = CallbackPositionMonitor(telescope, callback=on_update)
monitor.start()
```

**Best for:** Real-time notifications and event-driven apps

#### 4. Queue-Based Approach

Producer-consumer pattern with queues.

```python
monitor = QueuePositionMonitor(telescope, interval=1.0)
monitor.start()

# Consumer: get positions from queue
position_data = monitor.get_position(timeout=2.0)
```

**Best for:** Decoupled producers/consumers, buffering updates

---

### Real-World Example: Monitor During Slew

**File:** `track_during_slew.py`

Monitor telescope position while it's slewing to a target. Shows real-time progress!

```python
monitor = SlewMonitor(telescope)
monitor.start_slew(target_ra=2.5303, target_dec=89.2641)

# Displays progress bar, ETA, distance remaining...
# [42] RA: 2.4523h  Dec: +88.234°  |  [███████████░░░] 75.3%  |  Dist: 1.45°  |  ETA: 12s
```

**Features:**

- ✓ Real-time progress bar
- ✓ Distance to target
- ✓ Estimated time remaining
- ✓ Current position updates
- ✓ Angular separation calculations

**Best for:** Monitoring long slews, user feedback, GUI applications

---

## Quick Comparison

| Approach | Complexity | Use Case | Performance |
|----------|-----------|----------|-------------|
| **Simple Tracker** | ⭐ Low | Quick scripts, learning | Good |
| **Threading** | ⭐⭐ Medium | General purpose apps | Excellent |
| **Asyncio** | ⭐⭐⭐ High | Async applications | Excellent |
| **Callbacks** | ⭐⭐ Medium | Event-driven apps | Excellent |
| **Queue-Based** | ⭐⭐⭐ High | Producer/consumer | Good |
| **Slew Monitor** | ⭐⭐ Medium | User feedback during slews | Excellent |

## Running the Examples

### Prerequisites

1. Install the library:

```bash
uv sync --all-extras
```

1. Update the serial port in examples:

```python
telescope = NexStarTelescope('/dev/ttyUSB0')  # Change to your port
```

1. Connect your telescope via USB

### Run Examples

```bash
# Simple position tracking
uv run python examples/simple_position_tracking.py

# Advanced monitoring (choose approach)
uv run python examples/background_position_monitor.py

# Monitor during slew
uv run python examples/track_during_slew.py
```

## Tips

### Thread Safety

When using threading approaches, the monitors handle thread safety for you:

```python
# Safe to call from any thread
position = monitor.get_position_ra_dec()
```

### Update Intervals

Choose interval based on your needs:

- **0.5s** - High-frequency updates, smooth tracking
- **1.0s** - Standard, good balance
- **2.0s** - Low-frequency, less CPU usage

### Error Handling

All monitors catch exceptions internally:

```python
# Monitors continue running even if telescope errors occur
# Check logs for error messages
```

### Performance

Background monitoring has minimal impact:

- **CPU Usage:** < 1% per monitor
- **Memory:** ~1-2 MB per monitor
- **Network:** None (local serial only)

## Integration Examples

### With GUI Applications

```python
# Update GUI in callback
def update_gui(ra_dec, alt_az, timestamp):
    gui.update_position_display(ra_dec, alt_az)

monitor = CallbackPositionMonitor(telescope, callback=update_gui)
```

### With Web Applications

```python
# Use asyncio approach with FastAPI/Flask
async def websocket_handler():
    monitor = AsyncPositionMonitor(telescope)
    task = asyncio.create_task(monitor.run())

    while True:
        position = monitor.get_position_ra_dec()
        await websocket.send(position)
```

### With Data Logging

```python
# Log positions to file
def log_position(ra_dec, alt_az, timestamp):
    with open('positions.csv', 'a') as f:
        f.write(f"{timestamp},{ra_dec.ra_hours},{ra_dec.dec_degrees}\n")

monitor = CallbackPositionMonitor(telescope, callback=log_position)
```

## Troubleshooting

### Monitor not starting

- Check telescope is connected first
- Verify serial port is correct
- Ensure no other programs using the port

### Positions not updating

- Check update interval isn't too long
- Verify telescope is powered on
- Check for error messages in console

### High CPU usage

- Increase update interval
- Use threading approach instead of polling
- Check for exception loops

## Additional Resources

- [Main README](../README.md) - Library overview
- [API Documentation](../docs/telescope_docs.md) - Full API reference
- [Protocol Documentation](../docs/protocol_docs.md) - Low-level protocol details

## Contributing

Have a useful example? Please contribute!

1. Create your example file
2. Add documentation
3. Test thoroughly
4. Submit a pull request
