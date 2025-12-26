"""populate_constellation_for_messier_objects

Revision ID: c92fca48be10
Revises: 648fa53bd17a
Create Date: 2025-12-25 20:47:49.666159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c92fca48be10'
down_revision: Union[str, Sequence[str], None] = '648fa53bd17a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Populate constellation_id and constellation for Messier objects using spatial queries.

    Messier objects don't have geometry populated, so the regular spatial query process
    during import doesn't work for them. This migration uses RA/Dec coordinates to
    create temporary points and find which constellation contains each object.
    """
    import math
    from sqlalchemy import text

    conn = op.get_bind()

    # Load SpatiaLite extension directly on the connection
    raw_conn = conn.connection.dbapi_connection
    raw_conn.enable_load_extension(True)
    try:
        raw_conn.load_extension("mod_spatialite")
    except Exception:
        try:
            raw_conn.load_extension("mod_spatialite.so")
        except Exception as e:
            print(f"Warning: Could not load SpatiaLite: {e}")
    raw_conn.enable_load_extension(False)

    # Process each table that contains Messier objects
    for table_name in ['galaxies', 'nebulae', 'clusters']:
        print(f"Processing {table_name}...")

        # Get all Messier objects from this table that don't have constellation_id set
        result = conn.execute(text(f"""
            SELECT id, name, ra_hours, dec_degrees
            FROM {table_name}
            WHERE catalog = 'messier' AND constellation_id IS NULL
        """))

        objects = result.fetchall()
        print(f"  Found {len(objects)} Messier objects without constellation data")

        for obj_id, name, ra_hours, dec_degrees in objects:
            # Convert RA/Dec to radians for SpatiaLite point creation
            # SpatiaLite uses longitude/latitude (RA/Dec) in degrees
            ra_degrees = ra_hours * 15.0  # Convert hours to degrees

            # Find constellation using spatial query
            # Create a temporary point at (RA, Dec) and check which constellation polygon contains it
            const_result = conn.execute(text("""
                SELECT id, name
                FROM constellations
                WHERE ST_Within(
                    MakePoint(:ra_degrees, :dec_degrees, 0),
                    geometry
                ) = 1
                LIMIT 1
            """), {"ra_degrees": ra_degrees, "dec_degrees": dec_degrees})

            constellation = const_result.fetchone()

            if constellation:
                const_id, const_name = constellation

                # Update the object with constellation_id and constellation string
                conn.execute(text(f"""
                    UPDATE {table_name}
                    SET constellation_id = :const_id,
                        constellation = :const_name
                    WHERE id = :obj_id
                """), {"const_id": const_id, "const_name": const_name, "obj_id": obj_id})

                print(f"  Updated {name}: constellation={const_name}")
            else:
                # Handle polar cap objects (declination > 88.6639° or < -88.6639°)
                # These are outside constellation boundary polygons
                if dec_degrees > 88.0:
                    # Northern polar cap -> Ursa Minor (contains Polaris)
                    const_result = conn.execute(text("""
                        SELECT id, name
                        FROM constellations
                        WHERE name = 'Ursa Minor'
                        LIMIT 1
                    """))
                elif dec_degrees < -88.0:
                    # Southern polar cap -> Octans
                    const_result = conn.execute(text("""
                        SELECT id, name
                        FROM constellations
                        WHERE name = 'Octans'
                        LIMIT 1
                    """))
                else:
                    # Not in polar cap and not in any constellation polygon
                    # This shouldn't happen for Messier objects, log a warning
                    print(f"  Warning: {name} at ({ra_degrees:.2f}°, {dec_degrees:.2f}°) not in any constellation")
                    continue

                constellation = const_result.fetchone()
                if constellation:
                    const_id, const_name = constellation
                    conn.execute(text(f"""
                        UPDATE {table_name}
                        SET constellation_id = :const_id,
                            constellation = :const_name
                        WHERE id = :obj_id
                    """), {"const_id": const_id, "const_name": const_name, "obj_id": obj_id})

                    print(f"  Updated {name} (polar cap): constellation={const_name}")

        print(f"  Completed {table_name}")

    print("Migration complete!")


def downgrade() -> None:
    """Downgrade schema."""
    pass
