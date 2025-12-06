# DuckDB Migration Cleanup Guide

## Overview

After migrating to DuckDB, we can remove SQLAlchemy/Alembic dependencies for the catalog database. However, some parts of the codebase may still use SQLAlchemy for other features (observations, preferences, etc.).

## What Can Be Removed

### ✅ Safe to Remove

1. **Alembic Migration Files** (`alembic/versions/*.py`)
   - All Alembic migration files can be removed
   - We now use DuckDB's native migration system

2. **Alembic Configuration** (`alembic.ini`, `alembic/env.py`)
   - Can be removed if not used elsewhere
   - Check if other features use Alembic

3. **SQLAlchemy References in Catalog Database**
   - `src/celestron_nexstar/api/database/database.py` - Can be deprecated/removed
   - Only keep if needed for backward compatibility

### ⚠️ Keep (May Still Be Used)

1. **SQLAlchemy Models** (`src/celestron_nexstar/api/database/models.py`)
   - May still be used for:
     - Observations
     - User preferences
     - Other non-catalog features
   - Check usage before removing

2. **Database Seeder** (`src/celestron_nexstar/api/database/database_seeder.py`)
   - May need to be adapted for DuckDB
   - Or kept for SQLite compatibility if needed

## Starplot Parquet File Setup

### No Setup Required! ✅

Starplot's parquet files are automatically available:

1. **Abridged Catalog (Included)**
   - `bigsky.0.4.0.stars.mag11.parquet` (~370k stars)
   - Included with starplot package
   - Automatically found via `DataFiles.BIG_SKY_MAG11`

2. **Full Catalog (Auto-Download)**
   - `bigsky.0.4.0.stars.parquet` (~2.5M stars)
   - Downloads automatically when first used
   - Saved to `~/.cache/celestron-nexstar/starplot-data/`

3. **DSO Database**
   - `sky.db` (DuckDB database with DSOs)
   - Included with starplot package
   - Automatically found via `DataFiles.DATABASE`

### How It Works

The DuckDB implementation automatically:
1. Checks starplot's `DataFiles` for included files
2. Falls back to checking the starplot data directory
3. Uses whatever is available (abridged or full)

**No manual setup needed!** The abridged version works out of the box.

## Migration Command

The `nexstar data migrate` command now:
1. ✅ Creates DuckDB database
2. ✅ Runs schema migrations
3. ✅ Migrates data from SQLite (if exists)
4. ✅ Populates seed data (constellations, asterisms, etc.)
5. ✅ Verifies starplot parquet files are available

## Next Steps

1. **Test the migrate command** - Ensure it works end-to-end
2. **Remove Alembic files** - After confirming everything works
3. **Update documentation** - Remove references to SQLite/Alembic
4. **Adapt seed data** - If needed for DuckDB (or keep SQLite compatibility)

