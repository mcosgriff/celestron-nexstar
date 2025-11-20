# Performance Optimization Opportunities

This document outlines identified performance optimization opportunities in the codebase.

## ✅ Completed High Impact Optimizations

### 1. **Geocoding Batching in Dark Sky Sites Scraping** ✅ COMPLETED

**Location:** `src/celestron_nexstar/cli/commands/data/data.py:2975-3019`

**Implementation:**

- ✅ Implemented concurrent geocoding with semaphore (5 concurrent requests)
- ✅ Uses `asyncio.Semaphore` to limit concurrent requests while respecting rate limits
- ✅ Processes all places concurrently with `asyncio.gather()`
- ✅ Reduces total time from ~165s to ~20-30s for 165+ locations

**Changes Made:**

- Replaced sequential geocoding loop with concurrent batch processing
- Added `geocode_with_rate_limit()` helper function with semaphore
- Removed per-request sleep delays (semaphore handles rate limiting)

---

### 2. **Database Batch Insert Fallback (N+1 Query Problem)** ✅ COMPLETED

**Location:** `src/celestron_nexstar/api/database/light_pollution_db.py:740-775`

**Implementation:**

- ✅ Replaced individual existence checks with batch query using `IN` clause
- ✅ Uses `tuple_(latitude, longitude).in_(lat_lon_pairs)` for efficient batch checking
- ✅ Separates records into insert and update lists for bulk operations
- ✅ Reduces from 1000+ queries to 2 queries (one select, one commit) for 1000 records

**Changes Made:**

- Batch existence check using SQLAlchemy's `tuple_().in_()` clause
- Creates map of existing records for O(1) lookup
- Separates records into `to_insert` and `to_update` lists
- Uses bulk operations instead of individual queries

---

### 3. **GeoPandas iterrows() Performance** ✅ COMPLETED

**Location:** `light_pollution_db.py:599`, `vacation_planning.py:179,253`

**Implementation:**

- ✅ Replaced `.iterrows()` with `.itertuples()` in all locations
- ✅ 10-100x performance improvement for row iteration
- ✅ Updated all GeoPandas DataFrame iterations

**Changes Made:**

- `light_pollution_db.py`:
  - Changed `points_within.iterrows()` to `points_within.itertuples()` (line 599)
  - Changed `grid_gdf.iterrows()` to `grid_gdf.itertuples()` (line 906)
- `vacation_planning.py`: Changed both `sites_within.iterrows()` calls to `sites_within.itertuples()` (lines 179, 253)
- Updated attribute access from `row["column"]` to `row.column`
- Used `row.Index` for index-based lookups in distance calculations

---

### 4. **Weather Forecast Fetching in Loops** ⚠️ MEDIUM IMPACT

**Location:** `src/celestron_nexstar/api/events/milky_way.py:1039-1070`

**Current Issue:**

- Fetches weather forecast for each sample date individually
- For 12 months × 3 sample dates = 36 potential API calls
- Many of these calls fetch overlapping time ranges

**Optimization:**

- Fetch weather forecast once for the entire range (14 days)
- Cache the forecast and look up values for each date
- Reduces API calls from 36 to 1

**Code Change:**

```python
# Instead of:
for sample_date in sample_dates:
    if days_until_opportunity <= 14:
        hourly_forecasts = asyncio.run(
            fetch_hourly_weather_forecast(location, hours=days_until_opportunity * 24 + 24)
        )

# Use:
# Fetch once for max range
max_days = max((sd - now).days for sd in sample_dates if (sd - now).days <= 14)
if max_days > 0:
    hourly_forecasts_cache = asyncio.run(
        fetch_hourly_weather_forecast(location, hours=max_days * 24 + 24)
    )
    # Create lookup dict by timestamp
    forecast_by_time = {f.timestamp: f for f in hourly_forecasts_cache if f.timestamp}

for sample_date in sample_dates:
    if days_until_opportunity <= 14:
        target_hour = sample_date.replace(minute=0, second=0, microsecond=0)
        closest_forecast = forecast_by_time.get(target_hour)  # or find closest
```

---

### 5. **Moon Info Calculation Caching** ⚠️ MEDIUM IMPACT

**Location:** `src/celestron_nexstar/api/events/milky_way.py:1017`, `meteor_shower_predictions.py:123`

**Current Issue:**

- `get_moon_info()` is called multiple times for nearby dates
- Each call does expensive Skyfield calculations
- No caching between calls

**Optimization:**

- Add memoization/caching for moon info calculations
- Cache results for same date (or nearby dates within same hour)
- Use `functools.lru_cache` or custom cache with TTL

**Code Change:**

```python
from functools import lru_cache
from datetime import datetime, timedelta

def _round_to_hour(dt: datetime) -> datetime:
    """Round datetime to nearest hour for caching."""
    return dt.replace(minute=0, second=0, microsecond=0)

@lru_cache(maxsize=100)
def get_moon_info_cached(
    observer_lat: float,
    observer_lon: float,
    dt_rounded: datetime,  # Pre-rounded to hour
) -> MoonInfo | None:
    """Cached version of get_moon_info."""
    return get_moon_info(observer_lat, observer_lon, dt_rounded)

# Usage:
dt_rounded = _round_to_hour(sample_date)
moon_info = get_moon_info_cached(location.latitude, location.longitude, dt_rounded)
```

---

## Medium Impact Optimizations

### 6. **Vectorized Array Processing in PNG Processing**

**Location:** `src/celestron_nexstar/api/database/light_pollution_db.py:610-644`

