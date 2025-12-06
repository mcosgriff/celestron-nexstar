"""
DuckDB Migration System

Manages schema migrations for DuckDB database. Unlike SQLAlchemy/Alembic,
DuckDB uses direct SQL migrations.

Based on SQLite schema, excluding tables that come from starplot:
- stars (from starplot parquet)
- double_stars (from starplot)
- galaxies (from starplot DSO database)
- nebulae (from starplot DSO database)
- clusters (from starplot DSO database)

Note: Constellations may be available in starplot's database. If so, they're queried from there
instead of the custom table. The custom table is kept as a fallback and for additional metadata
(common_name, mythology, boundaries, etc.) that starplot may not provide.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

__all__ = ["Migration", "run_migrations", "get_current_version", "rollback_migration", "MIGRATIONS"]


class Migration:
    """Represents a database migration."""

    def __init__(self, version: int, name: str, up_sql: str, down_sql: str | None = None):
        """
        Initialize a migration.

        Args:
            version: Migration version number (must be unique and sequential)
            name: Human-readable migration name
            up_sql: SQL to apply the migration
            down_sql: Optional SQL to rollback the migration
        """
        self.version = version
        self.name = name
        self.up_sql = up_sql
        self.down_sql = down_sql

    def apply(self, con: duckdb.DuckDBPyConnection) -> None:
        """Apply this migration."""
        logger.info(f"Applying migration {self.version}: {self.name}")
        con.execute(self.up_sql)

    def rollback(self, con: duckdb.DuckDBPyConnection) -> None:
        """Rollback this migration."""
        if self.down_sql:
            logger.info(f"Rolling back migration {self.version}: {self.name}")
            con.execute(self.down_sql)
        else:
            raise ValueError(f"Migration {self.version} ({self.name}) does not support rollback")


# Migration history table
MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)
"""

