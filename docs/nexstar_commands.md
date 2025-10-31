# Celestron NexStar Raw Command Reference

## Protocol Specification

### Serial Communication Settings

- **Baud Rate**: 9600
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Flow Control**: None
- **Terminator**: `#` (ASCII character 0x23)

### Command Format

All commands follow this pattern:

- Commands are ASCII strings
- Each command must end with `#` character
- Responses also end with `#` character
- The terminator is stripped from response data

---

## Coordinate Encoding Format

The NexStar protocol uses 32-bit hexadecimal encoding for all angular measurements.

### Encoding Formula

```text
hex_value = int((degrees / 360.0) * 0x100000000)
hex_string = format(hex_value, '08X')  # 8-character uppercase hex
```

### Decoding Formula

```text
degrees = (hex_value / 0x100000000) * 360.0
```

### Range Mapping

- `0x00000000` = 0°
- `0x40000000` = 90°
- `0x80000000` = 180°
- `0xC0000000` = 270°
- `0xFFFFFFFF` = 360° (wraps to 0°)

### Coordinate Pair Format

When sending or receiving coordinate pairs (RA/Dec or Az/Alt):

```text
Format: "XXXXXXXX,YYYYYYYY"
        ^8 chars ^8 chars
        Total: 17 characters (16 hex + 1 comma)
```

### Negative Angles

For coordinates that can be negative (like Declination and Altitude):

- Positive: Use direct value (0° to 180°)
- Negative: Use 360° + value (e.g., -45° becomes 315°)

---

## Complete Command Reference

### 1. Connection Test Commands

#### Echo Test

**Purpose**: Test serial connection and verify communication

**Command**: `K<char>#`

- `<char>`: Any single ASCII character

**Response**: `<char>#`

- Returns the same character that was sent

**Example**:

```text
Send:    Kx#
Receive: x#
```

**Implementation Reference**: `protocol.py:276`

---

### 2. Information Query Commands

#### Get Firmware Version

**Purpose**: Retrieve telescope firmware version

**Command**: `V#`

**Response**: `<major><minor>#`

- `<major>`: Major version number (1 byte)
- `<minor>`: Minor version number (1 byte)

**Example**:

```text
Send:    V#
Receive: \x04\x0E#  (Version 4.14)
```

**Implementation Reference**: `protocol.py:294`

---

#### Get Telescope Model

**Purpose**: Retrieve telescope model number

**Command**: `m#`

**Response**: `<model>#`

- `<model>`: Model number (1 byte)
  - `6` = NexStar 6SE
  - `8` = NexStar 8SE
  - Other values for different models

**Example**:

```text
Send:    m#
Receive: \x06#  (NexStar 6SE)
```

**Implementation Reference**: `protocol.py:306`

---

### 3. Position Query Commands

#### Get Precise RA/Dec Position

**Purpose**: Get current Right Ascension and Declination in precise format

**Command**: `E#`

**Response**: `RRRRRRR,DDDDDDDDD#`

- `RRRRRRR`: RA in hex (8 chars)
- `DDDDDDDDD`: Dec in hex (8 chars)
- Total: 17 characters (excluding terminator)

**Coordinate Interpretation**:

- RA: 0x00000000 to 0xFFFFFFFF = 0° to 360° (or 0 to 24 hours)
- Dec: Use signed conversion (0-180° positive, 180-360° represents negative)

**Example**:

```text
Send:    E#
Receive: 12AB34CD,89EF0123#
```

**Decoding**:

```python
ra_hex = "12AB34CD"
dec_hex = "89EF0123"
ra_degrees = (int(ra_hex, 16) / 0x100000000) * 360.0
dec_degrees = (int(dec_hex, 16) / 0x100000000) * 360.0
# Convert dec to signed if > 180
if dec_degrees > 180:
    dec_degrees = dec_degrees - 360
```

**Implementation Reference**: `protocol.py:318`

---

#### Get Precise Alt/Az Position

**Purpose**: Get current Azimuth and Altitude in precise format

**Command**: `Z#`

**Response**: `AAAAAAAA,EEEEEEEE#`

- `AAAAAAAA`: Azimuth in hex (8 chars)
- `EEEEEEEE`: Altitude in hex (8 chars)
- Total: 17 characters (excluding terminator)

