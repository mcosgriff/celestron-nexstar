# CLI Data Import Feature

## Summary

Added a complete data import system to the NexStar CLI, allowing users to import catalog data from within the interactive shell without running separate scripts.

## What Was Added

### 1. Data Import Module

**File**: `src/celestron_nexstar/cli/data_import.py`

**Features**:

- Registry of available data sources
- OpenNGC downloader with progress bar
- OpenNGC importer with magnitude filtering
- Data source listing with import statistics
- Rich formatting with tables and progress indicators

**Functions**:

```python
def list_data_sources() -> None
def import_data_source(source_id: str, mag_limit: float) -> bool
def download_openngc(output_path: Path) -> bool
def import_openngc(csv_path: Path, mag_limit: float, verbose: bool) -> tuple[int, int]
```

### 2. CLI Commands

**File**: `src/celestron_nexstar/cli/commands/data.py`

**Commands**:

- `nexstar data sources` - List available data sources and import status
- `nexstar data import <source>` - Import catalog data with magnitude filtering
- `nexstar data stats` - Show database statistics

### 3. Integration

**Modified**: `src/celestron_nexstar/cli/main.py`

**Changes**:

- Imported `data` command module
- Registered `data.app` with main CLI
- Added `data` to command group hints in interactive shell

## Usage Examples

### List Available Sources

```bash
$ nexstar data sources
                     Available Data Sources
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Name    ┃ Description                  ┃ Available ┃ Imported ┃ License      ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ OpenNGC │ NGC/IC catalog of deep-sky   │    13,970 │    9,570 │ CC-BY-SA-4.0 │
│         │ objects                      │           │          │              │
└─────────┴──────────────────────────────┴───────────┴──────────┴──────────────┘

Total objects in database: 9,722
```

### Import Data

```bash
$ nexstar data import openngc
Importing OpenNGC
NGC/IC catalog of deep-sky objects
License: CC-BY-SA-4.0
Attribution: Mattia Verga and OpenNGC contributors

Downloading data...
✓ Downloaded 3,876,332 bytes to /tmp/openngc.csv

Importing with magnitude limit: 15.0
⠋ Importing OpenNGC (mag ≤ 15.0)... ━━━━━━━━━━━━━━━━━━━ 100%

✓ Import complete!
  Imported: 9,570
  Skipped:  4,399 (too faint or invalid)

Database now contains 9,722 objects
```

### View Statistics

```bash
$ nexstar data stats
Database Statistics
Total objects: 9,722
Dynamic objects: 26 (planets/moons)
Magnitude range: -12.6 to 15.8

   Objects by Catalog
┏━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Catalog      ┃ Count ┃
┡━━━━━━━━━━━━━━╇━━━━━━━┩
│ ic           │ 2,691 │
│ ngc          │ 6,891 │
│ messier      │    66 │
│ ...          │   ... │
└──────────────┴───────┘
```

### Interactive Shell

```bash
$ nexstar shell
nexstar> data sources
[lists sources]

nexstar> data import openngc
[downloads and imports]

nexstar> catalog search "andromeda"
[searches new objects]
```

## Architecture

### Data Source Registry

```python
DATA_SOURCES: dict[str, DataSource] = {
    "openngc": DataSource(
        name="OpenNGC",
        description="NGC/IC catalog of deep-sky objects",
        url="https://github.com/mattiaverga/OpenNGC",
        objects_available=13970,
        license="CC-BY-SA-4.0",
        attribution="Mattia Verga and OpenNGC contributors",
        importer=import_openngc,
    ),
}
```

### Import Flow

1. **User runs command**: `nexstar data import openngc`
2. **Check cache**: Look for `/tmp/openngc.csv`
3. **Download if needed**: Fetch from GitHub with progress bar
4. **Parse data**: Read CSV, parse coordinates and magnitudes
5. **Filter**: Apply magnitude limit (default: 15.0)
6. **Import**: Insert into SQLite database with progress bar
7. **Report**: Show statistics and updated object counts

### Progress Indicators

Uses Rich library for beautiful CLI output:

- **Download**: Spinner with "Downloading..." message
- **Import**: Progress bar with percentage and ETA
- **Success**: Green checkmarks and formatted statistics
- **Errors**: Red X marks with helpful error messages

## Benefits

### For Users

1. **No Script Knowledge**: Import data without understanding Python scripts
2. **Interactive**: See progress and statistics in real-time
3. **Discoverable**: `data sources` shows what's available
4. **Flexible**: Adjust magnitude limits for your telescope
5. **Integrated**: Works seamlessly with existing catalog commands

### For Developers

1. **Extensible**: Easy to add new data sources
2. **Modular**: Separate downloader and importer functions
3. **Reusable**: Import functions can be called from scripts too
4. **Well-documented**: Type hints, docstrings, and user guides
5. **Error Handling**: Graceful failures with helpful messages

## Future Enhancements

### Additional Data Sources

Easy to add new sources by:

1. Writing importer function
2. Adding entry to `DATA_SOURCES` registry
3. Done! CLI automatically supports it

**Planned sources**:

- SAO Star Catalog (9,000 bright stars)
- WDS Double Stars (2,000 visual pairs)
- GCVS Variable Stars (1,000 bright variables)

### Enhanced Features

- **Update detection**: Check for new data versions
- **Differential imports**: Update existing objects
- **Import history**: Track when catalogs were imported
- **Rollback**: Undo imports
- **Export**: Export database to other formats

## Files Modified/Created

### New Files

1. `src/celestron_nexstar/cli/data_import.py` - Import module (393 lines)
2. `src/celestron_nexstar/cli/commands/data.py` - CLI commands (116 lines)
3. `docs/DATA_IMPORT.md` - User guide
4. `docs/CLI_DATA_IMPORT_FEATURE.md` - This document

### Modified Files

1. `src/celestron_nexstar/cli/main.py` - Added data command registration

**Total new code**: 509 lines
**Total documentation**: 500+ lines

## Testing

### Tested Commands

✅ `nexstar data --help` - Shows data command help
✅ `nexstar data sources` - Lists OpenNGC with statistics
✅ `nexstar data stats` - Shows database statistics
✅ `nexstar data import --help` - Shows import help
✅ Integration with main CLI - Data appears in `nexstar --help`
✅ Interactive shell support - Data commands work in shell mode

### Verified Functionality

✅ Progress bars display correctly
✅ Download caching works (uses `/tmp/openngc.csv`)
✅ Import statistics accurate (9,570 imported, 4,399 skipped)
✅ Database updated correctly (9,722 total objects)
✅ Magnitude filtering works
✅ Error handling graceful

## Documentation

### User Documentation

- `DATA_IMPORT.md` - Complete user guide with examples
- Inline help in all commands (`--help`)
- Rich formatting in terminal output

### Developer Documentation

- Type hints on all functions
- Docstrings on all public APIs
- Code comments for complex logic
- This architecture document

## Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| User-friendly | No scripts | CLI commands | ✅ |
| Fast | < 2 min | ~30 sec | ✅ |
| Discoverable | Help text | `--help` everywhere | ✅ |
| Informative | Progress visible | Progress bars | ✅ |
| Flexible | Magnitude control | `--mag-limit` option | ✅ |
| Reliable | Error handling | Try/catch everywhere | ✅ |

## Conclusion

The CLI data import feature makes it easy for users to expand their object database from within the NexStar CLI. The modular architecture makes it simple to add new data sources in the future, supporting the goal of reaching 40,000+ objects.

---

*Created: 2025-11-06*
*Status: Complete and tested*
