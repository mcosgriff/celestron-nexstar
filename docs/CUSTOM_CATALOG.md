# Custom Catalog Guide

## Overview

The custom catalog feature allows you to add your own celestial objects to the NexStar database using a simple YAML file. This is perfect for:

- Personal observing lists
- Local asterisms and patterns
- Objects not in standard catalogs
- Targets for specific observing sessions
- Organizing objects by theme or project

## Quick Start

1. **Copy the example file:**

   ```bash
   cd src/celestron_nexstar/cli/data/
   cp catalogs_example.yaml my_catalog.yaml
   ```

2. **Edit the file** with your objects (see format below)

3. **Rename to catalogs.yaml:**

   ```bash
   mv my_catalog.yaml catalogs.yaml
   ```

4. **Import into database:**

   ```bash
   nexstar data import custom
   ```

That's it! Your objects are now searchable and usable for GoTo commands.

## File Format

### Basic Structure

````yaml
# Catalog Name (appears in database)
catalog_name:
  - name: Object Name
    ra_hours: 12.5
    dec_degrees: 45.0
    type: galaxy

  - name: Another Object
    ra_hours: 15.2
    dec_degrees: -22.3
    type: star
```yaml

### Required Fields

Every object **must** have these fields:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `name` | string | any | Object name (unique identifier) |
| `ra_hours` | float | 0-24 | Right ascension in decimal hours |
| `dec_degrees` | float | -90 to +90 | Declination in decimal degrees |
| `type` | string | see below | Object type |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `common_name` | string | Popular name (e.g., "Andromeda Galaxy") |
| `magnitude` | float | Apparent magnitude (smaller = brighter) |
| `description` | string | Notes, observing details, etc. |
| `parent` | string | For moons, the parent planet |

### Object Types

Valid values for `type`:

- `star` - Single star
- `double_star` - Binary or multiple star system
- `planet` - Planet (uses ephemeris)
- `moon` - Moon (uses ephemeris)
- `galaxy` - Galaxy
- `nebula` - Any nebula type
- `cluster` - Star cluster (open or globular)
- `asterism` - Star pattern

## Coordinate Conversion

### RA: HMS to Decimal Hours

**Formula**: `hours + (minutes / 60) + (seconds / 3600)`

**Examples**:

```text
12h 30m 00s  →  12.5 hours
06h 45m 00s  →  6.75 hours
18h 36m 56s  →  18.615 hours
````

**Quick conversion**:

````python
# Python helper
def hms_to_hours(h, m, s):
    return h + m/60 + s/3600

# Example
ra_hours = hms_to_hours(12, 30, 0)  # 12.5
```python

### Dec: DMS to Decimal Degrees

**Formula**: `degrees + (arcmin / 60) + (arcsec / 3600)`

**Examples**:

```text
+45° 30' 00"  →  45.5 degrees
-22° 18' 00"  →  -22.3 degrees
+00° 00' 30"  →  0.008 degrees
````

**Quick conversion**:

````python
# Python helper
def dms_to_degrees(d, m, s):
    sign = 1 if d >= 0 else -1
    return sign * (abs(d) + m/60 + s/3600)

# Example
dec_degrees = dms_to_degrees(45, 30, 0)  # 45.5
```python

## Complete Examples

### Example 1: Simple Observing List

```yaml
# Tonight's Targets
tonight:
  - name: M31
    common_name: Andromeda Galaxy
    ra_hours: 0.71
    dec_degrees: 41.27
    magnitude: 3.4
    type: galaxy
    description: Nearest major galaxy, visible to naked eye

  - name: M42
    common_name: Orion Nebula
    ra_hours: 5.58
    dec_degrees: -5.39
    magnitude: 4.0
    type: nebula
    description: Best nebula for small telescopes

  - name: M13
    common_name: Hercules Globular Cluster
    ra_hours: 16.69
    dec_degrees: 36.46
    magnitude: 5.8
    type: cluster
    description: Premier northern hemisphere globular
