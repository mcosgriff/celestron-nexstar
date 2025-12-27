# Database Seeding and Maintenance Scripts

This directory contains scripts for seeding, migrating, and maintaining the database.

## Overview

The scripts should be run in this order when setting up a new database or after importing new celestial data:

1. **seed_object_types.py** - Populate object type definitions
2. **migrate_object_subtypes.py** - Link objects to their type definitions
3. **apply_object_corrections.py** - Fix known data quality issues

## Scripts

### seed_object_types.py

Populates the `object_types` table with comprehensive astronomical object type definitions.

**Data source**: `data/object_types_seed.yaml`

**What it does**:
- Inserts all object types and subtypes (e.g., "Open Cluster", "Planetary Nebula")
- Adds abbreviation mappings (e.g., "oc" → "Open Cluster", "pn" → "Planetary Nebula")
- Updates descriptions for existing types if the new one is better

**Usage**:
```bash
python scripts/seed_object_types.py
```

**When to run**:
- After creating a new database
- When adding new object types to the seed file
- When updating descriptions

### migrate_object_subtypes.py

Migrates object_subtype string values to object_subtype_id foreign key references.

**What it does**:
- Finds all objects with `object_subtype` values (abbreviations or full names)
- Looks up the corresponding `object_types.id`
- Sets the `object_subtype_id` foreign key

**Tables migrated**:
- stars
- clusters
- nebulae
- galaxies
- double_stars
- moons
- planets

**Usage**:
```bash
python scripts/migrate_object_subtypes.py
```

**When to run**:
- After running `seed_object_types.py`
- After importing new celestial data
- When object_subtype_id values are missing

### apply_object_corrections.py

Applies manual corrections for objects with missing or incorrect data.

**Data source**: `data/object_corrections.yaml`

**What it does**:
- Fixes known objects with missing subtype information (e.g., NGC 185, NGC 147)
- Updates descriptions
- Can be extended to fix other data quality issues

**Usage**:
```bash
python scripts/apply_object_corrections.py
```

**When to run**:
- After discovering objects with missing data
- After adding corrections to `object_corrections.yaml`
- As part of regular database maintenance

## Data Files

### data/object_types_seed.yaml

Comprehensive definitions of astronomical object types including:
- **Star types**: Double Star, Binary Star, Variable Star, etc.
- **Cluster types**: Open Cluster (oc), Globular Cluster (gc), etc.
- **Nebula types**: Emission (en), Reflection (rn), Planetary (pn), Supernova Remnant (snr), etc.
- **Galaxy types**: Spiral (s), Elliptical (e), Irregular (i), Dwarf Spheroidal (dsph), etc.
- **Other types**: Planet, Moon, Asteroid, Comet, Asterism, etc.

Each entry includes:
- `name`: Full name or abbreviation
- `category`: Type category (e.g., "cluster_subtype", "nebula_subtype")
- `description`: Human-readable description

### data/object_corrections.yaml

Manual corrections for specific objects with data quality issues.

Each correction includes:
- `name`: Object name (e.g., "NGC 185")
- `catalog`: Catalog name (optional, for disambiguation)
- `object_subtype`: The correct subtype
- `description`: Additional description

## Common Workflows

### Setting up a new database

```bash
# 1. Create database and run migrations
alembic upgrade head

# 2. Import celestial data (messier, NGC, etc.)
# ... your import commands ...

# 3. Seed object types
python scripts/seed_object_types.py

# 4. Link objects to their types
python scripts/migrate_object_subtypes.py

# 5. Apply corrections
python scripts/apply_object_corrections.py
```

### After importing new data

```bash
# 1. Migrate new objects to use object_subtype_id
python scripts/migrate_object_subtypes.py

# 2. Check for and fix any missing data
# (inspect database, add corrections to object_corrections.yaml)

# 3. Apply corrections
python scripts/apply_object_corrections.py
```

### Adding new object types

1. Edit `data/object_types_seed.yaml` and add the new type(s)
2. Run `python scripts/seed_object_types.py`
3. If existing objects use this type, run `python scripts/migrate_object_subtypes.py`

### Fixing data quality issues

1. Identify objects with missing or incorrect data
2. Add corrections to `data/object_corrections.yaml`
3. Run `python scripts/apply_object_corrections.py`

## Validation

To check for objects missing subtype information:

```bash
# Galaxies without subtypes
sqlite3 ~/.config/celestron-nexstar/catalogs.db \
  "SELECT COUNT(*) FROM galaxies WHERE object_subtype IS NULL;"

# All objects without subtypes
sqlite3 ~/.config/celestron-nexstar/catalogs.db \
  "SELECT 'galaxies' as table_name, COUNT(*) as missing FROM galaxies WHERE object_subtype IS NULL
   UNION ALL
   SELECT 'clusters', COUNT(*) FROM clusters WHERE object_subtype IS NULL
   UNION ALL
   SELECT 'nebulae', COUNT(*) FROM nebulae WHERE object_subtype IS NULL;"
```

## Notes

- All scripts use `rich` for colored console output
- Scripts are idempotent - safe to run multiple times
- Changes are committed in a single transaction (all-or-nothing)
- Scripts provide detailed progress output and summaries