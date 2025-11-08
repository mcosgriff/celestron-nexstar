"""
Light Pollution Database Integration

Downloads and stores World Atlas 2015/2024 light pollution data in the database
for offline access. Supports downloading PNG images and extracting SQM values.

Uses SpatiaLite (https://www.gaia-gis.it/fossil/libspatialite/index) for fast
geospatial queries with R-tree spatial indexing when available. Falls back to
regular SQL queries if SpatiaLite is not installed.

SpatiaLite Installation (optional, for better performance):
    Linux: sudo apt-get install libspatialite-dev
    macOS: brew install spatialite-tools
    Windows: Download from SpatiaLite website

The system will work without SpatiaLite but queries will be slower for large datasets.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import error, request

from sqlalchemy import text

if TYPE_CHECKING:
    from .database import CatalogDatabase

logger = logging.getLogger(__name__)

# World Atlas 2024 data URLs (from djlorenz.github.io)
WORLD_ATLAS_URLS = {
    "world": "https://djlorenz.github.io/astronomy/lp2024/world2024.png",
    "north_america": "https://djlorenz.github.io/astronomy/lp2024/NorthAmerica2024.png",
    "south_america": "https://djlorenz.github.io/astronomy/lp2024/SouthAmerica2024.png",
    "europe": "https://djlorenz.github.io/astronomy/lp2024/Europe2024.png",
    "africa": "https://djlorenz.github.io/astronomy/lp2024/Africa2024.png",
    "asia": "https://djlorenz.github.io/astronomy/lp2024/Asia2024.png",
    "australia": "https://djlorenz.github.io/astronomy/lp2024/Australia2024.png",
}

# Map bounds for each region (lat_min, lat_max, lon_min, lon_max)
REGION_BOUNDS = {
    "world": (-65.0, 75.0, -180.0, 180.0),
    "north_america": (7.0, 75.0, -180.0, -51.0),
    "south_america": (-57.0, 14.0, -93.0, -33.0),
    "europe": (34.0, 75.0, -32.0, 70.0),
    "africa": (-36.0, 38.0, -26.0, 64.0),
    "asia": (5.0, 75.0, 60.0, 180.0),
    "australia": (-48.0, 8.0, 94.0, 180.0),
}

# Light pollution color scale mapping (RGB to SQM)
# Based on typical light pollution map color scales
# Dark blue = excellent (SQM ~22), Red = poor (SQM ~17)
def _rgb_to_sqm(r: int, g: int, b: int) -> float:
    """
    Convert RGB pixel value to SQM (mag/arcsec²).

    Color scale approximation:
    - Dark blue/black (0,0,0-50): SQM 21.5-22.0 (excellent)
    - Blue (0,0,50-150): SQM 20.5-21.5 (good)
    - Green (0,100-200,0): SQM 19.0-20.5 (fair)
    - Yellow (200-255,200-255,0): SQM 18.0-19.0 (poor)
    - Red (200-255,0-100,0): SQM 17.0-18.0 (very poor)
    - White (255,255,255): SQM <17.0 (worst)

    This is an approximation - actual conversion would require
    the exact color scale used by the map.
    """
    # Normalize RGB to 0-1
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    # Calculate brightness (weighted average)
    brightness = 0.299 * r_norm + 0.587 * g_norm + 0.114 * b_norm

    # Map brightness to SQM (inverse relationship: brighter = lower SQM)
    # SQM ranges from ~17 (brightest/white) to ~22 (darkest/black)
    # Using a logarithmic scale for better distribution
    if brightness < 0.01:  # Very dark (black)
        sqm = 22.0
    elif brightness < 0.1:  # Dark blue
        sqm = 21.5 + (brightness / 0.1) * 0.5
    elif brightness < 0.3:  # Blue to green
        sqm = 20.5 + ((brightness - 0.1) / 0.2) * 1.0
    elif brightness < 0.6:  # Green to yellow
        sqm = 19.0 + ((brightness - 0.3) / 0.3) * 1.5
    elif brightness < 0.9:  # Yellow to red
        sqm = 18.0 + ((brightness - 0.6) / 0.3) * 1.0
    else:  # Red to white
        sqm = 17.0 + ((brightness - 0.9) / 0.1) * 0.5

    # Clamp to reasonable range
    return max(17.0, min(22.0, sqm))


def _check_spatialite_available(db: CatalogDatabase) -> bool:
    """
    Check if SpatiaLite extension is available.

    SpatiaLite provides fast spatial queries with R-tree indexing.
    Install system package: libspatialite-dev (Linux) or use pyspatialite (Python wrapper)

    Returns:
        True if SpatiaLite is available, False otherwise
    """
    try:
        with db._get_session() as session:
            # Try to initialize SpatiaLite
            # First check if spatial_ref_sys table exists (indicates SpatiaLite is initialized)
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='spatial_ref_sys'")
            ).fetchone()
            if result is not None:
                return True

            # Try to initialize SpatiaLite
            # Note: load_extension() may require special permissions or configuration
            try:
                # Try loading the extension (may fail if not available or not permitted)
                session.execute(text("SELECT load_extension('mod_spatialite')"))
                session.commit()
                # Check if initialization worked
                result = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='spatial_ref_sys'")
                ).fetchone()
                return result is not None
            except Exception:
                # Extension loading failed, SpatiaLite not available
                return False
    except Exception:
        return False


def _create_light_pollution_table(db: CatalogDatabase) -> None:
    """Create light pollution grid table in database with spatial support if available."""
    use_spatialite = _check_spatialite_available(db)

    if use_spatialite:
        # Create table with SpatiaLite geometry column
        schema_sql = """
        -- Initialize SpatiaLite if not already done
        SELECT load_extension('mod_spatialite');
        
        -- Create table with geometry column
        CREATE TABLE IF NOT EXISTS light_pollution_grid (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            sqm_value REAL NOT NULL,
            region TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(latitude, longitude)
        );
        
        -- Add geometry column if it doesn't exist
        SELECT AddGeometryColumn('light_pollution_grid', 'geometry', 4326, 'POINT', 'XY');
        
        -- Create spatial index (R-tree)
        SELECT CreateSpatialIndex('light_pollution_grid', 'geometry');
        
        -- Create regular indexes
        CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region);
        """
    else:
        # Create table without spatial support
        schema_sql = """
        CREATE TABLE IF NOT EXISTS light_pollution_grid (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            sqm_value REAL NOT NULL,
            region TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(latitude, longitude)
        );

        CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region);
        """

    with db._get_session() as session:
        # Execute statements one by one (some may fail if already exists)
        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
        for stmt in statements:
            try:
                if stmt.startswith("SELECT"):
                    # SELECT statements need to be executed differently
                    session.execute(text(stmt))
                else:
                    session.execute(text(stmt))
            except Exception as e:
                # Ignore errors for "already exists" cases
                if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                    logger.debug(f"Schema statement warning: {e}")
        session.commit()


async def _download_png_async(url: str, output_path: Path) -> bool:
    """Download PNG image asynchronously."""
    try:
        import aiohttp  # type: ignore[import-untyped]

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response,
        ):
            if response.status == 200:
                with open(output_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                return True
            else:
                logger.error(f"Failed to download {url}: HTTP {response.status}")
                return False
    except ImportError:
        # Fallback to synchronous download
        try:
            with request.urlopen(url, timeout=300) as response:
                if response.status == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.read())
                    return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def _process_png_to_database(
    png_path: Path, region: str, db: CatalogDatabase, grid_resolution: float = 0.1
) -> int:
    """
    Process PNG image and store SQM values in database.

    Args:
        png_path: Path to PNG image
        region: Region name
        db: Database instance
        grid_resolution: Grid resolution in degrees (default 0.1° ≈ 11km)

    Returns:
        Number of grid points inserted
    """
    try:
        from PIL import Image

        # Increase PIL image size limit to handle large World Atlas images
        # These are trusted source images, not security risks
        Image.MAX_IMAGE_PIXELS = None  # Disable limit (or set to a very large number)
    except ImportError:
        logger.error("PIL/Pillow not installed. Install with: pip install Pillow")
        return 0

    if not png_path.exists():
        logger.error(f"PNG file not found: {png_path}")
        return 0

    # Get region bounds
    lat_min, lat_max, lon_min, lon_max = REGION_BOUNDS.get(region, (-90, 90, -180, 180))

    # Open image (suppress decompression bomb warning for trusted source)
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)
        img = Image.open(png_path)
    width, height = img.size

    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Calculate lat/lon step per pixel
    lat_step = (lat_max - lat_min) / height
    lon_step = (lon_max - lon_min) / width

    # Create table if needed
    _create_light_pollution_table(db)

    # Process pixels and insert into database
    inserted = 0
    batch_size = 1000
    batch_data = []

    logger.info(f"Processing {region} image ({width}x{height} pixels)...")

    for y in range(0, height, max(1, int(grid_resolution / lat_step))):
        for x in range(0, width, max(1, int(grid_resolution / lon_step))):
            # Get pixel RGB
            r, g, b = img.getpixel((x, y))

            # Convert to lat/lon
            lat = lat_max - (y * lat_step)
            lon = lon_min + (x * lon_step)

            # Convert RGB to SQM
            sqm = _rgb_to_sqm(r, g, b)

            # Round to grid resolution
            lat_rounded = round(lat / grid_resolution) * grid_resolution
            lon_rounded = round(lon / grid_resolution) * grid_resolution

            batch_data.append((lat_rounded, lon_rounded, sqm, region))

            # Insert in batches
            if len(batch_data) >= batch_size:
                _insert_batch(db, batch_data)
                inserted += len(batch_data)
                batch_data = []

    # Insert remaining
    if batch_data:
        _insert_batch(db, batch_data)
        inserted += len(batch_data)

    logger.info(f"Inserted {inserted} grid points for {region}")
    return inserted


def _insert_batch(db: CatalogDatabase, batch_data: list[tuple[float, float, float, str]]) -> None:
    """Insert batch of light pollution data with spatial geometry if available."""
    use_spatialite = _check_spatialite_available(db)

    with db._get_session() as session:
        if use_spatialite:
            # Insert with geometry column
            sql = text(
                """
                INSERT OR REPLACE INTO light_pollution_grid 
                (latitude, longitude, sqm_value, region, geometry)
                VALUES (:lat, :lon, :sqm, :region, MakePoint(:lon, :lat, 4326))
                """
            )
        else:
            # Insert without geometry column
            sql = text(
                """
                INSERT OR REPLACE INTO light_pollution_grid 
                (latitude, longitude, sqm_value, region)
                VALUES (:lat, :lon, :sqm, :region)
                """
            )

        # Execute each row individually (SQLAlchemy doesn't support bulk insert with OR REPLACE easily)
        for lat, lon, sqm, region in batch_data:
            session.execute(sql, {"lat": lat, "lon": lon, "sqm": sqm, "region": region})
        session.commit()


def get_sqm_from_database(lat: float, lon: float, db: CatalogDatabase) -> float | None:
    """
    Get SQM value from database using spatial queries if available, otherwise regular SQL.

    Uses SpatiaLite for fast nearest neighbor queries with spatial indexing.
    Falls back to regular SQL if SpatiaLite is not available.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        db: Database instance

    Returns:
        SQM value or None if not found
    """
    from sqlalchemy import text

    # Check if table exists first
    try:
        with db._get_session() as session:
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='light_pollution_grid'")
            ).fetchone()
            if result is None:
                logger.debug("light_pollution_grid table does not exist")
                return None
    except Exception as e:
        logger.debug(f"Error checking for table: {e}")
        return None

    use_spatialite = _check_spatialite_available(db)
    search_radius_km = 22.0  # ~22km search radius

    with db._get_session() as session:
        if use_spatialite:
            # Use SpatiaLite spatial query with R-tree index for fast nearest neighbor
            # Distance calculation in degrees (approximate: 1 degree ≈ 111 km)
            search_radius_deg = search_radius_km / 111.0

            sql = text(
                """
                SELECT latitude, longitude, sqm_value,
                       Distance(MakePoint(:lon, :lat, 4326), geometry) as dist
                FROM light_pollution_grid
                WHERE Distance(MakePoint(:lon, :lat, 4326), geometry) <= :radius
                ORDER BY Distance(MakePoint(:lon, :lat, 4326), geometry)
                LIMIT 4
                """
            )
            result = session.execute(
                sql,
                {
                    "lat": lat,
                    "lon": lon,
                    "radius": search_radius_deg,
                },
            ).fetchall()
        else:
            # Fallback to regular SQL with bounding box
            search_radius = search_radius_km / 111.0  # Convert km to degrees

            sql = text(
                """
                SELECT latitude, longitude, sqm_value
                FROM light_pollution_grid
                WHERE latitude BETWEEN :lat_min AND :lat_max
                  AND longitude BETWEEN :lon_min AND :lon_max
                ORDER BY ABS(latitude - :lat) + ABS(longitude - :lon)
                LIMIT 4
                """
            )
            result = session.execute(
                sql,
                {
                    "lat_min": lat - search_radius,
                    "lat_max": lat + search_radius,
                    "lon_min": lon - search_radius,
                    "lon_max": lon + search_radius,
                    "lat": lat,
                    "lon": lon,
                },
            ).fetchall()

        if not result:
            logger.debug(f"No grid points found within {search_radius_km}km of {lat},{lon}")
            return None

        if len(result) == 1:
            sqm = float(result[0][2])
            logger.debug(f"Found single grid point: SQM={sqm:.2f}")
            return sqm

        # Bilinear interpolation
        points = [(float(r[0]), float(r[1]), float(r[2])) for r in result]

        # Find the 4 closest points forming a rectangle
        lats = sorted(set(p[0] for p in points))
        lons = sorted(set(p[1] for p in points))

        if len(lats) < 2 or len(lons) < 2:
            # Not enough points for interpolation, use nearest
            return points[0][2]

        # Find bounding rectangle
        lat1, lat2 = lats[0], lats[-1]
        lon1, lon2 = lons[0], lons[-1]

        # Get values at corners
        values = {}
        for p in points:
            values[(p[0], p[1])] = p[2]

        # Bilinear interpolation
        def get_value(la: float, lo: float) -> float:
            # Find nearest point
            min_dist = float("inf")
            nearest_val = points[0][2]
            for p in points:
                dist = math.sqrt((p[0] - la) ** 2 + (p[1] - lo) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_val = p[2]
            return nearest_val

        # Interpolate
        v11 = get_value(lat1, lon1)
        v12 = get_value(lat1, lon2)
        v21 = get_value(lat2, lon1)
        v22 = get_value(lat2, lon2)

        # Bilinear interpolation formula
        if lat2 != lat1 and lon2 != lon1:
            t_lat = (lat - lat1) / (lat2 - lat1)
            t_lon = (lon - lon1) / (lon2 - lon1)
            sqm = (
                v11 * (1 - t_lat) * (1 - t_lon)
                + v21 * t_lat * (1 - t_lon)
                + v12 * (1 - t_lat) * t_lon
                + v22 * t_lat * t_lon
            )
        else:
            # Fallback to nearest neighbor
            sqm = get_value(lat, lon)

        return sqm


async def download_world_atlas_data(
    regions: list[str] | None = None, grid_resolution: float = 0.1, force: bool = False
) -> dict[str, int]:
    """
    Download and process World Atlas 2024 light pollution data.

    Args:
        regions: List of regions to download (None = all)
        grid_resolution: Grid resolution in degrees (default 0.1° ≈ 11km)
        force: Force re-download even if data exists

    Returns:
        Dictionary mapping region to number of points inserted
    """
    from .database import get_database

    db = get_database()
    _create_light_pollution_table(db)

    if regions is None:
        regions = list(WORLD_ATLAS_URLS.keys())

    # Create download directory
    download_dir = Path.home() / ".celestron_nexstar" / "light_pollution"
    download_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, int] = {}

    for region in regions:
        if region not in WORLD_ATLAS_URLS:
            logger.warning(f"Unknown region: {region}")
            continue

        url = WORLD_ATLAS_URLS[region]
        png_path = download_dir / f"{region}2024.png"

        # Download if needed
        if not png_path.exists() or force:
            logger.info(f"Downloading {region} data from {url}...")
            success = await _download_png_async(url, png_path)
            if not success:
                logger.error(f"Failed to download {region}")
                continue
        else:
            logger.info(f"Using existing {region} data")

        # Process and store in database
        count = _process_png_to_database(png_path, region, db, grid_resolution)
        results[region] = count

    return results


def download_world_atlas_data_sync(
    regions: list[str] | None = None, grid_resolution: float = 0.1, force: bool = False
) -> dict[str, int]:
    """
    Synchronous wrapper for downloading World Atlas data.

    Args:
        regions: List of regions to download (None = all)
        grid_resolution: Grid resolution in degrees (default 0.1° ≈ 11km)
        force: Force re-download even if data exists

    Returns:
        Dictionary mapping region to number of points inserted
    """
    try:
        loop = asyncio.get_running_loop()
        # In async context, can't use run_until_complete
        logger.warning("Cannot download in async context. Use download_world_atlas_data() instead.")
        return {}
    except RuntimeError:
        return asyncio.run(download_world_atlas_data(regions, grid_resolution, force))

