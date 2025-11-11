# Astronomical Catalog Data Sources

This document lists online sources for astronomical data that can be imported into the database, allowing `catalogs.yaml` to be reserved for custom/curated data only.

## Current Status

- **OpenNGC**: Already implemented - imports NGC/IC objects (covers most Messier objects)
- **Custom YAML**: Currently contains bright stars, Messier, NGC, Caldwell, planets, moons, asterisms

## Recommended Data Sources

### 1. Bright Stars (Navigation Stars)

#### Yale Bright Star Catalog (BSC)

- **Source**: https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html
- **Format**: ASCII/FITS
- **Objects**: ~9,000 stars brighter than magnitude 6.5
- **License**: Public domain
- **Notes**: Includes proper names, Bayer/Flamsteed designations, magnitudes, coordinates

#### Alternative: Hipparcos Catalog

- **Source**: https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/hip.html
- **Format**: ASCII/FITS
- **Objects**: ~118,000 stars with high-precision astrometry
- **License**: Public domain
- **Notes**: More comprehensive but larger; may want to filter by magnitude

#### Alternative: SIMBAD

- **Source**: http://simbad.u-strasbg.fr/simbad/
- **Format**: API/CSV export
- **License**: Free for non-commercial use
- **Notes**: Most comprehensive but requires API calls or manual exports

### 2. Messier Objects

#### Already Covered by OpenNGC

- OpenNGC includes all 110 Messier objects
- No separate import needed if OpenNGC is imported

#### Alternative: Dedicated Messier Lists

- Various sources maintain Messier-only lists, but OpenNGC is more comprehensive

### 3. NGC/IC Objects

**OpenNGC** (Already Implemented)

- **Source**: https://github.com/mattiaverga/OpenNGC
- **Format**: CSV
- **Objects**: 13,970 NGC/IC objects
- **License**: CC-BY-SA-4.0
- **Status**: ✅ Already implemented

### 4. Caldwell Objects

**OpenNGC** (Partial)

- OpenNGC includes many Caldwell objects (they're NGC objects)
- May need to add Caldwell designations separately

#### Alternative: Manual List

- Caldwell catalog is small (109 objects)
- Could be added as a mapping table (Caldwell number → NGC number)
- Source: Various astronomy websites maintain lists

### 5. Planets and Moons

#### Dynamic Objects - Not Suitable for Static Database

- Planets and moons have changing positions
- Already handled via ephemeris calculations in `api/ephemeris.py` and `api/solar_system.py`
- **Recommendation**: Keep planet/moon entries in YAML as reference only (magnitude, descriptions)
- Positions are calculated dynamically at runtime

### 6. Asterisms

#### Custom Groupings - Keep in YAML

- Asterisms are custom star patterns, not official catalog objects
- **Recommendation**: Keep in `catalogs.yaml` as they're user-defined groupings

## Implementation Plan

### Phase 1: Bright Stars Import

1. **Add Yale Bright Star Catalog importer**
   - Download BSC5P from HEASARC
   - Parse ASCII format
   - Import stars with magnitude ≤ 6.5 (or configurable limit)
   - Map to `bright_stars` catalog or create `yale_bsc` catalog

2. **Update `catalogs.yaml`**
   - Remove bright stars section (or keep only custom/curated ones)
   - Keep only stars not in BSC or with custom descriptions

### Phase 2: Caldwell Designations

1. **Add Caldwell mapping**
   - Create Caldwell → NGC mapping table
   - Can be a simple CSV or YAML file
   - Update database schema to support multiple catalog designations per object

2. **Alternative**: Add Caldwell numbers as additional catalog entries
   - Import NGC objects, add Caldwell designations where applicable

### Phase 3: Clean Up YAML

1. **Remove redundant data**
   - Remove Messier objects (covered by OpenNGC)
   - Remove NGC objects (covered by OpenNGC)
   - Remove bright stars (covered by BSC)
   - Keep only:
     - Custom descriptions/notes
     - Asterisms (custom groupings)
     - Planet/moon reference entries (for descriptions only)
     - Any objects not in standard catalogs

## Recommended Data Source Priority

1. **High Priority**:
   - ✅ OpenNGC (already implemented)
   - ⭐ Yale Bright Star Catalog (add importer)

2. **Medium Priority**:
   - Caldwell designation mapping (small dataset, can be manual)

3. **Low Priority**:
   - Hipparcos (if more stars needed beyond BSC)
   - SIMBAD (if specific object lookups needed)

## Example: Yale Bright Star Catalog Format

The BSC5P catalog format:

```text
HR  Number | Name | RA (hours) | Dec (degrees) | Vmag | ...
```

Typical entry:

```text
1|Alp And|0.13979167|29.090556|2.07|...
```

## Next Steps

1. Create `import_yale_bsc()` function in `data_import.py`
2. Add "yale_bsc" to `DATA_SOURCES` dictionary
3. Update `catalogs.yaml` to remove bright stars (or mark as custom-only)
4. Test import and verify data quality
5. Update documentation

## References

- **Yale Bright Star Catalog**: https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html
- **Hipparcos Catalog**: https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/hip.html
- **OpenNGC**: https://github.com/mattiaverga/OpenNGC
- **SIMBAD**: http://simbad.u-strasbg.fr/simbad/
- **VizieR**: https://vizier.cds.unistra.fr/ (catalog search service)
