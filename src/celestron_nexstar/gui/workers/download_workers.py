"""
Download Worker Threads

QThread workers for async data downloads to prevent UI blocking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from PySide6.QtCore import QThread, Signal


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _backfill_spatial_relationships(
    *, session: Any, include_stars: bool, include_dsos: bool, include_double_stars: bool = False
) -> None:
    """Backfill constellation/asterism relationships using spatial queries.

    - DSOs (galaxies/nebulae/clusters) store POINT geometries.
    - Constellations store polygon/multipolygon geometries.
    - Asterisms store line geometries; we assign nearest within 2 degrees (best-effort).

    This is idempotent and only fills missing relationship columns / junction rows.
    """
    from sqlalchemy import text

    if include_dsos:
        # Constellation containment (POINT-in-POLYGON)
        # Use set-based CTEs to avoid SQLite correlated UPDATE quirks.
        session.execute(
            text(
                """
                WITH matches AS (
                    SELECT
                        g.id AS obj_id,
                        c.id AS const_id,
                        ROW_NUMBER() OVER (PARTITION BY g.id ORDER BY c.id) AS rn
                    FROM galaxies g
                    JOIN constellations c
                      ON c.geometry IS NOT NULL
                     AND g.geometry IS NOT NULL
                     AND ST_Contains(c.geometry, g.geometry)
                    WHERE g.constellation_id IS NULL
                )
                UPDATE galaxies
                SET constellation_id = (
                    SELECT const_id FROM matches
                    WHERE matches.obj_id = galaxies.id AND matches.rn = 1
                )
                WHERE constellation_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM matches
                    WHERE matches.obj_id = galaxies.id AND matches.rn = 1
                  )
                """
            )
        )
        session.execute(
            text(
                """
                WITH matches AS (
                    SELECT
                        n.id AS obj_id,
                        c.id AS const_id,
                        ROW_NUMBER() OVER (PARTITION BY n.id ORDER BY c.id) AS rn
                    FROM nebulae n
                    JOIN constellations c
                      ON c.geometry IS NOT NULL
                     AND n.geometry IS NOT NULL
                     AND ST_Contains(c.geometry, n.geometry)
                    WHERE n.constellation_id IS NULL
                )
                UPDATE nebulae
                SET constellation_id = (
                    SELECT const_id FROM matches
                    WHERE matches.obj_id = nebulae.id AND matches.rn = 1
                )
                WHERE constellation_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM matches
                    WHERE matches.obj_id = nebulae.id AND matches.rn = 1
                  )
                """
            )
        )
        session.execute(
            text(
                """
                WITH matches AS (
                    SELECT
                        cl.id AS obj_id,
                        c.id AS const_id,
                        ROW_NUMBER() OVER (PARTITION BY cl.id ORDER BY c.id) AS rn
                    FROM clusters cl
                    JOIN constellations c
                      ON c.geometry IS NOT NULL
                     AND cl.geometry IS NOT NULL
                     AND ST_Contains(c.geometry, cl.geometry)
                    WHERE cl.constellation_id IS NULL
                )
                UPDATE clusters
                SET constellation_id = (
                    SELECT const_id FROM matches
                    WHERE matches.obj_id = clusters.id AND matches.rn = 1
                )
                WHERE constellation_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM matches
                    WHERE matches.obj_id = clusters.id AND matches.rn = 1
                  )
                """
            )
        )

        # Asterism proximity (POINT-to-LINE distance)
        session.execute(
            text(
                """
                WITH nearest AS (
                    SELECT
                        g.id AS obj_id,
                        a.id AS ast_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY g.id
                            ORDER BY ST_Distance(a.geometry, g.geometry)
                        ) AS rn
                    FROM galaxies g
                    JOIN asterisms a
                      ON a.geometry IS NOT NULL
                     AND g.geometry IS NOT NULL
                     AND ST_Distance(a.geometry, g.geometry) <= 2.0
                    WHERE g.asterism_id IS NULL
                )
                UPDATE galaxies
                SET asterism_id = (
                    SELECT ast_id FROM nearest
                    WHERE nearest.obj_id = galaxies.id AND nearest.rn = 1
                )
                WHERE asterism_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM nearest
                    WHERE nearest.obj_id = galaxies.id AND nearest.rn = 1
                  )
                """
            )
        )
        session.execute(
            text(
                """
                WITH nearest AS (
                    SELECT
                        n.id AS obj_id,
                        a.id AS ast_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY n.id
                            ORDER BY ST_Distance(a.geometry, n.geometry)
                        ) AS rn
                    FROM nebulae n
                    JOIN asterisms a
                      ON a.geometry IS NOT NULL
                     AND n.geometry IS NOT NULL
                     AND ST_Distance(a.geometry, n.geometry) <= 2.0
                    WHERE n.asterism_id IS NULL
                )
                UPDATE nebulae
                SET asterism_id = (
                    SELECT ast_id FROM nearest
                    WHERE nearest.obj_id = nebulae.id AND nearest.rn = 1
                )
                WHERE asterism_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM nearest
                    WHERE nearest.obj_id = nebulae.id AND nearest.rn = 1
                  )
                """
            )
        )
        session.execute(
            text(
                """
                WITH nearest AS (
                    SELECT
                        cl.id AS obj_id,
                        a.id AS ast_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY cl.id
                            ORDER BY ST_Distance(a.geometry, cl.geometry)
                        ) AS rn
                    FROM clusters cl
                    JOIN asterisms a
                      ON a.geometry IS NOT NULL
                     AND cl.geometry IS NOT NULL
                     AND ST_Distance(a.geometry, cl.geometry) <= 2.0
                    WHERE cl.asterism_id IS NULL
                )
                UPDATE clusters
                SET asterism_id = (
                    SELECT ast_id FROM nearest
                    WHERE nearest.obj_id = clusters.id AND nearest.rn = 1
                )
                WHERE asterism_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM nearest
                    WHERE nearest.obj_id = clusters.id AND nearest.rn = 1
                  )
                """
            )
        )

    if include_double_stars:
        # Some user databases may not yet have the required columns, and in-memory DB setups
        # can be sensitive to which underlying connection is used. Introspect using PRAGMA
        # via the same session/connection we will execute the UPDATEs on.
        try:
            from sqlalchemy import text

            conn = session.connection()
            pragma_rows = conn.execute(text("PRAGMA table_info('double_stars')")).fetchall()
            columns = {row[1] for row in pragma_rows}  # row[1] == column name
            required_cols = {"geometry", "constellation_id", "asterism_id"}
            if not required_cols.issubset(columns):
                logger.warning(
                    "Skipping double star spatial mapping: missing required columns on double_stars "
                    f"(need {sorted(required_cols)}; have {sorted(columns)}). "
                    "Please run database migrations and restart if using an in-memory DB."
                )
                return
        except Exception as e:
            logger.warning(f"Could not inspect double_stars columns; skipping double star spatial mapping: {e}")
            return

        # Use set-based CTEs with window functions to avoid SQLite quirks around
        # qualifying columns in UPDATE statements.
        session.execute(
            text(
                """
                WITH matches AS (
                    SELECT
                        d.id AS ds_id,
                        c.id AS const_id,
                        ROW_NUMBER() OVER (PARTITION BY d.id ORDER BY c.id) AS rn
                    FROM double_stars d
                    JOIN constellations c
                      ON c.geometry IS NOT NULL
                     AND d.geometry IS NOT NULL
                     AND ST_Contains(c.geometry, d.geometry)
                    WHERE d.catalog = 'wds'
                      AND d.constellation_id IS NULL
                )
                UPDATE double_stars
                SET constellation_id = (
                    SELECT const_id FROM matches
                    WHERE matches.ds_id = double_stars.id AND matches.rn = 1
                )
                WHERE catalog = 'wds'
                  AND constellation_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM matches
                    WHERE matches.ds_id = double_stars.id AND matches.rn = 1
                  )
                """
            )
        )

        session.execute(
            text(
                """
                WITH nearest AS (
                    SELECT
                        d.id AS ds_id,
                        a.id AS ast_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY d.id
                            ORDER BY ST_Distance(a.geometry, d.geometry)
                        ) AS rn
                    FROM double_stars d
                    JOIN asterisms a
                      ON a.geometry IS NOT NULL
                     AND d.geometry IS NOT NULL
                     AND ST_Distance(a.geometry, d.geometry) <= 2.0
                    WHERE d.catalog = 'wds'
                      AND d.asterism_id IS NULL
                )
                UPDATE double_stars
                SET asterism_id = (
                    SELECT ast_id FROM nearest
                    WHERE nearest.ds_id = double_stars.id AND nearest.rn = 1
                )
                WHERE catalog = 'wds'
                  AND asterism_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM nearest
                    WHERE nearest.ds_id = double_stars.id AND nearest.rn = 1
                  )
                """
            )
        )

    if include_stars:
        # Populate star constellation_id / asterism_id using the same spatial logic as DSOs.
        session.execute(
            text(
                """
                WITH matches AS (
                    SELECT
                        s.id AS obj_id,
                        c.id AS const_id,
                        ROW_NUMBER() OVER (PARTITION BY s.id ORDER BY c.id) AS rn
                    FROM stars s
                    JOIN constellations c
                      ON c.geometry IS NOT NULL
                     AND s.geometry IS NOT NULL
                     AND ST_Contains(c.geometry, s.geometry)
                    WHERE s.constellation_id IS NULL
                )
                UPDATE stars
                SET constellation_id = (
                    SELECT const_id FROM matches
                    WHERE matches.obj_id = stars.id AND matches.rn = 1
                )
                WHERE constellation_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM matches
                    WHERE matches.obj_id = stars.id AND matches.rn = 1
                  )
                """
            )
        )
        session.execute(
            text(
                """
                WITH nearest AS (
                    SELECT
                        s.id AS obj_id,
                        a.id AS ast_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY s.id
                            ORDER BY ST_Distance(a.geometry, s.geometry)
                        ) AS rn
                    FROM stars s
                    JOIN asterisms a
                      ON a.geometry IS NOT NULL
                     AND s.geometry IS NOT NULL
                     AND ST_Distance(a.geometry, s.geometry) <= 2.0
                    WHERE s.asterism_id IS NULL
                )
                UPDATE stars
                SET asterism_id = (
                    SELECT ast_id FROM nearest
                    WHERE nearest.obj_id = stars.id AND nearest.rn = 1
                )
                WHERE asterism_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM nearest
                    WHERE nearest.obj_id = stars.id AND nearest.rn = 1
                  )
                """
            )
        )

        # Backfill junction tables from the FK columns (idempotent via OR IGNORE).
        session.execute(
            text(
                """
                INSERT OR IGNORE INTO star_constellation (star_id, constellation_id)
                SELECT id, constellation_id FROM stars
                WHERE constellation_id IS NOT NULL
                """
            )
        )
        session.execute(
            text(
                """
                INSERT OR IGNORE INTO star_asterism (star_id, asterism_id)
                SELECT id, asterism_id FROM stars
                WHERE asterism_id IS NOT NULL
                """
            )
        )


class DownloadEphemerisFileThread(QThread):
    """Worker thread to download an ephemeris file."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    download_complete = Signal(str, bool, str)  # type: ignore[type-arg,misc]  # Emits (file_key, success, message)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (file_key, error_message)

    def __init__(self, file_key: str, force: bool = False) -> None:
        """Initialize the download thread."""
        super().__init__()
        self.file_key = file_key
        self.force = force

    def run(self) -> None:
        """Download ephemeris file in background thread."""
        try:
            from celestron_nexstar.api.ephemeris.ephemeris_manager import EPHEMERIS_FILES, download_file

            if self.file_key not in EPHEMERIS_FILES:
                self.error_occurred.emit(self.file_key, f"Unknown ephemeris file: {self.file_key}")
                return

            info = EPHEMERIS_FILES[self.file_key]
            self.progress_updated.emit(f"Downloading {info.display_name}...", 0, 100)

            # Download the file (this is synchronous but runs in background thread)
            # Note: Skyfield's download doesn't provide progress callbacks,
            # so we show 50% progress while downloading to indicate activity
            self.progress_updated.emit(f"Downloading {info.display_name}...", 50, 100)
            file_path = download_file(self.file_key, force=self.force)

            size_mb = file_path.stat().st_size / (1024 * 1024)
            self.progress_updated.emit(f"Downloaded {info.display_name}", 100, 100)
            self.download_complete.emit(self.file_key, True, f"Downloaded {info.display_name} ({size_mb:.1f} MB)")
        except Exception as e:
            logger.error(f"Error downloading ephemeris file {self.file_key}: {e}", exc_info=True)
            self.error_occurred.emit(self.file_key, str(e))
            self.download_complete.emit(self.file_key, False, str(e))


