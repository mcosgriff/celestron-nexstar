# Performance Optimization Opportunities

This document outlines identified performance optimization opportunities in the codebase.

## High Impact Optimizations

### 1. **Geocoding Batching in Dark Sky Sites Scraping** ⚠️ HIGH IMPACT

**Location:** `src/celestron_nexstar/cli/commands/data/data.py:2902-2930`

**Current Issue:**

- Sequential geocoding with 1-second delays between requests
- Processing 165+ locations sequentially takes 165+ seconds minimum
- Rate limiting is necessary but can be optimized

**Optimization:**

- Batch geocoding requests using `geocode_location_batch()` (already exists)
- Use semaphore to limit concurrent requests (e.g., 5-10 at a time)
- Reduces total time from ~165s to ~20-30s

**Code Change:**

```python
# Instead of:
for place in places:
    coords = await geocode_location(place["name"], ...)
    await asyncio.sleep(GEOCODE_DELAY)

# Use:
async def geocode_with_rate_limit(semaphore, place):
    async with semaphore:
        coords = await geocode_location(place["name"], ...)
        await asyncio.sleep(GEOCODE_DELAY)
        return coords

semaphore = asyncio.Semaphore(5)  # 5 concurrent requests
tasks = [geocode_with_rate_limit(semaphore, place) for place in places]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

---

### 2. **Database Batch Insert Fallback (N+1 Query Problem)** ⚠️ HIGH IMPACT

**Location:** `src/celestron_nexstar/api/database/light_pollution_db.py:740-758`

**Current Issue:**

- When bulk insert fails, falls back to individual queries for each record
- For 1000 records, this means 1000+ database queries
- Very slow for large datasets

**Optimization:**

- Batch the existence checks using `IN` clause or bulk select
- Use SQLAlchemy's `bulk_update_mappings()` and `bulk_insert_mappings()`
- Or use `ON CONFLICT` with SQLite 3.24+ (INSERT OR REPLACE)

**Code Change:**

```python
# Instead of:
for record in records_to_insert:
    result = await session.execute(
        select(...).where(...)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # update
    else:
        # insert

# Use:
# Batch check existence
lat_lon_pairs = [(r.latitude, r.longitude) for r in records_to_insert]
existing_records = await session.execute(
    select(LightPollutionGridModel).where(
        tuple_(LightPollutionGridModel.latitude, LightPollutionGridModel.longitude).in_(lat_lon_pairs)
    )
).all()

existing_map = {(r.latitude, r.longitude): r for r in existing_records}
to_insert = [r for r in records_to_insert if (r.latitude, r.longitude) not in existing_map]
to_update = [r for r in records_to_insert if (r.latitude, r.longitude) in existing_map]

if to_insert:
    session.bulk_insert_mappings(LightPollutionGridModel, to_insert)
if to_update:
    session.bulk_update_mappings(LightPollutionGridModel, to_update)
```

---

### 3. **GeoPandas iterrows() Performance** ⚠️ MEDIUM IMPACT

**Location:** Multiple files using `.iterrows()`

**Current Issue:**

- `.iterrows()` is slow (creates Series for each row)
- Used in: `light_pollution_db.py:592`, `vacation_planning.py:179,246`

**Optimization:**

- Use `.itertuples()` which is 10-100x faster
- Or use vectorized operations where possible
- For GeoPandas, can use `.apply()` with vectorized functions

**Code Change:**

```python
# Instead of:
for _, row in points_within.iterrows():
    lat = float(row["latitude"])
    lon = float(row["longitude"])
    sqm = float(row["sqm_value"])

# Use:
for row in points_within.itertuples():
    lat = float(row.latitude)
    lon = float(row.longitude)
    sqm = float(row.sqm_value)

# Or even better, vectorized:
batch_data = [
    (float(row.latitude), float(row.longitude), float(row.sqm_value), region)
    for row in points_within.itertuples()
]
```

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

## Low Impact / Future Optimizations

### 9. **Database Index Optimization**

- Ensure indexes exist on frequently queried columns:
  - `light_pollution_grid`: `(latitude, longitude)`, `geohash`
  - `historical_weather`: `(latitude, longitude, month)`
  - `dark_sky_sites`: `geohash`

### 10. **Connection Pooling**

- Ensure SQLAlchemy connection pooling is optimized
- Check pool size and overflow settings

### 11. **Async Context Manager Optimization**

- Review async context manager usage
- Ensure proper resource cleanup

### 12. **Memory Optimization for Large Datasets**

- For very large PNG processing, consider chunked processing
- Stream data instead of loading all into memory

---

## Implementation Priority

1. **High Priority:**
   - #1: Geocoding batching (easy, high impact)
   - #2: Database batch insert fallback (medium difficulty, high impact)
   - #3: GeoPandas iterrows() (easy, medium impact)

2. **Medium Priority:**
   - #4: Weather forecast caching (medium difficulty, medium impact)
   - #5: Moon info caching (easy, medium impact)
   - #6: Vectorized array processing (easy, medium impact)

3. **Low Priority:**
   - #7-12: Nice to have, but lower impact

---

## Testing Recommendations

After implementing optimizations:

1. Benchmark before/after for each optimization
2. Test with realistic data sizes (e.g., 165 dark sky sites, large PNG files)
3. Verify correctness (optimizations shouldn't change results)
4. Monitor memory usage (some optimizations may use more memory)
