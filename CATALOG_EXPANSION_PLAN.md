# Catalog Expansion Plan: Matching Celestron's 40,000+ Object Database

## Current State

- **Current objects**: ~152 objects across 7 catalogs
- **Current catalogs**: Messier (110), bright stars, NGC popular, Caldwell, planets, planetary moons
- **Storage**: YAML file (`catalogs.yaml`) - 1,268 lines
- **Infrastructure**: Already supports dynamic ephemeris calculations via JPL data

## Goal

Match Celestron's NexStar hand controller database of **40,000+ celestial objects** with offline-capable storage and ephemeris integration.

---

## Phase 1: Database Architecture Design

### 1.1 Storage Strategy

**Switch from YAML to SQLite**
- **Why**: YAML works great for 150 objects, but 40K+ objects need efficient indexing
- **Benefits**:
  - Fast fuzzy search with FTS5 (Full-Text Search)
  - Efficient filtering by magnitude, type, catalog
  - ~5-10MB database size (compressed)
  - Zero-dependency (sqlite3 in Python stdlib)
  - Can still bundle in package as `.db` file

**Schema Design**:
```sql
CREATE TABLE objects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- e.g., "M31", "NGC 224"
    common_name TEXT,              -- e.g., "Andromeda Galaxy"
    catalog TEXT NOT NULL,         -- e.g., "messier", "ngc", "ic", "sao"
    catalog_number INTEGER,        -- Numeric part for sorting

    -- Position (J2000 epoch for fixed objects)
    ra_hours REAL NOT NULL,
    dec_degrees REAL NOT NULL,

    -- Physical properties
    magnitude REAL,
    object_type TEXT NOT NULL,     -- galaxy, nebula, cluster, star, etc.
    size_arcmin REAL,              -- Angular size

    -- Metadata
    description TEXT,
    constellation TEXT,

    -- Dynamic object support
    is_dynamic BOOLEAN DEFAULT 0,  -- True for planets/moons
    ephemeris_name TEXT,           -- Name for JPL ephemeris lookup
    parent_planet TEXT             -- For moons
);

CREATE INDEX idx_name ON objects(name);
CREATE INDEX idx_catalog ON objects(catalog);
CREATE INDEX idx_magnitude ON objects(magnitude);
CREATE INDEX idx_type ON objects(object_type);
CREATE INDEX idx_constellation ON objects(constellation);

-- Full-text search for fuzzy matching
CREATE VIRTUAL TABLE objects_fts USING fts5(
    name, common_name, description,
    content=objects, content_rowid=id
);
```

### 1.2 Data Migration

**Create migration script**: `scripts/migrate_catalog_to_sqlite.py`
- Read existing `catalogs.yaml`
- Populate initial SQLite database
- Preserve all existing functionality

---

## Phase 2: Data Source Integration

### 2.1 Deep-Sky Objects (NGC/IC) - ~14,000 objects

