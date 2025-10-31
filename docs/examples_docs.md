# Basic Demo (`basic_demo.py`)

## Overview

This script provides a basic demonstration of how to use the `celestron_nexstar` library to control a telescope. It covers the fundamental operations of connecting, retrieving information, and getting the telescope's current position.

## How to Run the Demo

1.  **Connect your telescope**: Ensure your Celestron telescope is connected to your computer via the appropriate serial or USB cable.
2.  **Identify your serial port**:
    -   **macOS**: `/dev/tty.usbserial-XXXXX`
    -   **Linux**: `/dev/ttyUSB0`
    -   **Windows**: `COM3`
3.  **Update the script**: Open `basic_demo.py` and change the `port` argument in the `NexStarTelescope` constructor to match your serial port.
4.  **Run from the command line** (if the script exists):
    ```bash
    uv run python examples/simple_position_tracking.py
    ```
    Note: The `nexstar-demo` script was removed. Use the example scripts in the `examples/` directory instead.

## Script Functionality

The demo performs the following actions:

1.  **Initializes `NexStarTelescope`**: Creates an instance of the main telescope control class.
2.  **Connects to the telescope**: Establishes a serial connection.
3.  **Retrieves and prints**:
    -   Firmware version
    -   Telescope model number
    -   Current position in both RA/Dec and Alt/Az coordinates
    -   Current tracking mode
    -   Observer's location
4.  **Disconnects**: Safely closes the connection to the telescope.
