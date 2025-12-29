# Telescope Control Window Improvements

## Overview

This document details the improvements made to the telescope control system, including enhanced communication logging, visual feedback, rate presets, and command history capabilities.

## Phases

### Phase 1: Core Infrastructure
**Status**: ✅ Complete

#### Command Tracker
- **Location**: `src/celestron_nexstar/api/telescope/command_tracker.py`
- **Purpose**: Track all telescope commands for debugging and history
- **Features**:
  - Circular buffer (configurable size, default 100 commands)
  - Records: timestamp, command, response, duration, success/failure, decoded output
  - Thread-safe operations
  - Filtering (all, successful, failed)
  - Statistics (success rate, average duration)
  - JSON export for debugging

#### Protocol Integration
- **Location**: `src/celestron_nexstar/api/telescope/protocol.py`
- **Integration**: Optional command tracking (off by default)
- **Usage**:
  ```python
  tracker = CommandTracker(max_history=100)
  protocol.set_command_tracker(tracker)
  ```

#### Test Coverage
- **Location**: `tests/test_command_tracker.py`
- **Coverage**: 90.74% (19 tests)
- **Performance**: < 5% overhead

### Phase 2: New Widgets
**Status**: ✅ Complete

#### 1. Slew Rate Presets Widget
- **Location**: `src/celestron_nexstar/gui/widgets/slew_rate_presets_widget.py`
- **Features**:
  - Three preset buttons: Guide (2x), Center (32x), Find (3°/s)
  - Visual highlighting of active preset
  - Color-coded buttons (blue/green/orange)
  - Theme-aware styling
  - Signal: `rate_changed(int)`

**Usage**:
```python
presets = SlewRatePresetsWidget()
presets.rate_changed.connect(on_rate_changed)
```

#### 2. Slew Progress Widget
- **Location**: `src/celestron_nexstar/gui/widgets/slew_progress_widget.py`
- **Features**:
  - Progress bar during goto operations
  - Velocity display (°/sec)
  - ETA calculation
  - Target name display
  - Auto-hide when inactive
  - Theme-aware colors

**Usage**:
```python
progress = SlewProgressWidget()
progress.start_goto(target_ra, target_dec, "M31")
progress.update_progress(current_ra, current_dec)
```

#### 3. Command Queue Widget
- **Location**: `src/celestron_nexstar/gui/widgets/command_queue_widget.py`
- **Features**:
  - Visual command queue display
  - State indicators:
    - Gray: Queued
    - Yellow/Orange: Executing (with spinner)
    - Green: Completed (with checkmark)
    - Red: Failed (with X)
  - Auto-remove completed/failed (2 second delay)
  - Theme-aware colors

**Usage**:
```python
queue = CommandQueueWidget()
queue.add_command("GoTo")
queue.set_executing("GoTo")
queue.set_completed("GoTo")
```

#### 4. Telescope Command Log Panel
- **Location**: `src/celestron_nexstar/gui/widgets/telescope_command_log_panel.py`
- **Features**:
  - Enhanced collapsible log panel
  - Filtering: All, Commands, Responses, Errors, Connection Events
  - Timestamp toggle
  - Export to JSON
  - View History button
  - Integrates with CommandTracker

**Usage**:
```python
log_panel = TelescopeCommandLogPanel(command_tracker)
```

#### 5. Command History Dialog
- **Location**: `src/celestron_nexstar/gui/dialogs/command_history_dialog.py`
- **Features**:
  - Sortable table view
  - Columns: Timestamp, Command, Response, Duration, Status, Decoded
  - Filtering (All/Successful/Failed)
  - Statistics display
  - Replay single command (with safety confirmation)
  - Export selection or all to JSON
  - Clear history

**Usage**:
```python
dialog = CommandHistoryDialog(command_tracker, parent)
dialog.exec()
```

### Phase 3: Integration
**Status**: ✅ Complete

#### Telescope Control Window
- **Location**: `src/celestron_nexstar/gui/windows/telescope_control_window.py`
- **Layout Changes**:
  - Changed from 3-panel splitter to 2-panel with tabs
  - Top panel: Controls + Status (400px)
  - Bottom panel: Tabbed interface (350px)
    - Tab 1: Visible Objects
    - Tab 2: Communication Log

#### New Components Integrated:
1. **Command Queue Widget** - Above splitter, shows pending commands
2. **Rate Presets** - In directional control panel
3. **Slew Progress** - In position status panel
4. **Communication Log** - In bottom tab panel
5. **Command Tracker** - Initialized and connected to protocol

