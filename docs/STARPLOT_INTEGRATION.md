# Starplot Integration and Data Caching

This document explains how we integrate with the [starplot](https://starplot.dev) library and configure it to use our standard cache directory for offline data storage.

## Benefits of Using Starplot's Star Catalog

Starplot provides access to comprehensive astronomical data sources:

### Star Catalogs

1. **Big Sky Catalog (Abridged)** - Included with starplot
   - ~370,000 stars up to magnitude 10
   - Based on Hipparcos, Tycho-1, and Tycho-2 catalogs
   - Epoch J2000 coordinates
   - No download required - included in starplot package

2. **Big Sky Catalog (Full)** - Available on demand
   - ~2.5 million stars
   - Same sources as abridged version
   - ~100 MB download
   - Automatically cached when first used

### Deep Sky Objects (DSOs)

- **OpenNGC** - Comprehensive NGC/IC catalog
  - 13,970 NGC/IC objects
  - Includes all 110 Messier objects
  - Stored in DuckDB database (`sky.db`)

### Other Data Sources

- Constellation lines and borders (IAU)
- Milky Way outline
- Planet and Moon ephemeris data
- Star designations and proper names

## Data Caching Configuration

We configure starplot to store its downloaded data in our standard cache location:

**Cache Directory**: `~/.cache/celestron-nexstar/starplot-data/`

This ensures:
- **Consistency**: All cached data is in one location
- **Offline Use**: Data persists between sessions
- **Portability**: Easy to backup or transfer to other systems
- **Organization**: Follows our standard data storage pattern

### How It Works

The configuration is set up automatically when the application starts:

1. **Early Configuration**: Before starplot is imported, we set the `STARPLOT_DOWNLOAD_PATH` environment variable
2. **Automatic Caching**: When starplot needs to download data (e.g., full Big Sky catalog), it saves it to our cache directory
3. **Persistent Storage**: Data remains available for offline use

### Configuration Code

The configuration is handled in `src/celestron_nexstar/api/data/starplot_config.py`:

```python
from celestron_nexstar.api.data.starplot_config import configure_starplot_cache

# Call before importing starplot
configure_starplot_cache()
```

This is automatically called in:
- `src/celestron_nexstar/__init__.py` (library initialization)
- `src/celestron_nexstar/gui/main.py` (GUI application startup)

## Using Starplot's Star Catalog

### Current Usage

We currently use starplot for:
- **Sky Maps**: Horizon plots showing visible sky
- **Zenith Charts**: Full-sky star charts
- **Optic Plots**: Field of view through telescope/eyepiece
- **Constellation Maps**: Detailed constellation views
- **Asterism Maps**: Star pattern visualizations

### Potential Future Integration

Instead of maintaining our own star catalog in `catalogs.yaml` and the database, we could:

1. **Query starplot directly** for star data
2. **Use starplot's DSO database** instead of importing OpenNGC separately
3. **Leverage starplot's constellation data** for more accurate boundaries

### Benefits of Full Integration

- **Reduced Maintenance**: No need to maintain duplicate star catalogs
- **Better Data Quality**: Starplot uses authoritative sources (Hipparcos, Tycho)
- **Automatic Updates**: Starplot updates its data sources
- **Consistency**: Same data used for plotting and searching
- **Storage Efficiency**: Single source of truth for star data

### Considerations

- **Performance**: Starplot uses DuckDB for fast queries, but may be slower than our SQLite database for simple lookups
- **API Differences**: Would need to adapt our code to use starplot's query API
- **Migration**: Existing database entries would need to be migrated or kept for compatibility

## Data Sources Reference

For more information about starplot's data sources, see:
- [Starplot Data Sources Documentation](https://starplot.dev/data-sources/)
- [Big Sky Catalog](https://github.com/steveberardi/bigsky)
- [OpenNGC](https://github.com/mattiaverga/OpenNGC)

## Environment Variables

You can override the cache location by setting:

```bash
export STARPLOT_DOWNLOAD_PATH=/path/to/custom/cache
```

This is useful for:
- Testing with different data sets
- Using a shared cache across multiple applications
- Storing data on a different drive

## Cache Management

The starplot cache directory contains:
- `bigsky.0.4.0.stars.parquet` - Full Big Sky catalog (if downloaded)
- Other downloaded data files as needed

To clear the cache:
```bash
rm -rf ~/.cache/celestron-nexstar/starplot-data/
```

The abridged catalog and built-in data (constellations, DSOs) are stored in the starplot package itself and don't need to be cached separately.