```yaml

### Example 2: Custom Asterisms

```yaml
# My Asterisms
local_patterns:
  - name: My House Pattern
    ra_hours: 20.0
    dec_degrees: 40.0
    magnitude: 3.0
    type: asterism
    description: Pattern visible from my backyard

  - name: Diamond of Virgo
    ra_hours: 13.0
    dec_degrees: 5.0
    magnitude: 2.0
    type: asterism
    description: Formed by Arcturus, Spica, Denebola, Cor Caroli
```yaml

### Example 3: Double Stars

```yaml
# Beautiful Double Stars
doubles:
  - name: Albireo
    common_name: Beta Cygni
    ra_hours: 19.51
    dec_degrees: 27.96
    magnitude: 3.1
    type: double_star
    description: Gold and blue, beautiful contrast

  - name: Mizar
    common_name: Zeta Ursae Majoris
    ra_hours: 13.40
    dec_degrees: 54.93
    magnitude: 2.3
    type: double_star
    description: In Big Dipper handle, test of eyesight
```yaml

### Example 4: Multi-line Descriptions

```yaml
favorites:
  - name: NGC 2244
    common_name: Rosette Nebula Cluster
    ra_hours: 6.54
    dec_degrees: 4.95
    magnitude: 4.8
    type: cluster
    description: |
      Open cluster at center of Rosette Nebula.
      Best viewed with nebula filter.
      Approximately 5,000 light years away.
      Contains about 100 stars.
```yaml

## Organizing Your Catalog

### By Season

```yaml
spring_objects:
  - name: M51
    # ... fields

summer_objects:
  - name: M57
    # ... fields

autumn_objects:
  - name: M31
    # ... fields

winter_objects:
  - name: M42
    # ... fields
```yaml

### By Type

```yaml
my_galaxies:
  - name: NGC 4565
    # ... fields

my_nebulae:
  - name: NGC 7000
    # ... fields

my_clusters:
  - name: M37
    # ... fields
```yaml

### By Difficulty

```yaml
easy_targets:
  - name: M31
    magnitude: 3.4
    # ... fields

moderate_targets:
  - name: M101
    magnitude: 7.9
    # ... fields

challenging_targets:
  - name: NGC 891
    magnitude: 10.0
    # ... fields
```yaml

## Importing Your Catalog

### Basic Import

```bash
nexstar data import custom
````

This imports all objects with magnitude ≤ 15.0 (default).

### With Magnitude Limit

````bash
# Only bright objects
nexstar data import custom --mag-limit 10.0

# Only very bright objects
nexstar data import custom --mag-limit 6.0

# Import everything regardless of magnitude
nexstar data import custom --mag-limit 99.0
```bash

### Verify Import

```bash
# Show database statistics
nexstar data stats

# Search for your object
nexstar catalog search "my object name"

# List all custom catalogs
nexstar catalog list custom
```bash

## Using Your Objects

Once imported, your objects work exactly like built-in objects:

### Search

```bash
nexstar catalog search "object name"
nexstar catalog info "object name"
````

### GoTo

```bash
nexstar goto object "object name"
```

### In Shell

```text
nexstar> catalog search "m31"
nexstar> goto object m31
nexstar> position get
```

## Re-importing

If you edit your YAML file, you can re-import:

1. **Objects with the same name will be updated** (not duplicated)
2. **New objects will be added**
3. **Removed objects will remain in database** (manual deletion required)

To completely refresh:

```bash
# Delete database
rm src/celestron_nexstar/cli/data/catalogs.db

# Re-import OpenNGC
nexstar data import openngc

# Re-import custom
nexstar data import custom
```

## Tips & Best Practices

### 1. Use Descriptive Names

**Good**:

```yaml
- name: NGC 2244
  common_name: Rosette Cluster
```

**Bad**:

```yaml
- name: That one cluster
```

### 2. Include Magnitude

This helps with filtering and observing planning:

```yaml
- name: M101
  magnitude: 7.9 # Always include if known
```

### 3. Add Detailed Descriptions

````yaml
description: |
  Face-on spiral galaxy.
  Best with OIII filter in light pollution.
  Look for HII regions in spiral arms.
  Requires dark skies for best view.