**Coordinate Interpretation**:

- Az: 0x00000000 to 0xFFFFFFFF = 0° to 360° (0° = North, 90° = East)
- Alt: Use signed conversion (0-90° positive, >180° represents negative)

**Example**:

```text
Send:    Z#
Receive: 40000000,20000000#
```

**Implementation Reference**: `protocol.py:330`

---

### 4. Slew Commands (Goto)

#### Goto RA/Dec Precise

**Purpose**: Slew telescope to specified RA/Dec coordinates

**Command**: `R<RA>,<DEC>#`

- `<RA>`: Right Ascension in hex (8 chars)
- `<DEC>`: Declination in hex (8 chars)

**Response**: `#` (empty response indicates success)

**Example** (Goto RA=0°, Dec=45°):

```text
RA:  0° → 0x00000000 → "00000000"
Dec: 45° → 0x20000000 → "20000000"
Send: R00000000,20000000#
Receive: #
```

**Example** (Goto RA=180°, Dec=-30°):

```text
RA:  180° → 0x80000000 → "80000000"
Dec: -30° → 330° → 0xE8000000 → "E8000000"
Send: R80000000,E8000000#
Receive: #
```

**Implementation Reference**: `protocol.py:343`

---

#### Goto Alt/Az Precise

**Purpose**: Slew telescope to specified Azimuth/Altitude coordinates

**Command**: `B<AZ>,<ALT>#`

- `<AZ>`: Azimuth in hex (8 chars)
- `<ALT>`: Altitude in hex (8 chars)

**Response**: `#` (empty response indicates success)

**Example** (Goto Az=90° East, Alt=45°):

```text
Az:  90° → 0x40000000 → "40000000"
Alt: 45° → 0x20000000 → "20000000"
Send: B40000000,20000000#
Receive: #
```

**Implementation Reference**: `protocol.py:360`

---

### 5. Alignment Commands

#### Sync RA/Dec Precise

**Purpose**: Synchronize telescope's current position to specified RA/Dec coordinates (for alignment)

**Command**: `S<RA>,<DEC>#`

- `<RA>`: Right Ascension in hex (8 chars)
- `<DEC>`: Declination in hex (8 chars)

**Response**: `#` (empty response indicates success)

**Usage**:

1. Manually center a known star
2. Send sync command with the star's known coordinates
3. Improves pointing accuracy

**Example** (Sync to RA=6h, Dec=23.5°):

```text
RA:  6h = 90° → 0x40000000 → "40000000"
Dec: 23.5° → 0x0A666666 → "0A666666"
Send: S40000000,0A666666#
Receive: #
```

**Implementation Reference**: `protocol.py:377`

---

### 6. Motion Control Commands

#### Check Goto Status

**Purpose**: Determine if a slew operation is in progress

**Command**: `L#`

**Response**:

- `0#` - Telescope is stationary (goto complete)
- `1#` - Telescope is slewing (goto in progress)

**Example**:

```text
Send:    L#
Receive: 1#  (currently slewing)
```

**Usage**: Poll this command to wait for slew completion

```python
while send_command("L") == "1":
    time.sleep(0.5)  # Wait 500ms
# Slew complete
```

**Implementation Reference**: `protocol.py:393`

---

#### Cancel Goto

**Purpose**: Immediately stop current slew operation

**Command**: `M#`

**Response**: `#` (empty response indicates success)

**Example**:

```text
Send:    M#
Receive: #
```

**Implementation Reference**: `protocol.py:405`

---

#### Variable Rate Motion

**Purpose**: Move telescope at variable rates in azimuth or altitude

**Command**: `P<axis><direction><rate><0><0><0>#`

**Parameters** (all single bytes):

- `<axis>`:
  - `\x01` (1) = Azimuth (horizontal)
  - `\x02` (2) = Altitude (vertical)
- `<direction>`:
  - `\x11` (17) = Positive direction
  - `\x12` (18) = Negative direction
- `<rate>`: Speed (0-9)
  - `\x00` (0) = Stop motion
  - `\x01` (1) = Slowest
  - `\x09` (9) = Fastest
- Last three bytes are always `\x00`

**Response**: `#` (empty response indicates success)