**Source**: [OpenNGC](https://github.com/mattiaverga/OpenNGC)
- **License**: CC-BY-SA-4.0 (compatible!)
- **Objects**: 13,957 NGC + IC objects
- **Format**: CSV (easily parseable)
- **Data includes**:
  - Accurate positions (RA/Dec J2000)
  - Object types (galaxy, nebula, cluster, etc.)
  - Magnitudes
  - Angular sizes
  - Common names

**Implementation**:
```python
# scripts/import_openngc.py
import csv
import sqlite3

def import_openngc(db_path: str, csv_path: str):
    """Import OpenNGC catalog into database."""
    conn = sqlite3.connect(db_path)

    with open(csv_path) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            # Parse NGC/IC object
            # Filter by magnitude (<= 15 for NexStar 6SE visibility)
            # Insert into objects table
            pass
```

### 2.2 Bright Stars (SAO Catalog) - ~9,000 objects

**Source**: SAO Star Catalog (public domain)
- **Total stars**: 258,997 (filter to mag <= 9 for practicality)
- **Filtered count**: ~9,000 stars brighter than magnitude 9
- **Data**: RA/Dec, proper motion, magnitudes, spectral types

**Why mag 9 cutoff**:
- GoTo mounts typically include stars for alignment
- Visual limit ~6.5 naked eye, ~13 with 6" telescope
- Mag 9 covers all alignment stars + visible stars

**Source locations**:
- CDS VizieR: [SAO catalog](https://cdsarc.cds.unistra.fr/viz-bin/cat/I/131A)
- Format: ASCII or CSV

### 2.3 Double Stars (WDS) - ~2,000 objects

**Source**: Washington Double Star Catalog
- **Filter**: Mag <= 10, separation > 2" (resolvable with 6")
- **Count**: ~2,000 interesting doubles
- **Why include**: Popular observing targets

### 2.4 Variable Stars (GCVS) - ~1,000 objects

**Source**: General Catalogue of Variable Stars
- **Filter**: Bright variables (mag <= 10)
- **Count**: ~1,000 observable variables
- **Popular targets**: Mira, Algol, Delta Cephei, etc.

### 2.5 Additional Catalogs

**Caldwell Catalog** - 109 objects (already have, migrate)
**Messier Catalog** - 110 objects (already have, migrate)
**Bright Stars** - ~50 navigation stars (already have, migrate)
**Herschel 400** - 400 deep-sky objects (popular observing list)
**Planets + Moons** - ~30 dynamic objects (already have, migrate)

---

## Phase 3: Implementation Roadmap

### 3.1 Database Module (`src/celestron_nexstar/api/database.py`)

```python
"""
SQLite-based catalog database with offline support.
"""

import sqlite3
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

@dataclass
class CatalogObject:
    """Represents a celestial object from the database."""
    id: int
    name: str
    common_name: str | None
    ra_hours: float
    dec_degrees: float
    magnitude: float | None
    object_type: str
    catalog: str
    # ... other fields

class CatalogDatabase:
    """Interface to the SQLite catalog database."""

    def __init__(self, db_path: Path | None = None):
        """Initialize database connection."""
        if db_path is None:
            # Use bundled database
            db_path = Path(__file__).parent / "data" / "catalogs.db"
        self.conn = sqlite3.connect(db_path)

    def search(self, query: str, max_results: int = 100) -> list[CatalogObject]:
        """Fuzzy search using FTS5."""
        # Use SQLite FTS5 for fast fuzzy matching
        pass

    def get_by_catalog(self, catalog: str, limit: int = 1000) -> list[CatalogObject]:
        """Get all objects from a specific catalog."""
        pass

    def filter_visible(
        self,
        max_magnitude: float = 13.0,
        object_types: list[str] | None = None,
        constellation: str | None = None
    ) -> list[CatalogObject]:
        """Filter objects by visibility criteria."""
        pass

    def get_dynamic_object(self, name: str, dt: datetime | None = None) -> CatalogObject:
        """Get planet/moon with current ephemeris position."""
        # Query database for object
        # If is_dynamic, calculate position using existing ephemeris module
        # Return object with updated RA/Dec
        pass
```

### 3.2 CLI Updates

**Maintain backward compatibility**:
- Keep existing `catalog` commands working
- Add new database-backed implementation
- Preserve YAML for custom user catalogs (optional)

**New capabilities**:
```bash
# Search now handles 40K+ objects efficiently
catalog search andromeda           # FTS5 fuzzy search

# Filter by catalog
catalog list --catalog ngc --limit 100
catalog list --catalog sao --magnitude-max 6

# Filter by visibility
catalog list --visible --mag-max 10 --type galaxy

# Statistics
catalog stats                      # Show catalog breakdown
# Output:
#   Total objects: 42,156
#   NGC:          7,840
#   IC:           5,386
#   SAO:          9,147
#   Messier:        110
#   ...
```

### 3.3 Data Pipeline Scripts

**Location**: `scripts/build_catalog_database.py`

```python
"""
Build the complete catalog database from source data.

Usage:
    python scripts/build_catalog_database.py --output data/catalogs.db

Downloads and processes:
- OpenNGC (NGC/IC)
- SAO catalog
- WDS (double stars)
- GCVS (variables)
- Existing YAML catalogs
"""
```

**CI/CD Integration**:
- Download sources during package build
- Generate `catalogs.db`
- Bundle in package distribution
- Keep database updated (monthly/quarterly)

---

## Phase 4: Offline & Distribution Strategy

### 4.1 Database Distribution

**Bundle with package**:
```
celestron-nexstar/
├── src/
│   └── celestron_nexstar/
│       └── api/
│           └── data/
│               ├── catalogs.db          # 8-12 MB SQLite database
│               └── catalogs.db.gz       # 3-5 MB compressed (optional)
```

**Package size impact**:
- Current package: ~500 KB
- With database: ~8-12 MB (uncompressed) or ~4-5 MB (compressed)
- Still reasonable for Python package

### 4.2 Ephemeris Integration

**Keep existing JPL ephemeris system**:
- Database stores `is_dynamic` flag
- Dynamic objects (planets/moons) link to ephemeris via `ephemeris_name`
- Position calculated on-demand using existing `ephemeris.py` module
- Fully offline after `ephemeris download` command

**Flow**:
```
User: catalog info "Jupiter"
  → Query database: SELECT * WHERE name='Jupiter'
  → Object has is_dynamic=1
  → Call get_planetary_position("Jupiter", dt=now)
  → Return object with current RA/Dec
```

---

## Phase 5: Testing & Validation

### 5.1 Data Quality Checks

- Verify RA/Dec ranges (0-24h, -90 to +90°)
- Check magnitude ranges (filter outliers)
- Validate object types against enum
- Ensure no duplicate names/IDs

### 5.2 Performance Testing

- Search performance: < 100ms for fuzzy search
- Filter performance: < 50ms for magnitude/type filters
- Database size: < 15 MB uncompressed
- Memory usage: < 50 MB resident

### 5.3 Compatibility Testing

- Ensure existing commands still work
- Verify ephemeris integration
- Test visibility filtering
- Validate goto commands with new objects

---

## Phase 6: Rollout Plan

### 6.1 Development Milestones

1. **M1 - Database Schema** (1-2 days)
   - Design and create SQLite schema
   - Create migration script from YAML
   - Test with existing 152 objects

2. **M2 - OpenNGC Import** (2-3 days)
   - Download and parse OpenNGC
   - Import into database
   - Validate data quality
   - Test search/filter performance

3. **M3 - Star Catalogs** (3-4 days)
   - Import SAO catalog (filtered)
   - Add double stars (WDS)
   - Add variable stars (GCVS)
   - Validate star data

4. **M4 - CLI Integration** (2-3 days)
   - Update catalog.py to use database
   - Maintain backward compatibility
   - Add new filter options
   - Update documentation

5. **M5 - Testing & Polish** (2-3 days)
   - Performance optimization
   - Data quality validation
   - Documentation updates
   - Tutorial updates

**Total estimated time**: 10-15 days of focused development

### 6.2 Release Strategy

**Version 0.2.0 - "Catalog Expansion"**
- Add SQLite database with 40K+ objects
- Maintain YAML backward compatibility (deprecated)
- Update documentation
- Add migration guide

**Breaking changes**: None (backward compatible)

---

## Expected Outcomes

### Final Database Stats
```
Total Objects: ~42,000
├── NGC Catalog:      7,840 deep-sky objects
├── IC Catalog:       5,386 deep-sky objects
├── SAO Stars:        9,000 bright stars (mag <= 9)
├── Double Stars:     2,000 resolvable pairs
├── Variable Stars:   1,000 bright variables
├── Messier:            110 popular objects
├── Caldwell:           109 deep-sky objects
├── Herschel 400:       400 deep-sky objects
├── Planets:              8 solar system planets
└── Moons:               28 planetary satellites
```

### Performance Targets
- Search latency: < 100ms
- Database size: 8-12 MB
- Memory footprint: < 50 MB
- Offline-capable: 100% (with ephemeris downloaded)

### User Benefits
- **40,000+ objects** vs current 152 (263x increase!)
- **Fast fuzzy search** with FTS5
- **Advanced filtering** by magnitude, type, catalog
- **Still fully offline** after initial download
- **Backward compatible** with existing scripts
- **Professional-grade** catalog matching commercial hand controllers

---

## Future Enhancements (Post-v1.0)

1. **Astrometry.net Integration**
   - Plate solving from images
   - Automatic alignment from photos

2. **Custom User Catalogs**
   - Allow users to add personal objects
   - Import from CSV/FITS
   - Share catalogs with community

3. **Observation Planning**
   - Tonight's best objects
   - Object rise/set times
   - Seasonal recommendations

4. **Mobile App**
   - Use catalog database via API
   - Offline-first architecture
   - Sync with desktop

5. **Catalog Updates**
   - Periodic database updates
   - Download via `catalog update` command
   - Version tracking

---

## Technical Considerations

### Licensing
- OpenNGC: CC-BY-SA-4.0 ✓
- SAO: Public domain ✓
- WDS: Public domain ✓
- GCVS: Public domain ✓
- All compatible with MIT license

### Dependencies
- No new dependencies needed!
- sqlite3: Python stdlib
- Existing: skyfield (ephemeris), pyyaml (config)

### Backward Compatibility
- Keep `catalogs.yaml` support for custom catalogs
- Database becomes default
- Migration script for power users
- No breaking API changes

---

## Success Metrics

- ✅ 40,000+ total objects
- ✅ < 100ms search performance
- ✅ < 15 MB package size increase
- ✅ 100% offline capable
- ✅ Backward compatible
- ✅ Professional feature parity with commercial hand controllers

---

**Next Steps**: Approval to begin Phase 1 (Database Architecture Design)
