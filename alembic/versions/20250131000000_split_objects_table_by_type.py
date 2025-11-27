"""Split objects table into separate tables by object type

Revision ID: 20250131000000
Revises: 20251117210131
Create Date: 2025-01-31 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20250131000000"
down_revision: str | Sequence[str] | None = "20251117210131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Split objects table into separate tables by object type."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Check if new tables already exist (migration partially completed)
    new_tables = ['stars', 'double_stars', 'galaxies', 'nebulae', 'clusters', 'planets', 'moons']
    new_tables_exist = all(table in existing_tables for table in new_tables)

    # Check if objects table exists
    objects_table_exists = "objects" in existing_tables

    # If new tables exist but objects table also exists, migration partially completed
    if new_tables_exist and objects_table_exists:
        # Migration partially completed - just migrate remaining data and clean up
        _migrate_data(conn)
        _update_observations_table(conn)
        _drop_old_tables(conn)
        return

    # If new tables exist and objects table doesn't, migration already completed
    if new_tables_exist and not objects_table_exists:
        # Just ensure observations table is updated
        _update_observations_table(conn)
        return

    # If objects table doesn't exist and new tables don't exist, just create new tables
    if not objects_table_exists:
        _create_new_tables()
        return

    # Normal migration path: objects table exists, new tables don't
    # Step 1: Create new tables
    _create_new_tables()

    # Step 2: Migrate data from objects table to new tables
    _migrate_data(conn)

    # Step 3: Update observations table to use polymorphic reference
    _update_observations_table(conn)

    # Step 4: Drop old objects table and related FTS table
    _drop_old_tables(conn)


def _create_new_tables() -> None:
    """Create the new type-specific tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Stars table
    if "stars" not in existing_tables:
        op.create_table(
            "stars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Double stars table
    if "double_stars" not in existing_tables:
        op.create_table(
            "double_stars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Galaxies table
    if "galaxies" not in existing_tables:
        op.create_table(
            "galaxies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Nebulae table
    if "nebulae" not in existing_tables:
        op.create_table(
            "nebulae",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Clusters table
    if "clusters" not in existing_tables:
        op.create_table(
            "clusters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Planets table
    if "planets" not in existing_tables:
        op.create_table(
            "planets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("ephemeris_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Moons table
    if "moons" not in existing_tables:
        op.create_table(
            "moons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("ephemeris_name", sa.String(length=255), nullable=True),
        sa.Column("parent_planet", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        )

    # Create indexes (only for tables that were just created)
    _create_indexes(existing_tables)


def _create_indexes(existing_tables: set[str] | None = None) -> None:
    """Create indexes on the new tables."""
    if existing_tables is None:
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        existing_tables = set(inspector.get_table_names())
    
    # Get existing indexes to avoid duplicates
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = set()
    for table_name in ['stars', 'double_stars', 'galaxies', 'nebulae', 'clusters', 'planets', 'moons']:
        if table_name in existing_tables:
            for idx in inspector.get_indexes(table_name):
                existing_indexes.add(idx['name'])
    
    # Stars indexes
    if "stars" in existing_tables:
        indexes_to_create = [
            ("ix_stars_name", "stars", ["name"]),
            ("ix_stars_common_name", "stars", ["common_name"]),
            ("ix_stars_catalog", "stars", ["catalog"]),
            ("ix_stars_magnitude", "stars", ["magnitude"]),
            ("ix_stars_constellation", "stars", ["constellation"]),
            ("idx_star_catalog_number", "stars", ["catalog", "catalog_number"]),
            ("idx_star_magnitude", "stars", ["magnitude"]),
            ("idx_star_position", "stars", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Double stars indexes
    if "double_stars" in existing_tables:
        indexes_to_create = [
            ("ix_double_stars_name", "double_stars", ["name"]),
            ("ix_double_stars_common_name", "double_stars", ["common_name"]),
            ("ix_double_stars_catalog", "double_stars", ["catalog"]),
            ("ix_double_stars_magnitude", "double_stars", ["magnitude"]),
            ("ix_double_stars_constellation", "double_stars", ["constellation"]),
            ("idx_double_star_catalog_number", "double_stars", ["catalog", "catalog_number"]),
            ("idx_double_star_magnitude", "double_stars", ["magnitude"]),
            ("idx_double_star_position", "double_stars", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Galaxies indexes
    if "galaxies" in existing_tables:
        indexes_to_create = [
            ("ix_galaxies_name", "galaxies", ["name"]),
            ("ix_galaxies_common_name", "galaxies", ["common_name"]),
            ("ix_galaxies_catalog", "galaxies", ["catalog"]),
            ("ix_galaxies_magnitude", "galaxies", ["magnitude"]),
            ("ix_galaxies_constellation", "galaxies", ["constellation"]),
            ("idx_galaxy_catalog_number", "galaxies", ["catalog", "catalog_number"]),
            ("idx_galaxy_magnitude", "galaxies", ["magnitude"]),
            ("idx_galaxy_position", "galaxies", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Nebulae indexes
    if "nebulae" in existing_tables:
        indexes_to_create = [
            ("ix_nebulae_name", "nebulae", ["name"]),
            ("ix_nebulae_common_name", "nebulae", ["common_name"]),
            ("ix_nebulae_catalog", "nebulae", ["catalog"]),
            ("ix_nebulae_magnitude", "nebulae", ["magnitude"]),
            ("ix_nebulae_constellation", "nebulae", ["constellation"]),
            ("idx_nebula_catalog_number", "nebulae", ["catalog", "catalog_number"]),
            ("idx_nebula_magnitude", "nebulae", ["magnitude"]),
            ("idx_nebula_position", "nebulae", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Clusters indexes
    if "clusters" in existing_tables:
        indexes_to_create = [
            ("ix_clusters_name", "clusters", ["name"]),
            ("ix_clusters_common_name", "clusters", ["common_name"]),
            ("ix_clusters_catalog", "clusters", ["catalog"]),
            ("ix_clusters_magnitude", "clusters", ["magnitude"]),
            ("ix_clusters_constellation", "clusters", ["constellation"]),
            ("idx_cluster_catalog_number", "clusters", ["catalog", "catalog_number"]),
            ("idx_cluster_magnitude", "clusters", ["magnitude"]),
            ("idx_cluster_position", "clusters", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Planets indexes
    if "planets" in existing_tables:
        indexes_to_create = [
            ("ix_planets_name", "planets", ["name"]),
            ("ix_planets_common_name", "planets", ["common_name"]),
            ("ix_planets_catalog", "planets", ["catalog"]),
            ("ix_planets_magnitude", "planets", ["magnitude"]),
            ("ix_planets_constellation", "planets", ["constellation"]),
            ("ix_planets_is_dynamic", "planets", ["is_dynamic"]),
            ("idx_planet_ephemeris_name", "planets", ["ephemeris_name"]),
            ("idx_planet_position", "planets", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)

    # Moons indexes
    if "moons" in existing_tables:
        indexes_to_create = [
            ("ix_moons_name", "moons", ["name"]),
            ("ix_moons_common_name", "moons", ["common_name"]),
            ("ix_moons_catalog", "moons", ["catalog"]),
            ("ix_moons_magnitude", "moons", ["magnitude"]),
            ("ix_moons_constellation", "moons", ["constellation"]),
            ("ix_moons_is_dynamic", "moons", ["is_dynamic"]),
            ("ix_moons_parent_planet", "moons", ["parent_planet"]),
            ("idx_moon_parent_planet", "moons", ["parent_planet"]),
            ("idx_moon_ephemeris_name", "moons", ["ephemeris_name"]),
            ("idx_moon_position", "moons", ["ra_hours", "dec_degrees"]),
        ]
        for idx_name, table, cols in indexes_to_create:
            if idx_name not in existing_indexes:
                op.create_index(idx_name, table, cols)


def _migrate_data(conn: sa.engine.Connection) -> None:
    """Migrate data from objects table to new type-specific tables."""
    # Map object_type values to table names
    type_to_table = {
        "star": "stars",
        "double_star": "double_stars",
        "galaxy": "galaxies",
        "nebula": "nebulae",
        "cluster": "clusters",
        "planet": "planets",
        "moon": "moons",
    }

    # Get all objects from the old table
    result = conn.execute(text("SELECT * FROM objects"))
    objects = result.fetchall()
    columns = result.keys()

    # Create a mapping of old_id -> (new_table, new_id) for observations migration
    id_mapping: dict[int, tuple[str, int]] = {}

    for obj in objects:
        # Convert row to dict
        obj_dict = dict(zip(columns, obj))
        object_type = obj_dict["object_type"]
        old_id = obj_dict["id"]

        # Skip unknown types
        if object_type not in type_to_table:
            continue

        table_name = type_to_table[object_type]

        # Build INSERT statement
        if object_type == "moon":
            # Moons include parent_planet
            conn.execute(
                text(f"""
                INSERT INTO {table_name} (
                    name, common_name, catalog, catalog_number,
                    ra_hours, dec_degrees, magnitude, size_arcmin,
                    description, constellation,
                    is_dynamic, ephemeris_name, parent_planet,
                    created_at, updated_at
                ) VALUES (
                    :name, :common_name, :catalog, :catalog_number,
                    :ra_hours, :dec_degrees, :magnitude, :size_arcmin,
                    :description, :constellation,
                    :is_dynamic, :ephemeris_name, :parent_planet,
                    :created_at, :updated_at
                )
            """),
                {
                    "name": obj_dict["name"],
                    "common_name": obj_dict.get("common_name"),
                    "catalog": obj_dict["catalog"],
                    "catalog_number": obj_dict.get("catalog_number"),
                    "ra_hours": obj_dict["ra_hours"],
                    "dec_degrees": obj_dict["dec_degrees"],
                    "magnitude": obj_dict.get("magnitude"),
                    "size_arcmin": obj_dict.get("size_arcmin"),
                    "description": obj_dict.get("description"),
                    "constellation": obj_dict.get("constellation"),
                    "is_dynamic": obj_dict.get("is_dynamic", False),
                    "ephemeris_name": obj_dict.get("ephemeris_name"),
                    "parent_planet": obj_dict.get("parent_planet"),
                    "created_at": obj_dict.get("created_at"),
                    "updated_at": obj_dict.get("updated_at"),
                },
            )
        elif object_type == "planet":
            # Planets don't have parent_planet
            conn.execute(
                text(f"""
                INSERT INTO {table_name} (
                    name, common_name, catalog, catalog_number,
                    ra_hours, dec_degrees, magnitude, size_arcmin,
                    description, constellation,
                    is_dynamic, ephemeris_name,
                    created_at, updated_at
                ) VALUES (
                    :name, :common_name, :catalog, :catalog_number,
                    :ra_hours, :dec_degrees, :magnitude, :size_arcmin,
                    :description, :constellation,
                    :is_dynamic, :ephemeris_name,
                    :created_at, :updated_at
                )
            """),
                {
                    "name": obj_dict["name"],
                    "common_name": obj_dict.get("common_name"),
                    "catalog": obj_dict["catalog"],
                    "catalog_number": obj_dict.get("catalog_number"),
                    "ra_hours": obj_dict["ra_hours"],
                    "dec_degrees": obj_dict["dec_degrees"],
                    "magnitude": obj_dict.get("magnitude"),
                    "size_arcmin": obj_dict.get("size_arcmin"),
                    "description": obj_dict.get("description"),
                    "constellation": obj_dict.get("constellation"),
                    "is_dynamic": obj_dict.get("is_dynamic", False),
                    "ephemeris_name": obj_dict.get("ephemeris_name"),
                    "created_at": obj_dict.get("created_at"),
                    "updated_at": obj_dict.get("updated_at"),
                },
            )
        else:
            # Regular objects without dynamic fields
            conn.execute(
                text(f"""
                INSERT INTO {table_name} (
                    name, common_name, catalog, catalog_number,
                    ra_hours, dec_degrees, magnitude, size_arcmin,
                    description, constellation,
                    created_at, updated_at
                ) VALUES (
                    :name, :common_name, :catalog, :catalog_number,
                    :ra_hours, :dec_degrees, :magnitude, :size_arcmin,
                    :description, :constellation,
                    :created_at, :updated_at
                )
            """),
                {
                    "name": obj_dict["name"],
                    "common_name": obj_dict.get("common_name"),
                    "catalog": obj_dict["catalog"],
                    "catalog_number": obj_dict.get("catalog_number"),
                    "ra_hours": obj_dict["ra_hours"],
                    "dec_degrees": obj_dict["dec_degrees"],
                    "magnitude": obj_dict.get("magnitude"),
                    "size_arcmin": obj_dict.get("size_arcmin"),
                    "description": obj_dict.get("description"),
                    "constellation": obj_dict.get("constellation"),
                    "created_at": obj_dict.get("created_at"),
                    "updated_at": obj_dict.get("updated_at"),
                },
            )

        # Get the new ID (lastrowid)
        new_id_result = conn.execute(text(f"SELECT last_insert_rowid()"))
        new_id = new_id_result.scalar()
        id_mapping[old_id] = (table_name, new_id)

    # Store mapping for observations migration
    conn.execute(text("CREATE TABLE IF NOT EXISTS _object_id_mapping (old_id INTEGER, object_type TEXT, new_id INTEGER)"))
    for old_id, (table_name, new_id) in id_mapping.items():
        # Extract object_type from table_name
        object_type = table_name.rstrip("s")  # Remove plural
        if object_type == "double_star":
            object_type = "double_star"
        elif object_type == "galaxie":
            object_type = "galaxy"
        elif object_type == "nebula":
            object_type = "nebula"
        elif object_type == "cluster":
            object_type = "cluster"
        elif object_type == "planet":
            object_type = "planet"
        elif object_type == "moon":
            object_type = "moon"
        elif object_type == "star":
            object_type = "star"

        conn.execute(
            text("INSERT INTO _object_id_mapping (old_id, object_type, new_id) VALUES (:old_id, :object_type, :new_id)"),
            {"old_id": old_id, "object_type": object_type, "new_id": new_id},
        )

    conn.commit()


def _update_observations_table(conn: sa.engine.Connection) -> None:
    """Update observations table to use polymorphic reference."""
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "observations" not in existing_tables:
        return

    # Check if columns already exist
    existing_columns = [col["name"] for col in inspector.get_columns("observations")]

    # Check if table has already been fully migrated
    # If object_type exists but new_object_id doesn't, the table has been recreated
    if "object_type" in existing_columns and "new_object_id" not in existing_columns and "old_object_id" not in existing_columns:
        # Table has already been migrated, just ensure indexes exist
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_object_type ON observations(object_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_object_id ON observations(object_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_observations_object_ref ON observations(object_type, object_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_object_observed ON observations(object_type, object_id, observed_at)"))
        conn.commit()
        return

    # Add new columns if they don't exist
    if "object_type" not in existing_columns:
        op.add_column("observations", sa.Column("object_type", sa.String(length=50), nullable=True))
    if "new_object_id" not in existing_columns:
        op.add_column("observations", sa.Column("new_object_id", sa.Integer(), nullable=True))

    # Migrate observation references using the mapping table
    conn.execute(
        text("""
        UPDATE observations
        SET object_type = (
            SELECT object_type FROM _object_id_mapping
            WHERE _object_id_mapping.old_id = observations.object_id
        ),
        new_object_id = (
            SELECT new_id FROM _object_id_mapping
            WHERE _object_id_mapping.old_id = observations.object_id
        )
        WHERE EXISTS (
            SELECT 1 FROM _object_id_mapping
            WHERE _object_id_mapping.old_id = observations.object_id
        )
    """)
    )

    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Step 1: Get existing columns from old table
    old_columns = [col["name"] for col in inspector.get_columns("observations")]
    
    # Step 2: Create new table with correct schema
    conn.execute(text("""
        CREATE TABLE observations_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            location_lat REAL,
            location_lon REAL,
            location_geohash TEXT,
            location_name TEXT,
            seeing_quality INTEGER,
            transparency INTEGER,
            sky_brightness REAL,
            weather_notes TEXT,
            telescope TEXT,
            eyepiece TEXT,
            filters TEXT,
            notes TEXT,
            rating INTEGER,
            image_path TEXT,
            sketch_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """))

    # Step 3: Build column lists for INSERT and SELECT, only including columns that exist
    insert_columns = ["id", "object_type", "object_id", "observed_at"]
    select_columns = [
        "id",
        "COALESCE(object_type, 'unknown') as object_type",
        "COALESCE(new_object_id, object_id) as object_id",
        "observed_at"
    ]
    
    # Add optional columns if they exist in the old table
    optional_columns = [
        "location_lat", "location_lon", "location_geohash", "location_name",
        "seeing_quality", "transparency", "sky_brightness", "weather_notes",
        "telescope", "eyepiece", "filters", "notes", "rating",
        "image_path", "sketch_path", "created_at", "updated_at"
    ]
    
    for col in optional_columns:
        if col in old_columns:
            insert_columns.append(col)
            select_columns.append(col)
    
    # Step 4: Copy data from old table to new table
    insert_sql = f"""
        INSERT INTO observations_new ({', '.join(insert_columns)})
        SELECT {', '.join(select_columns)}
        FROM observations
    """
    conn.execute(text(insert_sql))

    # Step 3: Drop old table
    conn.execute(text("DROP TABLE observations"))

    # Step 4: Rename new table
    conn.execute(text("ALTER TABLE observations_new RENAME TO observations"))

    # Step 5: Recreate indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_observed_at ON observations(observed_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_location_geohash ON observations(location_geohash)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_object_type ON observations(object_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_observations_object_id ON observations(object_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_observations_object_ref ON observations(object_type, object_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_object_observed ON observations(object_type, object_id, observed_at)"))

    conn.commit()


def _drop_old_tables(conn: sa.engine.Connection) -> None:
    """Drop old objects table and related structures."""
    # Drop FTS table if it exists
    conn.execute(text("DROP TABLE IF EXISTS objects_fts"))

    # Drop triggers
    conn.execute(text("DROP TRIGGER IF EXISTS objects_ai"))
    conn.execute(text("DROP TRIGGER IF EXISTS objects_ad"))
    conn.execute(text("DROP TRIGGER IF EXISTS objects_au"))

    # Drop old objects table
    op.drop_table("objects")

    # Drop mapping table
    conn.execute(text("DROP TABLE IF EXISTS _object_id_mapping"))

    conn.commit()


def downgrade() -> None:
    """Revert the split - merge tables back into objects table."""
    # This is a complex downgrade that would require:
    # 1. Recreate objects table
    # 2. Migrate data from all type-specific tables back
    # 3. Update observations to use old foreign key
    # 4. Drop type-specific tables
    # For now, we'll raise an error as this is a destructive migration
    raise NotImplementedError("Downgrade not supported - this migration splits the objects table permanently")