# Initial migration - creates all custom tables (excluding starplot tables)
MIGRATION_001_INITIAL_SCHEMA = Migration(
    version=1,
    name="initial_schema",
    up_sql="""
    -- Metadata table for database version and stats
    CREATE TABLE IF NOT EXISTS metadata (
        key VARCHAR PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Planets table
    CREATE TABLE IF NOT EXISTS planets (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        common_name VARCHAR,
        catalog VARCHAR NOT NULL DEFAULT 'planets',
        catalog_number INTEGER,
        ra_hours DOUBLE NOT NULL,
        dec_degrees DOUBLE NOT NULL,
        magnitude DOUBLE,
        size_arcmin DOUBLE,
        description TEXT,
        constellation VARCHAR,
        is_dynamic BOOLEAN NOT NULL DEFAULT true,
        ephemeris_name VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Moons table
    CREATE TABLE IF NOT EXISTS moons (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        common_name VARCHAR,
        catalog VARCHAR NOT NULL DEFAULT 'moons',
        catalog_number INTEGER,
        ra_hours DOUBLE NOT NULL,
        dec_degrees DOUBLE NOT NULL,
        magnitude DOUBLE,
        size_arcmin DOUBLE,
        description TEXT,
        constellation VARCHAR,
        is_dynamic BOOLEAN NOT NULL DEFAULT true,
        ephemeris_name VARCHAR,
        parent_planet VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Asterisms table
    CREATE TABLE IF NOT EXISTS asterisms (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        alt_names VARCHAR,
        ra_hours DOUBLE NOT NULL,
        dec_degrees DOUBLE NOT NULL,
        size_degrees DOUBLE,
        parent_constellation VARCHAR,
        description TEXT,
        stars TEXT,
        season VARCHAR,
        wikipedia_url VARCHAR,
        cultural_info TEXT,
        guidepost_info TEXT,
        historical_notes TEXT,
        shape_description VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Constellations table
    CREATE TABLE IF NOT EXISTS constellations (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        abbreviation VARCHAR(3) NOT NULL UNIQUE,
        common_name VARCHAR,
        ra_hours DOUBLE NOT NULL,
        dec_degrees DOUBLE NOT NULL,
        ra_min_hours DOUBLE NOT NULL,
        ra_max_hours DOUBLE NOT NULL,
        dec_min_degrees DOUBLE NOT NULL,
        dec_max_degrees DOUBLE NOT NULL,
        area_sq_deg DOUBLE,
        brightest_star VARCHAR,
        mythology TEXT,
        season VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Observations table
    CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY,
        object_type VARCHAR NOT NULL,
        object_id INTEGER NOT NULL,
        observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
        location_lat DOUBLE,
        location_lon DOUBLE,
        location_geohash VARCHAR,
        location_name VARCHAR,
        seeing_quality INTEGER,
        transparency INTEGER,
        sky_brightness DOUBLE,
        weather_notes TEXT,
        telescope VARCHAR,
        eyepiece VARCHAR,
        filters VARCHAR,
        notes TEXT,
        rating INTEGER,
        image_path VARCHAR,
        sketch_path VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- User preferences table
    CREATE TABLE IF NOT EXISTS user_preferences (
        key VARCHAR PRIMARY KEY,
        value TEXT NOT NULL,
        category VARCHAR NOT NULL,
        description TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Favorites table
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY,
        object_name VARCHAR NOT NULL UNIQUE,
        object_type VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Light pollution grid table
    CREATE TABLE IF NOT EXISTS light_pollution_grid (
        id INTEGER PRIMARY KEY,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        geohash VARCHAR NOT NULL,
        sqm_value DOUBLE NOT NULL,
        region VARCHAR,
        created_at VARCHAR
    );

    -- Weather forecast table
    CREATE TABLE IF NOT EXISTS weather_forecast (
        id INTEGER PRIMARY KEY,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        geohash VARCHAR,
        forecast_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
        temperature_f DOUBLE,
        dew_point_f DOUBLE,
        humidity_percent DOUBLE,
        cloud_cover_percent DOUBLE,
        wind_speed_mph DOUBLE,
        seeing_score DOUBLE,
        fetched_at TIMESTAMP WITH TIME ZONE NOT NULL
    );

    -- Historical weather table
    CREATE TABLE IF NOT EXISTS historical_weather (
        id INTEGER PRIMARY KEY,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        geohash VARCHAR,
        month INTEGER NOT NULL,
        avg_cloud_cover_percent DOUBLE,
        min_cloud_cover_percent DOUBLE,
        max_cloud_cover_percent DOUBLE,
        p25_cloud_cover_percent DOUBLE,
        p40_cloud_cover_percent DOUBLE,
        p60_cloud_cover_percent DOUBLE,
        p75_cloud_cover_percent DOUBLE,
        std_dev_cloud_cover_percent DOUBLE,
        years_of_data INTEGER,
        fetched_at TIMESTAMP WITH TIME ZONE NOT NULL
    );

    -- ISS passes table
    CREATE TABLE IF NOT EXISTS iss_passes (
        id INTEGER PRIMARY KEY,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        geohash VARCHAR,
        rise_time TIMESTAMP WITH TIME ZONE NOT NULL,
        max_time TIMESTAMP WITH TIME ZONE NOT NULL,
        set_time TIMESTAMP WITH TIME ZONE NOT NULL,
        duration_seconds INTEGER NOT NULL,
        max_altitude_deg DOUBLE NOT NULL,
        magnitude DOUBLE,
        rise_azimuth_deg DOUBLE NOT NULL,
        max_azimuth_deg DOUBLE NOT NULL,
        set_azimuth_deg DOUBLE NOT NULL,
        is_visible BOOLEAN NOT NULL DEFAULT true,
        fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Meteor showers table
    CREATE TABLE IF NOT EXISTS meteor_showers (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        code VARCHAR,
        start_month INTEGER NOT NULL,
        start_day INTEGER NOT NULL,
        end_month INTEGER NOT NULL,
        end_day INTEGER NOT NULL,
        peak_month INTEGER NOT NULL,
        peak_day INTEGER NOT NULL,
        radiant_ra_hours DOUBLE NOT NULL,
        radiant_dec_degrees DOUBLE NOT NULL,
        radiant_constellation VARCHAR,
        zhr_peak INTEGER NOT NULL,
        velocity_km_s DOUBLE,
        parent_comet VARCHAR,
        best_time VARCHAR,
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Dark sky sites table
    CREATE TABLE IF NOT EXISTS dark_sky_sites (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        latitude DOUBLE NOT NULL,
        longitude DOUBLE NOT NULL,
        geohash VARCHAR,
        bortle_class INTEGER NOT NULL,
        sqm_value DOUBLE NOT NULL,
        description TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Space events table
    CREATE TABLE IF NOT EXISTS space_events (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        event_type VARCHAR NOT NULL,
        date TIMESTAMP WITH TIME ZONE NOT NULL,
        description TEXT NOT NULL,
        min_latitude DOUBLE,
        max_latitude DOUBLE,
        min_longitude DOUBLE,
        max_longitude DOUBLE,
        dark_sky_required BOOLEAN NOT NULL DEFAULT false,
        min_bortle_class INTEGER,
        equipment_needed VARCHAR,
        viewing_notes TEXT,
        source VARCHAR NOT NULL DEFAULT 'Planetary Society',
        url VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Ephemeris files table
    CREATE TABLE IF NOT EXISTS ephemeris_files (
        file_key VARCHAR PRIMARY KEY,
        filename VARCHAR NOT NULL UNIQUE,
        display_name VARCHAR NOT NULL,
        description TEXT NOT NULL,
        coverage_start INTEGER NOT NULL,
        coverage_end INTEGER NOT NULL,
        size_mb DOUBLE NOT NULL,
        file_type VARCHAR NOT NULL,
        url VARCHAR NOT NULL,
        contents TEXT NOT NULL,
        use_case TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Star name mappings table
    CREATE TABLE IF NOT EXISTS star_name_mappings (
        hr_number INTEGER PRIMARY KEY,
        common_name VARCHAR NOT NULL,
        bayer_designation VARCHAR,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- TLE data table
    CREATE TABLE IF NOT EXISTS tle_data (
        norad_id INTEGER PRIMARY KEY,
        satellite_name VARCHAR NOT NULL,
        satellite_group VARCHAR,
        line1 TEXT NOT NULL,
        line2 TEXT NOT NULL,
        epoch TIMESTAMP WITH TIME ZONE,
        fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Variable stars table
    CREATE TABLE IF NOT EXISTS variable_stars (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        designation VARCHAR NOT NULL,
        variable_type VARCHAR NOT NULL,
        period_days DOUBLE NOT NULL,
        magnitude_min DOUBLE NOT NULL,
        magnitude_max DOUBLE NOT NULL,
        ra_hours DOUBLE NOT NULL,
        dec_degrees DOUBLE NOT NULL,
        notes TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Comets table
    CREATE TABLE IF NOT EXISTS comets (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        designation VARCHAR NOT NULL UNIQUE,
        perihelion_date TIMESTAMP WITH TIME ZONE NOT NULL,
        perihelion_distance_au DOUBLE NOT NULL,
        peak_magnitude DOUBLE NOT NULL,
        peak_date TIMESTAMP WITH TIME ZONE NOT NULL,
        is_periodic BOOLEAN NOT NULL DEFAULT false,
        period_years DOUBLE,
        notes TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Eclipses table
    CREATE TABLE IF NOT EXISTS eclipses (
        id INTEGER PRIMARY KEY,
        eclipse_type VARCHAR NOT NULL,
        date TIMESTAMP WITH TIME ZONE NOT NULL,
        magnitude DOUBLE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Bortle characteristics table
    CREATE TABLE IF NOT EXISTS bortle_characteristics (
        bortle_class INTEGER PRIMARY KEY,
        sqm_min DOUBLE NOT NULL,
        sqm_max DOUBLE NOT NULL,
        naked_eye_mag DOUBLE NOT NULL,
        milky_way BOOLEAN NOT NULL DEFAULT false,
        airglow BOOLEAN NOT NULL DEFAULT false,
        zodiacal_light BOOLEAN NOT NULL DEFAULT false,
        description TEXT NOT NULL,
        recommendations TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- RSS feeds table
    CREATE TABLE IF NOT EXISTS rss_feeds (
        id INTEGER PRIMARY KEY,
        title VARCHAR NOT NULL,
        link VARCHAR NOT NULL UNIQUE,
        guid VARCHAR UNIQUE,
        description TEXT NOT NULL,
        content TEXT,
        published_date TIMESTAMP WITH TIME ZONE NOT NULL,
        author VARCHAR,
        categories TEXT,
        source VARCHAR NOT NULL DEFAULT 'Sky & Telescope',
        feed_url VARCHAR NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Eyepieces table
    CREATE TABLE IF NOT EXISTS eyepieces (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        focal_length_mm DOUBLE NOT NULL,
        apparent_fov_deg DOUBLE NOT NULL DEFAULT 50.0,
        barrel_size_mm DOUBLE,
        manufacturer VARCHAR,
        model VARCHAR,
        notes TEXT,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Filters table
    CREATE TABLE IF NOT EXISTS filters (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        filter_type VARCHAR NOT NULL,
        barrel_size_mm DOUBLE,
        manufacturer VARCHAR,
        model VARCHAR,
        transmission_percent DOUBLE,
        notes TEXT,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Cameras table
    CREATE TABLE IF NOT EXISTS cameras (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        camera_type VARCHAR NOT NULL,
        sensor_width_mm DOUBLE,
        sensor_height_mm DOUBLE,
        pixel_width_um DOUBLE,
        pixel_height_um DOUBLE,
        manufacturer VARCHAR,
        model VARCHAR,
        notes TEXT,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_planets_name ON planets(name);
    CREATE INDEX IF NOT EXISTS idx_planets_magnitude ON planets(magnitude);
    CREATE INDEX IF NOT EXISTS idx_planets_ephemeris_name ON planets(ephemeris_name);
    CREATE INDEX IF NOT EXISTS idx_planets_position ON planets(ra_hours, dec_degrees);

    CREATE INDEX IF NOT EXISTS idx_moons_name ON moons(name);
    CREATE INDEX IF NOT EXISTS idx_moons_parent ON moons(parent_planet);
    CREATE INDEX IF NOT EXISTS idx_moons_ephemeris_name ON moons(ephemeris_name);
    CREATE INDEX IF NOT EXISTS idx_moons_position ON moons(ra_hours, dec_degrees);

    CREATE INDEX IF NOT EXISTS idx_asterisms_name ON asterisms(name);
    CREATE INDEX IF NOT EXISTS idx_asterisms_parent ON asterisms(parent_constellation);
    CREATE INDEX IF NOT EXISTS idx_asterisms_position ON asterisms(ra_hours, dec_degrees);

    CREATE INDEX IF NOT EXISTS idx_constellations_name ON constellations(name);
    CREATE INDEX IF NOT EXISTS idx_constellations_abbreviation ON constellations(abbreviation);
    CREATE INDEX IF NOT EXISTS idx_constellations_position ON constellations(ra_hours, dec_degrees);
    CREATE INDEX IF NOT EXISTS idx_constellations_bounds ON constellations(ra_min_hours, ra_max_hours, dec_min_degrees, dec_max_degrees);

    CREATE INDEX IF NOT EXISTS idx_observations_object_type ON observations(object_type);
    CREATE INDEX IF NOT EXISTS idx_observations_object_id ON observations(object_id);
    CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations(observed_at);
    CREATE INDEX IF NOT EXISTS idx_observations_object_observed ON observations(object_type, object_id, observed_at);
    CREATE INDEX IF NOT EXISTS idx_observations_object_ref ON observations(object_type, object_id);
    CREATE INDEX IF NOT EXISTS idx_observations_geohash ON observations(location_geohash);

    CREATE INDEX IF NOT EXISTS idx_user_preferences_category ON user_preferences(category);

    CREATE INDEX IF NOT EXISTS idx_favorites_object_name ON favorites(object_name);
    CREATE INDEX IF NOT EXISTS idx_favorites_object_type ON favorites(object_type);
    CREATE INDEX IF NOT EXISTS idx_favorites_created_at ON favorites(created_at);

    CREATE INDEX IF NOT EXISTS idx_lp_geohash ON light_pollution_grid(geohash);
    CREATE INDEX IF NOT EXISTS idx_lp_lat_lon ON light_pollution_grid(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_lp_region ON light_pollution_grid(region);

    CREATE INDEX IF NOT EXISTS idx_weather_forecast_lat_lon ON weather_forecast(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_weather_forecast_timestamp ON weather_forecast(forecast_timestamp);
    CREATE INDEX IF NOT EXISTS idx_weather_forecast_fetched ON weather_forecast(fetched_at);
    CREATE INDEX IF NOT EXISTS idx_weather_forecast_location_timestamp ON weather_forecast(latitude, longitude, forecast_timestamp);
    CREATE INDEX IF NOT EXISTS idx_weather_forecast_location_fetched ON weather_forecast(latitude, longitude, fetched_at);
    CREATE INDEX IF NOT EXISTS idx_weather_forecast_geohash ON weather_forecast(geohash);

    CREATE INDEX IF NOT EXISTS idx_historical_weather_lat_lon ON historical_weather(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_historical_weather_month ON historical_weather(month);
    CREATE INDEX IF NOT EXISTS idx_historical_weather_fetched ON historical_weather(fetched_at);
    CREATE INDEX IF NOT EXISTS idx_historical_weather_location_month ON historical_weather(latitude, longitude, month);
    CREATE INDEX IF NOT EXISTS idx_historical_weather_geohash_month ON historical_weather(geohash, month);

    CREATE INDEX IF NOT EXISTS idx_iss_passes_lat_lon ON iss_passes(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_rise_time ON iss_passes(rise_time);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_fetched ON iss_passes(fetched_at);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_location_rise ON iss_passes(latitude, longitude, rise_time);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_location_fetched ON iss_passes(latitude, longitude, fetched_at);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_location_rise_fetched ON iss_passes(latitude, longitude, rise_time, fetched_at);
    CREATE INDEX IF NOT EXISTS idx_iss_passes_geohash ON iss_passes(geohash);

    CREATE INDEX IF NOT EXISTS idx_meteor_showers_name ON meteor_showers(name);
    CREATE INDEX IF NOT EXISTS idx_meteor_showers_peak_date ON meteor_showers(peak_month, peak_day);
    CREATE INDEX IF NOT EXISTS idx_meteor_showers_radiant_constellation ON meteor_showers(radiant_constellation);

    CREATE INDEX IF NOT EXISTS idx_dark_sky_sites_name ON dark_sky_sites(name);
    CREATE INDEX IF NOT EXISTS idx_dark_sky_sites_location ON dark_sky_sites(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_dark_sky_sites_bortle ON dark_sky_sites(bortle_class);
    CREATE INDEX IF NOT EXISTS idx_dark_sky_sites_geohash ON dark_sky_sites(geohash);

    CREATE INDEX IF NOT EXISTS idx_space_events_name ON space_events(name);
    CREATE INDEX IF NOT EXISTS idx_space_events_date ON space_events(date);
    CREATE INDEX IF NOT EXISTS idx_space_events_type ON space_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_space_events_date_type ON space_events(date, event_type);
    CREATE INDEX IF NOT EXISTS idx_space_events_source ON space_events(source);

    CREATE INDEX IF NOT EXISTS idx_ephemeris_files_filename ON ephemeris_files(filename);
    CREATE INDEX IF NOT EXISTS idx_ephemeris_files_type ON ephemeris_files(file_type);
    CREATE INDEX IF NOT EXISTS idx_ephemeris_files_coverage ON ephemeris_files(coverage_start, coverage_end);

    CREATE INDEX IF NOT EXISTS idx_star_name_mappings_common_name ON star_name_mappings(common_name);
    CREATE INDEX IF NOT EXISTS idx_star_name_mappings_bayer ON star_name_mappings(bayer_designation);

    CREATE INDEX IF NOT EXISTS idx_tle_satellite_name ON tle_data(satellite_name);
    CREATE INDEX IF NOT EXISTS idx_tle_satellite_group ON tle_data(satellite_group);
    CREATE INDEX IF NOT EXISTS idx_tle_fetched_at ON tle_data(fetched_at);

    CREATE INDEX IF NOT EXISTS idx_variable_stars_name ON variable_stars(name);
    CREATE INDEX IF NOT EXISTS idx_variable_stars_type ON variable_stars(variable_type);
    CREATE INDEX IF NOT EXISTS idx_variable_stars_position ON variable_stars(ra_hours, dec_degrees);

    CREATE INDEX IF NOT EXISTS idx_comets_name ON comets(name);
    CREATE INDEX IF NOT EXISTS idx_comets_designation ON comets(designation);
    CREATE INDEX IF NOT EXISTS idx_comets_perihelion_date ON comets(perihelion_date);
    CREATE INDEX IF NOT EXISTS idx_comets_peak_date ON comets(peak_date);
    CREATE INDEX IF NOT EXISTS idx_comets_is_periodic ON comets(is_periodic);

    CREATE INDEX IF NOT EXISTS idx_eclipses_type ON eclipses(eclipse_type);
    CREATE INDEX IF NOT EXISTS idx_eclipses_date ON eclipses(date);
    CREATE INDEX IF NOT EXISTS idx_eclipses_type_date ON eclipses(eclipse_type, date);

    CREATE INDEX IF NOT EXISTS idx_bortle_sqm_range ON bortle_characteristics(sqm_min, sqm_max);

    CREATE INDEX IF NOT EXISTS idx_rss_feeds_title ON rss_feeds(title);
    CREATE INDEX IF NOT EXISTS idx_rss_feeds_link ON rss_feeds(link);
    CREATE INDEX IF NOT EXISTS idx_rss_feeds_guid ON rss_feeds(guid);
    CREATE INDEX IF NOT EXISTS idx_rss_feeds_published_date ON rss_feeds(published_date);
    CREATE INDEX IF NOT EXISTS idx_rss_feeds_source_fetched ON rss_feeds(source, fetched_at);

    CREATE INDEX IF NOT EXISTS idx_eyepieces_name ON eyepieces(name);
    CREATE INDEX IF NOT EXISTS idx_eyepieces_focal_length ON eyepieces(focal_length_mm);
    CREATE INDEX IF NOT EXISTS idx_eyepieces_created_at ON eyepieces(created_at);

    CREATE INDEX IF NOT EXISTS idx_filters_name ON filters(name);
    CREATE INDEX IF NOT EXISTS idx_filters_type ON filters(filter_type);

    CREATE INDEX IF NOT EXISTS idx_cameras_name ON cameras(name);
    CREATE INDEX IF NOT EXISTS idx_cameras_type ON cameras(camera_type);
    """,
    down_sql="""
    DROP TABLE IF EXISTS cameras;
    DROP TABLE IF EXISTS filters;
    DROP TABLE IF EXISTS eyepieces;
    DROP TABLE IF EXISTS rss_feeds;
    DROP TABLE IF EXISTS bortle_characteristics;
    DROP TABLE IF EXISTS eclipses;
    DROP TABLE IF EXISTS comets;
    DROP TABLE IF EXISTS variable_stars;
    DROP TABLE IF EXISTS tle_data;
    DROP TABLE IF EXISTS star_name_mappings;
    DROP TABLE IF EXISTS ephemeris_files;
    DROP TABLE IF EXISTS space_events;
    DROP TABLE IF EXISTS dark_sky_sites;
    DROP TABLE IF EXISTS meteor_showers;
    DROP TABLE IF EXISTS iss_passes;
    DROP TABLE IF EXISTS historical_weather;
    DROP TABLE IF EXISTS weather_forecast;
    DROP TABLE IF EXISTS light_pollution_grid;
    DROP TABLE IF EXISTS favorites;
    DROP TABLE IF EXISTS user_preferences;
    DROP TABLE IF EXISTS observations;
    DROP TABLE IF EXISTS constellations;
    DROP TABLE IF EXISTS asterisms;
    DROP TABLE IF EXISTS moons;
    DROP TABLE IF EXISTS planets;
    DROP TABLE IF EXISTS metadata;
    """,
)

