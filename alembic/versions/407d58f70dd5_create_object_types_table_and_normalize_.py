"""create_object_types_table_and_normalize_all_types

Revision ID: 407d58f70dd5
Revises: c92fca48be10
Create Date: 2025-12-26 12:47:46.697701

This migration creates a normalized object_types table and adds foreign key columns.
Data will be populated during import. Old VARCHAR columns kept temporarily for backwards compatibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '407d58f70dd5'
down_revision: Union[str, Sequence[str], None] = 'c92fca48be10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - creates table and adds ID columns, keeps VARCHAR columns."""
    conn = op.get_bind()
    
    # Handle offline mode/SQL generation
    if conn.engine.name == 'mock':
        # In offline mode, we just emit the CREATE TABLE and assume it works
        # This matches the previous behavior for offline mode
        op.create_table(
            'object_types',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('name', name='uq_object_types_name'),
            sa.Index('ix_object_types_category', 'category'),
            sa.Index('ix_object_types_name', 'name'),
        )
        
        # Add columns to tables
        op.add_column('objects', sa.Column('object_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_objects_object_type_id', 'objects', ['object_type_id'])
        op.create_foreign_key('fk_objects_object_type_id', 'objects', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('observations', sa.Column('object_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_observations_object_type_id', 'observations', ['object_type_id'])
        op.create_foreign_key('fk_observations_object_type_id', 'observations', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('favorites', sa.Column('object_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_favorites_object_type_id', 'favorites', ['object_type_id'])
        op.create_foreign_key('fk_favorites_object_type_id', 'favorites', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

        for table_name in ['stars', 'double_stars', 'galaxies', 'nebulae', 'clusters', 'planets', 'moons']:
            op.add_column(table_name, sa.Column('object_subtype_id', sa.Integer(), nullable=True))
            op.create_index(f'ix_{table_name}_object_subtype_id', table_name, ['object_subtype_id'])
            op.create_foreign_key(f'fk_{table_name}_object_subtype_id', table_name, 'object_types', ['object_subtype_id'], ['id'], ondelete='SET NULL')

        op.add_column('variable_stars', sa.Column('variable_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_variable_stars_variable_type_id', 'variable_stars', ['variable_type_id'])
        op.create_foreign_key('fk_variable_stars_variable_type_id', 'variable_stars', 'object_types', ['variable_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('asteroids', sa.Column('asteroid_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_asteroids_asteroid_type_id', 'asteroids', ['asteroid_type_id'])
        op.create_foreign_key('fk_asteroids_asteroid_type_id', 'asteroids', 'object_types', ['asteroid_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('eclipses', sa.Column('eclipse_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_eclipses_eclipse_type_id', 'eclipses', ['eclipse_type_id'])
        op.create_foreign_key('fk_eclipses_eclipse_type_id', 'eclipses', 'object_types', ['eclipse_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('space_events', sa.Column('event_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_space_events_event_type_id', 'space_events', ['event_type_id'])
        op.create_foreign_key('fk_space_events_event_type_id', 'space_events', 'object_types', ['event_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('ephemeris_files', sa.Column('file_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_ephemeris_files_file_type_id', 'ephemeris_files', ['file_type_id'])
        op.create_foreign_key('fk_ephemeris_files_file_type_id', 'ephemeris_files', 'object_types', ['file_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('cameras', sa.Column('camera_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_cameras_camera_type_id', 'cameras', ['camera_type_id'])
        op.create_foreign_key('fk_cameras_camera_type_id', 'cameras', 'object_types', ['camera_type_id'], ['id'], ondelete='SET NULL')

        op.add_column('filters', sa.Column('filter_type_id', sa.Integer(), nullable=True))
        op.create_index('ix_filters_filter_type_id', 'filters', ['filter_type_id'])
        op.create_foreign_key('fk_filters_filter_type_id', 'filters', 'object_types', ['filter_type_id'], ['id'], ondelete='SET NULL')
        return

    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Step 1: Create object_types table if it doesn't exist
    if 'object_types' not in tables:
        op.create_table(
            'object_types',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('name', name='uq_object_types_name'),
            sa.Index('ix_object_types_category', 'category'),
            sa.Index('ix_object_types_name', 'name'),
        )

    # Step 2: Add foreign key ID columns to all tables (nullable, VARCHAR columns remain)
    # Tables with object_type column - add object_type_id
    if 'objects' in tables:
        columns = [c['name'] for c in inspector.get_columns('objects')]
        if 'object_type_id' not in columns:
            op.add_column('objects', sa.Column('object_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_objects_object_type_id', 'objects', ['object_type_id'])
            op.create_foreign_key('fk_objects_object_type_id', 'objects', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

    if 'observations' in tables:
        columns = [c['name'] for c in inspector.get_columns('observations')]
        if 'object_type_id' not in columns:
            op.add_column('observations', sa.Column('object_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_observations_object_type_id', 'observations', ['object_type_id'])
            op.create_foreign_key('fk_observations_object_type_id', 'observations', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

    if 'favorites' in tables:
        columns = [c['name'] for c in inspector.get_columns('favorites')]
        if 'object_type_id' not in columns:
            op.add_column('favorites', sa.Column('object_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_favorites_object_type_id', 'favorites', ['object_type_id'])
            op.create_foreign_key('fk_favorites_object_type_id', 'favorites', 'object_types', ['object_type_id'], ['id'], ondelete='SET NULL')

    # Tables with object_subtype column - add object_subtype_id
    for table_name in ['stars', 'double_stars', 'galaxies', 'nebulae', 'clusters', 'planets', 'moons']:
        if table_name in tables:
            # Check if object_subtype column exists
            columns = [c['name'] for c in inspector.get_columns(table_name)]
            if 'object_subtype' in columns and 'object_subtype_id' not in columns:
                op.add_column(table_name, sa.Column('object_subtype_id', sa.Integer(), nullable=True))
                op.create_index(f'ix_{table_name}_object_subtype_id', table_name, ['object_subtype_id'])
                op.create_foreign_key(f'fk_{table_name}_object_subtype_id', table_name, 'object_types', ['object_subtype_id'], ['id'], ondelete='SET NULL')

    # Other type columns
    if 'variable_stars' in tables:
        columns = [c['name'] for c in inspector.get_columns('variable_stars')]
        if 'variable_type_id' not in columns:
            op.add_column('variable_stars', sa.Column('variable_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_variable_stars_variable_type_id', 'variable_stars', ['variable_type_id'])
            op.create_foreign_key('fk_variable_stars_variable_type_id', 'variable_stars', 'object_types', ['variable_type_id'], ['id'], ondelete='SET NULL')

    if 'asteroids' in tables:
        columns = [c['name'] for c in inspector.get_columns('asteroids')]
        if 'asteroid_type_id' not in columns:
            op.add_column('asteroids', sa.Column('asteroid_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_asteroids_asteroid_type_id', 'asteroids', ['asteroid_type_id'])
            op.create_foreign_key('fk_asteroids_asteroid_type_id', 'asteroids', 'object_types', ['asteroid_type_id'], ['id'], ondelete='SET NULL')

    if 'eclipses' in tables:
        columns = [c['name'] for c in inspector.get_columns('eclipses')]
        if 'eclipse_type_id' not in columns:
            op.add_column('eclipses', sa.Column('eclipse_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_eclipses_eclipse_type_id', 'eclipses', ['eclipse_type_id'])
            op.create_foreign_key('fk_eclipses_eclipse_type_id', 'eclipses', 'object_types', ['eclipse_type_id'], ['id'], ondelete='SET NULL')

    if 'space_events' in tables:
        columns = [c['name'] for c in inspector.get_columns('space_events')]
        if 'event_type_id' not in columns:
            op.add_column('space_events', sa.Column('event_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_space_events_event_type_id', 'space_events', ['event_type_id'])
            op.create_foreign_key('fk_space_events_event_type_id', 'space_events', 'object_types', ['event_type_id'], ['id'], ondelete='SET NULL')

    if 'ephemeris_files' in tables:
        columns = [c['name'] for c in inspector.get_columns('ephemeris_files')]
        if 'file_type_id' not in columns:
            op.add_column('ephemeris_files', sa.Column('file_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_ephemeris_files_file_type_id', 'ephemeris_files', ['file_type_id'])
            op.create_foreign_key('fk_ephemeris_files_file_type_id', 'ephemeris_files', 'object_types', ['file_type_id'], ['id'], ondelete='SET NULL')

    if 'cameras' in tables:
        columns = [c['name'] for c in inspector.get_columns('cameras')]
        if 'camera_type_id' not in columns:
            op.add_column('cameras', sa.Column('camera_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_cameras_camera_type_id', 'cameras', ['camera_type_id'])
            op.create_foreign_key('fk_cameras_camera_type_id', 'cameras', 'object_types', ['camera_type_id'], ['id'], ondelete='SET NULL')

    if 'filters' in tables:
        columns = [c['name'] for c in inspector.get_columns('filters')]
        if 'filter_type_id' not in columns:
            op.add_column('filters', sa.Column('filter_type_id', sa.Integer(), nullable=True))
            op.create_index('ix_filters_filter_type_id', 'filters', ['filter_type_id'])
            op.create_foreign_key('fk_filters_filter_type_id', 'filters', 'object_types', ['filter_type_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema - remove object_types table and foreign key columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Drop foreign key constraints and columns
    if 'objects' in tables:
        op.drop_constraint('fk_objects_object_type_id', 'objects', type_='foreignkey')
        op.drop_index('ix_objects_object_type_id', table_name='objects')
        op.drop_column('objects', 'object_type_id')

    if 'observations' in tables:
        op.drop_constraint('fk_observations_object_type_id', 'observations', type_='foreignkey')
        op.drop_index('ix_observations_object_type_id', table_name='observations')
        op.drop_column('observations', 'object_type_id')

    if 'favorites' in tables:
        op.drop_constraint('fk_favorites_object_type_id', 'favorites', type_='foreignkey')
        op.drop_index('ix_favorites_object_type_id', table_name='favorites')
        op.drop_column('favorites', 'object_type_id')

    for table_name in ['stars', 'double_stars', 'galaxies', 'nebulae', 'clusters', 'planets', 'moons']:
        if table_name in tables:
            try:
                op.drop_constraint(f'fk_{table_name}_object_subtype_id', table_name, type_='foreignkey')
                op.drop_index(f'ix_{table_name}_object_subtype_id', table_name=table_name)
                op.drop_column(table_name, 'object_subtype_id')
            except:
                pass  # Column may not exist if object_subtype wasn't present

    if 'variable_stars' in tables:
        op.drop_constraint('fk_variable_stars_variable_type_id', 'variable_stars', type_='foreignkey')
        op.drop_index('ix_variable_stars_variable_type_id', table_name='variable_stars')
        op.drop_column('variable_stars', 'variable_type_id')

    if 'asteroids' in tables:
        op.drop_constraint('fk_asteroids_asteroid_type_id', 'asteroids', type_='foreignkey')
        op.drop_index('ix_asteroids_asteroid_type_id', table_name='asteroids')
        op.drop_column('asteroids', 'asteroid_type_id')

    if 'eclipses' in tables:
        op.drop_constraint('fk_eclipses_eclipse_type_id', 'eclipses', type_='foreignkey')
        op.drop_index('ix_eclipses_eclipse_type_id', table_name='eclipses')
        op.drop_column('eclipses', 'eclipse_type_id')

    if 'space_events' in tables:
        op.drop_constraint('fk_space_events_event_type_id', 'space_events', type_='foreignkey')
        op.drop_index('ix_space_events_event_type_id', table_name='space_events')
        op.drop_column('space_events', 'event_type_id')

    if 'ephemeris_files' in tables:
        op.drop_constraint('fk_ephemeris_files_file_type_id', 'ephemeris_files', type_='foreignkey')
        op.drop_index('ix_ephemeris_files_file_type_id', table_name='ephemeris_files')
        op.drop_column('ephemeris_files', 'file_type_id')

    if 'cameras' in tables:
        op.drop_constraint('fk_cameras_camera_type_id', 'cameras', type_='foreignkey')
        op.drop_index('ix_cameras_camera_type_id', table_name='cameras')
        op.drop_column('cameras', 'camera_type_id')

    if 'filters' in tables:
        op.drop_constraint('fk_filters_filter_type_id', 'filters', type_='foreignkey')
        op.drop_index('ix_filters_filter_type_id', table_name='filters')
        op.drop_column('filters', 'filter_type_id')

    # Drop object_types table
    op.drop_table('object_types')