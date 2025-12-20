# Comet, Eclipse & Asteroid Visibility Implementation Plan

## Status: Phase 3 Complete ✓ (Asteroid Visibility)

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

## Phase 3: Asteroid Visibility ✓

### 3.1 Asteroid Visibility Window ✓

**STATUS: COMPLETE**

Asteroid visibility has been fully implemented, similar to comets and eclipses.

#### Implemented Components ✓

1. **Seed File**: `cli/data/seed/asteroids.json`
   - 49 notable asteroids including Ceres, Vesta, Pallas, Juno, etc.
   - NEOs (Eros, Apollo, Apophis, Bennu, Ryugu, etc.)
   - Jupiter Trojans (Hektor, Achilles, Patroclus, Lucy targets)
   - Centaurs (Chiron, Chariklo)
   - Dwarf Planets (Ceres, Eris, Haumea, Makemake, Sedna)
   - Full orbital elements and photometric parameters

2. **Database Model**: `AsteroidModel`
   - Full orbital elements (a, e, i, Ω, ω, M, epoch)
   - Photometric: absolute magnitude H, slope G, diameter, albedo
   - Derived: perihelion, aphelion, orbital period
   - Type classification (main_belt, neo, trojan, centaur, dwarf_planet, tno)

3. **API Module**: `api/astronomy/asteroids.py` ✓
   - `Asteroid` dataclass with full orbital/photometric data
   - `AsteroidVisibility` dataclass with position, magnitude, status
   - `get_known_asteroids()`: Retrieve all asteroids from DB
   - `get_visible_asteroids()`: Calculate visibility with Keplerian propagation
   - `get_upcoming_oppositions()`: Find asteroids near opposition in next N months
   - `_compute_asteroid_position()`: SPK-first, fallback to Keplerian
   - `_compute_asteroid_magnitude()`: H-G photometric system

4. **GUI**: `gui/dialogs/asteroids_info_dialog.py` ✓
   - Theme-aware table with asteroids
   - Columns: Name, Type, Mag, Alt, Elong, Status
   - Color-coded types (NEO=red, Dwarf=purple, Trojan=orange, Centaur=cyan)
   - Details for top visible asteroids
   - Viewing tips section

5. **CLI**: `cli/commands/astronomy/asteroids.py` ✓
   - `nexstar asteroids visible`: Show currently visible asteroids
   - `nexstar asteroids oppositions`: Find upcoming oppositions
   - Export support with `--export` flag

6. **SPK Support**: Extended `horizons_spk.py` ✓
   - `download_asteroid_spk()`: Async download from Horizons
   - `download_asteroid_spk_sync()`: Sync version for CLI
   - `load_asteroid_spk()`: Check if SPK available
   - `get_asteroid_spk_file_path()`: Get expected SPK path
   - Asteroid position prefers SPK when available

7. **Database Migration**: `20251220140000_add_asteroids_table.py` ✓
   - Creates `asteroids` table with all fields
   - Indexes on designation, type, magnitude, name

8. **Settings Integration** ✓
   - Asteroids added to Seed Data tab
   - `seed_asteroids()` function in database_seeder.py
   - Included in `seed_all()` function

9. **Main Window Integration** ✓
   - "Asteroids" menu item in Celestial > Solar System
   - Opens AsteroidsInfoDialog on click

#### Sample CLI Output

```bash
$ nexstar asteroids visible --max-mag 10
Asteroid Visibility for Arvada, Colorado

Found 5 asteroids, 3 above horizon

┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Name       ┃ Type  ┃ Mag ┃  Alt ┃ Elong ┃ Status          ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ Vesta      │ Belt  │ 6.8 │ -27° │  153° │ ✗ Below horizon │
│ Iris       │ Belt  │ 8.8 │   8° │  104° │ ✓ Visible       │
│ Ceres      │ Dwarf │ 8.9 │  23° │   15° │ ✓ Visible       │
...

$ nexstar asteroids oppositions --months 12
Upcoming Asteroid Oppositions

┏━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━┓
┃ Date       ┃ Asteroid   ┃ Type  ┃  Mag ┃ Elong ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━┩
│ 2026-01-10 │ Vesta      │ Belt  │  6.5 │  178° │
│ 2026-02-14 │ Psyche     │ Belt  │ 10.3 │  177° │
│ 2026-07-11 │ Ceres      │ Dwarf │  7.1 │  172° │
...
```

