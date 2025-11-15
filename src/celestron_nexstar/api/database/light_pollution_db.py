"""
Light Pollution Database Integration

Downloads and stores World Atlas 2015/2024 light pollution data in the database
for offline access. Supports downloading PNG images and extracting SQM values.

Uses geohash (https://en.wikipedia.org/wiki/Geohash) for fast geospatial queries
with hierarchical spatial indexing. Geohash provides efficient proximity searches
without requiring external spatial database extensions.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib import request

from celestron_nexstar.api.location.geohash_utils import encode, get_neighbors_for_search


if TYPE_CHECKING:
    from celestron_nexstar.api.database.database import CatalogDatabase

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


def _create_light_pollution_table(db: CatalogDatabase) -> None:
    """Ensure light pollution grid table exists using SQLAlchemy model."""
    from celestron_nexstar.api.database.models import LightPollutionGridModel

    # Use SQLAlchemy to create the table if it doesn't exist
    # This ensures consistency with the model definition
    LightPollutionGridModel.__table__.create(db._engine, checkfirst=True)  # type: ignore[attr-defined]


def clear_light_pollution_data(db: CatalogDatabase) -> int:
    """
    Clear all light pollution data from the database.

    Deletes all rows from the light_pollution_grid table.

    Args:
        db: Database instance

    Returns:
        Number of rows deleted
    """
    from sqlalchemy import func, select

    from celestron_nexstar.api.database.models import LightPollutionGridModel

    with db._get_session_sync() as session:
        # First, get count of rows to be deleted
        row_count = session.scalar(select(func.count(LightPollutionGridModel.id))) or 0

        if row_count == 0:
            logger.info("Light pollution table is already empty")
            return 0

        # Delete all rows using SQLAlchemy ORM
        session.query(LightPollutionGridModel).delete()
        session.commit()

        logger.info(f"Cleared {row_count} rows from light_pollution_grid table")
        return row_count


def _load_state_boundaries(state_names: list[str], region: str) -> list[dict[str, Any]] | None:
    """
    Load state/province boundary polygons for filtering.

    Uses bounding boxes for US states, Canadian provinces, and Mexican states.
    Returns a list of boundary dictionaries with geometry data.

    Args:
        state_names: List of state/province names to load
        region: Region name (used to determine which country boundaries to load)

    Returns:
        List of boundary dictionaries or None if unavailable
    """
    # Map region to supported countries
    country_map = {
        "north_america": ["usa", "canada", "mexico"],
    }

    countries = country_map.get(region, [])
    if not countries:
        logger.warning(f"State filtering not supported for region: {region}")
        return None

    # Get state bounding boxes
    state_bboxes = _get_state_bounding_boxes()

    boundaries: list[dict[str, Any]] = []

    for state_name in state_names:
        state_lower = state_name.lower().strip()
        # Try to match state name (handle variations)
        matched = False
        for state_key, bbox in state_bboxes.items():
            if state_lower in state_key.lower() or state_key.lower() in state_lower:
                boundaries.append(
                    {
                        "name": state_key,
                        "bbox": bbox,  # (min_lat, max_lat, min_lon, max_lon)
                        "type": "bbox",  # Simplified to bounding box for now
                    }
                )
                matched = True
                break

        if not matched:
            logger.warning(f"Could not find boundary for: {state_name}")

    return boundaries if boundaries else None


def _get_state_bounding_boxes() -> dict[str, tuple[float, float, float, float]]:
    """
    Get bounding boxes for US states, Canadian provinces, and Mexican states.

    Returns:
        Dictionary mapping state/province name to (min_lat, max_lat, min_lon, max_lon)
    """
    # US States bounding boxes (approximate)
    us_states = {
        "Colorado": (36.99, 41.00, -109.05, -102.04),
        "New Mexico": (31.33, 37.00, -109.05, -103.00),
        "Arizona": (31.33, 37.00, -114.82, -109.05),
        "Utah": (36.99, 42.00, -114.05, -109.05),
        "Wyoming": (41.00, 45.00, -111.05, -104.05),
        "Montana": (44.36, 49.00, -116.05, -104.04),
        "Idaho": (41.99, 49.00, -117.24, -111.05),
        "Nevada": (35.00, 42.00, -120.00, -114.05),
        "California": (32.53, 42.00, -124.45, -114.13),
        "Oregon": (41.99, 46.30, -124.57, -116.47),
        "Washington": (45.54, 49.00, -124.79, -116.92),
        "Texas": (25.84, 36.50, -106.66, -93.51),
        "Oklahoma": (33.62, 37.00, -103.00, -94.43),
        "Kansas": (36.99, 40.00, -102.05, -94.59),
        "Nebraska": (40.00, 43.00, -104.05, -95.31),
        "South Dakota": (42.48, 45.94, -104.06, -96.44),
        "North Dakota": (45.93, 49.00, -104.05, -96.55),
        "Minnesota": (43.50, 49.38, -97.23, -89.49),
        "Iowa": (40.38, 43.50, -96.64, -90.14),
        "Missouri": (35.99, 40.61, -95.77, -89.10),
        "Arkansas": (33.00, 36.50, -94.62, -89.64),
        "Louisiana": (28.93, 33.02, -94.04, -88.82),
        "Mississippi": (30.14, 35.00, -91.66, -88.10),
        "Alabama": (30.14, 35.00, -88.47, -84.89),
        "Tennessee": (34.98, 36.68, -90.31, -81.65),
        "Kentucky": (36.50, 39.15, -89.57, -81.96),
        "Illinois": (36.97, 42.51, -91.51, -87.49),
        "Indiana": (37.77, 41.76, -88.10, -84.78),
        "Ohio": (38.40, 41.98, -84.82, -80.52),
        "Michigan": (41.70, 48.31, -90.42, -82.13),
        "Wisconsin": (42.49, 47.08, -92.89, -86.25),
        "Pennsylvania": (39.72, 42.27, -80.52, -74.69),
        "New York": (40.48, 45.01, -79.76, -71.85),
        "Vermont": (42.73, 45.01, -73.44, -71.47),
        "New Hampshire": (42.70, 45.31, -72.56, -70.61),
        "Maine": (43.06, 47.46, -71.08, -66.95),
        "Massachusetts": (41.19, 42.89, -73.51, -69.86),
        "Rhode Island": (41.15, 42.02, -71.86, -71.12),
        "Connecticut": (40.99, 42.05, -73.73, -71.78),
        "New Jersey": (38.93, 41.36, -75.56, -73.89),
        "Delaware": (38.45, 39.72, -75.79, -75.05),
        "Maryland": (37.91, 39.72, -79.49, -75.05),
        "West Virginia": (37.20, 40.64, -82.64, -77.72),
        "Virginia": (36.54, 39.47, -83.68, -75.24),
        "North Carolina": (33.84, 36.59, -84.32, -75.46),
        "South Carolina": (32.03, 35.22, -83.35, -78.54),
        "Georgia": (30.36, 35.00, -85.61, -80.84),
        "Florida": (24.52, 31.00, -87.63, -79.97),
    }

    # Canadian Provinces (approximate)
    canada_provinces = {
        "Alberta": (48.99, 60.00, -120.00, -110.00),
        "British Columbia": (48.30, 60.00, -139.06, -114.04),
        "Manitoba": (49.00, 60.00, -102.00, -89.00),
        "New Brunswick": (44.56, 48.07, -69.06, -63.70),
        "Newfoundland and Labrador": (46.62, 60.00, -67.81, -52.64),
        "Northwest Territories": (60.00, 78.00, -136.00, -102.00),
        "Nova Scotia": (43.42, 47.04, -66.42, -59.80),
        "Nunavut": (51.00, 83.00, -141.00, -61.00),
        "Ontario": (41.68, 56.86, -95.15, -74.32),
        "Prince Edward Island": (45.95, 47.06, -64.42, -61.97),
        "Quebec": (44.99, 62.61, -79.76, -57.10),
        "Saskatchewan": (49.00, 60.00, -110.00, -101.36),
        "Yukon": (60.00, 70.00, -141.00, -123.00),
    }

    # Mexican States (approximate - key ones)
    mexico_states = {
        "Baja California": (28.00, 32.72, -118.00, -112.00),
        "Baja California Sur": (22.87, 28.00, -115.00, -109.00),
        "Sonora": (26.04, 32.72, -115.00, -108.00),
        "Chihuahua": (25.84, 31.78, -109.00, -103.00),
        "Coahuila": (25.84, 30.00, -103.00, -98.00),
        "Nuevo León": (23.63, 27.50, -101.00, -98.00),
        "Tamaulipas": (22.27, 27.50, -100.00, -96.00),
    }

    # Combine all
    all_boundaries = {**us_states, **canada_provinces, **mexico_states}
    return all_boundaries


def _point_in_boundaries(lat: float, lon: float, boundaries: list[dict[str, Any]]) -> bool:
    """
    Check if a point is within any of the given boundaries.

    Uses bounding box check for simplicity. For more accurate results,
    would need full polygon geometry and point-in-polygon algorithm.

    Args:
        lat: Latitude
        lon: Longitude
        boundaries: List of boundary dictionaries with bbox

    Returns:
        True if point is within any boundary
    """
    for boundary in boundaries:
        if boundary.get("type") == "bbox":
            min_lat, max_lat, min_lon, max_lon = boundary["bbox"]
            if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                return True
    return False


async def _download_png(url: str, output_path: Path) -> bool:
    """Download PNG image asynchronously."""
    try:
        import aiohttp

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
                else:
                    logger.error(f"Failed to download {url}: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def _process_png_to_database(
    png_path: Path,
    region: str,
    db: CatalogDatabase,
    grid_resolution: float = 0.1,
    state_filter: list[str] | None = None,
) -> int:
    """
    Process PNG image and store SQM values in database.

    Args:
        png_path: Path to PNG image
        region: Region name
        db: Database instance
        grid_resolution: Grid resolution in degrees (default 0.1° ≈ 11km)
        state_filter: Optional list of state/province names to filter by

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
        img: Any = Image.open(png_path)
    width, height = img.size

    # Convert to RGB if needed
    if img.mode != "RGB":
        img = cast(Any, img.convert("RGB"))

    # Calculate lat/lon step per pixel
    lat_step = (lat_max - lat_min) / height
    lon_step = (lon_max - lon_min) / width

    # Create table if needed
    _create_light_pollution_table(db)

    # Load state/province boundaries if filtering is requested
    boundary_filter = None
    if state_filter:
        boundary_filter = _load_state_boundaries(state_filter, region)
        if boundary_filter:
            logger.info(f"Filtering to {len(state_filter)} states/provinces: {', '.join(state_filter)}")
        else:
            logger.warning(f"Could not load boundaries for {state_filter}, processing all data")

    # Process pixels and insert into database
    inserted = 0
    batch_size = 1000
    batch_data = []

    logger.info(f"Processing {region} image ({width}x{height} pixels)...")

    # Try to use numpy for faster processing if available
    try:
        import numpy as np

        numpy_available = True
    except ImportError:
        numpy_available = False
        np = cast(Any, None)

    # Calculate sampling step
    y_step = max(1, int(grid_resolution / lat_step))
    x_step = max(1, int(grid_resolution / lon_step))

    # Use numpy for vectorized processing if available
    if numpy_available and np is not None:
        # Convert PIL image to numpy array
        img_array = np.array(img)
        if len(img_array.shape) == 2:
            # Grayscale - convert to RGB
            img_array = np.stack([img_array, img_array, img_array], axis=2)
        elif len(img_array.shape) == 4:
            # RGBA - take only RGB
            img_array = img_array[:, :, :3]

        # Create coordinate grids (vectorized)
        y_indices = np.arange(0, height, y_step)
        x_indices = np.arange(0, width, x_step)
        y_grid, x_grid = np.meshgrid(y_indices, x_indices, indexing="ij")

        # Calculate lat/lon for all pixels at once (vectorized)
        lats = lat_max - (y_grid * lat_step)
        lons = lon_min + (x_grid * lon_step)

        # Extract RGB values (vectorized)
        r_values = img_array[y_grid, x_grid, 0]
        g_values = img_array[y_grid, x_grid, 1]
        b_values = img_array[y_grid, x_grid, 2]

        # Convert RGB to SQM (vectorized)
        # Use the same weighted brightness calculation as _rgb_to_sqm()
        r_norm = r_values / 255.0
        g_norm = g_values / 255.0
        b_norm = b_values / 255.0
        # Weighted brightness (luminance): 0.299*R + 0.587*G + 0.114*B
        brightness = 0.299 * r_norm + 0.587 * g_norm + 0.114 * b_norm

        # Apply the same piecewise conversion as _rgb_to_sqm()
        # This matches the more accurate conversion function
        sqm_values = np.where(
            brightness < 0.01,  # Very dark (black)
            22.0,
            np.where(
                brightness < 0.1,  # Dark blue
                21.5 + (brightness / 0.1) * 0.5,
                np.where(
                    brightness < 0.3,  # Blue to green
                    20.5 + ((brightness - 0.1) / 0.2) * 1.0,
                    np.where(
                        brightness < 0.6,  # Green to yellow
                        19.0 + ((brightness - 0.3) / 0.3) * 1.5,
                        np.where(
                            brightness < 0.9,  # Yellow to red
                            18.0 + ((brightness - 0.6) / 0.3) * 1.0,
                            # Red to white
                            17.0 + ((brightness - 0.9) / 0.1) * 0.5,
                        ),
                    ),
                ),
            ),
        )
        # Clamp to reasonable range
        sqm_values = np.clip(sqm_values, 17.0, 22.0)

        # Round to grid resolution (vectorized)
        lat_rounded = np.round(lats / grid_resolution) * grid_resolution
        lon_rounded = np.round(lons / grid_resolution) * grid_resolution

        # Flatten arrays for iteration
        for i in range(len(y_indices)):
            for j in range(len(x_indices)):
                lat = float(lat_rounded[i, j])
                lon = float(lon_rounded[i, j])
                sqm = float(sqm_values[i, j])

                # Apply state/province filter if specified
                if boundary_filter and not _point_in_boundaries(lat, lon, boundary_filter):
                    continue

                batch_data.append((lat, lon, sqm, region))

                # Insert in batches
                if len(batch_data) >= batch_size:
                    _insert_batch(db, batch_data)
                    inserted += len(batch_data)
                    batch_data = []
    else:
        # Fallback to original pixel-by-pixel method
        for y in range(0, height, y_step):
            for x in range(0, width, x_step):
                # Get pixel RGB
                pixel = img.getpixel((x, y))
                if isinstance(pixel, (int, float)):
                    # Grayscale image
                    r = g = b = int(pixel)
                elif isinstance(pixel, tuple) and len(pixel) >= 3:
                    # RGB/RGBA tuple
                    r, g, b = pixel[0], pixel[1], pixel[2]
                else:
                    # Fallback (shouldn't happen with RGB mode)
                    r = g = b = 0

                # Convert to lat/lon
                lat = lat_max - (y * lat_step)
                lon = lon_min + (x * lon_step)

                # Apply state/province filter if specified
                if boundary_filter and not _point_in_boundaries(lat, lon, boundary_filter):
                    continue

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
    """Insert batch of light pollution data with geohash indexing."""
    from celestron_nexstar.api.database.models import LightPollutionGridModel

    with db._get_session_sync() as session:
        # Use SQLAlchemy ORM for inserts
        for lat, lon, sqm, region in batch_data:
            # Calculate geohash for indexing (use precision 9 for ~5m accuracy)
            geohash_str = encode(lat, lon, precision=9)

            # Use merge() for INSERT OR REPLACE behavior (upsert)
            # First try to find existing record
            existing = (
                session.query(LightPollutionGridModel)
                .filter(
                    LightPollutionGridModel.latitude == lat,
                    LightPollutionGridModel.longitude == lon,
                )
                .first()
            )

            if existing:
                # Update existing record
                existing.geohash = geohash_str
                existing.sqm_value = sqm
                existing.region = region
            else:
                # Insert new record
                new_record = LightPollutionGridModel(
                    latitude=lat,
                    longitude=lon,
                    geohash=geohash_str,
                    sqm_value=sqm,
                    region=region,
                )
                session.add(new_record)
        session.commit()


