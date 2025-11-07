# SQLAlchemy Migration Plan

## Overview

This document outlines the plan to migrate the celestron-nexstar database from raw SQLite to SQLAlchemy ORM with Alembic migrations.

## Current Status: IN PROGRESS

### ✅ Completed

1. **Dependencies Installed**
   - SQLAlchemy 2.0.44
   - Alembic 1.17.1
   - Added to `pyproject.toml`

2. **SQLAlchemy Models Created**
   - File: `src/celestron_nexstar/api/models.py`
   - `Base` - Declarative base class
   - `CelestialObjectModel` - Main objects table
   - `MetadataModel` - Database metadata

3. **Alembic Initialized**
   - Config: `alembic.ini`
   - Environment: `alembic/env.py`
   - Auto-detects database location
   - Supports SQLite batch operations

4. **Initial Migration Created**
   - File: `alembic/versions/565d35ca5a03_initial_schema_with_fts5_support.py`
   - Detected all schema changes
   - NOTE: FTS5 tables need manual handling

### 🔨 Next Steps

1. **Add FTS5 Support to Migration**
   - FTS5 virtual tables are not handled by SQLAlchemy autogenerate
   - Need to add raw SQL for FTS5 creation
   - Add triggers to keep FTS in sync

2. **Create Database Refactoring Strategy**
   - Option A: Stamp existing DB and keep it (no migration needed)
   - Option B: Export data, recreate with SQLAlchemy, re-import
   - Option C: Gradual migration with both systems running

3. **Refactor `database.py`**
   - Replace raw SQL with SQLAlchemy ORM
   - Use sessions instead of raw connections
   - Keep existing API compatible

4. **Update Import Scripts**
   - Modify `data_import.py` to use SQLAlchemy models
   - Update migration script to use SQLAlchemy

5. **Testing**
   - Test migrations on copy of database
   - Verify all queries still work
   - Performance testing

6. **Documentation**
   - Migration guide for users
   - Schema change procedures
   - Rollback procedures

## Benefits of SQLAlchemy

### Type Safety
```python
# Before (raw SQL)
cursor.execute("SELECT * FROM objects WHERE id = ?", (object_id,))
row = cursor.fetchone()  # Returns dict/tuple, no type checking

# After (SQLAlchemy)
obj: CelestialObjectModel = session.get(CelestialObjectModel, object_id)
# IDE autocomplete, type checking, validation
```

### Migrations
```bash
# Create migration after model changes
alembic revision --autogenerate -m "Add new_field to objects"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Query Building
```python
# Before
cursor.execute("""
    SELECT * FROM objects
    WHERE magnitude <= ?
    AND object_type = ?
    ORDER BY magnitude
""", (mag_limit, obj_type))

# After
objects = session.query(CelestialObjectModel)
    .filter(CelestialObjectModel.magnitude <= mag_limit)
    .filter(CelestialObjectModel.object_type == obj_type)
    .order_by(CelestialObjectModel.magnitude)
    .all()
```

### Relationships (Future)
```python
# Can add relationships between tables
class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id"))
    object: Mapped[CelestialObjectModel] = relationship()
