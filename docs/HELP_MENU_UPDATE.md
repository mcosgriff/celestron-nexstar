# Help Menu Update

## Changes Made

Updated the interactive shell help menu to include the new data import commands.

## What Was Added

### 1. Command Group List

Added `data` to the available command groups:

```
Available command groups:
  connect    - Connection commands
  position   - Position query commands
  goto       - Slew (goto) commands
  move       - Manual movement commands
  track      - Tracking control commands
  align      - Alignment commands
  location   - Observer location commands
  time       - Time and date commands
  catalog    - Celestial object catalogs
  data       - Data import and management      ← NEW!
  optics     - Telescope and eyepiece configuration
  ephemeris  - Ephemeris file management
```

### 2. Dedicated Data Import Section

Added a new "Data Import Commands" section with all data commands:

```
Data Import Commands:
  data sources                    - List available catalog data sources
  data import <source>            - Import catalog data (e.g., data import openngc)
  data import <source> -m <mag>   - Import with custom magnitude limit
  data stats                      - Show database statistics
```

## File Modified

**File**: `src/celestron_nexstar/cli/main.py`

**Lines**: 378-423

**Changes**:
1. Added `data` entry to command groups list (line 389)
2. Added new "Data Import Commands" section (lines 411-415)

## Testing

Verified by running:
```bash
nexstar shell
help
```

Result: ✅ All data commands appear in help menu correctly

## User Experience

When users type `help` in the shell, they now see:
1. **data** listed among command groups
2. Dedicated section showing all data import commands
3. Clear examples of usage (e.g., "data import openngc")
4. Magnitude limit option clearly documented

This makes the data import feature discoverable without having to consult external documentation.

---

*Updated: 2025-11-06*
