# Custom YAML Catalog Feature - Summary

## Overview

Added support for importing user-defined custom catalogs from YAML files into the database. Users can now keep `catalogs.yaml` for their personal objects and import them via the CLI.

## What Was Built

### 1. YAML Import Function

**File**: `src/celestron_nexstar/cli/data_import.py`

**New Functions**:
- `import_custom_yaml()` - Imports YAML catalog into database
- `parse_catalog_number()` - Extracts catalog numbers from names
- Updated `import_data_source()` - Handles custom catalog specially

**Features**:
- Reads YAML catalog structure
- Validates required fields (name, ra_hours, dec_degrees, type)
- Supports magnitude filtering
- Progress bar with ETA
- Error handling with helpful messages
- Commits all changes atomically

### 2. Data Source Registry

**Updated**: `DATA_SOURCES` dictionary

**Added**:
```python
"custom": DataSource(
    name="Custom YAML",
    description="User-defined custom catalog (catalogs.yaml)",
    url="local file",
    objects_available=152,
    license="User-defined",
    attribution="User-defined",
    importer=import_custom_yaml,
)
```

### 3. Documentation

**Created Files**:
1. `src/celestron_nexstar/cli/data/catalogs_example.yaml` - Complete example with all fields
2. `docs/CUSTOM_CATALOG.md` - Comprehensive user guide (500+ lines)

## How It Works

### User Workflow

1. **Create or edit** `src/celestron_nexstar/cli/data/catalogs.yaml`
2. **Import into database**: `nexstar data import custom`
3. **Search and use**: `nexstar catalog search "my object"`

### Example YAML

```yaml
# My Observing List
favorites:
  - name: M31
    common_name: Andromeda Galaxy
    ra_hours: 0.71
    dec_degrees: 41.27
    magnitude: 3.4
    type: galaxy
    description: Nearest major galaxy

  - name: M42
    common_name: Orion Nebula
    ra_hours: 5.58
    dec_degrees: -5.39
    magnitude: 4.0
    type: nebula
    description: Best nebula for small telescopes
```

### Import Command

```bash
# Import all objects
nexstar data import custom

# Import with magnitude limit
nexstar data import custom --mag-limit 10.0
```

### What Happens

1. Locates `catalogs.yaml` in `src/celestron_nexstar/cli/data/`
2. Parses YAML structure
3. Validates each object
4. Applies magnitude filtering
5. Inserts into SQLite database
6. Shows import statistics

## Data Sources Comparison

| Source | Type | Objects | Import Command |
|--------|------|---------|----------------|
| Custom YAML | Local file | User-defined | `nexstar data import custom` |
| OpenNGC | Download | 13,970 | `nexstar data import openngc` |

## Import Results

### Before

```
Available Data Sources:
- OpenNGC: 13,970 available, 9,570 imported
```

### After

```
Available Data Sources:
- Custom YAML: 152 available, 0 imported  ← NEW!
- OpenNGC: 13,970 available, 9,570 imported
```

### After First Import

```bash
$ nexstar data import custom

Importing Custom YAML
User-defined custom catalog (catalogs.yaml)
License: User-defined
Attribution: User-defined

Reading custom catalog from: .../catalogs.yaml
Importing with magnitude limit: 15.0

⠋ Importing custom catalog... ━━━━━━━━━━━━━━━━━━━ 100%

✓ Import complete!
  Imported: 151
  Skipped:  1 (too faint or invalid)

Database now contains 9,873 objects
```

## Features

### Supported Fields

**Required**:
- `name` - Object name
- `ra_hours` - Right ascension (0-24)
- `dec_degrees` - Declination (-90 to +90)
- `type` - Object type

**Optional**:
- `common_name` - Popular name
- `magnitude` - Apparent magnitude
- `description` - Notes and details
- `parent` - For moons, parent planet

### Object Types

- `star` - Single star
- `double_star` - Binary/multiple system
- `planet` - Planet (uses ephemeris)
- `moon` - Moon (uses ephemeris)
- `galaxy` - Galaxy
- `nebula` - Nebula
- `cluster` - Star cluster
- `asterism` - Star pattern

### Catalog Organization

Users can organize objects into multiple catalogs:

```yaml
spring_galaxies:
  - name: M51
    # ...

summer_nebulae:
  - name: M57
    # ...

my_favorites:
  - name: Custom1
    # ...
```

Each top-level key becomes a catalog name in the database.

## Use Cases

### 1. Personal Observing Lists

```yaml
tonight:
  - name: M31
    # ... Andromeda
  - name: M42
    # ... Orion Nebula
```

### 2. Custom Asterisms

```yaml
local_patterns:
  - name: My House Pattern
    type: asterism
    # ... coordinates
```

### 3. Target Planning

```yaml
astrophotography:
  - name: NGC 7000
    description: North America Nebula - 2hr exposure
    # ...

visual_showpieces:
  - name: M13
    description: Best globular for public viewing
    # ...
```

