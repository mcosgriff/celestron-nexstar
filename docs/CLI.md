# CLI Command Reference

This document provides comprehensive documentation for the `nexstar` command-line interface.

## Table of Contents

- [Overview](#overview)
- [Multi-Night Planning](#multi-night-planning)
  - [Week Comparison](#week-comparison)
  - [Best Night for Object](#best-night-for-object)
  - [Clear Sky Chart](#clear-sky-chart)
- [Location Management](#location-management)
- [Catalog Commands](#catalog-commands)
- [Shell](#shell)

## Overview

The `nexstar` CLI provides commands for telescope control, observation planning, and sky condition analysis. All commands follow a consistent pattern:

```bash
nexstar [COMMAND] [SUBCOMMAND] [OPTIONS]
```

Use `--help` with any command to see detailed options:

```bash
nexstar --help
nexstar multi-night --help
nexstar multi-night clear-sky --help
```

## Multi-Night Planning

The `multi-night` command group helps you plan observing sessions by comparing conditions across multiple nights.

### Week Comparison

Compare observing conditions for the next 7 nights:

```bash
nexstar multi-night week
```

**Output:**
- Table showing quality, seeing, clouds, moon phase/illumination for each night
- Best seeing window for each night
- Summary of best nights for different conditions

**Example:**
```
7-Night Comparison
┌────────────┬────────────┬────────┬────────┬──────────┬────────┬────────────────────┐
│ Date       │ Quality    │ Seeing │ Clouds │ Moon     │ Moon % │ Best Window        │
├────────────┼────────────┼────────┼────────┼──────────┼────────┼────────────────────┤
│ Sat Nov 09 │ Excellent  │ 85/100 │ 15%    │ Waxing   │ 45%    │ 09:00 PM - 11:30 PM│
│ Sun Nov 10 │ Good       │ 72/100 │ 25%    │ Waxing   │ 55%    │ 09:15 PM - 11:00 PM│
└────────────┴────────────┴────────┴────────┴──────────┴────────┴────────────────────┘

Best Nights:
  Best Overall: Saturday, November 09 (Quality: 87/100)
  Best Seeing: Saturday, November 09 (Seeing: 85/100)
  Clearest Sky: Saturday, November 09 (Clouds: 15%)
```

### Best Night for Object

Find the optimal night to observe a specific celestial object:

```bash
nexstar multi-night best-night <OBJECT_NAME> [OPTIONS]
```

**Options:**
- `--days`, `-d` INTEGER - Number of days to check (default: 7)

**Example:**
```bash
nexstar multi-night best-night M31 --days 7
```

**Output:**
- Table ranking nights by observation quality score
- Combines atmospheric conditions with object visibility
- Shows transit time and altitude for each night
- Detailed information for the best night

**Scoring Algorithm:**
- 40% - Overall observing quality (weather, seeing, transparency)
- 30% - Seeing quality
- 20% - Object visibility (altitude, magnitude)
- 10% - Moon interference (less moon = better)

### Clear Sky Chart

Display a detailed Clear Sky Chart-style forecast grid showing hourly conditions:

```bash
nexstar multi-night clear-sky [OPTIONS]
```

#### Basic Options

**`--days`, `-d` INTEGER**
- Number of days to show (1-7, default: 4)
- Example: `--days 7`

**`--nighttime-only`, `-n`**
- Only show hours when the sun is below the horizon
- Filters out daytime hours for cleaner charts
- Example: `-n`

#### Condition Filtering

**`--conditions`, `-c` TEXT**
- Comma-separated list of conditions to display
- Available conditions:
  - `clouds` - Cloud cover percentage
  - `transparency` - Atmospheric transparency
  - `seeing` - Seeing quality (turbulence)
  - `darkness` - Sky darkness (limiting magnitude)
  - `wind` - Wind speed
  - `humidity` - Relative humidity
  - `temperature` - Air temperature
- Default: All conditions
- Examples:
  ```bash
  -c clouds,seeing,darkness
  --conditions clouds,transparency,seeing
  ```

#### Quality Highlighting

**`--highlight-good`**
- Highlight hours meeting quality thresholds with green stars (★)
- Stars appear in a row above the time header
- An hour is marked with ★ only if it meets ALL threshold criteria:
  - Cloud cover ≤ max-clouds
  - Darkness ≥ min-darkness
  - Seeing ≥ min-seeing
- Makes it easy to identify the best observing hours at a glance
- Combines with the threshold options below to customize criteria

**`--max-clouds` FLOAT**
- Maximum cloud cover % for highlighting (default: 30.0)
- Only used with `--highlight-good`
- Example: `--max-clouds 20`

**`--min-darkness` FLOAT**
- Minimum limiting magnitude for highlighting (default: 5.0)
- Higher values = darker skies
- Only used with `--highlight-good`
- Example: `--min-darkness 6.0`

**`--min-seeing` FLOAT**
- Minimum seeing score (0-100) for highlighting (default: 60.0)
- Higher values = better seeing
- Only used with `--highlight-good`
- Example: `--min-seeing 70`

#### Data Export

**`--export`, `-e` PATH**
- Export chart data to file
- Supported formats: `.csv`, `.json`
- Includes both UTC and local timestamps
- Exports all forecast fields
- Chart is still displayed on screen
- Examples:
  ```bash
  --export forecast.csv
  -e conditions.json
  ```

**CSV Format:**
```csv
timestamp_utc,timestamp_local,cloud_cover,transparency,seeing,darkness,wind,humidity,temperature
2025-11-09T20:00:00+00:00,2025-11-09T12:00:00-08:00,15.0,transparent,85.0,5.8,8.5,45.0,58.0
```

**JSON Format:**
```json
[
  {
    "timestamp_utc": "2025-11-09T20:00:00+00:00",
    "timestamp_local": "2025-11-09T12:00:00-08:00",
    "cloud_cover": 15.0,
    "transparency": "transparent",
    "seeing": 85.0,
    "darkness": 5.8,
    "wind": 8.5,
    "humidity": 45.0,
    "temperature": 58.0
  }
]
```

#### Usage Examples

**Basic chart for next 4 days:**
```bash
nexstar multi-night clear-sky
```

**Show only nighttime hours:**
```bash
nexstar multi-night clear-sky --nighttime-only
```

**Focus on key observing conditions:**
```bash
nexstar multi-night clear-sky -c clouds,seeing,darkness
```

**Highlight excellent observing hours:**
```bash
nexstar multi-night clear-sky --highlight-good
```

**Strict quality thresholds:**
```bash
nexstar multi-night clear-sky --highlight-good --max-clouds 15 --min-darkness 6.5 --min-seeing 80
```

**Export data for analysis:**
```bash
nexstar multi-night clear-sky --export forecast.csv --days 7
```

**Comprehensive example:**
```bash
nexstar multi-night clear-sky \
  --days 7 \
  --nighttime-only \
  --conditions clouds,seeing,darkness \
  --highlight-good \
  --max-clouds 20 \
  --min-darkness 6.0 \
  --export conditions.json
```

#### Chart Format

The clear-sky chart displays conditions in a grid format:

```
Clear Sky Chart

           Saturday, 9    Sunday, 10
           0 0 0 0 1 1 1  0 0 0 0 1 1 1
           0 1 2 3 0 1 2  0 1 2 3 0 1 2
           ★ ★ ★   ★ ★ ★    ★ ★     ★ ★
Cloud Cover            ████  ████  ████   ████  ████  ████  ████
Transparency           ████  ████  ████   ████  ████  ████  ████
Seeing                 ████  ████  ████   ████  ████  ████  ████
Darkness               ████  ████  ████   ████  ████  ████  ████
Wind                   ████  ████  ████   ████  ████  ████  ████
Humidity               ████  ████  ████   ████  ████  ████  ████
Temperature            ████  ████  ████   ████  ████  ████  ████

Legend:
Cloud Cover:      Overcast  90% covered  80% covered ... Clear
Transparency:     Too cloudy to forecast  Poor  Below Average  Average  Above average  Transparent
Seeing:           Too cloudy to forecast  Bad  Poor  Average  Good  Excellent
Darkness:         Day  -4  -3  -2  -1  0  1.0  2.0  3.0  3.5  4.0  4.5  5.0  5.5  6.0  6.5
Wind:             0-5 mph  6-11 mph  12-16 mph  17-28 mph  29-45 mph  >45 mph
Humidity:         <25%  25-30%  30-35% ... 95-100%
Temperature:      < -40°F  -40--31°F ... >113°F

Note: Each block represents one hour. Time shown in 24-hour format (tens digit above, ones digit below).
```

**Legend:**
- Each colored block (█) represents one hour
- Colors range from optimal (dark blue) to poor (white/gray/red)
- Green stars (★) indicate hours meeting quality thresholds
- Day names shown at top, with date for full days
- Time shown as two-digit 24-hour format (tens above, ones below)

#### Color Interpretations

**Cloud Cover:** Dark blue (clear) → White (overcast)
- Clear skies: Deep blue
- Light clouds (10-30%): Medium blue
- Moderate clouds (40-60%): Light blue/gray
- Heavy clouds (70%+): Light gray/white

**Seeing:** Dark blue (excellent) → White (too cloudy)
- Excellent (80-100): Deep blue - Ideal for planetary observation
- Good (60-80): Medium blue - Good for most targets
- Average (40-60): Light blue - Acceptable conditions
- Poor (<40): Gray - Challenging conditions

**Darkness:** Black (dark sky) → White (daylight)
- 6.5+ mag: Black - Darkest skies, faintest objects visible
- 5.0-6.5 mag: Dark blue - Excellent for deep sky
- 3.0-5.0 mag: Medium blue - Good conditions
- 0-3.0 mag: Light blue/turquoise - Twilight
- Negative: Yellow/white - Dusk/day

**Wind:** Dark blue (calm) → White (high)
- 0-5 mph: Dark blue - Calm, ideal conditions
- 6-16 mph: Medium blue - Acceptable
- 17-28 mph: Light blue - May cause vibration
- 29+ mph: Gray/white - Difficult conditions

## Location Management

Set your observing location for accurate calculations:

```bash
# Set location by coordinates
nexstar location set --lat 34.05 --lon -118.24 --name "Los Angeles"

# Geocode an address
nexstar location geocode "Griffith Observatory, Los Angeles, CA"

# Show current location
nexstar location show
```

## Catalog Commands

Explore celestial object catalogs:

```bash
# List available catalogs
nexstar catalog catalogs

# Browse a catalog
nexstar catalog list --catalog messier

# Search for objects
nexstar catalog search "andromeda"

# Get object details
nexstar catalog info M31
```

## Shell

Launch the interactive telescope control shell:

```bash
nexstar shell

# Or with a specific port
nexstar shell --port /dev/ttyUSB0
```

See the main [README](../README.md) for detailed shell documentation.

## Configuration

Most commands require a configured location. Set this once:

```bash
nexstar location set --lat YOUR_LAT --lon YOUR_LON --name "Your Location"
```

Or use geocoding:

```bash
nexstar location geocode "Your City, State"
```

## Exit Codes

- `0` - Success
- `1` - Error (invalid input, missing configuration, API failure, etc.)

## Environment Variables

Currently, the CLI does not use environment variables. All configuration is stored in the application's config directory.

## Tips

1. **Use short options for quick commands:**
   ```bash
   nexstar multi-night clear-sky -n --highlight-good -c clouds,seeing -d 7
   ```

2. **Combine export with filtering:**
   ```bash
   nexstar multi-night clear-sky -n -c darkness,seeing -e nighttime.csv
   ```

3. **Create aliases for common commands:**
   ```bash
   alias sky-tonight='nexstar multi-night clear-sky -n --highlight-good -c clouds,seeing,darkness'
   ```

4. **Check conditions before observing:**
   ```bash
   nexstar multi-night clear-sky --days 1 --nighttime-only --highlight-good
   ```

## Troubleshooting

**"No location set" error:**
```bash
nexstar location set --lat YOUR_LAT --lon YOUR_LON
```

**"No nighttime forecast data available":**
- Try without `--nighttime-only` flag
- Check if you're in polar regions during summer/winter
- Verify your location is set correctly

**Empty or incomplete charts:**
- Check internet connection (weather data requires API access)
- Verify location is set correctly
- Try reducing `--days` parameter

**Export file issues:**
- Ensure you have write permissions in the target directory
- Use absolute paths or ensure working directory is correct
- Check file extension is `.csv` or `.json`

## Further Reading

- [Main README](../README.md) - Project overview and interactive shell
- [Installation Guide](INSTALL.md) - Setup instructions
- [Python API Documentation](telescope_docs.md) - Programmatic usage
