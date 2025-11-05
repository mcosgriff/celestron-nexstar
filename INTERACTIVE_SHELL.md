# Interactive Shell Mode

The NexStar CLI includes a powerful interactive shell mode with tab completion, command history, and all the benefits of Typer.

## Starting the Shell

```bash
nexstar shell
```

Or with connection options:

```bash
nexstar --port /dev/ttyUSB0 shell
```

## Features

### Background Position Tracking

The shell includes automatic background position tracking that continuously monitors your telescope's position after alignment:

- **Auto-starts after alignment** - Tracking begins automatically when you run an `align` command
- **Live status bar** - Position updates appear in a status bar at the bottom of the screen
- **2-second refresh** - Position updates every 2 seconds
- **Thread-safe** - Runs in a background thread without interfering with commands
- **Smart error handling** - Automatically stops after 3 consecutive errors

**Tracking Commands:**

```bash
nexstar> tracking start    # Manually start tracking
nexstar> tracking stop     # Stop tracking
nexstar> tracking status   # Show tracking status
```

**Status Bar Display:**

```
Position: RA: 05h42m36s  Dec: +41°16'12"  Alt: 45.3°  Az: 180.5° [live]
```

The status bar shows:
- **RA** (Right Ascension) in hours:minutes:seconds
- **Dec** (Declination) in degrees:arcminutes:arcseconds
- **Alt** (Altitude) in degrees
- **Az** (Azimuth) in degrees
- **[live]** indicator for fresh data (< 5 seconds old)

### Tab Completion
Press `Tab` to autocomplete commands and subcommands:

```
nexstar> cat[TAB]
catalog

nexstar> catalog [TAB]
catalogs  goto  info  list  search

nexstar> catalog search "and[TAB]
```

### Command History
- Use **Up/Down arrows** to navigate command history
- Use **Ctrl+R** for reverse history search
- History persists within the session

### Shell Commands

All regular nexstar commands work without the `nexstar` prefix:

```bash
nexstar> position get
nexstar> goto radec --ra 5.5 --dec 22.5
nexstar> catalog search "andromeda"
nexstar> optics show
nexstar> ephemeris list
```

### Special Commands

- `help` - Show available command groups
- `clear` - Clear the screen
- `exit` or `quit` - Exit the shell
- `Ctrl+C` - Cancel current input
- `Ctrl+D` - Exit the shell

## Example Session

### Basic Session
```
$ nexstar --port /dev/ttyUSB0 shell

╔═══════════════════════════════════════════════════╗
║   NexStar Interactive Shell                       ║
╚═══════════════════════════════════════════════════╝

Type 'help' for available commands, 'exit' to quit

nexstar> help

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
  optics     - Telescope and eyepiece configuration
  ephemeris  - Ephemeris file management

Shell-specific commands:
  tracking start  - Start background position tracking
  tracking stop   - Stop background position tracking
  tracking status - Show tracking status

Use '<command> --help' for detailed help on each command

nexstar> catalog search "andromeda"

Found 1 result:

  M31 (Andromeda Galaxy)
  Type: Galaxy
  RA: 0.71 hours, Dec: 41.27°
  Magnitude: 3.4
  Description: Great spiral galaxy

nexstar> goto radec --ra 0.71 --dec 41.27

Slewing to RA: 0.71 hours, Dec: 41.27°
...

nexstar> position get

Current Position:
  RA: 0.71 hours (0h 42m 36s)
  Dec: 41.27° (41° 16' 12")
  Alt: 45.32°
  Az: 180.50°

nexstar> exit

Goodbye!
```

### Session with Background Tracking
```
$ nexstar --port /dev/ttyUSB0 shell

╔═══════════════════════════════════════════════════╗
║   NexStar Interactive Shell                       ║
╚═══════════════════════════════════════════════════╝

Type 'help' for available commands, 'exit' to quit

nexstar> catalog search "polaris"

Found 1 result:

  Polaris (North Star)
  Type: Star
  RA: 2.53 hours, Dec: 89.26°
  ...

nexstar> goto radec --ra 2.53 --dec 89.26

Slewing to Polaris...

nexstar> align sync --ra 2.53 --dec 89.26

✓ Telescope synced to RA: 2.53 hours, Dec: 89.26°

→ Background position tracking started automatically
  Position updates will appear in the status bar
  Use 'tracking stop' to disable

nexstar> catalog list --catalog planets
┌─────────────────────────────────────────────────────────────────┐
│ Position: RA: 02h31m49s  Dec: +89°15'51"  Alt: 89.3°  Az: 0.0° [live] │
└─────────────────────────────────────────────────────────────────┘

  Jupiter - RA: 5.5h, Dec: 22.5°, Mag: -2.5
  Saturn - RA: 14.2h, Dec: -8.5°, Mag: 0.2
  Mars - RA: 8.3h, Dec: 24.1°, Mag: -2.0
  ...

nexstar> goto radec --object "Jupiter"
┌─────────────────────────────────────────────────────────────────┐
│ Position: RA: 02h31m55s  Dec: +89°15'48"  Alt: 89.2°  Az: 1.2° [live] │
└─────────────────────────────────────────────────────────────────┘

Slewing to Jupiter...

# ... position automatically updates in status bar as telescope moves ...

nexstar> tracking status
┌─────────────────────────────────────────────────────────────────┐
│ Position: RA: 05h30m12s  Dec: +22°30'05"  Alt: 45.8°  Az: 120.5° [live] │
└─────────────────────────────────────────────────────────────────┘

● Tracking active: RA: 05h30m12s  Dec: +22°30'05"  Alt: 45.8°  Az: 120.5° [live]
Update interval: 2.0s

nexstar> exit

Goodbye!
```

**Note:** The status bar at the bottom continuously updates with the telescope's current position without interrupting your command input.

## Tips

1. **Quoted Arguments**: Use quotes for multi-word arguments:
   ```
   nexstar> catalog search "orion nebula"
   ```

2. **Command Help**: Get help for any command:
   ```
   nexstar> catalog --help
   nexstar> goto radec --help
   ```

3. **Persistent Connection**: The telescope connection persists across commands in the shell, making it more efficient than running individual CLI commands.

4. **Error Handling**: Errors don't exit the shell - you can correct and retry:
   ```
   nexstar> goto radec --ra invalid
   Error: invalid is not a valid float

   nexstar> goto radec --ra 5.5 --dec 22.5
   Slewing...
   ```

5. **Verbose Mode**: Start with verbose mode for debugging:
   ```bash
   nexstar --verbose shell
   ```

6. **Background Tracking**: The position tracker is perfect for:
   - **Monitoring slews**: Watch the telescope move to your target
   - **Drift checking**: Verify your polar alignment
   - **Field rotation**: Track position changes during long exposures
   - **Multi-target sessions**: Keep position visible while planning next target

7. **Manual Tracking Control**: You can manually control tracking:
   ```bash
   nexstar> tracking start    # Start before alignment if needed
   nexstar> tracking stop     # Stop to reduce telescope queries
   ```

## Advantages Over Regular CLI

- **No repetition**: Don't type `nexstar` for every command
- **Command history**: Easily repeat or modify previous commands
- **Tab completion**: Discover commands and options faster
- **Persistent state**: Connection and configuration persist between commands
- **Background tracking**: Real-time position monitoring without additional commands
- **Faster workflow**: Ideal for observing sessions with many commands
- **Better UX**: Live status bar shows position without cluttering output
