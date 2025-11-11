# Data Import - CLI Guide

The `data` command group provides tools for importing and managing catalog data within the NexStar CLI.

## Overview

The data import system allows you to:

- View available data sources
- Import catalogs directly from the CLI
- Monitor database statistics
- Control magnitude filtering

All imports happen through the interactive CLI, making it easy to expand your object database without running separate scripts.

## Commands

### `data sources`

List all available data sources and their import status.

**Usage:**

```bash
nexstar data sources
```

**Example Output:**

```text
                     Available Data Sources
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Name    ┃ Description                  ┃ Available ┃ Imported ┃ License      ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ OpenNGC │ NGC/IC catalog of deep-sky   │    13,970 │    9,570 │ CC-BY-SA-4.0 │
│         │ objects                      │           │          │              │
└─────────┴──────────────────────────────┴───────────┴──────────┴──────────────┘

Total objects in database: 9,722
```text

**Columns:**

- **Name**: Data source identifier
- **Description**: What the catalog contains
- **Available**: Total objects in the source
- **Imported**: How many are currently in your database
- **License**: Data license (all open-source)

---

### `data import`

Import data from a catalog source.

**Usage:**

```bash
nexstar data import <source> [--mag-limit MAGNITUDE]
```

**Arguments:**

- `source`: Data source ID (e.g., `openngc`)

**Options:**

- `--mag-limit`, `-m`: Maximum magnitude to import (default: 15.0)

**Examples:**

```bash
# Import OpenNGC with default magnitude limit (15.0)
nexstar data import openngc

# Import only bright objects (magnitude 12 or brighter)
nexstar data import openngc --mag-limit 12.0

# Import all objects (no magnitude filtering)
nexstar data import openngc --mag-limit 99.0
```

**How it works:**

1. **Download**: Fetches the latest data from the source (cached in `/tmp/`)
2. **Parse**: Reads and validates the catalog data
3. **Filter**: Applies magnitude filtering to match your telescope capabilities
4. **Import**: Inserts objects into the SQLite database
5. **Report**: Shows import statistics

**Import Progress:**

The import shows a progress bar with:

- Spinner animation
- Percentage complete
- Estimated time remaining
- Current operation

**Example Output:**

```text
Importing OpenNGC
NGC/IC catalog of deep-sky objects
License: CC-BY-SA-4.0
Attribution: Mattia Verga and OpenNGC contributors

Downloading data...
✓ Downloaded 3,876,332 bytes to /tmp/openngc.csv

Importing with magnitude limit: 15.0
⠋ Importing OpenNGC (mag ≤ 15.0)... ━━━━━━━━━━━━━━━━━━━ 68% 0:00:15

✓ Import complete!
  Imported: 9,570
  Skipped:  4,399 (too faint or invalid)

Database now contains 9,722 objects
```text

---

### `data stats`

Show detailed database statistics.

**Usage:**

```bash
nexstar data stats
```

**Example Output:**

```text
Database Statistics
Total objects: 9,722
Dynamic objects: 26 (planets/moons)
Magnitude range: -12.6 to 15.8

   Objects by Catalog
┏━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Catalog      ┃ Count ┃
┡━━━━━━━━━━━━━━╇━━━━━━━┩
│ asterisms    │     9 │
│ bright_stars │    35 │
│ caldwell     │     4 │
│ ic           │ 2,691 │
│ messier      │    66 │
│ moons        │    18 │
│ ngc          │ 6,891 │
│ planets      │     8 │
└──────────────┴───────┘

    Objects by Type
┏━━━━━━━━━━━━━┳━━━━━━━┓
┃ Type        ┃ Count ┃
┡━━━━━━━━━━━━━╇━━━━━━━┩
│ asterism    │     9 │
│ cluster     │ 1,031 │
│ double_star │   247 │
│ galaxy      │ 7,474 │
│ moon        │    19 │
│ nebula      │   376 │
│ planet      │     7 │
│ star        │   559 │
└─────────────┴───────┘

Last updated: 2025-11-07 00:41:01
Database version: 1.0.0
```text

---

## Available Data Sources

### OpenNGC

