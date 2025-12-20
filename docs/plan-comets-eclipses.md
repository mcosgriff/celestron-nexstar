# Comet & Eclipse Visibility Implementation Plan

## Status: Phase 2 Complete ✓

---

## Phase 1: Keplerian Propagation & Eclipse Enhancement ✓

### Completed Work

#### Comet Visibility with Keplerian Propagation ✓
- **New module**: `api/astronomy/keplerian.py`
  - `solve_kepler()`: Newton-Raphson solver for elliptic/parabolic/hyperbolic orbits
  - `compute_comet_position()`: Full two-body propagation from orbital elements
  - `compute_comet_magnitude()`: H/G photometric model for brightness
  - `find_best_visibility_window()`: Sample dates to find optimal viewing
  
- **Updated**: `api/astronomy/comets.py`
  - `get_visible_comets()` now uses Keplerian propagation when orbital elements available
  - Falls back to heuristic model when elements missing
  - `CometVisibility` dataclass extended with RA/Dec, elongation, distances, propagation_method, source

#### Eclipse Visibility with Path Checking ✓
- **Updated**: `api/astronomy/eclipses.py`
  - `Eclipse` dataclass extended with contact times, obscuration, path status
  - `_check_point_in_path()`: Point-in-polygon check using Shapely
  - Uses stored contact times from database when available

#### GUI Updates ✓
- **Comets Dialog**: Shows propagation method, RA/Dec, elongation, distances, source
- **Eclipse Dialog**: Shows path status, contact times, obscuration, central duration

---

## Phase 2: Horizons SPK Support & Enhanced Eclipse Data ✓

### Completed Work

#### Horizons SPK Download & Management ✓
- **New module**: `api/solar_system/horizons_spk.py`
  - `download_comet_spk()`: Async download from JPL Horizons API
  - `download_comet_spk_sync()`: Synchronous version for CLI
  - `compute_position_from_spk()`: Compute comet position from cached SPK
  - `list_cached_spks()`: List all cached SPK files
  - `get_spk_cache_dir()`: Manage SPK cache in `~/.skyfield/spk/`

#### Database SPK Tracking ✓
- **New model**: `CometSPKModel` in `api/database/models.py`
  - Tracks comet designation, filename, file path, size
  - Stores coverage period (start/end dates)
  - Records download timestamp and validation status
- **New migration**: `20251220120000_add_comet_spk_table.py`

#### Updated Comet Propagation ✓
- **Modified**: `api/astronomy/keplerian.py`
  - `compute_comet_position()` now has `prefer_spk=True` parameter
  - `_compute_from_spk()`: Attempts SPK-based calculation first
  - Falls back to Keplerian propagation if SPK not available

#### SPK Manager GUI ✓
- **New dialog**: `gui/dialogs/spk_manager_dialog.py`
  - Table showing all comets with SPK status
  - "Download Selected" button for individual comets
  - "Download Bright Comets" button for bulk download (mag < 8)
  - Progress tracking during downloads
- **Updated**: `gui/dialogs/settings_dialog.py`
  - Solar System Data tab now has "Manage SPKs..." button
  - Shows count of cached SPK files

#### SPK CLI Commands ✓
- **New commands** in `cli/commands/data/data.py`:
  - `nexstar data spk-download <designation>`: Download SPK for specific comet
  - `nexstar data spk-list`: List all cached SPK files with status
  - `nexstar data spk-download-bright`: Bulk download for bright comets

#### Enhanced Eclipse Seed Data ✓
- **Updated**: `cli/data/seed/eclipses.json`
  - Added `start_time`, `max_time`, `end_time` (UTC) for all eclipses
  - Added `obscuration` values
  - Added `central_duration_sec` for solar eclipses
  - Added `path_geojson` polygons for solar eclipses (totality/annularity paths)
- **Updated**: `api/database/database_seeder.py`
  - `seed_eclipses()` now parses all new datetime and path fields
  - `_update_eclipse_fields()` helper for updating existing records

#### Enhanced CLI Commands ✓
- **Updated**: `cli/commands/astronomy/comets.py`
  - Table shows "Method" column (Orbital/Est.)
  - Details show RA/Dec, elongation, distances
  - Shows propagation method and data source
- **Updated**: `cli/commands/astronomy/eclipse.py`
  - Table shows "Path" column (IN PATH/Outside/Global)
  - Details show contact times, obscuration, central duration
  - Highlights when observer is in path of totality

---

## Technical Details

### Keplerian Propagation Algorithm
1. Compute mean anomaly M from time since perihelion
2. Solve Kepler's equation for eccentric anomaly E (or hyperbolic H)
3. Compute true anomaly ν from E
4. Compute heliocentric distance r from ν
5. Transform to heliocentric ecliptic coordinates
6. Subtract Earth's position to get geocentric coordinates
7. Convert ecliptic to equatorial (RA/Dec)
8. Convert to observer's alt/az

### Magnitude Computation
```
m = H + 5·log₁₀(Δ) + k·log₁₀(r)
```
Where:
- H = absolute magnitude (from DB)
- Δ = geocentric distance (AU)
- r = heliocentric distance (AU)
- k = slope parameter (from DB, default 4.0)

### SPK Integration
- SPK files cached in `~/.skyfield/spk/`
- Metadata tracked in `comet_spks` database table
- `compute_comet_position()` tries SPK first, then Keplerian
- Skyfield loads SPK and computes state vectors

### Eclipse Path Checking
- Uses Shapely for point-in-polygon checks
- Path stored as GeoJSON (Polygon/MultiPolygon)
- Observer coordinates checked against path geometry
- Returns None if path data unavailable

---

## Files Created/Modified

### New Files
- `src/celestron_nexstar/api/astronomy/keplerian.py`
- `src/celestron_nexstar/api/solar_system/horizons_spk.py`
- `src/celestron_nexstar/gui/dialogs/spk_manager_dialog.py`
- `alembic/versions/20251220120000_add_comet_spk_table.py`

### Modified Files
- `src/celestron_nexstar/api/astronomy/comets.py`
- `src/celestron_nexstar/api/astronomy/eclipses.py`
- `src/celestron_nexstar/api/database/models.py`
- `src/celestron_nexstar/api/database/database_seeder.py`
- `src/celestron_nexstar/gui/dialogs/comets_info_dialog.py`
- `src/celestron_nexstar/gui/dialogs/eclipse_info_dialog.py`
- `src/celestron_nexstar/gui/dialogs/settings_dialog.py`
- `src/celestron_nexstar/gui/workers/download_workers.py`
- `src/celestron_nexstar/cli/commands/data/data.py`
- `src/celestron_nexstar/cli/commands/astronomy/comets.py`
- `src/celestron_nexstar/cli/commands/astronomy/eclipse.py`
- `src/celestron_nexstar/cli/data/seed/eclipses.json`

---

## Future Enhancements (Optional)

### Potential Future Work
- [ ] Add asteroid SPK support
- [ ] Map visualization for eclipse paths
- [ ] Automatic SPK refresh before expiration
- [ ] SPK download queue with priority ordering
- [ ] More detailed path GeoJSON from NASA's eclipse data
- [ ] Local magnitude computation for partial eclipses (Besselian elements)
