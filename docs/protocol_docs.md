# NexStar Communication Protocol (`protocol.py`)

## Overview

This module provides a low-level implementation of the NexStar serial communication protocol used for controlling Celestron telescopes. It handles the core functionalities of serial communication, including command formatting, response parsing, and coordinate encoding/decoding.

### Protocol Specification

- **Baud Rate**: 9600
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Terminator**: `#` character
- **Coordinate Format**: 32-bit hexadecimal (0x00000000 to 0xFFFFFFFF, representing 0° to 360°)

## `NexStarProtocol` Class

This class encapsulates the low-level details of the NexStar protocol.

### Initialization

To use the protocol, create an instance of the `NexStarProtocol` class:

```python
from celestron_nexstar.protocol import NexStarProtocol

# Replace '/dev/tty.usbmodem14201' with your serial port
protocol = NexStarProtocol(port='/dev/tty.usbmodem14201')
```

The constructor accepts the following arguments:

- `port` (str): The serial port path for the telescope connection.
- `baudrate` (int, optional): The communication speed. Defaults to `9600`.
- `timeout` (float, optional): The serial timeout in seconds. Defaults to `2.0`.

### Connection Management

#### `open()`

Opens the serial connection to the telescope.

- **Returns**: `True` if the connection is successful.
- **Raises**: `TelescopeConnectionError` if the serial port cannot be opened.

```python
try:
    protocol.open()
    print("Connection successful!")
except TelescopeConnectionError as e:
    print(f"Failed to connect: {e}")
```

#### `close()`

Closes the serial connection.

```python
protocol.close()
```

#### `is_open()`

Checks if the connection is currently open.

- **Returns**: `True` if the connection is open, `False` otherwise.

### Command Sending

#### `send_command(command: str)`

Sends a command to the telescope and waits for a response.

- **Arguments**:
  - `command` (str): The command string to send (without the `#` terminator).
- **Returns**: The response string from the telescope (without the `#` terminator).
- **Raises**:
  - `NotConnectedError`: If the serial port is not open.
  - `TelescopeTimeoutError`: If no response is received within the timeout period.

### Coordinate Encoding/Decoding

The protocol includes static methods for handling the NexStar coordinate format.

- `degrees_to_hex(degrees: float)`: Converts degrees (0-360) to an 8-character hexadecimal string.
- `hex_to_degrees(hex_str: str)`: Converts an 8-character hexadecimal string to degrees.
- `encode_coordinate_pair(value1: float, value2: float)`: Encodes a pair of degree values into the "XXXXXXXX,YYYYYYYY" format.
- `decode_coordinate_pair(response: str)`: Decodes a "XXXXXXXX,YYYYYYYY" string into a tuple of two floats.

### Protocol Commands

The following methods implement specific NexStar protocol commands:

| Method | Description | Command | Response |
| --- | --- | --- | --- |
| `echo(char: str)` | Tests the connection. | `K<char>#` | `<char>#` |
| `get_version()` | Gets the firmware version. | `V#` | `<major><minor>#` |
| `get_model()` | Gets the telescope model number. | `m#` | `<model>#` |
| `get_ra_dec_precise()` | Gets the precise RA/Dec position. | `E#` | `RRRRRRR,DDDDDDDDD#` |
| `get_alt_az_precise()` | Gets the precise Alt/Az position. | `Z#` | `AAAAAAAA,EEEEEEEE#` |
| `goto_ra_dec_precise(ra, dec)` | Slews to RA/Dec coordinates. | `R<RA>,<DEC>#` | `#` |
| `goto_alt_az_precise(az, alt)` | Slews to Alt/Az coordinates. | `B<AZ>,<ALT>#` | `#` |
| `sync_ra_dec_precise(ra, dec)` | Syncs to RA/Dec coordinates. | `S<RA>,<DEC>#` | `#` |
| `is_goto_in_progress()` | Checks if a goto is in progress. | `L#` | `0#` or `1#` |
| `cancel_goto()` | Cancels the current goto. | `M#` | `#` |
| `variable_rate_motion(...)` | Initiates variable rate motion. | `P<params>#` | `#` |
| `get_tracking_mode()` | Gets the tracking mode. | `t#` | `<mode>#` |
| `set_tracking_mode(mode)` | Sets the tracking mode. | `T<mode>#` | `#` |
| `get_location()` | Gets the observer's location. | `w#` | `<lat><lon>#` |
| `set_location(lat, lon)` | Sets the observer's location. | `W<lat>,<lon>#` | `#` |
| `get_time()` | Gets the date and time. | `h#` | `<time_bytes>#` |
| `set_time(...)` | Sets the date and time. | `H<time_bytes>#` | `#` |
