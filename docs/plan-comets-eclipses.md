# Comet & Eclipse Visibility Implementation Plan

## Status: Phase 1 Complete ✓

### Completed Work (Phase 1)

#### Comet Visibility with Keplerian Propagation ✓
- **New module**: `api/astronomy/keplerian.py`
  - `solve_kepler()`: Newton-Raphson solver for elliptic/parabolic/hyperbolic orbits
  - `compute_comet_position()`: Full two-body propagation from orbital elements
  - `compute_comet_magnitude()`: H/G photometric model for brightness
  - `find_best_visibility_window()`: Sample dates to find optimal viewing
  
- **Updated**: `api/astronomy/comets.py`
  - `get_visible_comets()` now uses Keplerian propagation when orbital elements available
  - Falls back to heuristic model when elements missing
  - `CometVisibility` dataclass extended with:
    - `ra_hours`, `dec_degrees`, `azimuth`
    - `elongation_deg`, `helio_distance_au`, `geo_distance_au`
    - `propagation_method` ("keplerian" or "heuristic")
    - `source` (data source identifier)

#### Eclipse Visibility with Path Checking ✓
- **Updated**: `api/astronomy/eclipses.py`
  - `Eclipse` dataclass extended with:
    - `start_time`, `end_time` (contact times from DB)
    - `obscuration`, `central_duration_sec`
    - `in_path` (boolean for solar eclipse path check)
    - `path_available` (indicates if path data exists)
  - `_check_point_in_path()`: Point-in-polygon check using Shapely
  - `get_known_eclipses()`: Returns all new DB fields
  - `_calculate_lunar_eclipse()` / `_calculate_solar_eclipse()`: Use stored contact times

#### GUI Updates ✓
- **Comets Dialog** (`gui/dialogs/comets_info_dialog.py`)
  - Shows propagation method column (⚙ Orbital / ≈ Est.)
  - Details section shows RA/Dec, elongation, distances
  - Displays data source when available
  
- **Eclipse Dialog** (`gui/dialogs/eclipse_info_dialog.py`)
  - Shows "Path" column for solar eclipses (IN PATH / Outside / N/A)
  - Details show contact times when available from DB
  - Shows obscuration percentage and central duration
  - Highlights when observer is in path of totality/annularity

---

## Remaining Work (Phase 2 - Future)

### Horizons SPK Support
- [ ] Add SPK download support for selected comets (CLI + Solar System tab)
- [ ] Store SPKs in cache dir; track metadata in DB (new table or reuse comet fields with path)
- [ ] Propagation: if SPK present for comet designation, load kernel and compute state; else fallback to elements
- [ ] UI: show SPK availability and last-updated

### Eclipse Path Data Enhancement
- [ ] Enrich `eclipses.json` seed file with contact times and path GeoJSON from NASA
- [ ] Add migration to populate existing eclipse records with enhanced data
- [ ] Consider adding a map visualization for eclipse paths

### CLI Parity
- [ ] Add comet visibility command that shows propagation details
- [ ] Add eclipse visibility command that shows path status

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

### Eclipse Path Checking
- Uses Shapely for point-in-polygon checks
- Path stored as GeoJSON (Polygon/MultiPolygon)
- Observer coordinates checked against path geometry
- Returns None if path data unavailable

---

## Files Modified

### API Layer
- `src/celestron_nexstar/api/astronomy/keplerian.py` (NEW)
- `src/celestron_nexstar/api/astronomy/comets.py`
- `src/celestron_nexstar/api/astronomy/eclipses.py`

### GUI Layer
- `src/celestron_nexstar/gui/dialogs/comets_info_dialog.py`
- `src/celestron_nexstar/gui/dialogs/eclipse_info_dialog.py`

### Database (previously added)
- `alembic/versions/20251219101000_expand_eclipses_fields.py`
- `alembic/versions/20251219112000_extend_comets_with_orbital_elements.py`