**Direction Mapping**:

- Azimuth positive (17) = Counterclockwise (East)
- Azimuth negative (18) = Clockwise (West)
- Altitude positive (17) = Up
- Altitude negative (18) = Down

**Examples**:

Move up at medium speed (rate 5):

```text
Send: P\x02\x11\x05\x00\x00\x00#
      (axis=2, dir=17, rate=5)
Receive: #
```

Move right (clockwise) at fast speed (rate 9):

```text
Send: P\x01\x12\x09\x00\x00\x00#
      (axis=1, dir=18, rate=9)
Receive: #
```

Stop altitude motion:

```text
Send: P\x02\x11\x00\x00\x00\x00#
      (axis=2, dir=17, rate=0)
Receive: #
```

**Implementation Reference**: `protocol.py:417`

---

### 7. Tracking Mode Commands

#### Get Tracking Mode

**Purpose**: Retrieve current tracking mode setting

**Command**: `t#`

**Response**: `<mode>#`

- `<mode>`: Single byte tracking mode value
  - `\x00` (0) = Tracking OFF
  - `\x01` (1) = Alt-Az tracking
  - `\x02` (2) = Equatorial tracking (Northern Hemisphere)
  - `\x03` (3) = Equatorial tracking (Southern Hemisphere)

**Example**:

```text
Send:    t#
Receive: \x01#  (Alt-Az tracking active)
```

**Implementation Reference**: `protocol.py:433`

---

#### Set Tracking Mode

**Purpose**: Configure telescope tracking mode

**Command**: `T<mode>#`

- `<mode>`: Single byte tracking mode value
  - `\x00` (0) = Turn tracking OFF
  - `\x01` (1) = Alt-Az tracking
  - `\x02` (2) = Equatorial tracking (Northern Hemisphere)
  - `\x03` (3) = Equatorial tracking (Southern Hemisphere)

**Response**: `#` (empty response indicates success)

**Examples**:

Enable Alt-Az tracking:

```text
Send:    T\x01#
Receive: #
```

Disable tracking:

```text
Send:    T\x00#
Receive: #
```

Enable equatorial tracking for Northern Hemisphere:

```text
Send:    T\x02#
Receive: #
```

**Implementation Reference**: `protocol.py:446`

---

### 8. Location Commands

#### Get Observer Location

**Purpose**: Retrieve configured observer latitude and longitude

**Command**: `w#`

**Response**: `<lat><lon>#`

- `<lat>`: Latitude in hex (8 chars)
- `<lon>`: Longitude in hex (8 chars)
- Total: 16 characters (no comma separator)

**Coordinate Interpretation**:

- Both use same hex encoding (0-360°)
- Latitude: 0-180° = 0° to 180° N, 180-360° = 0° to 180° S
- Longitude: 0-180° = 0° to 180° E, 180-360° = 0° to 180° W

**Example**:

```text
Send:    w#
Receive: 22B851EB851EB851#
         ^^^^^^^^ ^^^^^^^^
         lat      lon
```

**Decoding**:

```python
lat_hex = "22B851EB"
lon_hex = "851EB851"
lat = (int(lat_hex, 16) / 0x100000000) * 360.0
lon = (int(lon_hex, 16) / 0x100000000) * 360.0
# Convert to signed coordinates
if lat > 180:
    lat = lat - 360
if lon > 180:
    lon = lon - 360
```

**Implementation Reference**: `protocol.py:460`

---

#### Set Observer Location

**Purpose**: Configure observer latitude and longitude for calculations

**Command**: `W<lat>,<lon>#`

- `<lat>`: Latitude in hex (8 chars)
- `<lon>`: Longitude in hex (8 chars)
- Note: Comma separator (unlike get command)

**Response**: `#` (empty response indicates success)

**Example** (Set location to 40.7°N, 74.0°W):

```text
Lat: 40.7° → 0x1C71C71C → "1C71C71C"
Lon: -74° = 286° → 0xCCCCCCCC → "CCCCCCCC"
Send: W1C71C71C,CCCCCCCC#
Receive: #
```

**Implementation Reference**: `protocol.py:479`

---

### 9. Date and Time Commands

#### Get Date and Time

**Purpose**: Retrieve telescope's configured date and time