### 4. Project Tracking

```yaml
messier_marathon:
  # Objects for Messier marathon

herschel_400:
  # Herschel 400 observing program

double_stars:
  # Beautiful double star targets
```

## Benefits

### For Users

1. **Keep custom data** - Don't lose your personal catalog
2. **Easy import** - Single command to add to database
3. **Flexible organization** - Organize by any criteria
4. **Full CLI integration** - Works with all catalog commands
5. **Documented format** - Clear examples and guides

### For Developers

1. **Extensible** - Easy to add more YAML features
2. **Reusable** - Import function can be called from scripts
3. **Well-tested** - Validated with 152-object catalog
4. **Type-safe** - Full type hints and validation
5. **Error handling** - Graceful failures with helpful messages

## Files Modified/Created

### Modified
1. `src/celestron_nexstar/cli/data_import.py` - Added YAML import (+150 lines)

### Created
1. `src/celestron_nexstar/cli/data/catalogs_example.yaml` - Example catalog
2. `docs/CUSTOM_CATALOG.md` - User guide (500+ lines)
3. `docs/CUSTOM_YAML_FEATURE.md` - This document

**Total new code**: ~150 lines
**Total documentation**: ~600 lines

## Testing

### Tested Scenarios

✅ Import default catalogs.yaml (151 objects imported)
✅ Magnitude filtering works
✅ Progress bar displays correctly
✅ Statistics updated
✅ Objects searchable after import
✅ Error handling for missing fields
✅ Multiple catalog sections supported
✅ Data sources list shows custom

### Verified Functionality

✅ YAML parsing
✅ Field validation
✅ Type conversion (string → enum)
✅ Catalog number extraction
✅ Dynamic object detection
✅ Database insertion
✅ Progress tracking
✅ Error messages

## Database Impact

### Before Custom Import
```
Total objects: 9,722
- OpenNGC: 9,570
- Original catalogs: 152
```

### After Custom Import
```
Total objects: 9,873
- OpenNGC: 9,570
- Custom YAML: 151
- Original catalogs: 152
```

Note: Original 152 objects were from initial YAML. After custom import, they're in the database as separate entries if re-imported.

## Coordinate Conversion Help

Users often struggle with coordinates. The guide includes:

### RA Conversion (HMS → Hours)
```
12h 30m 00s → 12.5 hours
Formula: h + m/60 + s/3600
```

### Dec Conversion (DMS → Degrees)
```
45° 30' 00" → 45.5 degrees
Formula: d + m/60 + s/3600
```

### Python Helper Functions
```python
def hms_to_hours(h, m, s):
    return h + m/60 + s/3600

def dms_to_degrees(d, m, s):
    sign = 1 if d >= 0 else -1
    return sign * (abs(d) + m/60 + s/3600)
```

## Best Practices Documented

1. **Use descriptive names**
2. **Always include magnitude** (helps filtering)
3. **Add detailed descriptions** (observing notes)
4. **Organize by observing goals** (themes, seasons, etc.)
5. **Include coordinate sources** (where you got data)

## Error Handling

### Missing Required Fields
```
Warning: Missing required fields for M31
```

### Invalid Object Type
```
Warning: Unknown object type 'comet' for Halley
(Falls back to 'star')
```

### File Not Found
```
✗ Custom catalog not found at .../catalogs.yaml
Create a catalogs.yaml file in src/celestron_nexstar/cli/data/
```

### YAML Syntax Error
```
✗ Import failed: YAML parse error on line 15
(Shows full traceback)
```

## Future Enhancements

### Possible Additions

1. **Validate coordinates** - Check RA/Dec ranges
2. **Duplicate detection** - Warn about duplicate names
3. **Constellation lookup** - Auto-determine constellation
4. **Export to YAML** - Export database objects to YAML
5. **Update existing** - Smart update vs insert
6. **Delete support** - Remove objects from database

### User Requests

- Import from CSV
- Import from Stellarium files
- Import from SkySafari lists
- Batch coordinate conversion
- Visual YAML editor

## Integration with Existing Features

### Catalog Commands

```bash
# Search custom objects
nexstar catalog search "my object"

# Get info
nexstar catalog info "my object"

# List by catalog
nexstar catalog list my_favorites
```

### GoTo Commands

```bash
# GoTo custom object
nexstar goto object "my object"

# Works exactly like built-in objects
nexstar goto object M31
nexstar goto object "my custom target"
```

### Data Management

```bash
# See what's imported
nexstar data sources

# Re-import after edits
nexstar data import custom

# Check statistics
nexstar data stats
```

## Conclusion

The custom YAML catalog feature provides a simple, flexible way for users to:
1. Keep their personal object lists
2. Import them into the searchable database
3. Use them with all CLI commands
4. Organize objects however they want

All while maintaining backward compatibility with the original YAML catalog format.

---

*Created: 2025-11-06*
*Status: Complete and tested*
