# Background Position Tracking Feature

## Overview

The interactive shell now includes automatic background position tracking that continuously monitors the telescope's current position in a background thread. This provides real-time position updates without requiring manual polling.

## Key Features

### 1. **Automatic Activation**
- Automatically starts after any `align` command completes successfully
- Runs in a daemon thread that doesn't prevent shell exit
- Thread-safe implementation using locks

### 2. **Live Status Bar**
- Position displayed in bottom toolbar using prompt_toolkit
- Updates every 0.5 seconds in the UI (telescope polled every 2 seconds)
- Shows:
  - RA (Right Ascension) in HH:MM:SS format
  - Dec (Declination) in DD:MM:SS format with sign
  - Alt (Altitude) in degrees
  - Az (Azimuth) in degrees
  - Freshness indicator: `[live]` if < 5 seconds old, or `[Ns ago]`

### 3. **Manual Control**
Users can manually control tracking with shell commands:

```bash
tracking start   # Start background tracking
tracking stop    # Stop background tracking
tracking status  # Show current status and last position
```

### 4. **Smart Error Handling**
- Gracefully handles connection errors
- Stops automatically after 3 consecutive errors
- No error spam - fails silently in background
- Works even when telescope is not yet connected (waits for connection)

### 5. **Clean Shutdown**
- Automatically stops when exiting shell
- Thread is daemon so won't block exit
- Proper cleanup on Ctrl+C and Ctrl+D

## Implementation Details

### Architecture

```python
class PositionTracker:
    """Background thread for tracking telescope position."""

    - enabled: bool          # User wants tracking on/off
    - running: bool          # Thread is actually running
    - thread: Thread         # Background thread
    - lock: Lock            # Thread synchronization
    - update_interval: 2.0  # Poll telescope every 2 seconds
    - last_position: dict   # Cached position data
    - last_update: datetime # When position was last updated
    - error_count: int      # Consecutive error counter
```

### Thread Safety

- All shared state protected by `threading.Lock`
- Separate `enabled` and `running` flags for clean shutdown
- Position reads are atomic (read from cache, not live telescope query)

### Integration with prompt_toolkit

```python
def bottom_toolbar() -> HTML:
    """Generate bottom toolbar with position tracking."""
    status = tracker.get_status_text()
    if status:
        return HTML(f'<b><style bg="ansiblue" fg="ansiwhite"> Position: {status} </style></b>')
    return HTML('')

session = PromptSession(
    ...
    bottom_toolbar=bottom_toolbar,
    refresh_interval=0.5,  # UI refresh rate
)
```

## User Experience

### Before Alignment
```
nexstar> position get
Current Position: RA: 12.5h, Dec: 45.0°

nexstar> _
```

### After Alignment
```
nexstar> align sync --ra 5.5 --dec 22.5
✓ Telescope synced

→ Background position tracking started automatically
  Position updates will appear in the status bar
  Use 'tracking stop' to disable

nexstar> catalog list --catalog planets
┌─────────────────────────────────────────────────────────────────┐
│ Position: RA: 05h30m12s  Dec: +22°30'05"  Alt: 45.8°  Az: 120.5° [live] │
└─────────────────────────────────────────────────────────────────┘
  Jupiter - RA: 5.5h, Dec: 22.5°
  ...
```

## Benefits for Observing Sessions

1. **Continuous Monitoring**: Always know where the telescope is pointing
2. **Slew Verification**: Watch position change in real-time during goto commands
3. **Drift Detection**: See if polar alignment needs adjustment
4. **Multi-Target Planning**: Position visible while browsing catalogs
5. **No Manual Polling**: Don't need to run `position get` repeatedly
6. **Non-Intrusive**: Status bar doesn't interfere with command input or output

## Performance

- **Telescope Load**: One query every 2 seconds (RA/Dec + Alt/Az)
- **CPU Impact**: Minimal - thread sleeps between polls
- **Memory**: ~1KB for position cache
- **UI Refresh**: 0.5 seconds (smooth updates)

## Why This Makes Sense with Interactive Shell

Without the shell, caching position wouldn't help since each CLI command creates a new process. With the interactive shell:

1. **Process Lives**: One process for entire observing session
2. **Thread Persists**: Background thread runs continuously
3. **State Maintained**: Position cache stays valid between commands
4. **Natural UX**: Status bar is always visible, like a real telescope display

## Code Location

All tracking code is contained within the `shell()` function in:
- `src/celestron_nexstar/cli/main.py` (lines 162-479)

The `PositionTracker` class is defined as a nested class, making it scoped to the shell session and avoiding global state issues.

## Future Enhancements

Potential improvements:
- Configurable update interval (`tracking interval <seconds>`)
- Position history/logging
- Alert on unexpected position change (collision detection)
- Visual representation (ASCII star chart in status bar?)
- Export position log to file
- Track rate of change (slew speed)