```

## Migration Strategies

### Strategy A: Stamp Existing Database (RECOMMENDED)

**Pros**:
- No data loss
- No downtime
- Existing database continues working

**Cons**:
- Existing schema must exactly match models
- May need to apply fixes manually

**Steps**:
1. Backup database
2. Add FTS5 support to initial migration
3. Mark migration as applied without running it:
   ```bash
   alembic stamp head
   ```
4. Refactor code to use SQLAlchemy
5. Future changes use migrations

### Strategy B: Fresh Migration

**Pros**:
- Clean schema
- Guaranteed match with models
- Good for finding schema issues

**Cons**:
- Need to export/import data
- More complex process

**Steps**:
1. Export all data from existing database
2. Drop existing database
3. Run migration to create new schema
4. Import data using SQLAlchemy models

### Strategy C: Parallel Systems

**Pros**:
- Can gradually migrate
- Test both systems

**Cons**:
- Complex
- Duplication
- Hard to maintain

## FTS5 Handling

FTS5 tables are SQLite-specific and won't be handled by SQLAlchemy autogenerate. Need to add manually:

```python
# In migration file
def upgrade():
    # ... SQLAlchemy operations ...

    # Create FTS5 virtual table
    op.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(
            name,
            common_name,
            description,
            content=objects,
            content_rowid=id
        )
    ''')

    # Create triggers
    op.execute('''
        CREATE TRIGGER IF NOT EXISTS objects_ai AFTER INSERT ON objects BEGIN
            INSERT INTO objects_fts(rowid, name, common_name, description)
            VALUES (new.id, new.name, new.common_name, new.description);
        END
    ''')

    # ... more triggers ...

def downgrade():
    op.execute('DROP TRIGGER IF EXISTS objects_ai')
    op.execute('DROP TABLE IF EXISTS objects_fts')
```

## Code Refactoring Example

### Before (database.py)
```python
class CatalogDatabase:
    def get_by_id(self, object_id: int) -> CelestialObject | None:
        if not self.conn:
            raise RuntimeError("Database not connected")

        cursor = self.conn.execute("SELECT * FROM objects WHERE id = ?", (object_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_object(row)
```

### After (database.py with SQLAlchemy)
```python
from sqlalchemy.orm import Session
from .models import CelestialObjectModel

class CatalogDatabase:
    def get_by_id(self, object_id: int) -> CelestialObject | None:
        with Session(self.engine) as session:
            model = session.get(CelestialObjectModel, object_id)

            if model is None:
                return None

            return self._model_to_object(model)
```

## Files Modified/Created

### Created
- ✅ `src/celestron_nexstar/api/models.py` - SQLAlchemy models
- ✅ `alembic/` - Migration framework
- ✅ `alembic.ini` - Alembic configuration
- ✅ `alembic/env.py` - Migration environment
- ✅ `alembic/versions/565d35ca5a03_*.py` - Initial migration

### To Modify
- ⏳ `src/celestron_nexstar/api/database.py` - Refactor to SQLAlchemy
- ⏳ `src/celestron_nexstar/cli/data_import.py` - Use SQLAlchemy models
- ⏳ `scripts/migrate_catalog_to_sqlite.py` - Use SQLAlchemy models

### To Create
- ⏳ Migration with FTS5 support
- ⏳ Database session management utilities
- ⏳ Migration documentation

## Testing Plan

1. **Backup Current Database**
   ```bash
   cp src/celestron_nexstar/cli/data/catalogs.db catalogs.db.backup
   ```

2. **Test Migration on Copy**
   ```bash
   cp catalogs.db.backup catalogs.db.test
   # Edit alembic.ini to point to test DB
   alembic upgrade head
   ```

3. **Verify Data Integrity**
   ```python
   # Compare row counts
   # Verify FTS5 search works
   # Check all indexes exist
   ```

4. **Performance Testing**
   ```python
   # Benchmark common queries
   # Compare SQLAlchemy vs raw SQL
   # Ensure no regression
   ```

## Rollback Plan

If migration fails:

1. **Restore Backup**
   ```bash
   cp catalogs.db.backup src/celestron_nexstar/cli/data/catalogs.db
   ```

2. **Revert Code Changes**
   ```bash
   git revert <commit>
   ```

3. **Remove Alembic**
   ```bash
   rm -rf alembic/
   rm alembic.ini
   # Remove from pyproject.toml
   ```

## Next Steps (Immediate)

1. **Complete FTS5 Migration**
   - Edit initial migration to include FTS5 tables
   - Add all triggers
   - Test migration on backup

2. **Stamp Existing Database**
   ```bash
   alembic stamp head
   ```

3. **Start Refactoring database.py**
   - Create session management
   - Refactor one method at a time
   - Keep tests passing

4. **Document Migration Process**
   - User-facing migration guide
   - Developer migration guide
   - Schema change procedures

## Questions to Resolve

1. **Migration Strategy**: Which strategy to use (A, B, or C)?
   - **Recommendation**: Strategy A (stamp existing)

2. **FTS5 Management**: How to handle FTS5 in SQLAlchemy?
   - **Solution**: Manual SQL in migrations

3. **Session Management**: Where to create/close sessions?
   - **Solution**: Context managers in database.py

4. **Backward Compatibility**: Keep old API?
   - **Solution**: Yes, refactor internals only

5. **Testing**: How to test migrations?
   - **Solution**: Copy database, test on copy

## Timeline Estimate

- **FTS5 Migration Update**: 1-2 hours
- **Database Refactoring**: 4-6 hours
- **Import Scripts Update**: 2-3 hours
- **Testing**: 2-3 hours
- **Documentation**: 1-2 hours
- **Total**: 10-16 hours

## Resources

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/en/latest/)
- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html)
- [Alembic Batch Operations](https://alembic.sqlalchemy.org/en/latest/batch.html)

---

*Status: Phase 1 Complete (Setup)*
*Next: Phase 2 (FTS5 Migration)*
*Updated: 2025-11-06*