**Command**: `h#`

**Response**: `<H><M><S><month><day><year><tz><dst>#`

**Response Bytes** (8 bytes total):

1. `<H>`: Hour (0-23)
2. `<M>`: Minute (0-59)
3. `<S>`: Second (0-59)
4. `<month>`: Month (1-12)
5. `<day>`: Day of month (1-31)
6. `<year>`: Years since 2000 (0 = year 2000, 25 = year 2025)
7. `<tz>`: Timezone offset from GMT in hours (0-255, values >127 are negative)
8. `<dst>`: Daylight Saving Time (0 = standard time, 1 = DST active)

**Example**:

```text
Send:    h#
Receive: \x0E\x1E\x00\x0A\x18\x19\xFB\x00#
         14:30:00 on October 24, 2025, GMT-5, no DST
```

**Decoding**:

```python
response = "\x0E\x1E\x00\x0A\x18\x19\xFB\x00"
hour = ord(response[0])      # 14
minute = ord(response[1])    # 30
second = ord(response[2])    # 0
month = ord(response[3])     # 10 (October)
day = ord(response[4])       # 24
year = ord(response[5])      # 25 (2025)
tz = ord(response[6])        # 251 → -5 (if > 127: tz - 256)
dst = ord(response[7])       # 0
```

**Implementation Reference**: `protocol.py:496`

---

#### Set Date and Time

**Purpose**: Configure telescope's date and time for coordinate calculations

**Command**: `H<H><M><S><month><day><year><tz><dst>#`

**Parameters** (8 bytes):

1. `<H>`: Hour (0-23)
2. `<M>`: Minute (0-59)
3. `<S>`: Second (0-59)
4. `<month>`: Month (1-12)
5. `<day>`: Day of month (1-31)
6. `<year>`: Years since 2000
7. `<tz>`: Timezone offset from GMT
8. `<dst>`: Daylight Saving Time (0 or 1)

**Response**: `#` (empty response indicates success)

**Example** (Set to 14:30:00 on October 24, 2025, GMT-5, no DST):

```text
Send: H\x0E\x1E\x00\x0A\x18\x19\xFB\x00#
Receive: #
```

**Timezone Encoding** (for negative offsets):

```python
# For GMT-5:
if offset < 0:
    tz_byte = 256 + offset  # 256 + (-5) = 251 = 0xFB
else:
    tz_byte = offset
```

**Implementation Reference**: `protocol.py:512`

---

## Command Summary Table

| Command | Description | Bytes Sent | Response | Reference |
|---------|-------------|------------|----------|-----------|
| `K<c>#` | Echo test | 3 | 1 + term | protocol.py:276 |
| `V#` | Get version | 2 | 2 + term | protocol.py:294 |
| `m#` | Get model | 2 | 1 + term | protocol.py:306 |
| `E#` | Get RA/Dec | 2 | 17 + term | protocol.py:318 |
| `Z#` | Get Alt/Az | 2 | 17 + term | protocol.py:330 |
| `R<coords>#` | Goto RA/Dec | 19 | term only | protocol.py:343 |
| `B<coords>#` | Goto Alt/Az | 19 | term only | protocol.py:360 |
| `S<coords>#` | Sync RA/Dec | 19 | term only | protocol.py:377 |
| `L#` | Check goto status | 2 | 1 + term | protocol.py:393 |
| `M#` | Cancel goto | 2 | term only | protocol.py:405 |
| `P<params>#` | Variable rate motion | 8 | term only | protocol.py:417 |
| `t#` | Get tracking mode | 2 | 1 + term | protocol.py:433 |
| `T<mode>#` | Set tracking mode | 3 | term only | protocol.py:446 |
| `w#` | Get location | 2 | 16 + term | protocol.py:460 |
| `W<coords>#` | Set location | 19 | term only | protocol.py:479 |
| `h#` | Get time | 2 | 8 + term | protocol.py:496 |
| `H<time>#` | Set time | 10 | term only | protocol.py:512 |

**Note**: "term" refers to the `#` terminator character

---

## Practical Examples

### Example 1: Simple Connection Test

```text
1. Send: Kx#
2. Receive: x#
3. Success: Connection is working
```

### Example 2: Get Current Position