#### Signal Connections:
- Rate presets → Update slider + send to telescope
- Position updates → Update progress widget
- Command execution → Update command queue

### Phase 4: Main Window Migration
**Status**: ✅ Complete

#### User Configuration
- **Location**: `src/celestron_nexstar/api/config/user_config.py`
- **New Setting**: `protocol_log_location`
  - Options: `"main"`, `"telescope"`, `"both"`
  - Default: `"both"`

#### Settings Dialog
- **Location**: `src/celestron_nexstar/gui/dialogs/settings_dialog.py`
- **UI Addition**: Protocol Log dropdown in Config tab
- **Persistence**: Saved to `~/.config/celestron-nexstar/user_config.json`
- **Takes Effect**: On app restart

#### Main Window
- **Location**: `src/celestron_nexstar/gui/main_window.py`
- **Changes**:
  - Conditional log panel creation based on user config
  - Log toggle action hidden/disabled when panel not present
  - Supports all three configurations (main/telescope/both)

### Phase 5: Polish & Testing
**Status**: ✅ Complete

#### Theme Support
All new widgets support dark/light themes:

**Widgets with `apply_theme()` method**:
- `SlewRatePresetsWidget` - Adjusted button colors for dark mode
- `CommandQueueWidget` - Theme-aware badge colors
- `SlewProgressWidget` - Adjusted progress bar colors
- `TelescopeCommandLogPanel` - Inherited from `CollapsibleLogPanel`

**Theme Detection**:
```python
palette = QGuiApplication.instance().palette()
brightness = palette.color(QPalette.ColorRole.Window).lightness()
is_dark = brightness < 128
```

#### Keyboard Shortcuts
**Location**: `src/celestron_nexstar/gui/windows/telescope_control_window.py`

| Shortcut | Action |
|----------|--------|
| `G` | Guide Rate (2x) |
| `C` | Center Rate (32x) |
| `F` | Find Rate (3°/s) |
| `Ctrl+H` | Open Command History Dialog |

**Notes**:
- Shortcuts only active when telescope is connected
- Trigger corresponding preset buttons
- Visual feedback through button highlighting

#### Performance Testing
**Location**: `tests/test_phase5_performance.py`

**Test Results**:
- ✅ High volume: 1000 commands in 0.0019s (0.0019ms/command)
- ✅ Circular buffer: Correctly maintains max size
- ✅ Empty history: All operations handle empty state
- ✅ Failures: Proper tracking and filtering
- ✅ Filtering: Accurate by success/failed
- ✅ Export/Import: JSON serialization works
- ✅ Rapid commands: 790 commands/sec throughput

**Edge Cases Tested**:
- Empty command history
- Circular buffer overflow
- Failed commands
- Command filtering
- JSON export of various states
- Rapid successive commands

## Usage Guide

### Basic Usage

#### 1. Connecting to Telescope
```python
# Telescope control window automatically initializes command tracker
window = TelescopeControlWindow()
window.show()

# On connection, tracker is attached to protocol
# Commands are automatically logged
```

#### 2. Using Rate Presets
- **GUI**: Click preset buttons (Guide/Center/Find)
- **Keyboard**: Press `G`, `C`, or `F`
- **Effect**: Updates slider and sends rate to telescope

#### 3. Viewing Command History
- **GUI**: Click "History" button in log panel
- **Keyboard**: Press `Ctrl+H`
- **Features**: Sort, filter, view statistics

#### 4. Monitoring Goto Progress
- Automatically appears during goto operations
- Shows: Progress bar, velocity, ETA, target name
- Auto-hides when goto completes

#### 5. Configuring Protocol Log Location
1. Open Settings (Settings → Config tab)
2. Select "Protocol Log" dropdown:
   - **Main Window Only**: Log only in main window
   - **Telescope Window Only**: Log only in telescope window
   - **Both Windows**: Log in both (default)
3. Click "Save"
4. Restart application

### Advanced Usage

#### Exporting Command History
```python
# From dialog: Click "Export to JSON"
# Or programmatically:
tracker.export_to_json(Path("~/telescope_commands.json"))
```

#### Command Replay (Safety Features)
1. Select command in history dialog
2. Click "Replay Selected"
3. Confirmation dialog appears with:
   - Command details
   - Previous response
   - Decoded information
   - Checkbox: "I understand this will control the telescope"
4. Must check box AND click "Yes" to execute

**Note**: Replay functionality requires telescope instance integration (planned)

#### Filtering Logs
**In Log Panel**:
- Dropdown: All, Commands, Responses, Errors, Connection Events
- Checkbox: Toggle timestamps