class DownloadEphemerisSetThread(QThread):
    """Worker thread to download an ephemeris file set."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    download_complete = Signal(str, bool, str)  # type: ignore[type-arg,misc]  # Emits (set_name, success, message)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (set_name, error_message)

    def __init__(self, set_name: str, force: bool = False) -> None:
        """Initialize the download thread."""
        super().__init__()
        self.set_name = set_name
        self.force = force

    def run(self) -> None:
        """Download ephemeris set in background thread."""
        try:
            from celestron_nexstar.api.ephemeris.ephemeris_manager import (
                EPHEMERIS_SETS,
                download_set,
                get_set_info,
            )

            if self.set_name not in EPHEMERIS_SETS:
                self.error_occurred.emit(self.set_name, f"Unknown ephemeris set: {self.set_name}")
                return

            set_info = get_set_info(self.set_name)
            file_count = set_info["file_count"]
            self.progress_updated.emit(f"Downloading {self.set_name} set ({file_count} files)...", 0, file_count)

            # Download the set
            set_name = cast(Literal["recommended", "minimal", "standard", "complete", "full"], self.set_name)
            downloaded = download_set(set_name, force=self.force)

            self.progress_updated.emit(f"Downloaded {self.set_name} set", file_count, file_count)
            total_size = sum(p.stat().st_size for p in downloaded) / (1024 * 1024)
            self.download_complete.emit(
                self.set_name, True, f"Downloaded {len(downloaded)} files ({total_size:.1f} MB total)"
            )
        except Exception as e:
            logger.error(f"Error downloading ephemeris set {self.set_name}: {e}", exc_info=True)
            self.error_occurred.emit(self.set_name, str(e))
            self.download_complete.emit(self.set_name, False, str(e))


class DownloadCelestialDataThread(QThread):
    """Worker thread to download celestial data."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    download_complete = Signal(str, bool, str)  # type: ignore[type-arg,misc]  # Emits (source_id, success, message)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (source_id, error_message)

    def __init__(self, source_id: str, force: bool = False) -> None:
        """Initialize the download thread."""
        super().__init__()
        self.source_id = source_id
        self.force = force

    def run(self) -> None:
        """Download celestial data in background thread."""
        try:
            from celestron_nexstar.cli.data_import import DATA_SOURCES, download_celestial_data, get_cache_dir

            if self.source_id not in DATA_SOURCES:
                self.error_occurred.emit(self.source_id, f"Unknown data source: {self.source_id}")
                return

            source = DATA_SOURCES[self.source_id]

            # Map source IDs to filenames
            filename_map = {
                "celestial_stars_6": "stars.6.min.geojson",
                "celestial_stars_8": "stars.8.min.geojson",
                "celestial_stars_14": "stars.14.min.geojson",
                "celestial_dsos_6": "dsos.6.min.geojson",
                "celestial_dsos_14": "dsos.14.min.geojson",
                "celestial_dsos_20": "dsos.20.min.geojson",
                "celestial_dsos_bright": "dsos.bright.min.geojson",
                "celestial_messier": "messier.min.geojson",
                "celestial_asterisms": "asterisms.min.geojson",
                "celestial_constellations": "constellations.min.geojson",
                "celestial_local_group": "lg.min.geojson",
            }

            filename = filename_map.get(self.source_id)
            if not filename:
                self.error_occurred.emit(self.source_id, f"No download available for {self.source_id}")
                return

            cache_dir = get_cache_dir()
            cache_path = cache_dir / filename

            # Check if we need to download the main file
            need_main_download = not cache_path.exists() or self.force

            if need_main_download:
                if self.force and cache_path.exists():
                    cache_path.unlink()

                self.progress_updated.emit(f"Downloading {source.name}...", 0, 100)

                # Download the file
                success = download_celestial_data(filename, cache_path)
            else:
                # File already exists and not forcing re-download
                success = True
                size_mb = cache_path.stat().st_size / (1024 * 1024)
                self.progress_updated.emit(f"Already downloaded ({size_mb:.1f} MB)", 0, 100)

            # If downloading star data, also download starnames.csv
            if success and "star" in self.source_id.lower() and "dso" not in self.source_id.lower():
                starnames_path = cache_dir / "starnames.csv"
                need_starnames = not starnames_path.exists() or self.force
                if need_starnames:
                    if self.force and starnames_path.exists():
                        starnames_path.unlink()
                    self.progress_updated.emit("Downloading starnames.csv...", 50, 100)
                    download_celestial_data("starnames.csv", starnames_path)

            # If downloading DSO data, also download dsonames.csv
            if success and "dso" in self.source_id.lower():
                dsonames_path = cache_dir / "dsonames.csv"
                need_dsonames = not dsonames_path.exists() or self.force
                if need_dsonames:
                    if self.force and dsonames_path.exists():
                        dsonames_path.unlink()
                    self.progress_updated.emit("Downloading dsonames.csv...", 50, 100)
                    download_celestial_data("dsonames.csv", dsonames_path)

            # If downloading constellations, also download bounds file (REQUIRED)
            # Always check for bounds file, even if main file already exists
            if success and self.source_id == "celestial_constellations":
                bounds_path = cache_dir / "constellations.bounds.min.geojson"
                need_bounds = not bounds_path.exists() or self.force
                if need_bounds:
                    if self.force and bounds_path.exists():
                        bounds_path.unlink()
                    self.progress_updated.emit("Downloading constellation bounds...", 50, 100)
                    bounds_success = download_celestial_data("constellations.bounds.min.geojson", bounds_path)
                    if not bounds_success:
                        error_msg = "Failed to download constellation bounds file. This file is required for accurate spatial queries."
                        self.error_occurred.emit(self.source_id, error_msg)
                        self.download_complete.emit(self.source_id, False, error_msg)
                        return
                    if not bounds_path.exists():
                        error_msg = "Constellation bounds file was not downloaded. This file is required for accurate spatial queries."
                        self.error_occurred.emit(self.source_id, error_msg)
                        self.download_complete.emit(self.source_id, False, error_msg)
                        return

            if success:
                size_mb = cache_path.stat().st_size / (1024 * 1024)
                self.progress_updated.emit(f"Downloaded {source.name}", 100, 100)
                self.download_complete.emit(self.source_id, True, f"Downloaded {source.name} ({size_mb:.1f} MB)")
            else:
                self.error_occurred.emit(self.source_id, "Download failed")
                self.download_complete.emit(self.source_id, False, "Download failed")
        except Exception as e:
            logger.error(f"Error downloading celestial data {self.source_id}: {e}", exc_info=True)
            self.error_occurred.emit(self.source_id, str(e))
            self.download_complete.emit(self.source_id, False, str(e))