**Source**: [OpenNGC on GitHub](https://github.com/mattiaverga/OpenNGC)
**License**: CC-BY-SA-4.0
**Attribution**: Mattia Verga and OpenNGC contributors

**Description:**

- Complete NGC (New General Catalogue) and IC (Index Catalogue) data
- 13,970 total objects
- Includes galaxies, nebulae, star clusters
- Coordinate data in J2000 epoch
- Magnitude data (V-band and B-band)
- Common names and Hubble classifications
- Constellation assignments

**Object Types:**

- Galaxies (G, GPair, GTrpl, GGroup)
- Nebulae (PN, HII, EmN, RfN, DrkN, SNR)
- Star Clusters (OCl, GCl, Cl+N)
- Stars (*, **, Nova,*Ass)

**Typical Import:**

- With mag ≤ 15.0: ~9,570 objects imported
- With mag ≤ 12.0: ~3,200 objects imported
- With mag ≤ 10.0: ~1,100 objects imported

---

## Magnitude Filtering

### Why Filter by Magnitude?

Not all objects in a catalog are visible with your telescope. The magnitude limit ensures you only import objects you can actually observe.

### Recommended Limits by Telescope

| Telescope Aperture | Theoretical Limit | Recommended Import Limit |
|-------------------|-------------------|-------------------------|
| 60mm (2.4")       | 11.5             | 11.0                   |
| 80mm (3.1")       | 12.0             | 11.5                   |
| 114mm (4.5")      | 13.0             | 12.5                   |
| 150mm (6") NexStar 6SE | 14.0        | 13.5-15.0              |
| 200mm (8")        | 14.5             | 14.0-15.0              |
| 254mm (10")       | 15.0             | 15.0                   |

**Notes:**

- Theoretical limits assume dark skies and perfect seeing
- Light pollution reduces effective magnitude by 1-3 magnitudes
- Extended objects (galaxies, nebulae) appear fainter than their listed magnitude
- Point sources (stars) are easier to see than their magnitude suggests

### Choosing Your Magnitude Limit

**Conservative (best for light pollution):**

```bash
nexstar data import openngc --mag-limit 12.0
```

- Only bright objects
- Visible from suburban locations
- ~3,200 objects from OpenNGC

**Recommended (NexStar 6SE in dark skies):**

```bash
nexstar data import openngc --mag-limit 15.0
```

- Default setting
- Includes most observable objects
- ~9,570 objects from OpenNGC

**Comprehensive (all available data):**

```bash
nexstar data import openngc --mag-limit 99.0
```

- Everything in the catalog
- Useful for planning future observations
- ~13,970 objects from OpenNGC

---

## Interactive Shell Usage

The data commands work seamlessly in the interactive shell:

```bash
$ nexstar shell
nexstar> data sources
[displays available sources]

nexstar> data import openngc
[downloads and imports OpenNGC]

nexstar> data stats
[shows updated statistics]

nexstar> catalog search "andromeda"
[search now includes NGC objects!]
```

---

## Database Information

### Storage Location

```text
src/celestron_nexstar/cli/data/catalogs.db
```

### Database Size

| Objects | Database Size |
|---------|--------------|
| 152 (initial) | 0.11 MB |
| 9,722 (+ OpenNGC) | 2.7 MB |
| 40,000 (future) | 8-12 MB (estimated) |

### Performance

- Search queries: <10ms (FTS5 full-text search)
- Filter queries: <20ms
- Startup time: <100ms
- Memory usage: ~15 MB

### Technology

- **Engine**: SQLite 3
- **Search**: FTS5 (Full-Text Search 5)
- **Indexes**: 6 B-tree indexes for fast lookups
- **Mode**: WAL (Write-Ahead Logging) for concurrent access

---

## Troubleshooting

### Import fails with download error

**Problem**: Network issues or GitHub unavailable

**Solution**:

1. Download manually: https://github.com/mattiaverga/OpenNGC/raw/master/database_files/NGC.csv
2. Save to `/tmp/openngc.csv`
3. Run import again (will use cached file)

### Import is slow

**Problem**: Processing 13,970 objects takes time

**Solution**:

- Use a stricter magnitude limit to import fewer objects
- The progress bar shows estimated time remaining
- Typical import time: 30-60 seconds

### Database is large

**Problem**: Database file is taking disk space

**Solution**:

- 2.7 MB is very small (3 MP3s worth)
- Can delete and recreate if needed
- Re-importing is fast (uses cached download)

### Objects not appearing in searches

**Problem**: Just imported but can't find objects

**Solution**:

1. Check import was successful (no errors)
2. Use `data stats` to verify object count
3. Try different search terms (name, common name)
4. Check magnitude - very faint objects may not be useful

---

## Future Data Sources

More catalogs will be added in future releases:

- **SAO Star Catalog** (9,000 bright stars)
- **WDS Double Stars** (2,000 visual pairs)
- **GCVS Variable Stars** (1,000 bright variables)
- **Caldwell Catalog** (109 deep-sky objects)
- **Herschel 400** (400 deep-sky objects)

Each will have its own `data import <source>` command.

---

## License & Attribution

### OpenNGC

**License**: CC-BY-SA-4.0 (Creative Commons Attribution-ShareAlike 4.0)

**Attribution**: Mattia Verga and OpenNGC contributors

**You must**:

- Give appropriate credit to OpenNGC
- Indicate if changes were made
- Distribute any derivative works under the same license

**Source**: https://github.com/mattiaverga/OpenNGC

---

## Examples

### Complete Workflow

```bash
# Start CLI
nexstar shell
```

# Check what's available

nexstar> data sources

# Import OpenNGC

nexstar> data import openngc

# Verify import

nexstar> data stats

# Search imported objects

nexstar> catalog search "whirlpool"
nexstar> catalog info "M51"

# Use in GoTo commands

nexstar> goto object M51

```text

### Custom Magnitude Limits

```bash
# For 4.5" telescope in city
nexstar data import openngc --mag-limit 11.0
```

# For 6" telescope in dark skies

nexstar data import openngc --mag-limit 14.0

# Import everything for research

nexstar data import openngc --mag-limit 99.0

```bash

### Re-importing with Different Settings

```bash
# Delete database
rm src/celestron_nexstar/cli/data/catalogs.db

# Re-run migration (restores original 152 objects)
uv run python scripts/migrate_catalog_to_sqlite.py

# Import with new settings
nexstar data import openngc --mag-limit 12.0
```

---

## See Also

- `CATALOG_EXPANSION_PLAN.md` - Full catalog expansion roadmap
- `PHASE_1_COMPLETE.md` - Database architecture details
- `PHASE_2_COMPLETE.md` - OpenNGC import documentation
- `nexstar catalog --help` - Catalog search commands