---

## Phase 4: Advanced Features (Planned)

### 4.1 MPC Asteroid Download

Like the comet MPC download, add on-demand asteroid data:

```bash
nexstar data asteroid-download     # Download MPC bright asteroids
nexstar data asteroid-import       # Import to database
        "COMMAND": designation,  # e.g., "1" for Ceres, "4" for Vesta
        ...
    }
```

New model: `AsteroidSPKModel` (or extend `CometSPKModel` to generic `SPKModel`)

Update SPK Manager dialog to show asteroids tab.

---

### 3.2 Map Visualization for Eclipse Paths

Add interactive map showing eclipse paths.

#### Implementation Options

1. **Static Map Image**:
   - Generate map with matplotlib/cartopy
   - Embed in dialog as QLabel
   - Simpler, no dependencies

2. **Interactive Web Map**:
   - Use QWebEngineView with Leaflet/Mapbox
   - Draw GeoJSON path on map
   - Show observer location marker
   - More interactive but heavier dependency

3. **PyQtGraph Map**:
   - Use pyqtgraph with map tiles
   - Draw path overlay
   - Middle ground

#### New Files

| File | Description |
|------|-------------|
| `gui/widgets/eclipse_map_widget.py` | Map widget component |
| Update `eclipse_info_dialog.py` | Add map tab/panel |

#### Features

- [ ] Show eclipse path (totality/annularity)
- [ ] Mark observer location
- [ ] Show "In Path" / "Outside Path" visually
- [ ] Animate eclipse progress over time
- [ ] Click to see local circumstances at any point

---

### 3.3 Automatic SPK Refresh

SPK files have coverage windows. Auto-refresh before expiration.

#### Implementation

```python
def check_spk_expiration() -> list[CometSPKModel]:
    """Find SPKs expiring within 30 days."""
    threshold = datetime.now(UTC) + timedelta(days=30)
    with get_db_session() as session:
        expiring = session.execute(
            select(CometSPKModel).where(
                CometSPKModel.coverage_end < threshold,
                CometSPKModel.is_valid == True
            )
        ).scalars().all()
    return expiring

def auto_refresh_spks() -> None:
    """Background task to refresh expiring SPKs."""
    for spk in check_spk_expiration():
        download_comet_spk_sync(spk.comet_designation, force=True)
```

#### Integration

- Settings option: "Auto-refresh SPKs before expiration"
- Background thread on app startup
- CLI: `nexstar data spk-refresh`

---

### 3.4 SPK Download Queue

Priority-ordered download queue for bulk SPK downloads.

#### Features

- Queue multiple SPK downloads
- Priority ordering (brighter objects first)
- Progress tracking for entire queue
- Pause/resume capability
- Retry failed downloads

#### Implementation

```python
@dataclass
class SPKDownloadJob:
    designation: str
    name: str
    priority: int  # Lower = higher priority
    status: Literal["pending", "downloading", "complete", "failed"]
    
class SPKDownloadQueue:
    def __init__(self):
        self.jobs: list[SPKDownloadJob] = []
        self._worker: QThread | None = None
    
    def add(self, designation: str, name: str, priority: int = 100) -> None:
        ...
    
    def start(self) -> None:
        ...
```

---

### 3.5 Enhanced Eclipse Path Data

Get more detailed path data from NASA.

#### Data Sources

