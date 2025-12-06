# DuckDB Migration Analysis

## Performance Comparison: DuckDB vs SQLite

### DuckDB Advantages

**For Your Use Case (Catalog Search):**
- ✅ **3x to 50x faster** for analytical queries (filtering, aggregations, joins)
- ✅ **Columnar storage** - better for filtering by magnitude, constellation, object_type
- ✅ **Native Parquet support** - can directly query starplot's parquet files without importing
- ✅ **Better parallelization** - multi-threaded query execution
- ✅ **Optimized for read-heavy workloads** (your catalog search is read-heavy)

**Your Current Queries Are Analytical:**
- Filtering by object_type, magnitude, constellation
- Searching across multiple tables
- Joining results from different object types
- Sorting by magnitude across large datasets

### SQLite Advantages

- ✅ Better for transactional workloads (frequent writes)
- ✅ More mature ecosystem
- ✅ Better for single-row lookups
- ✅ FTS5 full-text search (DuckDB has full-text search but different API)

### Verdict: **DuckDB is likely better for your use case**

Your catalog search is primarily analytical (filtering, searching, aggregating), not transactional. DuckDB should provide significant performance improvements.

## Architecture: DuckDB + Starplot Parquet Files

### Proposed Structure

```
~/.cache/celestron-nexstar/
├── catalogs.duckdb          # Your custom data (planets, moons, asterisms, constellations)
└── starplot-data/
    ├── bigsky.0.4.0.stars.parquet    # Starplot's star catalog (read directly)
    └── sky.db                         # Starplot's DSO database (DuckDB)
```

### Data Storage Strategy

1. **Use Starplot's Parquet Files Directly**
   - Query `bigsky.0.4.0.stars.parquet` directly (no import needed!)
   - Query starplot's `sky.db` for DSOs
   - Both are already in DuckDB format

2. **Store Custom Data in Your DuckDB Database**
   - Planets, Moons, Asterisms, Constellations
   - Any additional metadata
   - User favorites, notes, etc.

3. **Unified Query Interface**
   ```python
   # Query stars from starplot's parquet
   stars = con.read_parquet("starplot-data/bigsky.0.4.0.stars.parquet")
   
   # Query DSOs from starplot's database
   dsos = con.execute("SELECT * FROM 'starplot-data/sky.db'.dsos")
   
   # Query your custom data
   planets = con.execute("SELECT * FROM planets WHERE ...")
   
   # Union all results
   all_objects = union(stars, dsos, planets)
   ```

## Implementation Approach

### Option 1: Direct Parquet Queries (Recommended)

**Pros:**
- ✅ No data duplication
- ✅ Always uses latest starplot data
- ✅ Smaller database size
- ✅ No import process needed

**Cons:**
- ❌ Slightly more complex queries (need to reference external files)
- ❌ Need to handle schema differences

**Example:**
```python
import duckdb

con = duckdb.connect("catalogs.duckdb")

# Query stars directly from starplot's parquet
stars = con.execute("""
    SELECT 
        name,
        ra_degrees / 15.0 as ra_hours,
        dec_degrees,
        magnitude,
        'star' as object_type
    FROM read_parquet('~/.cache/celestron-nexstar/starplot-data/bigsky.0.4.0.stars.parquet')
    WHERE magnitude < 10
    LIMIT 100
""").fetchdf()

# Query DSOs from starplot's database
dsos = con.execute("""
    SELECT 
        name,
        ra / 15.0 as ra_hours,
        dec as dec_degrees,
        magnitude,
        type as object_type
    FROM '~/.cache/celestron-nexstar/starplot-data/sky.db'.dsos
    WHERE magnitude < 10
""").fetchdf()

# Query your custom data
planets = con.execute("""
    SELECT 
        name,
        ra_hours,
        dec_degrees,
        magnitude,
        'planet' as object_type
    FROM planets
    WHERE ...
""").fetchdf()
```

### Option 2: Import into Single Database

**Pros:**
- ✅ Simpler queries (all data in one place)
- ✅ Better for complex joins
- ✅ Single source of truth

**Cons:**
- ❌ Data duplication
- ❌ Need to re-import when starplot updates
- ❌ Larger database size

**Example:**
```python
# One-time import
con.execute("""
    CREATE TABLE stars AS 
    SELECT * FROM read_parquet('starplot-data/bigsky.0.4.0.stars.parquet')
""")

# Then query normally
stars = con.execute("SELECT * FROM stars WHERE magnitude < 10").fetchdf()
```

## Migration Path

### Phase 1: Add DuckDB Support (Parallel to SQLite)

1. Create `DuckDBCatalogDatabase` class alongside `CatalogDatabase`
2. Implement same interface as SQLite version
3. Test with subset of data
4. Benchmark performance

### Phase 2: Migrate Data

1. Export data from SQLite
2. Import into DuckDB
3. Set up parquet file references
4. Test all queries

### Phase 3: Switch Over

1. Update `get_database()` to return DuckDB instance
2. Keep SQLite as fallback
3. Monitor performance

## SQLAlchemy Compatibility

DuckDB has SQLAlchemy support via `duckdb-engine`:

```python
from sqlalchemy import create_engine

# DuckDB connection string
engine = create_engine("duckdb:///path/to/catalogs.duckdb")

# Or for in-memory
engine = create_engine("duckdb:///:memory:")
```

**However**, for best performance with Parquet files, you may want to use DuckDB's native API directly:

```python
import duckdb

con = duckdb.connect("catalogs.duckdb")
# Direct parquet queries are faster than SQLAlchemy
```

## Full-Text Search

DuckDB has full-text search, but it's different from SQLite FTS5:

```python
# DuckDB full-text search
con.execute("""
    SELECT * FROM objects
    WHERE name LIKE '%query%'
       OR common_name LIKE '%query%'
       OR description LIKE '%query%'
""")

# Or use DuckDB's text search functions
con.execute("""
    SELECT * FROM objects
    WHERE contains(name, 'query')
       OR contains(common_name, 'query')
""")
```

For better text search, you might want to:
- Use DuckDB's `fts_main` extension (if available)
- Or implement fuzzy matching in Python
- Or use a separate search index (like Whoosh or Meilisearch)

## Performance Benchmarks (Expected)

Based on your query patterns:

| Operation | SQLite | DuckDB | Improvement |
|-----------|--------|--------|-------------|
| Filter by magnitude | 100ms | 10-30ms | 3-10x faster |
| Search across all tables | 200ms | 20-50ms | 4-10x faster |
| Filter + Sort by magnitude | 150ms | 15-40ms | 4-10x faster |
| Query parquet directly | N/A | 5-20ms | New capability |
| Single row lookup | 1ms | 2-5ms | Slightly slower |

## Code Changes Required

### Minimal Changes (Using DuckDB Native API)

```python
# Before (SQLAlchemy)
async def filter_objects(self, object_type, max_magnitude):
    stmt = select(StarModel).where(StarModel.magnitude <= max_magnitude)
    result = await session.execute(stmt)
    return result.scalars().all()

# After (DuckDB)
def filter_objects(self, object_type, max_magnitude):
    query = f"""
        SELECT * FROM stars 
        WHERE magnitude <= {max_magnitude}
    """
    if object_type:
        query += f" AND object_type = '{object_type}'"
    
    return con.execute(query).fetchdf()
```

### More Changes (Keep SQLAlchemy)

You can use `duckdb-engine` to keep SQLAlchemy, but you'll need to:
- Update connection strings
- Test all queries (some SQL differences)
- Handle parquet file references differently

## Recommendations

### ✅ **Yes, switch to DuckDB if:**

1. You want better performance for catalog search
2. You want to use starplot's parquet files directly
3. You're willing to refactor database access code
4. You want a more modern, analytical database

### ⚠️ **Consider staying with SQLite if:**

1. Your current performance is acceptable
2. You want minimal code changes
3. You need FTS5 full-text search exactly as-is
4. You have complex transactional requirements

### 🎯 **Recommended Approach:**

1. **Start with Option 1** (direct parquet queries)
   - No data duplication
   - Always up-to-date with starplot
   - Best performance

2. **Create abstraction layer**
   - `CatalogDatabase` interface
   - Implementations: `SQLiteCatalogDatabase` and `DuckDBCatalogDatabase`
   - Easy to switch or support both

3. **Migrate incrementally**
   - Start with read-only queries
   - Test thoroughly
   - Keep SQLite as fallback

## Example Implementation

```python
from abc import ABC, abstractmethod
import duckdb
from pathlib import Path

class CatalogDatabase(ABC):
    @abstractmethod
    async def search(self, query: str) -> list[CelestialObject]:
        pass
    
    @abstractmethod
    async def filter_objects(self, **filters) -> list[CelestialObject]:
        pass

class DuckDBCatalogDatabase(CatalogDatabase):
    def __init__(self, db_path: Path):
        self.con = duckdb.connect(str(db_path))
        self.starplot_data_dir = Path.home() / ".cache" / "celestron-nexstar" / "starplot-data"
    
    async def search(self, query: str) -> list[CelestialObject]:
        # Query stars from parquet
        stars_query = f"""
            SELECT 
                name,
                ra_degrees / 15.0 as ra_hours,
                dec_degrees,
                magnitude,
                'star' as object_type
            FROM read_parquet('{self.starplot_data_dir}/bigsky.0.4.0.stars.parquet')
            WHERE name ILIKE '%{query}%'
            LIMIT 100
        """
        
        # Query DSOs from starplot database
        dsos_query = f"""
            SELECT 
                name,
                ra / 15.0 as ra_hours,
                dec as dec_degrees,
                magnitude,
                type as object_type
            FROM '{self.starplot_data_dir}/sky.db'.dsos
            WHERE name ILIKE '%{query}%'
            LIMIT 100
        """
        
        # Query custom data
        custom_query = f"""
            SELECT * FROM (
                SELECT name, ra_hours, dec_degrees, magnitude, 'planet' as object_type FROM planets
                UNION ALL
                SELECT name, ra_hours, dec_degrees, magnitude, 'moon' as object_type FROM moons
                UNION ALL
                SELECT name, ra_hours, dec_degrees, NULL as magnitude, 'asterism' as object_type FROM asterisms
                UNION ALL
                SELECT name, ra_hours, dec_degrees, NULL as magnitude, 'constellation' as object_type FROM constellations
            )
            WHERE name ILIKE '%{query}%'
            LIMIT 100
        """
        
        # Execute and combine
        stars = self.con.execute(stars_query).fetchdf()
        dsos = self.con.execute(dsos_query).fetchdf()
        custom = self.con.execute(custom_query).fetchdf()
        
        # Combine and convert to CelestialObject
        all_results = pd.concat([stars, dsos, custom])
        return [self._row_to_object(row) for _, row in all_results.iterrows()]
```

## Conclusion

**DuckDB is a good fit for your use case** because:
- ✅ Better performance for analytical queries (your main use case)
- ✅ Native Parquet support (can use starplot's files directly)
- ✅ No data duplication needed
- ✅ Modern, actively developed

**Migration effort:** Medium
- Need to refactor database access code
- Need to handle parquet file references
- Need to test all queries

**Performance gain:** High
- Expected 3-10x improvement for catalog search
- Can query millions of stars efficiently
- Better for filtering and aggregations

