-- Add foreign key columns to stars table if they don't exist
-- Run this with: sqlite3 <path-to-database> < scripts/add_star_foreign_keys.sql

-- Enable foreign keys
PRAGMA foreign_keys=ON;

-- Check if columns exist and add them if missing
-- Note: SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN
-- So we need to check first or handle the error

-- Add constellation_id if it doesn't exist
-- (This will fail silently if the column already exists in some SQLite versions)
ALTER TABLE stars ADD COLUMN constellation_id INTEGER;

-- Add asterism_id if it doesn't exist
ALTER TABLE stars ADD COLUMN asterism_id INTEGER;

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_stars_constellation_id ON stars(constellation_id);
CREATE INDEX IF NOT EXISTS ix_stars_asterism_id ON stars(asterism_id);

-- Verify columns were added
.schema stars