# All migrations in order
MIGRATIONS: list[Migration] = [
    MIGRATION_001_INITIAL_SCHEMA,
]


def get_current_version(con: duckdb.DuckDBPyConnection) -> int:
    """
    Get the current database schema version.

    Args:
        con: DuckDB connection

    Returns:
        Current version number, or 0 if no migrations have been applied
    """
    # Ensure migration table exists
    con.execute(MIGRATION_TABLE_SQL)

    try:
        result = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        if result and result[0] is not None:
            return int(result[0])
        return 0
    except Exception:
        return 0


def run_migrations(con: duckdb.DuckDBPyConnection, target_version: int | None = None) -> None:
    """
    Run all pending migrations up to target_version.

    Args:
        con: DuckDB connection
        target_version: Target version to migrate to (None = latest)
    """
    # Ensure migration table exists
    con.execute(MIGRATION_TABLE_SQL)

    current_version = get_current_version(con)
    target_version = target_version or max(m.version for m in MIGRATIONS)

    if current_version >= target_version:
        logger.info(f"Database is already at version {current_version} (target: {target_version})")
        return

    # Get migrations to apply
    migrations_to_apply = [m for m in MIGRATIONS if m.version > current_version and m.version <= target_version]
    migrations_to_apply.sort(key=lambda m: m.version)

    if not migrations_to_apply:
        logger.info("No migrations to apply")
        return

    logger.info(f"Applying {len(migrations_to_apply)} migration(s) (from version {current_version} to {target_version})")

    # Apply each migration in a transaction
    for migration in migrations_to_apply:
        try:
            # Start transaction
            con.execute("BEGIN TRANSACTION")
            migration.apply(con)

            # Record migration
            con.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                [migration.version, migration.name],
            )

            # Commit transaction
            con.execute("COMMIT")
            logger.info(f"Successfully applied migration {migration.version}: {migration.name}")

        except Exception as e:
            # Rollback on error
            con.execute("ROLLBACK")
            logger.error(f"Failed to apply migration {migration.version} ({migration.name}): {e}")
            raise

    logger.info(f"Migration complete. Database is now at version {target_version}")


