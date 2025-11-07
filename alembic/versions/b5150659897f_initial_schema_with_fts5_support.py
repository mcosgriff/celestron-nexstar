"""Initial schema with FTS5 support

Revision ID: b5150659897f
Revises:
Create Date: 2025-11-06 18:35:14.080829

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b5150659897f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial schema with FTS5 support."""
    # Create objects table
    op.create_table(
        "objects",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("catalog", sa.String(length=50), nullable=False),
        sa.Column("catalog_number", sa.Integer(), nullable=True),
        sa.Column("ra_hours", sa.Float(), nullable=False),
        sa.Column("dec_degrees", sa.Float(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("object_type", sa.String(length=50), nullable=False),
        sa.Column("size_arcmin", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("constellation", sa.String(length=50), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("ephemeris_name", sa.String(length=255), nullable=True),
        sa.Column("parent_planet", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_objects_name", "objects", ["name"])
    op.create_index("ix_objects_catalog", "objects", ["catalog"])
    op.create_index("ix_objects_magnitude", "objects", ["magnitude"])
    op.create_index("ix_objects_object_type", "objects", ["object_type"])
    op.create_index("ix_objects_constellation", "objects", ["constellation"])
    op.create_index("ix_objects_is_dynamic", "objects", ["is_dynamic"])
    op.create_index("idx_catalog_number", "objects", ["catalog", "catalog_number"])
    op.create_index("idx_type_magnitude", "objects", ["object_type", "magnitude"])

    # Create metadata table
    op.create_table(
        "metadata",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    # Create FTS5 virtual table for full-text search
    op.execute("""
        CREATE VIRTUAL TABLE objects_fts USING fts5(
            name,
            common_name,
            description,
            content=objects,
            content_rowid=id
        )
    """)

    # Create triggers to keep FTS in sync with objects table
    op.execute("""
        CREATE TRIGGER objects_ai AFTER INSERT ON objects BEGIN
            INSERT INTO objects_fts(rowid, name, common_name, description)
            VALUES (new.id, new.name, new.common_name, new.description);
        END
    """)

    op.execute("""
        CREATE TRIGGER objects_ad AFTER DELETE ON objects BEGIN
            DELETE FROM objects_fts WHERE rowid = old.id;
        END
    """)

    op.execute("""
        CREATE TRIGGER objects_au AFTER UPDATE ON objects BEGIN
            UPDATE objects_fts SET
                name = new.name,
                common_name = new.common_name,
                description = new.description
            WHERE rowid = new.id;
        END
    """)

    # Insert initial metadata
    op.execute("""
        INSERT INTO metadata (key, value) VALUES
            ('version', '1.0.0'),
            ('source', 'Fresh SQLAlchemy migration'),
            ('last_updated', datetime('now'))
    """)


def downgrade() -> None:
    """Drop all tables and triggers."""
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS objects_au")
    op.execute("DROP TRIGGER IF EXISTS objects_ad")
    op.execute("DROP TRIGGER IF EXISTS objects_ai")

    # Drop FTS5 table
    op.execute("DROP TABLE IF EXISTS objects_fts")

    # Drop tables
    op.drop_table("metadata")

    with op.batch_alter_table("objects", schema=None) as batch_op:
        batch_op.drop_index("idx_type_magnitude")
        batch_op.drop_index("idx_catalog_number")
        batch_op.drop_index("ix_objects_is_dynamic")
        batch_op.drop_index("ix_objects_constellation")
        batch_op.drop_index("ix_objects_object_type")
        batch_op.drop_index("ix_objects_magnitude")
        batch_op.drop_index("ix_objects_catalog")
        batch_op.drop_index("ix_objects_name")

    op.drop_table("objects")
