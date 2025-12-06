# Starplot Catalog Integration Analysis

## Current System

Your current catalog search system uses:
- **SQLAlchemy database** with separate tables for each object type
- **Tabs filtered by object type**: Planets, Moons, Stars, Galaxies, Nebulae, Clusters, Constellations, Asterisms
- **Unified search** across all object types
- **FTS5 full-text search** for name/description matching

## What Starplot Provides

### ✅ Available in Starplot

1. **Stars** (~370k abridged, ~2.5M full)
   - Queryable via `starplot.data.stars.load()` with ibis expressions
   - Includes proper names, Bayer designations, magnitudes, coordinates
   - Stored in Parquet files, accessed via DuckDB

2. **Deep Sky Objects (DSOs)**
   - Galaxies, Nebulae, Clusters in one database
   - Queryable via `DSO.find()` or `DSO.get()` with ibis expressions
   - Includes Messier, NGC, IC objects
   - Stored in DuckDB (`sky.db`)

### ❌ NOT Available in Starplot

1. **Planets & Moons**
   - Starplot calculates these from ephemeris files (not stored as queryable objects)
   - You can get current positions via `Planet.all()` or `Planet.get()`, but:
     - Not searchable by name in a database
     - Positions are calculated on-demand
     - No historical or catalog data

2. **Asterisms**
   - Not included in starplot at all
   - You maintain your own asterism database

3. **Constellations**
   - Starplot has constellation **boundaries** for plotting
   - But NOT constellation objects for searching
   - You maintain your own constellation reference data

## Hybrid Approach Recommendation

### Option 1: Keep Current System (Recommended for Now)

**Pros:**
- ✅ Maintains unified search across all object types
- ✅ Tabs work seamlessly (planets, moons, asterisms, constellations, etc.)
- ✅ Single query interface
- ✅ Full-text search works across all types
- ✅ No migration needed

**Cons:**
- ❌ Duplicate star/DSO data (but starplot is used for plotting, not searching)
- ❌ Need to maintain star catalog separately

**Best for:** Maintaining current functionality while using starplot for visualization

### Option 2: Hybrid Query System

Create an adapter layer that queries both sources:

```python
async def search_objects_hybrid(query: str, object_type: CelestialObjectType):
    results = []
    
    # Query your database for:
    # - Planets, Moons, Asterisms, Constellations
    if object_type in [PLANET, MOON, ASTERISM, CONSTELLATION]:
        results.extend(await db.search(query, object_type=object_type))
    
    # Query starplot for:
    # - Stars
    elif object_type == STAR:
        from starplot.data import stars
        star_data = stars.load(filters=[_.name.contains(query)])
        results.extend(convert_starplot_stars_to_celestial_objects(star_data))
    
    # - DSOs (galaxies, nebulae, clusters)
    elif object_type in [GALAXY, NEBULA, CLUSTER]:
        from starplot.models import DSO
        dso_data = DSO.find(where=[_.name.contains(query)])
        results.extend(convert_starplot_dsos_to_celestial_objects(dso_data))
    
    return results
```

**Pros:**
- ✅ Uses authoritative starplot data for stars/DSOs
- ✅ Maintains tabs and unified search
- ✅ Reduces data duplication

**Cons:**
- ❌ More complex query logic
- ❌ Need conversion layer (starplot models → CelestialObject)
- ❌ Different query APIs (SQLAlchemy vs ibis expressions)
- ❌ Performance considerations (querying two sources)

### Option 3: Import Starplot Data into Your Database

Periodically import starplot's star/DSO data into your SQLite database:

```python
# Import stars from starplot
from starplot.data import stars
star_data = stars.load()
for star in star_data:
    db.add_star(convert_to_star_model(star))

# Import DSOs from starplot
from starplot.models import DSO
dso_data = DSO.find()
for dso in dso_data:
    db.add_dso(convert_to_dso_model(dso))
```

**Pros:**
- ✅ Single unified database
- ✅ All tabs work as-is
- ✅ Single query interface
- ✅ Can still use starplot for plotting

**Cons:**
- ❌ Large import process (~2.5M stars)
- ❌ Need to keep data in sync
- ❌ Duplicate storage

## Recommendation

**Keep your current system** for catalog search, and use starplot for visualization only. Here's why:

1. **Tabs work perfectly** - Your current database supports all object types
2. **Unified search** - Single query interface across all types
3. **Planets/Moons** - Starplot doesn't provide these as searchable objects
4. **Asterisms/Constellations** - Not in starplot at all
5. **Performance** - Your SQLite database is optimized for your use case

### When to Consider Migration

Consider migrating to starplot's catalog if:
- You want the full 2.5M star catalog (currently you may have fewer)
- You want automatic updates from starplot's data sources
- You're willing to maintain a hybrid query system
- You want to reduce data maintenance burden

### Best of Both Worlds

You can:
1. **Keep your database** for search (planets, moons, asterisms, constellations, stars, DSOs)
2. **Use starplot** for visualization (plots, charts, optic views)
3. **Optionally sync** starplot's star/DSO data into your database periodically

This gives you:
- ✅ Unified catalog search with tabs
- ✅ Beautiful starplot visualizations
- ✅ All object types searchable
- ✅ No complex query adapters needed

## Implementation Notes

If you do want to use starplot's catalog for search:

1. **Create adapter functions** to convert starplot models to `CelestialObject`
2. **Modify `search_objects()`** to route queries to appropriate source
3. **Update `filter_objects()`** to handle both sources
4. **Test performance** - starplot uses DuckDB which is fast, but querying two sources adds overhead

The tabbed interface will work fine as long as you can filter by `object_type` regardless of the data source.