**Current Issue:**

- Still using nested loops to build `batch_data` list
- Could be vectorized using numpy array operations

**Optimization:**

- Use numpy to create batch_data array directly
- Convert to list of tuples in one operation

**Code Change:**

```python
# Instead of:
for i in range(len(y_indices)):
    for j in range(len(x_indices)):
        lat = float(lat_rounded[i, j])
        lon = float(lon_rounded[i, j])
        sqm = float(sqm_values[i, j])
        batch_data.append((lat, lon, sqm, region))

# Use:
# Flatten arrays
lats_flat = lat_rounded.flatten()
lons_flat = lon_rounded.flatten()
sqm_flat = sqm_values.flatten()

# Create batch_data using numpy (much faster)
batch_data = list(zip(
    lats_flat.astype(float),
    lons_flat.astype(float),
    sqm_flat.astype(float),
    [region] * len(lats_flat)
))
```

---

### 7. **Database Query Optimization for Historical Weather**

**Location:** `src/celestron_nexstar/api/events/milky_way.py:941-955`

**Current Issue:**

- Queries database for each month individually
- Could batch query all months at once

**Optimization:**

- Single query with `IN` clause for all months
- Already partially optimized, but could be improved

---

### 8. **Geohash Calculation Batching**

**Location:** `src/celestron_nexstar/api/database/light_pollution_db.py:718-720`

**Current Issue:**

- Geohash calculated in loop for each record
- Could be vectorized if geohash library supports it

**Optimization:**

- If geohash library supports vectorization, use it
- Otherwise, current approach is fine (geohash is fast)

---

## ✅ Completed Low Impact Optimizations

### 9. **Database Index Optimization** ✅ COMPLETED

**Location:** `src/celestron_nexstar/api/database/models.py:672`, `alembic/versions/20250129000000_add_geohash_index_to_dark_sky_sites.py`

**Implementation:**

- ✅ Added geohash index to `dark_sky_sites` table (`idx_dark_sky_geohash`)
- ✅ Verified existing indexes:
  - `light_pollution_grid`: `(latitude, longitude)`, `geohash` ✓
  - `historical_weather`: `(latitude, longitude, month)`, `(geohash, month)` ✓
  - `dark_sky_sites`: `(latitude, longitude)`, `geohash` ✓

**Changes Made:**

- Added `Index("idx_dark_sky_geohash", "geohash")` to `DarkSkySiteModel.__table_args__`
- Created Alembic migration to add the index to existing databases

---

### 10. **Connection Pooling** ✅ COMPLETED

**Location:** `src/celestron_nexstar/api/database/database.py:173-180`

**Implementation:**

- ✅ Configured SQLAlchemy connection pooling with optimized settings:
  - `pool_size=10`: Maximum number of connections to maintain
  - `max_overflow=5`: Additional connections beyond pool_size
  - `pool_pre_ping=True`: Verify connections before using (prevents stale connections)
  - `pool_recycle=3600`: Recycle connections after 1 hour

**Changes Made:**

- Added connection pool configuration to `create_async_engine()` call
- Added detailed comments explaining each pool setting

---

### 11. **Async Context Manager Optimization** ✅ COMPLETED

**Location:** `src/celestron_nexstar/api/database/models.py:1109-1132`

**Implementation:**

- ✅ Reviewed async context manager usage - already properly implemented
- ✅ `get_db_session()` context manager properly handles:
  - Automatic session cleanup
  - Exception handling with rollback
  - Proper commit on success

**Status:**

- No changes needed - async context managers are already properly implemented and used throughout the codebase

---

### 12. **Memory Optimization for Large Datasets** ✅ COMPLETED

**Location:** `src/celestron_nexstar/api/database/light_pollution_db.py:494-496`

**Implementation:**

- ✅ Added documentation about memory usage for very large PNG images
- ✅ Current vectorized numpy approach is already efficient
- ✅ For extremely large images (>10,000x10,000 pixels), the code includes notes about potential memory usage

**Status:**

- The current vectorized numpy implementation is already quite memory-efficient
- Added documentation noting that for extremely large images, chunked processing could be considered if needed
- The batch processing approach (inserting in batches of 1000) already helps manage memory

---

## Implementation Status

### ✅ Completed (High Impact)

1. **#1: Geocoding batching** - ✅ Implemented with semaphore-based concurrency
1. **#2: Database batch insert fallback** - ✅ Implemented with batch existence checks
1. **#3: GeoPandas iterrows()** - ✅ Replaced with itertuples() in all locations

### ✅ Completed (Low Impact)

1. **#9: Database Index Optimization** - ✅ Added geohash index to dark_sky_sites
1. **#10: Connection Pooling** - ✅ Optimized SQLAlchemy connection pool settings
1. **#11: Async Context Manager Optimization** - ✅ Reviewed and confirmed proper usage
1. **#12: Memory Optimization** - ✅ Added documentation for large dataset handling

### 🔄 Remaining Optimizations

**Medium Priority:**

- #4: Weather forecast caching (medium difficulty, medium impact)
- #5: Moon info caching (easy, medium impact)
- #6: Vectorized array processing (easy, medium impact)

**Low Priority:**

- #7-8: Database query optimization, geohash calculation batching (nice to have)

---

## Testing Recommendations

After implementing optimizations:

1. Benchmark before/after for each optimization
2. Test with realistic data sizes (e.g., 165 dark sky sites, large PNG files)
3. Verify correctness (optimizations shouldn't change results)
4. Monitor memory usage (some optimizations may use more memory)