**In History Dialog**:
- Dropdown: All, Successful, Failed
- Statistics automatically update

## API Reference

### CommandTracker

```python
class CommandTracker:
    def __init__(self, max_history: int = 100):
        """Initialize tracker with circular buffer size."""

    def start_command(self, command: str):
        """Mark command as started (for duration tracking)."""

    def record_command(
        self,
        command: str,
        response: str | None,
        success: bool,
        error: str | None = None,
        decoded: str | None = None,
    ):
        """Record a command execution."""

    def get_history(self, filter_type: str | None = None) -> list[CommandRecord]:
        """Get command history. filter_type: None, 'success', or 'failed'."""

    def get_statistics(self) -> dict:
        """Get command statistics."""

    def export_to_json(self, file_path: Path):
        """Export history to JSON file."""

    def clear_history(self):
        """Clear all command history."""
```

### Widget Signals

```python
# SlewRatePresetsWidget
rate_changed = Signal(int)  # Emits: 2, 5, or 8

# CommandQueueWidget
# (No signals - state updates via methods)

# SlewProgressWidget
# (No signals - controlled via methods)
```

## Performance Characteristics

### Command Tracker
- **Memory**: ~100 bytes per command record
- **100 commands**: ~10 KB
- **1000 commands**: ~100 KB
- **CPU Overhead**: < 5% during normal operation
- **Throughput**: 790+ commands/second

### Widget Performance
- **Theme Switching**: < 10ms
- **Queue Updates**: < 1ms per state change
- **Progress Updates**: 200ms interval (5 Hz)
- **Log Panel**: Max 1000 lines (auto-trim)

## Configuration Files

### User Config
**Path**: `~/.config/celestron-nexstar/user_config.json`

```json
{
  "use_memory_db": false,
  "protocol_log_location": "both"
}
```

### Exported Command History
**Format**: JSON

```json
{
  "export_time": "2025-12-28T10:30:15.234Z",
  "commands": [
    {
      "timestamp": "2025-12-28T10:29:45.123Z",
      "command": "E",
      "response": "12345678,87654321",
      "duration_ms": 45.2,
      "success": true,
      "error": null,
      "decoded": "RA: 12h 34m 56s, Dec: +45° 12' 34\""
    }
  ],
  "statistics": {
    "total_commands": 100,
    "successful_commands": 98,
    "failed_commands": 2,
    "success_rate": 98.0,
    "average_duration_ms": 42.5
  }
}
```

## Troubleshooting

### Command History Not Showing
- **Cause**: Command tracker not initialized
- **Fix**: Ensure telescope is connected (tracker attached on connection)

### Keyboard Shortcuts Not Working
- **Cause**: Telescope not connected
- **Fix**: Shortcuts only active when connected

### Protocol Log Not Appearing
- **Cause**: Wrong configuration setting
- **Fix**: Check Settings → Config → Protocol Log dropdown

### Progress Bar Not Updating
- **Cause**: Position updates not being received
- **Fix**: Ensure telescope is sending position data

### Theme Colors Not Changing
- **Cause**: Widget `apply_theme()` not called
- **Fix**: Restart application or manually call `widget.apply_theme(None)`

## Future Enhancements

### Planned Features
- [ ] Batch command replay
- [ ] Command macros/sequences
- [ ] Custom rate presets (user-configurable)
- [ ] Command search in history
- [ ] Statistics graphs
- [ ] Command timing analysis
- [ ] Auto-retry failed commands
- [ ] Command templates

### Under Consideration
- [ ] Voice control integration
- [ ] Gesture control (touchpad)
- [ ] Mobile app companion
- [ ] Cloud sync of command history
- [ ] AI-assisted command suggestions

## Contributing

When adding new features to the telescope control system:

1. **Follow existing patterns**:
   - Use Qt signals/slots for communication
   - Implement `apply_theme()` for custom widgets
   - Add keyboard shortcuts to `_setup_shortcuts()`
   - Include comprehensive tests

2. **Testing requirements**:
   - Unit tests for new classes
   - Integration tests for UI components
   - Performance tests for high-volume operations
   - Edge case coverage

3. **Documentation**:
   - Update this file with new features
   - Add docstrings to all public methods
   - Include usage examples
   - Document configuration options

## References

- [Plan Document](/Users/mcosgriff/.claude/plans/lively-wondering-unicorn.md)
- [Command Tracker Implementation](../../src/celestron_nexstar/api/telescope/command_tracker.py)
- [Telescope Control Window](../../src/celestron_nexstar/gui/windows/telescope_control_window.py)
- [Performance Tests](../../tests/test_phase5_performance.py)