```text
1. Send: E#
2. Receive: 34B4C876,DE3A5678#
3. Decode:
   RA = (0x34B4C876 / 0x100000000) * 360 = 74.71°
   Dec = (0xDE3A5678 / 0x100000000) * 360 = 311.14°
   Dec signed = 311.14 - 360 = -48.86°
4. Result: RA = 74.71° (4.98 hours), Dec = -48.86°
```

### Example 3: Slew to Polaris

```text
Polaris coordinates: RA = 2h 31m 49s, Dec = +89° 15' 51"

1. Convert to degrees:
   RA = (2 + 31/60 + 49/3600) * 15 = 37.954°
   Dec = 89 + 15/60 + 51/3600 = 89.264°

2. Encode to hex:
   RA: (37.954 / 360) * 0x100000000 = 0x1A5E93E7 → "1A5E93E7"
   Dec: (89.264 / 360) * 0x100000000 = 0x3F23D70A → "3F23D70A"

3. Send command:
   Send: R1A5E93E7,3F23D70A#
   Receive: #

4. Monitor slew:
   Loop:
     Send: L#
     Receive: 1#  (still slewing)
   Until:
     Send: L#
     Receive: 0#  (slew complete)
```

### Example 4: Manual Movement

```text
Move telescope up at medium speed (rate 5):

1. Parameters:
   axis = 2 (altitude)
   direction = 17 (positive/up)
   rate = 5

2. Build command:
   P + \x02 + \x11 + \x05 + \x00 + \x00 + \x00 + #

3. Send:
   Send: P\x02\x11\x05\x00\x00\x00#
   Receive: #

4. To stop:
   Send: P\x02\x11\x00\x00\x00\x00#
   Receive: #
```

### Example 5: Enable Tracking

```text
Enable Alt-Az tracking:

1. Send: T\x01#
2. Receive: #
3. Verify:
   Send: t#
   Receive: \x01#  (confirmed Alt-Az tracking)
```

---

## Error Handling

### Timeout

If no response is received within the timeout period (typically 2 seconds):

- Check serial connection
- Verify telescope is powered on
- Ensure correct baud rate (9600)

### Invalid Response

If response format is unexpected:

- Response too short/long
- Missing terminator
- Invalid hex characters
- Send command again or reconnect

### Command Fails

If telescope doesn't respond to command:

- Position may be at mechanical limit
- Cables may be wrapped
- Alignment may be needed
- Batteries may be low

---

## Technical Notes

### Timing Considerations

1. Allow 500ms after opening serial port for connection to stabilize
2. Clear input/output buffers before sending each command
3. Poll goto status every 500ms (not faster to avoid overwhelming controller)
4. Wait for one command to complete before sending the next

### Precision

- 32-bit hex encoding provides approximately 0.000000084° resolution
- Practical accuracy limited by mechanical precision (~1-2 arcminutes)
- Position queries are more accurate than movement commands

### Coordinate Conversions

**RA Hours to Degrees**: `degrees = hours * 15`
**Degrees to RA Hours**: `hours = degrees / 15`

**Signed to Unsigned** (for Dec/Alt):

```python
if angle < 0:
    unsigned = 360 + angle
else:
    unsigned = angle
```

**Unsigned to Signed** (for Dec/Alt):

```python
if unsigned > 180:
    signed = unsigned - 360
else:
    signed = unsigned
```

---

## Implementation References

All command implementations can be found in:

- **File**: `/src/celestron_nexstar/protocol.py`
- **Class**: `NexStarProtocol`
- **Lines**: 275-534

High-level wrapper API available in:

- **File**: `/src/celestron_nexstar/telescope.py`
- **Class**: `NexStarTelescope`

---

## Additional Resources

- **Official Protocol Specification**: [Celestron NexStar Serial Protocol PDF](https://s3.amazonaws.com/celestron-site-support-files/support_files/1154108406_nexstarcommprot.pdf)
- **Repository Documentation**: `/docs/protocol_docs.md`
- **Working Examples**: `/example_usage.py`

---

**Document Version**: 1.0
**Last Updated**: 2025-10-24
**Based on**: celestron-nexstar Python API
**Telescope Model**: NexStar 6SE (compatible with NexStar series)