1. **NASA Eclipse Website**: https://eclipse.gsfc.nasa.gov/
   - Detailed path coordinates
   - Local circumstances tables
   - Besselian elements

2. **Fred Espenak's Data**: 
   - Precise path coordinates
   - Contact times for many cities

#### Implementation

- Script to fetch and parse NASA eclipse data
- Convert to GeoJSON with high-resolution path
- Store path width (not just centerline)
- Include penumbra/umbra boundaries

---

### 3.6 Besselian Elements for Partial Eclipses

Compute local eclipse magnitude using Besselian elements.

#### What Are Besselian Elements?

Mathematical parameters describing the Moon's shadow cone:
- x, y: Shadow axis position
- d, μ: Declination and hour angle of shadow axis
- L1, L2: Penumbral and umbral cone radii
- tan(f1), tan(f2): Cone angles

#### Implementation

```python
def compute_local_eclipse_magnitude(
    lat: float, 
    lon: float, 
    eclipse_besselian: BesselianElements,
    t: datetime
) -> float:
    """
    Compute local eclipse magnitude using Besselian elements.
    
    Returns obscuration (0.0 = no eclipse, 1.0 = total)
    """
    # Transform observer to fundamental plane
    # Calculate distance from shadow axis
    # Determine if in umbra, penumbra, or outside
    ...
```

#### Use Cases

- Accurate magnitude for any location (not just path)
- Compute exact contact times (C1, C2, C3, C4)
- Generate eclipse animation showing progression

---

## Implementation Priority

| Phase | Feature | Effort | Impact | Priority |
|-------|---------|--------|--------|----------|
| 3.1 | Asteroid Visibility | High | High | ⭐⭐⭐ |
| 3.2 | Eclipse Map | Medium | High | ⭐⭐⭐ |
| 3.3 | SPK Auto-Refresh | Low | Medium | ⭐⭐ |
| 3.4 | SPK Queue | Medium | Low | ⭐ |
| 3.5 | Enhanced Eclipse Paths | Medium | Medium | ⭐⭐ |
| 3.6 | Besselian Elements | High | Medium | ⭐ |

**Recommended Order**: 3.1 → 3.2 → 3.3 → 3.5 → 3.4 → 3.6

---

## Asteroid Seed Data Structure

Example `asteroids.json` seed file:

```json
[
  {
    "designation": "1",
    "name": "Ceres",
    "asteroid_type": "dwarf_planet",
    "semi_major_axis_au": 2.769,
    "eccentricity": 0.0758,
    "inclination_deg": 10.59,
    "ascending_node_deg": 80.33,
    "arg_perihelion_deg": 73.60,
    "mean_anomaly_deg": 291.43,
    "epoch": "2024-01-01T00:00:00+00:00",
    "absolute_magnitude_h": 3.34,
    "slope_g": 0.12,
    "diameter_km": 939.4,
    "albedo": 0.09,
    "notes": "Largest object in asteroid belt, dwarf planet"
  },
  {
    "designation": "4",
    "name": "Vesta",
    "asteroid_type": "main_belt",
    "semi_major_axis_au": 2.362,
    "eccentricity": 0.0887,
    "inclination_deg": 7.14,
    "ascending_node_deg": 103.85,
    "arg_perihelion_deg": 151.20,
    "mean_anomaly_deg": 20.86,
    "epoch": "2024-01-01T00:00:00+00:00",
    "absolute_magnitude_h": 3.20,
    "slope_g": 0.32,
    "diameter_km": 525.4,
    "albedo": 0.42,
    "notes": "Brightest asteroid, occasionally naked-eye visible"
  }
]
```

Include ~50-100 asteroids:
- All dwarf planet candidates (Ceres)
- Brightest main belt (Vesta, Pallas, Juno, Iris, etc.)
- Notable NEOs (Eros, Apophis, Bennu, Ryugu)
- Trojan representatives
- Centaurs (Chiron, Chariklo)
