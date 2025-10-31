# COSMOS/OpenC3 Integration Guide for Celestron NexStar

This guide shows how to integrate the Celestron NexStar telescope with COSMOS (now OpenC3), a command and control system designed for controlling embedded systems and hardware.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Plugin Structure](#plugin-structure)
- [Configuration Files](#configuration-files)
- [Python Interface Script](#python-interface-script)
- [Installation](#installation)
- [Usage](#usage)
- [Telemetry Screens](#telemetry-screens)
- [Advanced Features](#advanced-features)

## Overview

COSMOS/OpenC3 is a suite of applications designed to control embedded systems. This integration allows you to:

- **Send commands** to the telescope (goto, track, move, etc.)
- **Monitor telemetry** (position, tracking mode, location, etc.)
- **Create custom screens** for telescope control
- **Log all operations** for analysis
- **Script complex operations** using Ruby or Python

### Why Use COSMOS?

- ✅ **Web-based interface** - Control from any browser
- ✅ **Real-time telemetry** - Monitor position continuously
- ✅ **Command logging** - Track all operations
- ✅ **Scripting support** - Automate complex sequences
- ✅ **Multiple users** - Collaborative observing sessions
- ✅ **Historical data** - Review past observations

## Architecture

```text
┌────────────────────────────────────────────────────────┐
│                    COSMOS/OpenC3                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Command   │  │  Telemetry   │  │   Scripts    │   │
│  │   Sender    │  │   Monitor    │  │              │   │
│  └──────┬──────┘  └──────▲───────┘  └──────────────┘   │
│         │                │                             │
│         ▼                │                             │
│  ┌──────────────────────────────────┐                  │
│  │  Serial/TCP Interface            │                  │
│  └────────────┬──────────▲──────────┘                  │
└───────────────┼──────────┼─────────────────────────────┘
                │          │
                ▼          │
         ┌──────────────────────────┐
         │  Python Bridge Script    │
         │  (celestron_interface.py)│
         └──────────┬──────▲────────┘
                    │      │
                    ▼      │
         ┌────────────────────────┐
         │  Celestron NexStar     │
         │  Python Library        │
         └──────────┬──────▲──────┘
                    │      │
                    ▼      │
              ┌──────────────────┐
              │  NexStar 6SE     │
              │  Telescope       │
              │  (Serial/USB)    │
              └──────────────────┘
```

## Plugin Structure

Create a COSMOS plugin with this structure:

```text
openc3-cosmos-celestron/
├── plugin.txt                      # Plugin definition
├── targets/
│   └── CELESTRON/
│       ├── cmd_tlm/
│       │   ├── cmd.txt            # Command definitions
│       │   └── tlm.txt            # Telemetry definitions
│       ├── lib/
│       │   └── celestron_interface.py  # Python bridge
│       ├── screens/
│       │   ├── telescope_control.txt   # Main control screen
│       │   └── position_monitor.txt    # Position display
│       └── procedures/
│           ├── goto_target.rb          # Ruby script examples
│           └── calibrate.rb
└── targets.txt                     # Target configuration
```

## Configuration Files

### 1. Plugin Definition (`plugin.txt`)

```ruby
VARIABLE celestron_plugin_name openc3-cosmos-celestron

TARGET CELESTRON <%= celestron_plugin_name %>
```

### 2. Target Configuration (`targets.txt`)

```ruby
# Celestron NexStar Telescope Target
TARGET CELESTRON CELESTRON
  IGNORE_PARAMETER CMD_PARAMS

  # Serial interface configuration
  INTERFACE CELESTRON_INT serial_interface.rb /dev/ttyUSB0 9600 NONE 1 5.0 5.0
    OPTION FLOW_CONTROL NONE
    OPTION DATA_BITS 8
    OPTION STOP_BITS 1
    OPTION PARITY NONE
```

### 3. Command Definitions (`targets/CELESTRON/cmd_tlm/cmd.txt`)

```ruby
# Celestron NexStar Command Definitions

# ============================================================================
# Connection Commands
# ============================================================================

COMMAND CELESTRON CONNECT BIG_ENDIAN "Connect to telescope"
  APPEND_PARAMETER ECHO_CHAR 8 STRING "x" "Character for echo test"

COMMAND CELESTRON DISCONNECT BIG_ENDIAN "Disconnect from telescope"

COMMAND CELESTRON ECHO_TEST BIG_ENDIAN "Test connection"
  APPEND_PARAMETER TEST_CHAR 8 STRING "x" "Character to echo"

# ============================================================================
# Information Commands
# ============================================================================

COMMAND CELESTRON GET_VERSION BIG_ENDIAN "Get firmware version"

COMMAND CELESTRON GET_MODEL BIG_ENDIAN "Get telescope model"

COMMAND CELESTRON GET_INFO BIG_ENDIAN "Get complete telescope info"

# ============================================================================
# Position Commands
# ============================================================================

COMMAND CELESTRON GET_POSITION_RA_DEC BIG_ENDIAN "Get RA/Dec position"

COMMAND CELESTRON GET_POSITION_ALT_AZ BIG_ENDIAN "Get Alt/Az position"

# ============================================================================
# Movement Commands
# ============================================================================

COMMAND CELESTRON GOTO_RA_DEC BIG_ENDIAN "Slew to RA/Dec coordinates"
  APPEND_PARAMETER RA_HOURS 32 FLOAT 0.0 24.0 12.0 "Right Ascension in hours"
    UNITS hours h
  APPEND_PARAMETER DEC_DEGREES 32 FLOAT -90.0 90.0 0.0 "Declination in degrees"
    UNITS degrees deg

COMMAND CELESTRON GOTO_ALT_AZ BIG_ENDIAN "Slew to Alt/Az coordinates"
  APPEND_PARAMETER AZIMUTH 32 FLOAT 0.0 360.0 0.0 "Azimuth in degrees"
    UNITS degrees deg
  APPEND_PARAMETER ALTITUDE 32 FLOAT -90.0 90.0 0.0 "Altitude in degrees"
    UNITS degrees deg

COMMAND CELESTRON SYNC_RA_DEC BIG_ENDIAN "Sync position to RA/Dec coordinates"
  APPEND_PARAMETER RA_HOURS 32 FLOAT 0.0 24.0 12.0 "Right Ascension in hours"
    UNITS hours h
  APPEND_PARAMETER DEC_DEGREES 32 FLOAT -90.0 90.0 0.0 "Declination in degrees"
    UNITS degrees deg

COMMAND CELESTRON MOVE_FIXED BIG_ENDIAN "Move telescope in direction"
  APPEND_PARAMETER DIRECTION 8 STRING "up" "Direction: up, down, left, right"
    STATE up UP
    STATE down DOWN
    STATE left LEFT
    STATE right RIGHT
  APPEND_PARAMETER RATE 8 UINT 0 9 5 "Movement rate (0-9)"

COMMAND CELESTRON STOP_MOTION BIG_ENDIAN "Stop telescope motion"
  APPEND_PARAMETER AXIS 8 STRING "both" "Axis to stop: az, alt, both"
    STATE azimuth az
    STATE altitude alt
    STATE both both

COMMAND CELESTRON IS_SLEWING BIG_ENDIAN "Check if telescope is slewing"

COMMAND CELESTRON CANCEL_GOTO BIG_ENDIAN "Cancel current goto operation"

# ============================================================================
# Tracking Commands
# ============================================================================

COMMAND CELESTRON GET_TRACKING_MODE BIG_ENDIAN "Get current tracking mode"

COMMAND CELESTRON SET_TRACKING_MODE BIG_ENDIAN "Set tracking mode"
  APPEND_PARAMETER MODE 8 UINT 0 3 1 "Tracking mode"
    STATE OFF 0
    STATE ALT_AZ 1
    STATE EQ_NORTH 2
    STATE EQ_SOUTH 3

# ============================================================================
# Location and Time Commands
# ============================================================================

COMMAND CELESTRON GET_LOCATION BIG_ENDIAN "Get observer location"

COMMAND CELESTRON SET_LOCATION BIG_ENDIAN "Set observer location"
  APPEND_PARAMETER LATITUDE 32 FLOAT -90.0 90.0 0.0 "Latitude in degrees"
    UNITS degrees deg
  APPEND_PARAMETER LONGITUDE 32 FLOAT -180.0 180.0 0.0 "Longitude in degrees"
    UNITS degrees deg

COMMAND CELESTRON GET_TIME BIG_ENDIAN "Get telescope date/time"

COMMAND CELESTRON SET_TIME BIG_ENDIAN "Set telescope date/time"
  APPEND_PARAMETER HOUR 8 UINT 0 23 12 "Hour (0-23)"
  APPEND_PARAMETER MINUTE 8 UINT 0 59 0 "Minute (0-59)"
  APPEND_PARAMETER SECOND 8 UINT 0 59 0 "Second (0-59)"
  APPEND_PARAMETER MONTH 8 UINT 1 12 1 "Month (1-12)"
  APPEND_PARAMETER DAY 8 UINT 1 31 1 "Day (1-31)"
  APPEND_PARAMETER YEAR 16 UINT 2000 2100 2024 "Year"
  APPEND_PARAMETER TIMEZONE 8 INT -12 12 0 "Timezone offset"
    UNITS hours h
  APPEND_PARAMETER DST 8 UINT 0 1 0 "Daylight savings (0 or 1)"
```

### 4. Telemetry Definitions (`targets/CELESTRON/cmd_tlm/tlm.txt`)

```ruby
# Celestron NexStar Telemetry Definitions

# ============================================================================
# Position Telemetry
# ============================================================================

TELEMETRY CELESTRON POSITION_RA_DEC BIG_ENDIAN "RA/Dec Position"
  APPEND_ITEM TIMESTAMP 64 FLOAT "Timestamp"
    UNITS seconds s
  APPEND_ITEM RA_HOURS 32 FLOAT "Right Ascension"
    UNITS hours h
    FORMAT_STRING "%.4f"
  APPEND_ITEM DEC_DEGREES 32 FLOAT "Declination"
    UNITS degrees deg
    FORMAT_STRING "%+.4f"
  APPEND_ITEM RA_FORMATTED 256 STRING "RA Formatted (HH:MM:SS)"
  APPEND_ITEM DEC_FORMATTED 256 STRING "Dec Formatted (DD:MM:SS)"

TELEMETRY CELESTRON POSITION_ALT_AZ BIG_ENDIAN "Alt/Az Position"
  APPEND_ITEM TIMESTAMP 64 FLOAT "Timestamp"
    UNITS seconds s
  APPEND_ITEM AZIMUTH 32 FLOAT "Azimuth"
    UNITS degrees deg
    FORMAT_STRING "%.2f"
  APPEND_ITEM ALTITUDE 32 FLOAT "Altitude"
    UNITS degrees deg
    FORMAT_STRING "%+.2f"

# ============================================================================
# Status Telemetry
# ============================================================================

TELEMETRY CELESTRON STATUS BIG_ENDIAN "Telescope Status"
  APPEND_ITEM TIMESTAMP 64 FLOAT "Timestamp"
  APPEND_ITEM CONNECTED 8 UINT "Connection status"
    STATE DISCONNECTED 0 RED
    STATE CONNECTED 1 GREEN
  APPEND_ITEM IS_SLEWING 8 UINT "Slewing status"
    STATE STATIONARY 0 GREEN
    STATE SLEWING 1 YELLOW
  APPEND_ITEM TRACKING_MODE 8 UINT "Tracking mode"
    STATE OFF 0 YELLOW
    STATE ALT_AZ 1 GREEN
    STATE EQ_NORTH 2 GREEN
    STATE EQ_SOUTH 3 GREEN
  APPEND_ITEM MODEL 8 UINT "Telescope model"
  APPEND_ITEM FIRMWARE_MAJOR 8 UINT "Firmware major version"
  APPEND_ITEM FIRMWARE_MINOR 8 UINT "Firmware minor version"

# ============================================================================
# Location Telemetry
# ============================================================================

TELEMETRY CELESTRON LOCATION BIG_ENDIAN "Observer Location"
  APPEND_ITEM TIMESTAMP 64 FLOAT "Timestamp"
  APPEND_ITEM LATITUDE 32 FLOAT "Latitude"
    UNITS degrees deg
    FORMAT_STRING "%+.4f"
  APPEND_ITEM LONGITUDE 32 FLOAT "Longitude"
    UNITS degrees deg
    FORMAT_STRING "%+.4f"

# ============================================================================
# Time Telemetry
# ============================================================================

TELEMETRY CELESTRON TIME BIG_ENDIAN "Telescope Time"
  APPEND_ITEM TIMESTAMP 64 FLOAT "Timestamp"
  APPEND_ITEM YEAR 16 UINT "Year"
  APPEND_ITEM MONTH 8 UINT "Month"
  APPEND_ITEM DAY 8 UINT "Day"
  APPEND_ITEM HOUR 8 UINT "Hour"
  APPEND_ITEM MINUTE 8 UINT "Minute"
  APPEND_ITEM SECOND 8 UINT "Second"
  APPEND_ITEM TIMEZONE 8 INT "Timezone offset"
  APPEND_ITEM DST 8 UINT "Daylight savings"
```

## Python Interface Script

Create `targets/CELESTRON/lib/celestron_interface.py`:

```python
#!/usr/bin/env python3
"""
COSMOS/OpenC3 Interface for Celestron NexStar Telescope

This script acts as a bridge between COSMOS and the Celestron Python library.
It listens for commands from COSMOS and sends back telemetry.
"""

import sys
import time
import json
import struct
import threading
from datetime import datetime
from celestron_nexstar import NexStarTelescope, TrackingMode
from celestron_nexstar.utils import format_ra, format_dec


class CosmosTelescopeInterface:
    """Interface between COSMOS and Celestron telescope."""

    def __init__(self, port='/dev/ttyUSB0'):
        """
        Initialize interface.

        Args:
            port: Serial port for telescope
        """
        self.telescope = NexStarTelescope(port)
        self.connected = False
        self.running = True

        # Background telemetry thread
        self.telemetry_thread = None

    def connect(self):
        """Connect to telescope."""
        try:
            self.telescope.connect()
            self.connected = True
            self.send_response({'status': 'connected'})

            # Start telemetry thread
            self.start_telemetry()

        except Exception as e:
            self.send_response({'status': 'error', 'message': str(e)})

    def disconnect(self):
        """Disconnect from telescope."""
        self.connected = False
        self.telescope.disconnect()
        self.send_response({'status': 'disconnected'})

    def start_telemetry(self):
        """Start background telemetry collection."""
        if self.telemetry_thread is None or not self.telemetry_thread.is_alive():
            self.telemetry_thread = threading.Thread(
                target=self._telemetry_loop,
                daemon=True
            )
            self.telemetry_thread.start()

    def _telemetry_loop(self):
        """Background loop to send telemetry."""
        while self.connected and self.running:
            try:
                # Send position telemetry
                self.send_position_telemetry()

                # Send status telemetry
                self.send_status_telemetry()

                # Wait before next update
                time.sleep(1.0)

            except Exception as e:
                print(f"Telemetry error: {e}", file=sys.stderr)
                time.sleep(1.0)

    def send_position_telemetry(self):
        """Send RA/Dec and Alt/Az position telemetry."""
        # Get RA/Dec position
        ra_dec = self.telescope.get_position_ra_dec()
        self.send_telemetry('POSITION_RA_DEC', {
            'timestamp': time.time(),
            'ra_hours': ra_dec.ra_hours,
            'dec_degrees': ra_dec.dec_degrees,
            'ra_formatted': format_ra(ra_dec.ra_hours),
            'dec_formatted': format_dec(ra_dec.dec_degrees)
        })

        # Get Alt/Az position
        alt_az = self.telescope.get_position_alt_az()
        self.send_telemetry('POSITION_ALT_AZ', {
            'timestamp': time.time(),
            'azimuth': alt_az.azimuth,
            'altitude': alt_az.altitude
        })

    def send_status_telemetry(self):
        """Send telescope status telemetry."""
        info = self.telescope.get_info()
        tracking_mode = self.telescope.get_tracking_mode()
        is_slewing = self.telescope.is_slewing()

        self.send_telemetry('STATUS', {
            'timestamp': time.time(),
            'connected': 1 if self.connected else 0,
            'is_slewing': 1 if is_slewing else 0,
            'tracking_mode': tracking_mode.value,
            'model': info.model,
            'firmware_major': info.firmware_major,
            'firmware_minor': info.firmware_minor
        })

    def send_telemetry(self, packet_name, data):
        """
        Send telemetry packet to COSMOS.

        Args:
            packet_name: Name of telemetry packet
            data: Dictionary of telemetry data
        """
        packet = {
            'type': 'TELEMETRY',
            'target': 'CELESTRON',
            'packet': packet_name,
            'data': data
        }
        print(json.dumps(packet), flush=True)

    def send_response(self, response):
        """Send command response."""
        print(json.dumps(response), flush=True)

    def handle_command(self, command):
        """
        Handle incoming command from COSMOS.

        Args:
            command: Command dictionary
        """
        cmd_name = command.get('command')
        params = command.get('params', {})

        try:
            if cmd_name == 'CONNECT':
                self.connect()

            elif cmd_name == 'DISCONNECT':
                self.disconnect()

            elif cmd_name == 'GOTO_RA_DEC':
                ra = params['RA_HOURS']
                dec = params['DEC_DEGREES']
                result = self.telescope.goto_ra_dec(ra, dec)
                self.send_response({'status': 'success', 'result': result})

            elif cmd_name == 'GOTO_ALT_AZ':
                az = params['AZIMUTH']
                alt = params['ALTITUDE']
                result = self.telescope.goto_alt_az(az, alt)
                self.send_response({'status': 'success', 'result': result})

            elif cmd_name == 'SET_TRACKING_MODE':
                mode = TrackingMode(params['MODE'])
                result = self.telescope.set_tracking_mode(mode)
                self.send_response({'status': 'success', 'result': result})

            elif cmd_name == 'MOVE_FIXED':
                direction = params['DIRECTION']
                rate = params['RATE']
                result = self.telescope.move_fixed(direction, rate)
                self.send_response({'status': 'success', 'result': result})

            elif cmd_name == 'STOP_MOTION':
                axis = params.get('AXIS', 'both')
                result = self.telescope.stop_motion(axis)
                self.send_response({'status': 'success', 'result': result})

            # Add more command handlers as needed...

        except Exception as e:
            self.send_response({'status': 'error', 'message': str(e)})

    def run(self):
        """Main loop - read commands from stdin."""
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                command = json.loads(line)
                self.handle_command(command)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)


if __name__ == '__main__':
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
    interface = CosmosTelescopeInterface(port)
    interface.run()
```

## Installation

### 1. Install COSMOS/OpenC3

Follow the official installation guide at <https://docs.openc3.com/docs/getting-started/installation>

### 2. Install Python Dependencies

```bash
# Install the Celestron library
cd /path/to/celestron-nexstar
uv sync --all-extras

# Or using pip
pip install .
```

### 3. Create Plugin Package

```bash
# Create plugin directory structure
mkdir -p openc3-cosmos-celestron/targets/CELESTRON/{cmd_tlm,lib,screens,procedures}

# Copy configuration files (created above)
# Copy Python interface script
```

### 4. Install Plugin in COSMOS

```bash
# Build and install plugin
openc3 cli load openc3-cosmos-celestron
```

## Usage

### 1. Start COSMOS

```bash
openc3 start
```

### 2. Access Web Interface

Open browser to `http://localhost:2900`

### 3. Send Commands

Using Command Sender:

1. Select target: `CELESTRON`
2. Select command: `GOTO_RA_DEC`
3. Enter parameters:
   - RA_HOURS: 12.5
   - DEC_DEGREES: 45.0
4. Click "Send"

### 4. Monitor Telemetry

Using Telemetry Viewer:

1. Select `CELESTRON POSITION_RA_DEC`
2. Watch real-time position updates

## Telemetry Screens

Create custom screens in `targets/CELESTRON/screens/telescope_control.txt`:

```ruby
SCREEN AUTO AUTO 1.0

VERTICAL
  TITLE "Celestron NexStar Control"

  # Status Section
  VERTICALBOX "Status"
    HORIZONTAL
      LABEL "Connected: "
      VALUE CELESTRON STATUS CONNECTED
      LABEL "Slewing: "
      VALUE CELESTRON STATUS IS_SLEWING
      LABEL "Tracking: "
      VALUE CELESTRON STATUS TRACKING_MODE
    END
  END

  # Position Display
  VERTICALBOX "Current Position"
    HORIZONTAL
      LABEL "RA: "
      VALUE CELESTRON POSITION_RA_DEC RA_FORMATTED WITH_UNITS 20
    END
    HORIZONTAL
      LABEL "Dec: "
      VALUE CELESTRON POSITION_RA_DEC DEC_FORMATTED WITH_UNITS 20
    END
    HORIZONTAL
      LABEL "Az: "
      VALUE CELESTRON POSITION_ALT_AZ AZIMUTH WITH_UNITS 15
    END
    HORIZONTAL
      LABEL "Alt: "
      VALUE CELESTRON POSITION_ALT_AZ ALTITUDE WITH_UNITS 15
    END
  END

  # Command Buttons
  VERTICALBOX "Quick Commands"
    HORIZONTAL
      BUTTON "Connect" "cmd('CELESTRON CONNECT with ECHO_CHAR x')"
      BUTTON "Disconnect" "cmd('CELESTRON DISCONNECT')"
    END
    HORIZONTAL
      BUTTON "Track Alt/Az" "cmd('CELESTRON SET_TRACKING_MODE with MODE 1')"
      BUTTON "Track OFF" "cmd('CELESTRON SET_TRACKING_MODE with MODE 0')"
    END
    HORIZONTAL
      BUTTON "Stop Motion" "cmd('CELESTRON STOP_MOTION with AXIS both')"
      BUTTON "Cancel Goto" "cmd('CELESTRON CANCEL_GOTO')"
    END
  END
END
```

## Advanced Features

### Scripting with Ruby

Create automated sequences in `targets/CELESTRON/procedures/goto_target.rb`:

```ruby
# Slew to specific target
def goto_polaris
  cmd("CELESTRON GOTO_RA_DEC with RA_HOURS 2.5303, DEC_DEGREES 89.2641")

  # Wait for slew to complete
  wait_check("CELESTRON STATUS IS_SLEWING == 0", 60)

  # Enable tracking
  cmd("CELESTRON SET_TRACKING_MODE with MODE 1")

  puts "Arrived at Polaris!"
end
```

### Telemetry Logging

All telemetry is automatically logged by COSMOS and can be:

- Viewed in Telemetry Grapher
- Exported to CSV
- Analyzed with Data Viewer

### Limits and Alerts

Add limits to telemetry items:

```ruby
LIMITS DEFAULT 3 ENABLED -90.0 -45.0 45.0 90.0 -90.0 90.0
LIMITS_RESPONSE ALTITUDE_OUT_OF_RANGE
```

## Troubleshooting

### Serial Port Issues

- Ensure telescope is connected
- Check port name in configuration
- Verify permissions: `sudo chmod 666 /dev/ttyUSB0`

### Telemetry Not Updating

- Check Python interface is running
- Verify telescope connection
- Check COSMOS logs

### Commands Not Working

- Verify command syntax in cmd.txt
- Check parameter types match
- Review Python interface error logs

## Resources

- [OpenC3 Documentation](https://docs.openc3.com/docs)
- [Celestron NexStar Library](../README.md)
- [Example Configurations](https://github.com/OpenC3/cosmos)

## Contributing

Improvements to this integration are welcome! Please submit issues or pull requests.