```yaml

### 4. Organize by Observing Goals

```yaml
astrophotography_targets:
  # Objects good for imaging

visual_showpieces:
  # Best visual objects

public_outreach:
  # Crowd-pleasers for star parties
```yaml

### 5. Include Observing Notes

```yaml
- name: M51
  description: |
    Whirlpool Galaxy.
    Companion NGC 5195 visible in same field.
    Best at 100-150x magnification.
    Spiral structure visible in 6" scope under dark skies.
```yaml

## Coordinate Sources

Where to find coordinates for your objects:

1. **Stellarium** (free planetarium software)
   - Right-click object → Copy coordinates
   - Convert to decimal format

2. **Online databases**:
   - SIMBAD: http://simbad.u-strasbg.fr/simbad/
   - NED: https://ned.ipac.caltech.edu/
   - WikiSky: http://www.wikisky.org/

3. **Mobile apps**:
   - SkySafari
   - Stellarium Mobile
   - Star Walk 2

## Troubleshooting

### Import fails with "Missing required fields"

Check that every object has:

- `name`
- `ra_hours`
- `dec_degrees`
- `type`

### Object not found after import

1. Check import succeeded (no errors)
2. Use exact name: `nexstar catalog search "exact name"`
3. Check magnitude wasn't filtered out
4. Verify with: `nexstar data stats`

### YAML syntax errors

Common mistakes:

```yaml
# Wrong - no space after colon
name:M31

# Correct - space after colon
name: M31

# Wrong - inconsistent indentation
- name: M31
    ra_hours: 12.5  # 4 spaces
  dec_degrees: 45.0  # 2 spaces

# Correct - consistent indentation (2 spaces)
- name: M31
  ra_hours: 12.5
  dec_degrees: 45.0
```yaml

### Coordinates seem wrong

Use this Python snippet to verify:

```python
# Test coordinate conversion
from celestron_nexstar.api.catalogs import parse_coordinates

# Your coordinates
ra_hours = 12.5
dec_degrees = 45.0

print(f"RA: {ra_hours}h = {ra_hours * 15}°")
print(f"Dec: {dec_degrees}°")

# Cross-check with Stellarium or SIMBAD
```python

## Example: Complete Custom Catalog

Here's a complete example showing all features:

```yaml
# My Observing List 2025
# Created: 2025-01-01
# Telescope: NexStar 6SE
# Location: My backyard

# Spring Galaxies
spring_galaxies:
  - name: M51
    common_name: Whirlpool Galaxy
    ra_hours: 13.49
    dec_degrees: 47.19
    magnitude: 8.4
    type: galaxy
    description: |
      Classic face-on spiral.
      Companion NGC 5195 visible.
      Best at 150x magnification.

# Summer Nebulae
summer_nebulae:
  - name: M57
    common_name: Ring Nebula
    ra_hours: 18.89
    dec_degrees: 33.03
    magnitude: 8.8
    type: nebula
    description: |
      Planetary nebula in Lyra.
      Looks like smoke ring.
      Use 200x to see central star.

# Autumn Targets
autumn_clusters:
  - name: M15
    common_name: Great Pegasus Cluster
    ra_hours: 21.50
    dec_degrees: 12.17
    magnitude: 6.2
    type: cluster
    description: |
      Dense globular cluster.
      Resolvable with 6" scope.
      Contains planetary nebula Pease 1.

# Winter Showpieces
winter_favorites:
  - name: M42
    common_name: Orion Nebula
    ra_hours: 5.58
    dec_degrees: -5.39
    magnitude: 4.0
    type: nebula
    description: |
      Best nebula in sky.
      Visible to naked eye.
      Trapezium star cluster at center.
```yaml

Save this as `catalogs.yaml` and import with:

```bash
nexstar data import custom
````

## See Also

- `DATA_IMPORT.md` - Complete data import guide
- `catalogs_example.yaml` - Example file with all fields
- `nexstar data --help` - CLI command help
- `nexstar catalog --help` - Catalog search commands