def rollback_migration(con: duckdb.DuckDBPyConnection, target_version: int) -> None:
    """
    Rollback migrations to a specific version.

    Args:
        con: DuckDB connection
        target_version: Version to rollback to
    """
    current_version = get_current_version(con)

    if current_version <= target_version:
        logger.info(f"Database is already at version {current_version} (target: {target_version})")
        return

    # Get migrations to rollback (in reverse order)
    migrations_to_rollback = [m for m in MIGRATIONS if m.version > target_version and m.version <= current_version]
    migrations_to_rollback.sort(key=lambda m: m.version, reverse=True)

    if not migrations_to_rollback:
        logger.info("No migrations to rollback")
        return

    logger.info(f"Rolling back {len(migrations_to_rollback)} migration(s) (from version {current_version} to {target_version})")

    for migration in migrations_to_rollback:
        try:
            con.execute("BEGIN TRANSACTION")
            migration.rollback(con)

            # Remove migration record
            con.execute("DELETE FROM schema_migrations WHERE version = ?", [migration.version])

            con.execute("COMMIT")
            logger.info(f"Successfully rolled back migration {migration.version}: {migration.name}")

        except Exception as e:
            con.execute("ROLLBACK")
            logger.error(f"Failed to rollback migration {migration.version} ({migration.name}): {e}")
            raise

    logger.info(f"Rollback complete. Database is now at version {target_version}")
