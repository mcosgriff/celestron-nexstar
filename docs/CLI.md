# CLI Command Reference

This document provides comprehensive documentation for the `nexstar` command-line interface.

## Table of Contents

- [Overview](#overview)
- [Export Functionality](#export-functionality)
- [Telescope Viewing Commands](#telescope-viewing-commands)
  - [Conditions](#conditions)
  - [Objects](#objects)
  - [Imaging](#imaging)
  - [Tonight](#tonight)
  - [Plan](#plan)
- [Multi-Night Planning](#multi-night-planning)
  - [Week Comparison](#week-comparison)
  - [Best Night for Object](#best-night-for-object)
  - [Clear Sky Chart](#clear-sky-chart)
- [Binocular & Naked-Eye Viewing](#binocular--naked-eye-viewing)
- [Celestial Events](#celestial-events)
  - [Aurora](#aurora)
  - [Eclipses](#eclipses)
  - [Planetary Events](#planetary-events)
  - [Meteor Showers](#meteor-showers)
  - [Comets](#comets)
  - [ISS Passes](#iss-passes)
  - [Satellites](#satellites)
  - [Zodiacal Light](#zodiacal-light)
  - [Variable Stars](#variable-stars)
  - [Occultations](#occultations)
- [Space Events Calendar](#space-events-calendar)
- [Vacation Planning](#vacation-planning)
- [Data Management](#data-management)
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

## Export Functionality

Many viewing and planning commands support exporting their output to text files for printing or offline reference. Export functionality uses a consistent pattern across all commands.

### Export Options

**`--export`, `-e`**

- Boolean flag that enables export
- When used without `--export-path`, automatically generates a filename
- Example: `nexstar telescope tonight --export`

**`--export-path` PATH**

- Optional custom file path for export
- Overrides auto-generated filename when provided
- Example: `nexstar telescope tonight --export --export-path my_plan.txt`

### Auto-Generated Filenames

When `--export` is used without `--export-path`, filenames are automatically generated using this pattern:

**Telescope Commands:**

```text
nexstar_{telescope_model}_{location}_{date}_{command}.txt
```

**Multi-Night Commands:**

```text
nexstar_{telescope_model}_{location}_{date}_{command}.txt
```

**Best Night Command:**

```text
nexstar_{telescope_model}_{location}_{date}_best-night_{object_name}.txt
```

**Binocular Commands:**

```text
binoculars_{model}_{location}_{date}_{command}.txt
```

**Naked-Eye Commands:**

```text
naked_eye_{location}_{date}_{command}.txt
```

**Examples:**

- `nexstar_6se_los_angeles_2024-11-15_tonight.txt`
- `nexstar_6se_los_angeles_2024-11-15_conditions.txt`
- `nexstar_6se_los_angeles_2024-11-15_best-night_m31.txt`
- `binoculars_10x50_los_angeles_2024-11-15_tonight.txt`
- `naked_eye_los_angeles_2024-11-15_tonight.txt`

### Export Format

Exported files contain:

- Plain text output with ASCII tables
- All information from the console output
- Formatted for readability and printing
- No color codes (suitable for printing)

### Commands with Export Support

**Telescope Viewing:**

- `nexstar telescope conditions --export`
- `nexstar telescope objects --export`
- `nexstar telescope imaging --export`
- `nexstar telescope tonight --export`
- `nexstar telescope plan --export`

**Multi-Night Planning:**

- `nexstar multi-night week --export`
- `nexstar multi-night best-night <OBJECT> --export`

**Binocular Viewing:**

- `nexstar binoculars tonight --export`

**Naked-Eye Viewing:**

- `nexstar naked-eye tonight --export`

**Celestial Events:**

- `nexstar aurora tonight --export`
- `nexstar eclipse next --export`
- `nexstar planets conjunctions --export`
- `nexstar meteors next --export`
- `nexstar comets visible --export`
- `nexstar iss passes --export`
- `nexstar satellites bright --export`
- `nexstar zodiacal zodiacal-light --export`
- `nexstar variables events --export`
- `nexstar occultations next --export`

**Space Events:**

- `nexstar events upcoming --export`

**Vacation Planning:**

- `nexstar vacation view --export`
- `nexstar vacation dark-sites --export`
- `nexstar vacation plan --export`

### Usage Examples

**Auto-generate filename:**

```bash
nexstar telescope tonight --export
# Creates: nexstar_6se_los_angeles_2024-11-15_tonight.txt
```

**Custom filename:**

```bash
nexstar telescope tonight --export --export-path observing_plan.txt
```

**Export with filters:**

```bash
nexstar telescope objects --export --type all --limit 10     # Export all object types
nexstar telescope objects --export --type planets --limit 10 # Export planets only
```

**Export best night analysis:**

```bash
nexstar multi-night best-night M31 --export --days 7
# Creates: nexstar_6se_los_angeles_2024-11-15_best-night_m31.txt
```

## Telescope Viewing Commands

The `telescope` command group provides viewing guides and recommendations for telescope observing sessions.

### Conditions

Show tonight's observing conditions including weather, seeing, light pollution, and moon events:

```bash
nexstar telescope conditions [OPTIONS]
```

**Options:**

- `--export`, `-e` - Export output to text file (auto-generates filename)
- `--export-path` PATH - Custom export file path

**Output includes:**

- Overall observing quality score
- Weather conditions (clouds, temperature, wind, etc.)
- Seeing conditions with hourly forecast
- Light pollution (Bortle class, SQM, limiting magnitude)
- Moon phase, illumination, and events
- Sun events (sunrise, sunset, twilight times)
- Recommendations and warnings

**Example:**

```bash
nexstar telescope conditions
nexstar telescope conditions --export
nexstar telescope conditions --export --export-path conditions.txt
```

### Objects

Show recommended objects for tonight based on visibility and conditions:

```bash
nexstar telescope objects [OPTIONS]
```

**Options:**

- `--type` TEXT - Filter by type (all, planets, deep_sky, messier, etc.). If not specified, shows interactive menu
- `--limit` INTEGER - Maximum objects to show (default: 20)
- `--best-for-seeing` - Show only objects ideal for current seeing conditions
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Object Types:**

- `all` - Show all object types (no filtering)
- `planets` - Solar system planets
- `moon` - Earth's moon
- `deep_sky` - Deep sky objects (galaxies, nebulae, clusters)
- `double_stars` - Double and multiple star systems
- `variable_stars` - Variable stars
- `messier` - Messier catalog objects
- `caldwell` - Caldwell catalog objects
- `ngc_ic` - NGC and IC catalog objects

**Example:**

```bash
nexstar telescope objects                                    # Interactive menu to select type
nexstar telescope objects --type all                        # Show all object types
nexstar telescope objects --type planets --limit 5           # Filter to planets only
nexstar telescope objects --best-for-seeing --export        # Best for seeing, export to file
```

### Imaging

Show imaging forecasts with seeing for planetary imaging and transparency for deep-sky:

```bash
nexstar telescope imaging [OPTIONS]
```

**Options:**

- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Planetary imaging seeing forecast (hourly)
- Deep-sky imaging transparency forecast (hourly)
- Exposure time recommendations
- Best imaging windows

**Example:**

```bash
nexstar telescope imaging
nexstar telescope imaging --export
```

### Tonight

Show complete viewing guide for tonight (conditions + objects):

```bash
nexstar telescope tonight [OPTIONS]
```

**Options:**

- `--type` TEXT - Filter objects by type (all, planets, deep_sky, messier, etc.). If not specified, shows interactive menu
- `--limit` INTEGER - Maximum objects to show (default: 20)
- `--best-for-seeing` - Show only objects ideal for current seeing
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Example:**

```bash
nexstar telescope tonight                                    # Interactive menu to select type
nexstar telescope tonight --type all                        # Show all object types
nexstar telescope tonight --export                          # Export with auto-generated filename
nexstar telescope tonight --type deep_sky --export --export-path deep_sky_tonight.txt
```

### Plan

Show complete observing plan (same as `tonight` command):

```bash
nexstar telescope plan [OPTIONS]
```

**Options:**

- `--type` TEXT - Filter objects by type (all, planets, deep_sky, messier, etc.). If not specified, shows interactive menu
- `--limit` INTEGER - Maximum objects to show (default: 20)
- `--best-for-seeing` - Show only objects ideal for current seeing
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Example:**

```bash
nexstar telescope plan                                      # Interactive menu to select type
nexstar telescope plan --type all                          # Show all object types
nexstar telescope plan --export                            # Export with auto-generated filename
```

## Multi-Night Planning

The `multi-night` command group helps you plan observing sessions by comparing conditions across multiple nights.

### Week Comparison

Compare observing conditions for the next 7 nights:

```bash
nexstar multi-night week [OPTIONS]
```

**Options:**

- `--export`, `-e` - Export output to text file (auto-generates filename)
- `--export-path` PATH - Custom export file path

**Output:**

- Table showing quality, seeing, clouds, moon phase/illumination for each night
- Best seeing window for each night
- Summary of best nights for different conditions

**Example:**

```text
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

Find the optimal night to observe a specific celestial object with intelligent, object-type specific scoring:

```bash
nexstar multi-night best-night <OBJECT_NAME> [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Number of days to check (default: 7)
- `--export`, `-e` - Export output to text file (auto-generates filename with object name)
- `--export-path` PATH - Custom export file path

**Example:**

```bash
nexstar multi-night best-night M31 --days 7
nexstar multi-night best-night Jupiter --days 14
nexstar multi-night best-night "Ring Nebula" --days 7
nexstar multi-night best-night M31 --days 7 --export
# Creates: nexstar_6se_los_angeles_2024-11-15_best-night_m31.txt
```

**Key Features:**

1. **Object-Type Optimized Scoring** - Different objects have different requirements:
   - **Planets**: Prioritize seeing quality (45%) and altitude (25%) - moon and light pollution have minimal impact
   - **Galaxies**: Prioritize moon separation (30%) and dark skies (25%) - very sensitive to light pollution (90%)
   - **Nebulae**: Prioritize atmospheric conditions (30%) and moon distance (25%) - sensitive to light pollution (80%)
   - **Clusters**: Prioritize altitude (30%) and conditions (25%) - moderately sensitive to light pollution (40%)
   - **Double Stars**: Prioritize seeing (50%) and altitude (25%) - unaffected by light pollution

2. **Moon-Object Separation** - Calculates angular distance between object and moon:
   - <15°: Very poor (moon glare ruins observation)
   - 15-30°: Poor (significant interference)
   - 30-60°: Fair (moderate interference)
   - 60-90°: Good (minimal interference)
   - >90°: Excellent (opposite sides of sky)
   - Combined with moon brightness for final moon score

3. **Light Pollution Integration** - Assesses your location's Bortle class:
   - Displays Bortle scale (1-9) and limiting magnitude
   - Applies penalties based on object sensitivity
   - Example: Galaxy from Bortle 6 receives ~63% penalty
   - Warns when location significantly limits visibility
   - Planets and double stars unaffected by light pollution

**Output:**

- Table ranking nights by total score (0-100)
- Columns: Date, Score, Quality, Seeing, Clouds, Transit Time, Altitude, Moon %, Moon Separation
- Shows location's Bortle class and description
- Best night summary with detailed metrics
- Object-type specific observing notes
- Light pollution impact warnings (if applicable)

**Example Output:**

```text
Best Night for M31
The Andromeda Galaxy
Type: Galaxy
Checking next 7 nights with galaxy-optimized scoring...
Location light pollution: Bortle 5 - Suburban sky. Milky Way washed out near horizon.

┌────────────┬───────┬──────────┬────────┬────────┬──────────┬──────────┬──────┬──────────┐
│ Date       │ Score │ Quality  │ Seeing │ Clouds │ Transit  │ Altitude │ Moon │ Moon Sep │
├────────────┼───────┼──────────┼────────┼────────┼──────────┼──────────┼──────┼──────────┤
│ Sat Nov 09 │ 78    │ Excellent│ 85/100 │ 15%    │ 10:30 PM │ 68°      │ 12%  │ 95°      │
│ Sun Nov 10 │ 72    │ Good     │ 72/100 │ 25%    │ 10:35 PM │ 67°      │ 20%  │ 85°      │
└────────────┴───────┴──────────┴────────┴────────┴──────────┴──────────┴──────┴──────────┘

Best Night: Saturday, November 09, 2025
  Score: 78/100
  Transit: 10:30 PM at 68° altitude
  Seeing: 85/100
  Cloud Cover: 15%
  Moon: 12% illuminated
  Moon Separation: 95°
  Note: Galaxies need dark skies and distance from the moon
        Your Bortle 5 location is suitable for galaxy observation
  ✓ Object will be visible
```

**Scoring Details:**

The algorithm uses weighted scoring based on object type. Base weights:

| Factor | Planets | Galaxies | Nebulae | Clusters | Double Stars |
|--------|---------|----------|---------|----------|--------------|
| Seeing | 45% | 10% | 10% | 20% | 50% |
| Visibility (altitude) | 25% | 25% | 25% | 30% | 25% |
| Conditions (weather) | 20% | 25% | 30% | 25% | 15% |
| Moon Separation | 5% | 30% | 25% | 15% | 5% |
| Moon Brightness | 5% | 10% | 10% | 10% | 5% |

Then applies light pollution penalty:

```text
final_score = base_score × (1 - sensitivity × (1 - bortle_quality))
```

Where sensitivity ranges from 0.0 (unaffected) to 0.9 (extremely sensitive).

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
```csv

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

```text
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

## Binocular & Naked-Eye Viewing

### Binocular Viewing

Show what's visible tonight with binoculars:

```bash
nexstar binoculars tonight [OPTIONS]
```

**Options:**

- `--model`, `-m` TEXT - Binocular model (e.g., 10x50, 7x50, 15x70, default: 10x50)
- `--export`, `-e` - Export output to text file (auto-generates filename)
- `--export-path` PATH - Custom export file path

**Output includes:**

- ISS passes visible with binoculars
- Prominent constellations
- Constellations partially visible
- Star patterns (asterisms)
- Active meteor showers
- Bright stars visible

**Example:**

```bash
nexstar binoculars tonight
nexstar binoculars tonight --model 15x70
nexstar binoculars tonight --export
# Creates: binoculars_10x50_los_angeles_2024-11-15_tonight.txt
```

### Naked-Eye Viewing

Show what's visible tonight with the naked eye:

```bash
nexstar naked-eye tonight [OPTIONS]
```

**Options:**

- `--export`, `-e` - Export output to text file (auto-generates filename)
- `--export-path` PATH - Custom export file path

**Output includes:**

- ISS passes visible to naked eye
- Prominent constellations
- Constellations partially visible
- Star patterns (asterisms)
- Active meteor showers
- Bright stars visible

**Example:**

```bash
nexstar naked-eye tonight
nexstar naked-eye tonight --export
# Creates: naked_eye_los_angeles_2024-11-15_tonight.txt
```

## Celestial Events

The `nexstar` CLI includes comprehensive tools for tracking and predicting celestial events. All event commands support export functionality and use your configured location.

### Aurora

Track aurora borealis (Northern Lights) visibility:

```bash
# Check if aurora is visible tonight
nexstar aurora tonight [OPTIONS]

# Find when aurora will be visible
nexstar aurora when [OPTIONS]

# Find next viewing opportunities (even months/years ahead)
nexstar aurora next [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 7 for `when`, 365 for `next`)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Kp index (geomagnetic activity)
- Visibility probability
- Cloud cover forecast
- Moon phase impact
- Viewing recommendations
- For `next`: Probabilistic forecasts based on solar cycle

**Example:**

```bash
nexstar aurora tonight
nexstar aurora when --days 14
nexstar aurora next --days 730  # 2 years ahead
nexstar aurora tonight --export
```

### Eclipses

Track lunar and solar eclipses:

```bash
# Find next eclipse (lunar or solar)
nexstar eclipse next [OPTIONS]

# Find next lunar eclipse
nexstar eclipse lunar [OPTIONS]

# Find next solar eclipse
nexstar eclipse solar [OPTIONS]
```

**Options:**

- `--years`, `-y` INTEGER - Years ahead to search (default: 10)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Eclipse type and date/time
- Visibility from your location
- Partial/total coverage percentage
- Maximum eclipse time
- Viewing recommendations

**Example:**

```bash
nexstar eclipse next
nexstar eclipse lunar --years 5
nexstar eclipse solar --export
```

### Planetary Events

Track planetary conjunctions and oppositions:

```bash
# Find upcoming conjunctions
nexstar planets conjunctions [OPTIONS]

# Find upcoming oppositions
nexstar planets oppositions [OPTIONS]
```

**Options:**

- `--years`, `-y` INTEGER - Years ahead to search (default: 5)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Event date and time
- Planets involved
- Separation angle (for conjunctions)
- Visibility information
- Best viewing times

**Example:**

```bash
nexstar planets conjunctions
nexstar planets oppositions --years 10
nexstar planets conjunctions --export
```

### Meteor Showers

Enhanced meteor shower predictions with moon phase analysis:

```bash
# Find upcoming meteor showers
nexstar meteors next [OPTIONS]

# Find best viewing windows (minimal moon interference)
nexstar meteors best [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 90)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Shower name and peak date
- Zenith Hourly Rate (ZHR)
- Moon phase and illumination
- Adjusted ZHR (accounting for moon)
- Best viewing times
- Viewing recommendations

**Example:**

```bash
nexstar meteors next
nexstar meteors best --days 180
nexstar meteors next --export
```

### Comets

Track bright comets and their visibility:

```bash
# Find visible comets
nexstar comets visible [OPTIONS]

# Find upcoming bright comets
nexstar comets next [OPTIONS]
```

**Options:**

- `--years`, `-y` INTEGER - Years ahead to search (default: 5)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Comet name and designation
- Current/peak magnitude
- Visibility dates
- Best viewing times
- Equipment needed

**Example:**

```bash
nexstar comets visible
nexstar comets next --years 10
nexstar comets visible --export
```

### ISS Passes

Track International Space Station passes:

```bash
nexstar iss passes [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 7)
- `--min-altitude` FLOAT - Minimum altitude in degrees (default: 10.0)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Pass date and time
- Maximum altitude
- Duration
- Direction (appears/disappears)
- Quality rating
- Detailed pass information

**Example:**

```bash
nexstar iss passes
nexstar iss passes --days 14 --min-altitude 30
nexstar iss passes --export
```

### Satellites

Track bright satellite passes and flares:

```bash
# Find bright satellite passes
nexstar satellites bright [OPTIONS]

# Find Starlink train passes (placeholder)
nexstar satellites starlink [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 7)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Satellite name
- Pass date and time
- Maximum altitude
- Brightness (magnitude)
- Direction and duration

**Example:**

```bash
nexstar satellites bright
nexstar satellites bright --days 14 --export
```

### Zodiacal Light

Predict zodiacal light and gegenschein visibility:

```bash
# Find zodiacal light viewing windows
nexstar zodiacal zodiacal-light [OPTIONS]

# Find gegenschein viewing windows
nexstar zodiacal gegenschein [OPTIONS]
```

**Options:**

- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Optimal viewing periods
- Best times of year
- Moon phase requirements
- Viewing recommendations

**Example:**

```bash
nexstar zodiacal zodiacal-light
nexstar zodiacal gegenschein --export
```

### Variable Stars

Track variable star events (eclipses, maxima, minima):

```bash
nexstar variables events [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 90)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Star name and type
- Event type (eclipse, maximum, minimum)
- Event date and time
- Magnitude range
- Visibility information

**Example:**

```bash
nexstar variables events
nexstar variables events --days 180 --export
```

### Occultations

Track asteroid occultation events:

```bash
nexstar occultations next [OPTIONS]
```

**Options:**

- `--days`, `-d` INTEGER - Days ahead to check (default: 90)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Note:** This is a framework for future occultation data integration. Specialized databases are required for accurate predictions.

**Example:**

```bash
nexstar occultations next
nexstar occultations next --days 365 --export
```

## Space Events Calendar

The `events` command group provides access to The Planetary Society's space events calendar with viewing location recommendations:

```bash
# List upcoming space events
nexstar events upcoming [OPTIONS]

# Find best viewing location for a specific event
nexstar events viewing <EVENT_NAME> [OPTIONS]
```

**Options for `upcoming`:**

- `--days`, `-d` INTEGER - Days ahead to show (default: 90, ignored if `--date` is used)
- `--date` DATE - Find events around this date (YYYY-MM-DD format, e.g., 2025-12-14)
- `--range`, `-r` INTEGER - Days before and after `--date` to search (default: 7, only used with `--date`)
- `--type` TEXT - Filter by event type (meteor_shower, eclipse, etc.)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Options for `viewing`:**

- `--location`, `-l` TEXT - Location to check (default: your saved location)
- `--max-distance` FLOAT - Maximum distance to search for better locations in miles (default: 500.0)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

- Event name, date, and type
- Description and viewing requirements
- Visibility from your location
- Current sky conditions (Bortle class, SQM)
- Recommendations for better viewing locations
- Nearby dark sky sites if needed

**Example:**

```bash
# List upcoming events
nexstar events upcoming --days 120
nexstar events upcoming --type meteor_shower

# Find events around a specific date (default ±7 days)
nexstar events upcoming --date 2025-12-14
nexstar events upcoming --date 2025-12-14 --range 14  # ±14 days
nexstar events upcoming --date 2025-12-14 --type meteor_shower
nexstar events upcoming --date 2025-12-14 --range 30 --type meteor_shower  # ±30 days, meteor showers only

# Find best viewing for Geminid meteor shower
nexstar events viewing "Geminid"
nexstar events viewing "Total Lunar Eclipse" --location "Denver, CO"
nexstar events viewing "Geminid" --export
```

**Event Types:**

- `meteor_shower` - Meteor shower peaks
- `lunar_eclipse` - Lunar eclipses
- `solar_eclipse` - Solar eclipses
- `planetary_opposition` - Planetary oppositions
- `planetary_elongation` - Planetary elongations
- `planetary_brightness` - Planetary brightness peaks
- `solstice` - Solstices
- `equinox` - Equinoxes
- `space_mission` - Space mission events
- `other` - Other space events

## Vacation Planning

Plan astronomy viewing for vacation destinations:

```bash
# Check viewing conditions at a location
nexstar vacation view --location "LOCATION" [OPTIONS]

# Find nearby dark sky sites
nexstar vacation dark-sites --location "LOCATION" [OPTIONS]

# Comprehensive vacation astronomy plan
nexstar vacation plan --location "LOCATION" [OPTIONS]
```

**Options for `view`:**

- `--location`, `-l` TEXT - Destination location (required)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Options for `dark-sites`:**

- `--location`, `-l` TEXT - Destination location (required)
- `--max-distance` FLOAT - Maximum distance in miles (default: 100.0)
- `--min-bortle` INTEGER - Minimum Bortle class (1-9, default: 4)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Options for `plan`:**

- `--location`, `-l` TEXT - Destination location (required)
- `--days`, `-d` INTEGER - Number of days ahead (default: 7)
- `--start-date` DATE - Start date (YYYY-MM-DD format)
- `--end-date` DATE - End date (YYYY-MM-DD format)
- `--export`, `-e` - Export output to text file
- `--export-path` PATH - Custom export file path

**Output includes:**

**`view`:**

- Light pollution (Bortle class, SQM)
- Viewing recommendations
- Best times for observing

**`dark-sites`:**

- List of nearby International Dark Sky Places
- Distance and direction
- Bortle class and SQM values
- Site descriptions

**`plan`:**

- Viewing conditions summary
- Nearby dark sky sites
- Aurora visibility (if applicable)
- Upcoming eclipses in date range
- Meteor showers in date range
- Visible comets
- Comprehensive recommendations

**Example:**

```bash
# Check viewing conditions
nexstar vacation view --location "Fairbanks, AK"
nexstar vacation view --location "Moab, UT" --export

# Find dark sky sites
nexstar vacation dark-sites --location "Denver, CO" --max-distance 200
nexstar vacation dark-sites --location "Albuquerque, NM" --min-bortle 3 --export

# Comprehensive vacation plan
nexstar vacation plan --location "Fairbanks, AK" --days 7
nexstar vacation plan --location "Moab, UT" --start-date 2025-12-15 --end-date 2025-12-22
nexstar vacation plan --location "Denver, CO" --days 14 --export
```

## Data Management

Manage database and static reference data:

```bash
# Initialize static data (meteor showers, constellations, dark sky sites, space events)
nexstar data init-static

# Show database statistics
nexstar data stats

# Import catalog data
nexstar data import <SOURCE> [OPTIONS]

# List available data sources
nexstar data sources

# Download light pollution data
nexstar data download-light-pollution [OPTIONS]

# Clear light pollution data
nexstar data clear-light-pollution [OPTIONS]

# Vacuum database (reclaim space)
nexstar data vacuum
```

**`init-static` Command:**
Populates the database with static reference data that works offline:

- Meteor showers calendar
- Constellations and asterisms
- Dark sky sites (International Dark Sky Places)
- Space events calendar (Planetary Society)

This should be run once after database setup to enable offline functionality.

**Example:**

```bash
nexstar data init-static
nexstar data stats
nexstar data import openngc --mag-limit 12.0
```

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

## Command Groups Summary

The CLI is organized into logical groups:

**Telescope Control:**

- `connect` - Connection management
- `position` - Position queries
- `goto` - Slew commands
- `move` - Manual movement
- `track` - Tracking control
- `align` - Alignment commands

**Planning & Observation:**

- `telescope` - Telescope viewing guides
- `multi-night` - Multi-night planning
- `binoculars` - Binocular viewing
- `naked-eye` - Naked-eye stargazing
- `catalog` - Celestial object catalogs
- `vacation` - Vacation planning
- `events` - Space events calendar

**Celestial Events:**

- `aurora` - Aurora borealis visibility
- `eclipse` - Lunar and solar eclipses
- `planets` - Planetary events
- `meteors` - Meteor shower predictions
- `comets` - Comet tracking
- `iss` - ISS pass predictions
- `satellites` - Satellite passes
- `zodiacal` - Zodiacal light and gegenschein
- `variables` - Variable star events
- `occultations` - Asteroid occultations

**Configuration:**

- `location` - Observer location
- `time` - Time and date
- `optics` - Telescope and eyepiece configuration
- `ephemeris` - Ephemeris file management

**Data & Management:**

- `data` - Data import and management
- `dashboard` - Full-screen dashboard

## Further Reading

- [Main README](../README.md) - Project overview and interactive shell
- [Installation Guide](INSTALL.md) - Setup instructions
- [Python API Documentation](api/telescope_docs.md) - Programmatic usage