class DownloadWDSCatalogThread(QThread):
    """Worker thread to download WDS catalog."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    download_complete = Signal(bool, str)  # type: ignore[type-arg,misc]  # Emits (success, message)
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits (error_message)

    def __init__(self, force: bool = False) -> None:
        """Initialize the download thread."""
        super().__init__()
        self.force = force

    def run(self) -> None:
        """Download WDS catalog in background thread."""
        try:
            from celestron_nexstar.cli.data_import import download_wds_catalog, get_cache_dir

            cache_dir = get_cache_dir()
            cache_path = cache_dir / "wdsweb_summ2.txt"

            if cache_path.exists() and not self.force:
                size_mb = cache_path.stat().st_size / (1024 * 1024)
                self.download_complete.emit(True, f"Already downloaded ({size_mb:.1f} MB)")
                return

            if self.force and cache_path.exists():
                cache_path.unlink()

            self.progress_updated.emit("Downloading WDS catalog...", 0, 100)

            # Download the file (this will output to console, but that's okay)
            # We'll emit progress updates
            self.progress_updated.emit("Connecting to server...", 10, 100)
            success = download_wds_catalog(cache_path)
            self.progress_updated.emit("Processing download...", 90, 100)

            if success:
                size_mb = cache_path.stat().st_size / (1024 * 1024)
                self.progress_updated.emit("Downloaded WDS catalog", 100, 100)
                self.download_complete.emit(True, f"Downloaded WDS catalog ({size_mb:.1f} MB)")
            else:
                self.error_occurred.emit("Download failed - all URLs failed")
                self.download_complete.emit(False, "Download failed")
        except Exception as e:
            logger.error(f"Error downloading WDS catalog: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.download_complete.emit(False, str(e))


class ImportWDSCatalogThread(QThread):
    """Worker thread to import WDS catalog into database."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    status_message = Signal(str)  # type: ignore[type-arg,misc]  # Emits status messages (e.g., "Loading existing...", "Found X existing...")
    import_complete = Signal(bool, str, int, int)  # type: ignore[type-arg,misc]  # Emits (success, message, imported, skipped)
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits (error_message)

    def __init__(self, mag_limit: float = 15.0) -> None:
        """Initialize the import thread."""
        super().__init__()
        self.mag_limit = mag_limit

    def run(self) -> None:
        """Import WDS catalog in background thread."""
        try:
            from celestron_nexstar.api.database.models import get_db_session
            from celestron_nexstar.cli.data_import import get_cache_dir, import_wds_catalog

            cache_dir = get_cache_dir()
            cache_path = cache_dir / "wdsweb_summ2.txt"

            if not cache_path.exists():
                self.error_occurred.emit("WDS catalog file not found. Please download it first.")
                self.import_complete.emit(False, "File not found", 0, 0)
                return

            self.progress_updated.emit("Importing WDS catalog...", 0, 100)

            # Create progress callback to emit progress updates
            def progress_callback(status: str, current: int, total: int) -> None:
                # Convert to percentage (0-100) for GUI progress bar
                percent = int(current / total * 100) if total > 0 else 0
                self.progress_updated.emit(status, percent, 100)

            # Create status callback to emit status messages (for toast notifications)
            def status_callback(message: str) -> None:
                self.status_message.emit(message)

            # Import with progress and status callbacks
            imported, skipped = import_wds_catalog(
                cache_path,
                mag_limit=self.mag_limit,
                verbose=False,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )

            # Post-import mapping: assign constellation_id / asterism_id for WDS double stars
            try:
                self.progress_updated.emit("Mapping WDS objects to constellations/asterisms...", 98, 100)
                with get_db_session() as session:
                    _backfill_spatial_relationships(
                        session=session, include_stars=False, include_dsos=False, include_double_stars=True
                    )
                    session.commit()
            except Exception as e:
                # Add extra diagnostics to help debug mismatched DB schema (file vs in-memory).
                try:
                    from sqlalchemy import text

                    conn = session.connection()
                    cols = conn.execute(text("PRAGMA table_info('double_stars')")).fetchall()
                    col_names = [row[1] for row in cols]
                    logger.warning(
                        "WDS post-import mapping failed: %s (engine=%s, double_stars cols=%s)",
                        e,
                        str(conn.engine.url),
                        col_names,
                        exc_info=True,
                    )
                except Exception:
                    logger.warning(f"WDS post-import mapping failed: {e}", exc_info=True)

            self.progress_updated.emit("Import complete", 100, 100)
            self.import_complete.emit(True, f"Imported {imported:,} objects, skipped {skipped:,}", imported, skipped)
        except Exception as e:
            logger.error(f"Error importing WDS catalog: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.import_complete.emit(False, str(e), 0, 0)


class ImportCelestialDataThread(QThread):
    """Worker thread to import celestial data into database."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    status_message = Signal(str)  # type: ignore[type-arg,misc]  # Emits status messages (e.g., "Loading existing...", "Found X existing...")
    import_complete = Signal(str, bool, str, int, int)  # type: ignore[type-arg,misc]  # Emits (source_id, success, message, imported, skipped)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (source_id, error_message)

    def __init__(self, source_id: str, mag_limit: float = 15.0) -> None:
        """Initialize the import thread."""
        super().__init__()
        self.source_id = source_id
        self.mag_limit = mag_limit

    def run(self) -> None:
        """Import celestial data in background thread."""
        try:
            from celestron_nexstar.cli.data_import import DATA_SOURCES, get_cache_dir

            if self.source_id not in DATA_SOURCES:
                self.error_occurred.emit(self.source_id, f"Unknown data source: {self.source_id}")
                self.import_complete.emit(self.source_id, False, "Unknown source", 0, 0)
                return

            source = DATA_SOURCES[self.source_id]

            # Map source IDs to filenames
            filename_map = {
                "celestial_stars_6": "stars.6.min.geojson",
                "celestial_stars_8": "stars.8.min.geojson",
                "celestial_stars_14": "stars.14.min.geojson",
                "celestial_dsos_6": "dsos.6.min.geojson",
                "celestial_dsos_14": "dsos.14.min.geojson",
                "celestial_dsos_20": "dsos.20.min.geojson",
                "celestial_dsos_bright": "dsos.bright.min.geojson",
                "celestial_messier": "messier.min.geojson",
                "celestial_asterisms": "asterisms.min.geojson",
                "celestial_constellations": "constellations.min.geojson",
                "celestial_local_group": "lg.min.geojson",
            }

            filename = filename_map.get(self.source_id)
            if not filename:
                self.error_occurred.emit(self.source_id, f"No import available for {self.source_id}")
                self.import_complete.emit(self.source_id, False, "No import available", 0, 0)
                return

            cache_dir = get_cache_dir()
            cache_path = cache_dir / filename

            if not cache_path.exists():
                self.error_occurred.emit(self.source_id, "File not found. Please download it first.")
                self.import_complete.emit(self.source_id, False, "File not found", 0, 0)
                return

            # For constellations, check if bounds file exists (REQUIRED)
            if self.source_id == "celestial_constellations":
                bounds_path = cache_dir / "constellations.bounds.min.geojson"
                if not bounds_path.exists():
                    error_msg = "Constellation bounds file not found. Please download constellations data first to get the bounds file."
                    logger.error(error_msg)
                    self.error_occurred.emit(self.source_id, error_msg)
                    self.import_complete.emit(self.source_id, False, error_msg, 0, 0)
                    return

            self.progress_updated.emit(f"Importing {source.name}...", 0, 100)

            # Create progress callback to emit progress updates
            def progress_callback(status: str, current: int, total: int) -> None:
                # Convert to percentage (0-100) for GUI progress bar
                percent = int(current / total * 100) if total > 0 else 0
                self.progress_updated.emit(status, percent, 100)

            # Create status callback to emit status messages (for toast notifications)
            def status_callback(message: str) -> None:
                self.status_message.emit(message)

            # Import the data (requires bounds file for constellations)
            # For DSO and star imports, we need to pass the progress callback
            try:
                if self.source_id.startswith("celestial_dsos"):
                    # Import DSOs with progress and status callbacks
                    from celestron_nexstar.cli.data_import import import_celestial_dsos

                    imported, skipped = import_celestial_dsos(
                        cache_path,
                        self.mag_limit,
                        verbose=False,
                        progress_callback=progress_callback,
                        status_callback=status_callback,
                    )
                elif self.source_id.startswith("celestial_stars"):
                    # Import stars with progress and status callbacks
                    from celestron_nexstar.cli.data_import import import_celestial_stars

                    imported, skipped = import_celestial_stars(
                        cache_path,
                        self.mag_limit,
                        verbose=False,
                        progress_callback=progress_callback,
                        status_callback=status_callback,
                    )
                elif self.source_id == "celestial_messier":
                    # Import Messier objects with progress and status callbacks
                    from celestron_nexstar.cli.data_import import import_celestial_messier

                    imported, skipped = import_celestial_messier(
                        cache_path,
                        self.mag_limit,
                        verbose=False,
                        progress_callback=progress_callback,
                        status_callback=status_callback,
                    )
                else:
                    # For other imports, use the standard importer (no progress callback yet)
                    imported, skipped = source.importer(cache_path, self.mag_limit, False)
            except FileNotFoundError as e:
                # Bounds file or other required file not found
                error_msg = str(e)
                logger.error(f"File not found during import: {error_msg}")
                self.error_occurred.emit(self.source_id, error_msg)
                self.import_complete.emit(self.source_id, False, error_msg, 0, 0)
                return
            except Exception as e:
                # Other import errors (InvalidCatalogFormatError, RuntimeError, etc.)
                error_msg = str(e)
                logger.error(f"Import error: {error_msg}")
                self.error_occurred.emit(self.source_id, error_msg)
                self.import_complete.emit(self.source_id, False, error_msg, 0, 0)
                return

            # Post-import decoration for constellations/asterisms happens on import button click,
            # not on the "Sync ..." relationship buttons.
            if self.source_id in {"celestial_constellations", "celestial_asterisms"}:
                try:
                    from celestron_nexstar.api.database.database_seeder import decorate_constellations, seed_asterisms
                    from celestron_nexstar.api.database.models import get_db_session

                    self.progress_updated.emit("Decorating imported data...", 95, 100)
                    with get_db_session() as session:
                        if self.source_id == "celestial_constellations":
                            decorate_constellations(session, force=False)
                        else:
                            seed_asterisms(session, force=False)
                except Exception as e:
                    # Decoration is best-effort; import itself succeeded, so keep going.
                    logger.warning(f"Post-import decoration failed for {self.source_id}: {e}", exc_info=True)

            # Post-import constellation/asterism mapping should happen when data is imported.
            # This backfills spatial relationships for newly-imported rows and is safe to rerun.
            try:
                from celestron_nexstar.api.database.models import get_db_session

                should_backfill = (
                    self.source_id
                    in {"celestial_constellations", "celestial_asterisms", "celestial_messier", "celestial_local_group"}
                    or self.source_id.startswith("celestial_stars")
                    or self.source_id.startswith("celestial_dsos")
                )
                if should_backfill:
                    self.progress_updated.emit("Mapping objects to constellations/asterisms...", 97, 100)
                    with get_db_session() as session:
                        _backfill_spatial_relationships(
                            session=session,
                            include_stars=(
                                self.source_id in {"celestial_constellations", "celestial_asterisms"}
                                or self.source_id.startswith("celestial_stars")
                            ),
                            include_dsos=True,
                        )
                        session.commit()
            except Exception as e:
                logger.warning(f"Post-import relationship mapping failed for {self.source_id}: {e}", exc_info=True)

            self.progress_updated.emit("Import complete", 100, 100)
            self.import_complete.emit(
                self.source_id,
                True,
                f"Imported {imported:,} objects, skipped {skipped:,}",
                imported,
                skipped,
            )
        except Exception as e:
            logger.error(f"Error importing celestial data {self.source_id}: {e}", exc_info=True)
            self.error_occurred.emit(self.source_id, str(e))
            self.import_complete.emit(self.source_id, False, str(e), 0, 0)


class ImportCustomYAMLThread(QThread):
    """Worker thread to import custom YAML catalog into database."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    import_complete = Signal(bool, str, int, int)  # type: ignore[type-arg,misc]  # Emits (success, message, imported, skipped)
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits (error_message)

    def __init__(self, mag_limit: float = 99.0) -> None:
        """Initialize the import thread."""
        super().__init__()
        self.mag_limit = mag_limit

    def run(self) -> None:
        """Import custom YAML catalog in background thread."""
        try:
            from celestron_nexstar.cli.data_import import import_custom_yaml

            module_path = Path(__file__).parent.parent.parent.parent / "cli" / "data"
            yaml_path = module_path / "catalogs.yaml"

            if not yaml_path.exists():
                self.error_occurred.emit("catalogs.yaml file not found. Please create it first.")
                self.import_complete.emit(False, "File not found", 0, 0)
                return

            self.progress_updated.emit("Importing custom YAML catalog...", 0, 100)

            # Import the catalog
            imported, skipped = import_custom_yaml(yaml_path, mag_limit=self.mag_limit, verbose=False)

            self.progress_updated.emit("Import complete", 100, 100)
            self.import_complete.emit(True, f"Imported {imported:,} objects, skipped {skipped:,}", imported, skipped)
        except Exception as e:
            logger.error(f"Error importing custom YAML catalog: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.import_complete.emit(False, str(e), 0, 0)


class SyncEphemerisThread(QThread):
    """Worker thread to sync ephemeris metadata to database."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    sync_complete = Signal(bool, str)  # type: ignore[type-arg,misc]  # Emits (success, message)
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits (error_message)

    def __init__(self, force: bool = False) -> None:
        """Initialize the sync thread."""
        super().__init__()
        self.force = force

    def run(self) -> None:
        """Sync ephemeris metadata in background thread."""
        try:
            from celestron_nexstar.api.database.database import sync_ephemeris_files_from_naif

            self.progress_updated.emit("Syncing ephemeris metadata from NAIF...", 0, 100)
            self.progress_updated.emit("Fetching ephemeris file information...", 25, 100)

            # Sync ephemeris files metadata to database (synchronous function)
            count = sync_ephemeris_files_from_naif(force=self.force)

            self.progress_updated.emit("Updating database...", 75, 100)
            self.progress_updated.emit("Sync complete", 100, 100)

            if count == 0:
                self.sync_complete.emit(True, "Ephemeris metadata is up to date (synced within last 24 hours)")
            else:
                self.sync_complete.emit(True, f"Synced {count} ephemeris files to database")
        except Exception as e:
            logger.error(f"Error syncing ephemeris metadata: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
            self.sync_complete.emit(False, str(e))


class DownloadLightPollutionThread(QThread):
    """Worker thread to download light pollution PNG file."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    download_complete = Signal(str, bool, str)  # type: ignore[type-arg,misc]  # Emits (region, success, message)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (region, error_message)

    def __init__(self, region: str, force: bool = False) -> None:
        """Initialize the download thread."""
        super().__init__()
        self.region = region
        self.force = force

    def run(self) -> None:
        """Download light pollution PNG file in background thread."""
        try:
            from pathlib import Path

            from celestron_nexstar.api.database.light_pollution_db import WORLD_ATLAS_URLS, _download_png

            if self.region not in WORLD_ATLAS_URLS:
                self.error_occurred.emit(self.region, f"Unknown region: {self.region}")
                self.download_complete.emit(self.region, False, "Unknown region")
                return

            url = WORLD_ATLAS_URLS[self.region]
            download_dir = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
            download_dir.mkdir(parents=True, exist_ok=True)
            png_path = download_dir / f"{self.region}2024.png"

            if png_path.exists() and not self.force:
                size_mb = png_path.stat().st_size / (1024 * 1024)
                self.download_complete.emit(self.region, True, f"Already downloaded ({size_mb:.1f} MB)")
                return

            if self.force and png_path.exists():
                png_path.unlink()

            self.progress_updated.emit(f"Downloading {self.region} PNG...", 0, 100)

            # Download the PNG file
            success = _download_png(url, png_path, progress=None, task_id=None)

            if success:
                size_mb = png_path.stat().st_size / (1024 * 1024)
                self.progress_updated.emit(f"Downloaded {self.region} PNG", 100, 100)
                self.download_complete.emit(self.region, True, f"Downloaded {self.region} PNG ({size_mb:.1f} MB)")
            else:
                self.error_occurred.emit(self.region, "Download failed")
                self.download_complete.emit(self.region, False, "Download failed")
        except Exception as e:
            logger.error(f"Error downloading light pollution data for {self.region}: {e}", exc_info=True)
            self.error_occurred.emit(self.region, str(e))
            self.download_complete.emit(self.region, False, str(e))


class ImportLightPollutionThread(QThread):
    """Worker thread to import light pollution data from PNG to database."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    import_complete = Signal(str, bool, str, int)  # type: ignore[type-arg,misc]  # Emits (region, success, message, points)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (region, error_message)

    def __init__(self, region: str, grid_resolution: float = 0.1) -> None:
        """Initialize the import thread."""
        super().__init__()
        self.region = region
        self.grid_resolution = grid_resolution

    def run(self) -> None:
        """Import light pollution data in background thread."""
        try:
            from pathlib import Path

            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.light_pollution_db import (
                WORLD_ATLAS_URLS,
                _create_light_pollution_table,
                _process_png_to_database,
            )
            from celestron_nexstar.api.database.models import LightPollutionGridModel

            if self.region not in WORLD_ATLAS_URLS:
                self.error_occurred.emit(self.region, f"Unknown region: {self.region}")
                self.import_complete.emit(self.region, False, "Unknown region", 0)
                return

            download_dir = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
            png_path = download_dir / f"{self.region}2024.png"

            if not png_path.exists():
                self.error_occurred.emit(self.region, "PNG file not found. Please download it first.")
                self.import_complete.emit(self.region, False, "PNG file not found", 0)
                return

            db = get_database()
            _create_light_pollution_table(db)

            # Truncate existing data for this region so import behaves like a fresh import
            try:
                with db._get_session() as session:
                    session.query(LightPollutionGridModel).filter(LightPollutionGridModel.region == self.region).delete(
                        synchronize_session=False
                    )
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to clear existing light pollution data for {self.region}: {e}")

            self.progress_updated.emit(f"Importing {self.region} region...", 0, 100)

            # Process PNG and store in database
            count = _process_png_to_database(
                png_path, self.region, db, self.grid_resolution, state_filter=None, progress=None, task_id=None
            )

            self.progress_updated.emit("Import complete", 100, 100)
            self.import_complete.emit(self.region, True, f"Imported {self.region} ({count:,} grid points)", count)
        except Exception as e:
            logger.error(f"Error importing light pollution data for {self.region}: {e}", exc_info=True)
            self.error_occurred.emit(self.region, str(e))
            self.import_complete.emit(self.region, False, str(e), 0)