def get_sqm_from_database(lat: float, lon: float, db: CatalogDatabase) -> float | None:
    """
    Get SQM value from database using geohash-based proximity search.

    Uses geohash for fast nearest neighbor queries with hierarchical spatial indexing.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        db: Database instance

    Returns:
        SQM value or None if not found
    """

    # Check if table exists first
    try:
        from sqlalchemy import inspect

        from celestron_nexstar.api.database.models import LightPollutionGridModel

        with db._get_session_sync() as session:
            inspector = inspect(session.bind)
            if inspector is not None and "light_pollution_grid" not in inspector.get_table_names():
                logger.debug("light_pollution_grid table does not exist")
                return None
    except Exception as e:
        logger.debug(f"Error checking for table: {e}")
        return None

    search_radius_km = 22.0  # ~22km search radius

    # Generate geohash for the search point
    center_geohash = encode(lat, lon, precision=12)

    # Get geohash prefixes to search (includes neighbors)
    search_geohashes = get_neighbors_for_search(center_geohash, search_radius_km)

    # Build query using geohash prefix matching
    # Use LIKE to match geohash prefixes
    geohash_patterns = [f"{gh}%" for gh in search_geohashes]

    from sqlalchemy import func, or_, select

    from celestron_nexstar.api.database.models import LightPollutionGridModel

    result: list[Any]
    with db._get_session_sync() as session:
        # Query using geohash prefix matching with SQLAlchemy ORM
        # This is much faster than bounding box queries for large datasets
        # Build OR conditions for geohash LIKE patterns
        geohash_conditions = or_(*[LightPollutionGridModel.geohash.like(pattern) for pattern in geohash_patterns])

        # Calculate distance using SQL functions
        distance_expr = func.abs(LightPollutionGridModel.latitude - lat) + func.abs(
            LightPollutionGridModel.longitude - lon
        )

        # Build query
        query = (
            select(
                LightPollutionGridModel.latitude,
                LightPollutionGridModel.longitude,
                LightPollutionGridModel.sqm_value,
                distance_expr.label("dist"),
            )
            .where(geohash_conditions)
            .order_by(distance_expr)
            .limit(4)
        )

        query_results = session.execute(query).fetchall()
        result = list(query_results)

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
        lats = sorted({p[0] for p in points})
        lons = sorted({p[1] for p in points})

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
    regions: list[str] | None = None,
    grid_resolution: float = 0.1,
    force: bool = False,
    state_filter: list[str] | None = None,
) -> dict[str, int]:
    """
    Download and process World Atlas 2024 light pollution data.

    Args:
        regions: List of regions to download (None = all)
        grid_resolution: Grid resolution in degrees (default 0.1° ≈ 11km)
        force: Force re-download even if data exists
        state_filter: Optional list of state/province names to filter by

    Returns:
        Dictionary mapping region to number of points inserted
    """
    from celestron_nexstar.api.database.database import get_database

    db = get_database()
    _create_light_pollution_table(db)

    if regions is None:
        regions = list(WORLD_ATLAS_URLS.keys())

    # Create download directory in cache
    download_dir = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
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
            success = await _download_png(url, png_path)
            if not success:
                logger.error(f"Failed to download {region}")
                continue
        else:
            logger.info(f"Using existing {region} data")

        # Process and store in database
        count = _process_png_to_database(png_path, region, db, grid_resolution, state_filter)
        results[region] = count

    return results
