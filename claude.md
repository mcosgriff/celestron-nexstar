# Development Guidelines for Claude Code

This file contains important patterns and guidelines for this project. AI assistants should follow these when making changes.

## Database Migrations (Alembic)

### Critical: Migrations MUST be Idempotent

**Problem:** Migrations have repeatedly failed due to trying to create tables/indexes that already exist.

**Root Cause:** The database can end up in intermediate states where tables or indexes exist but Alembic doesn't know about them (empty `alembic_version` table, or partial migrations).

**Solution:** ALL migrations must check if objects exist before creating them, and check if they exist before dropping them.

### Required Helper Function

Add this to the top of EVERY migration file:

```python
def _index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:table AND name=:index"
        ),
        {"table": table_name, "index": index_name}
    )
    return result.fetchone() is not None
```

### Table Creation Pattern

```python
# Check if table exists before creating
bind = op.get_bind()
inspector = sa.inspect(bind)
if 'table_name' not in inspector.get_table_names():
    op.create_table('table_name',
        sa.Column('id', sa.Integer(), primary_key=True),
        # ... other columns
    )
```

### Index Creation Pattern

```python
with op.batch_alter_table('table_name', schema=None) as batch_op:
    if not _index_exists('table_name', 'index_name'):
        batch_op.create_index('index_name', ['column'], unique=False)
```

### Index Deletion Pattern (for downgrade)

```python
with op.batch_alter_table('table_name', schema=None) as batch_op:
    if _index_exists('table_name', 'index_name'):
        batch_op.drop_index('index_name')
```

### SpatiaLite Special Handling

SpatiaLite automatically creates geometry indexes. Never try to create or drop them manually:

```python
# Geometry index created automatically by GeoAlchemy2/SpatiaLite
# DO NOT: batch_op.create_index('idx_table_geometry', ['geometry'], ...)
```

When initializing SpatialMetadata, wrap in try/except since it may already exist:

```python
try:
    op.execute("SELECT InitSpatialMetadata(1)")
except Exception:
    # SpatialMetadata already exists, continue
    pass
```

## Model Design

### Index Definitions in Models

Indexes defined in model `__table_args__` are NOT automatically created by Alembic's `op.create_table()`. They must be explicitly created in migrations.

Example from `models.py`:
```python
class ISSPassModel(Base):
    __tablename__ = "iss_passes"

    # ... columns ...

    __table_args__ = (
        Index("idx_location_fetched", "latitude", "longitude", "fetched_at"),
        # ... other indexes
    )
```

The corresponding migration MUST explicitly create these indexes:
```python
op.create_table('iss_passes', ...)

with op.batch_alter_table('iss_passes', schema=None) as batch_op:
    if not _index_exists('iss_passes', 'idx_location_fetched'):
        batch_op.create_index('idx_location_fetched', ['latitude', 'longitude', 'fetched_at'], unique=False)
```

## Testing Migrations

Before committing a migration, test it is idempotent:

```bash
# Clean start
rm -f ~/.config/celestron-nexstar/catalogs.db*

# First run - should create everything
alembic upgrade head

# Second run - should be no-op (migrations already applied)
alembic upgrade head

# Verify no errors
```

## Common Issues

### Issue: "index already exists" error

**Cause:** Migration trying to create index without checking if it exists first.

**Fix:** Add `_index_exists()` check before creating the index.

### Issue: "table already exists" error

**Cause:** Migration trying to create table without checking if it exists first.

**Fix:** Add table existence check using SQLAlchemy inspector.

### Issue: Empty alembic_version table

**Cause:** Database created with `Base.metadata.create_all()` instead of migrations.

**Fix:** Delete database and recreate using only migrations. Never use `create_all()` in production code.

## GUI Database Management

The "Create DB + Apply Migrations" button in `settings_dialog.py` should:
1. Create empty database file if it doesn't exist
2. Run `alembic upgrade head`
3. Handle errors gracefully

It should NOT call `Base.metadata.create_all()` or `db.init_schema()`.

## Seed File Location

**IMPORTANT: All seed files MUST be located in `src/celestron_nexstar/data/`**

This directory contains all static data files used to seed the database:

- **`src/celestron_nexstar/data/`** - Root for catalog configuration files:
  - `catalogs.yaml` - Custom catalog definitions (optional, for YAML-based catalogs)
  - `catalogs_example.yaml` - Example catalog file showing all available fields

- **`src/celestron_nexstar/data/seed/`** - JSON seed files for all reference data:
  - `object_types.json` - Object type definitions (galaxies, nebulae, etc.) and abbreviations
  - `object_corrections.json` - Manual corrections for objects with missing/incorrect data
  - `constellations.json` - Constellation decoration data
  - `asterisms.json` - Asterism decoration data
  - `star_name_mappings.json` - Common star names and Bayer designations
  - `meteor_showers.json` - Meteor shower data
  - `dark_sky_sites.json` - Dark sky site locations
  - `space_events.json` - Notable space events
  - `variable_stars.json` - Variable star data
  - `comets.json` - Comet orbital data
  - `eclipses.json` - Eclipse data
  - `asteroids.json` - Asteroid orbital data
  - `bortle_characteristics.json` - Bortle scale characteristics
  - `sol_planets.json` - Planet seed data
  - `sol_moons.json` - Moon seed data

**DO NOT** create seed files in any other location. The old locations (`data/` at project root and `src/celestron_nexstar/cli/data/`) are deprecated and should not be used.

## Database Seeding

### Object Types

The `object_types` table contains normalized type and subtype definitions for astronomical objects. This includes:
- Full names (e.g., "Open Cluster", "Planetary Nebula")
- Abbreviations (e.g., "oc", "gc", "pn", "rn")
- Descriptions for each type

**Seed file**: `src/celestron_nexstar/data/seed/object_types.json`
**Seeding script**: `scripts/seed_object_types.py`

To populate or update object types:
```bash
python scripts/seed_object_types.py
```

Or seed all reference data (including object types) from the GUI or CLI using the database seeder.

The seeder will:
- Insert new object types
- Update descriptions for existing types if the new description is longer/better (when force=True)
- Skip types that already exist with good descriptions

### Object Subtype Migration

After seeding object types, run the migration script to link existing objects to their proper type definitions:

```bash
python scripts/migrate_object_subtypes.py
```

This updates the `object_subtype_id` foreign key for all objects that have `object_subtype` string values.

### Data Quality Issues

Some objects may be missing subtype information entirely (e.g., NGC 185, NGC 147). These typically come from incomplete source data and will show as "-" or blank in the UI. To fix these:

1. Research the correct subtype (e.g., NGC 185 is a Dwarf Elliptical galaxy)
2. Either:
   - Update the source data file and re-import
   - Create a SQL script to update specific objects
   - Add to a "manual corrections" seed file

## Future Improvements

Consider adding these helper functions to `alembic/env.py` to make them available globally:
- `_index_exists(table, index)`
- `_table_exists(table)`
- `_column_exists(table, column)`
- `_constraint_exists(table, constraint)`

Consider creating:
- A "manual corrections" seed file for objects with missing or incorrect data
- A data validation script that identifies objects missing critical fields
- Automated lookups to external catalogs (SIMBAD, NED) to fill in missing data