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


class SyncStarRelationshipsThread(QThread):
    """Worker thread to sync star relationships with constellations and asterisms."""

    progress_updated = Signal(str, int, int)  # type: ignore[type-arg,misc]  # Emits (status, current, total)
    operation_complete = Signal(str, bool, str)  # type: ignore[type-arg,misc]  # Emits (operation, success, message)
    error_occurred = Signal(str, str)  # type: ignore[type-arg,misc]  # Emits (operation, error_message)

    def __init__(self, operations: list[str] | None = None) -> None:
        """Initialize the sync thread.

        Args:
            operations: List of operations to run. Options: "constellations", "asterisms".
                       If None, runs all operations.
        """
        super().__init__()
        self.operations = operations or ["constellations", "asterisms"]

    def run(self) -> None:
        """Sync star relationships in background thread."""
        try:
            import sqlalchemy as sa
            from geoalchemy2 import functions
            from sqlalchemy import select, update

            from celestron_nexstar.api.database.models import (
                AsterismModel,
                ConstellationModel,
                StarModel,
                get_db_session,
                star_asterism_table,
                star_constellation_table,
            )

            with get_db_session() as session:
                # Determine progress ranges based on which operations are running
                if len(self.operations) == 1:
                    # Single operation gets full 0-100% range
                    if "constellations" in self.operations:
                        const_start, const_end = 0, 50
                        brightest_const_start, brightest_const_end = 50, 100
                        # Not running asterisms, so set dummy values
                        asterism_start = asterism_end = 0
                        brightest_asterism_start = brightest_asterism_end = 0
                    else:  # asterisms
                        asterism_start, asterism_end = 0, 70
                        brightest_asterism_start, brightest_asterism_end = 70, 100
                        # Not running constellations, so set dummy values
                        const_start = const_end = 0
                        brightest_const_start = brightest_const_end = 0
                else:
                    # Multiple operations share the range
                    const_start, const_end = 0, 20
                    asterism_start, asterism_end = 20, 50
                    brightest_const_start, brightest_const_end = 50, 70
                    brightest_asterism_start, brightest_asterism_end = 70, 85

                # Operation 1: Map stars to constellations
                if "constellations" in self.operations:
                    # Load JSON seed file for constellation decoration (description, mythology, season, etc.)
                    # NOTE: Source of truth is the GeoJSON files in ~/.cache/celestron-nexstar/celestial-data/
                    # (constellations.min.geojson, asterisms.min.geojson, etc.) which are imported into the database.
                    # The seed files in cli/data/seed/ are ONLY for decoration (metadata, descriptions, names).
                    try:
                        from celestron_nexstar.api.database.database_seeder import load_seed_json

                        json_constellations_data = load_seed_json("constellations.json")
                        json_constellations_map: dict[str, dict[str, Any]] = {
                            item["name"]: item for item in json_constellations_data if "name" in item
                        }
                        logger.debug(
                            f"Loaded {len(json_constellations_map)} constellations from JSON seed file for decoration"
                        )
                    except Exception as e:
                        logger.warning(f"Could not load constellations JSON seed file: {e}")
                        json_constellations_map = {}

                    self.progress_updated.emit("Mapping stars to constellations...", const_start, 100)
                    try:
                        # Get all constellations with geometry
                        constellations = (
                            session.execute(select(ConstellationModel).where(ConstellationModel.geometry.isnot(None)))
                            .scalars()
                            .all()
                        )

                        # Decorate constellations with metadata from JSON seed file
                        # Decoration fields from JSON (not position/geometry - those come from GeoJSON)
                        # Note: brightest_star is now a foreign key, not a string field
                        decoration_fields = {
                            "common_name",
                            "description",
                            "magnitude",
                            "hemisphere",
                            "mythology",
                            "season",
                        }

                        decorated_count = 0
                        for constellation in constellations:
                            if constellation.name in json_constellations_map:
                                json_data = json_constellations_map[constellation.name]
                                update_values: dict[str, Any] = {}
                                for field in decoration_fields:
                                    # Only update if field exists in JSON and model has this attribute
                                    if (
                                        field in json_data
                                        and json_data.get(field) is not None
                                        and hasattr(ConstellationModel, field)
                                        and field in ConstellationModel.__table__.columns
                                    ):
                                        current_value = getattr(constellation, field, None)
                                        # Update if field is empty or missing
                                        if current_value is None or current_value == "":
                                            update_values[field] = json_data[field]
                                if update_values:
                                    session.execute(
                                        update(ConstellationModel)
                                        .where(ConstellationModel.id == constellation.id)
                                        .values(**update_values)
                                    )
                                    # Refresh constellation object to get updated values
                                    session.refresh(constellation)
                                    decorated_count += 1
                        if decorated_count > 0:
                            session.commit()
                            logger.debug(f"Decorated {decorated_count} constellations with seed data")

                        # Create a mapping of constellation names to IDs for faster lookup
                        constellation_name_to_id: dict[str, int] = {const.name: const.id for const in constellations}

                        # Get stars that don't have a constellation relationship in the junction table
                        # Check junction table to see which stars already have relationships
                        existing_relationships = (
                            session.execute(select(star_constellation_table.c.star_id)).scalars().all()
                        )
                        existing_star_ids = set(existing_relationships)

                        # Get all stars, then filter to those not in the junction table
                        all_stars = session.execute(select(StarModel)).scalars().all()
                        stars = [star for star in all_stars if star.id not in existing_star_ids]
                        total_stars = len(stars)
                        mapped_count = 0

                        if total_stars == 0:
                            logger.debug("All stars already have constellation relationships in junction table")
                            self.progress_updated.emit(
                                "All stars already have constellation relationships", const_end, 100
                            )
                            # Emit completion signal
                            self.operation_complete.emit(
                                "stars_to_constellations",
                                True,
                                "All stars already have constellation relationships",
                            )
                        else:
                            logger.debug(f"Found {total_stars} stars without constellation relationships")

                            # Batch inserts for junction table
                            junction_inserts: list[dict[str, int]] = []

                            for idx, star in enumerate(stars):
                                if self.isInterruptionRequested():
                                    return

                                # Convert RA from hours to degrees for spatial query
                                ra_degrees = star.ra_hours * 15.0
                                dec_degrees = star.dec_degrees

                                # Create point geometry
                                point_wkt = f"POINT({ra_degrees} {dec_degrees})"

                                # Find constellation containing this star using optimized query
                                # Use bounding box check first for speed, then spatial query
                                constellation_name = None

                                # Quick bounding box check
                                for const in constellations:
                                    # Check if star is within constellation bounding box
                                    if const.ra_min_hours <= star.ra_hours <= const.ra_max_hours or (
                                        (
                                            const.ra_min_hours > const.ra_max_hours
                                            and (
                                                star.ra_hours >= const.ra_min_hours
                                                or star.ra_hours <= const.ra_max_hours
                                            )
                                        )
                                        and (const.dec_min_degrees <= dec_degrees <= const.dec_max_degrees)
                                    ):
                                        # Within bounding box, do precise spatial check
                                        constellation_stmt = (
                                            select(ConstellationModel.name)
                                            .where(
                                                ConstellationModel.id == const.id,
                                                functions.ST_Contains(
                                                    ConstellationModel.geometry, functions.ST_GeomFromText(point_wkt, 0)
                                                ),
                                            )
                                            .limit(1)
                                        )
                                        result = session.execute(constellation_stmt)
                                        constellation_name = result.scalar_one_or_none()
                                        if constellation_name:
                                            break

                                if constellation_name:
                                    constellation_id = constellation_name_to_id.get(constellation_name)
                                    if constellation_id:
                                        junction_inserts.append(
                                            {"star_id": star.id, "constellation_id": constellation_id}
                                        )
                                        mapped_count += 1

                                # Emit progress more frequently (every 10 stars or every 1%)
                                if (idx + 1) % max(10, total_stars // 100) == 0 or (idx + 1) == total_stars:
                                    # Calculate progress within the constellation operation range
                                    progress_range = const_end - const_start
                                    progress_pct = (
                                        const_start + int((idx + 1) / total_stars * progress_range)
                                        if total_stars > 0
                                        else const_start
                                    )
                                    self.progress_updated.emit(
                                        f"Mapping stars to constellations... ({idx + 1}/{total_stars})",
                                        progress_pct,
                                        100,
                                    )

                            # Ensure we emit progress after loop completes and before batch update
                            logger.debug(
                                f"Completed star processing: {mapped_count} stars to update out of {total_stars} total"
                            )
                            self.progress_updated.emit(
                                f"Processing complete. Updating {mapped_count} stars in database...",
                                const_start + (const_end - const_start) // 2,
                                100,
                            )

                            # Batch insert into junction table in chunks of 1000 with progress updates
                            if junction_inserts:
                                total_updates = len(junction_inserts)
                                batch_size = 1000
                                num_batches = (total_updates + batch_size - 1) // batch_size

                                logger.debug(
                                    f"Starting batch insert into junction table: {total_updates} relationships in {num_batches} batches"
                                )

                                for batch_idx in range(num_batches):
                                    if self.isInterruptionRequested():
                                        return

                                    start_idx = batch_idx * batch_size
                                    end_idx = min(start_idx + batch_size, total_updates)
                                    batch = junction_inserts[start_idx:end_idx]

                                    logger.debug(
                                        f"Processing batch {batch_idx + 1}/{num_batches}: {len(batch)} relationships"
                                    )

                                    # Emit progress before batch insert
                                    progress_pct = (
                                        const_start + (const_end - const_start) // 2
                                    )  # Stay in middle of constellation range during batch insert
                                    self.progress_updated.emit(
                                        f"Inserting batch {batch_idx + 1}/{num_batches}... ({start_idx + 1}-{end_idx}/{total_updates})",
                                        progress_pct,
                                        100,
                                    )

                                    # Use executemany for efficient batch inserts into junction table
                                    if len(batch) > 0:
                                        session.execute(sa.insert(star_constellation_table), batch)

                                    # Emit progress before commit (in case commit is slow)
                                    self.progress_updated.emit(
                                        f"Committing batch {batch_idx + 1}/{num_batches}...", progress_pct, 100
                                    )

                                    # Commit this batch
                                    session.commit()

                                    # Emit progress update after each batch completes
                                    self.progress_updated.emit(
                                        f"Inserted relationships into database... ({end_idx}/{total_updates})",
                                        progress_pct,
                                        100,
                                    )
                            else:
                                logger.debug("No constellation relationships to insert")

                            # Emit final progress for this operation
                            self.progress_updated.emit(
                                f"Completed: Mapped {mapped_count} stars to constellations", const_end, 100
                            )

                            self.operation_complete.emit(
                                "stars_to_constellations",
                                True,
                                f"Mapped {mapped_count} stars to constellations",
                            )
                    except Exception as e:
                        session.rollback()
                        logger.error(f"Error mapping stars to constellations: {e}", exc_info=True)
                        self.error_occurred.emit("stars_to_constellations", str(e))
                        self.operation_complete.emit("stars_to_constellations", False, str(e))

                # Operation 2: Map stars to asterisms
                if "asterisms" in self.operations:
                    self.progress_updated.emit("Mapping stars to asterisms...", asterism_start, 100)
                    try:
                        # Load JSON seed file for decoration only (stars, description, season, etc.)
                        # NOTE: Source of truth is asterisms.min.geojson in ~/.cache/celestron-nexstar/celestial-data/
                        # which is imported into the database. The seed file is ONLY for decoration.
                        try:
                            from celestron_nexstar.api.database.database_seeder import load_seed_json

                            json_asterisms_data = load_seed_json("asterisms.json")
                            json_asterisms_map: dict[str, dict[str, Any]] = {
                                item["name"]: item for item in json_asterisms_data if "name" in item
                            }
                            logger.debug(
                                f"Loaded {len(json_asterisms_map)} asterisms from JSON seed file for decoration"
                            )
                        except Exception as e:
                            logger.warning(f"Could not load asterisms JSON seed file: {e}")
                            json_asterisms_map = {}

                        # Get all asterisms from database (source of truth is GeoJSON files in cache directory)
                        asterisms = session.execute(select(AsterismModel)).scalars().all()

                        # Get existing relationships from junction table to avoid duplicates
                        existing_relationships = session.execute(
                            select(star_asterism_table.c.star_id, star_asterism_table.c.asterism_id)
                        ).all()
                        existing_pairs = {(row[0], row[1]) for row in existing_relationships}

                        total_asterisms = len(asterisms)
                        asterism_junction_inserts: list[dict[str, int]] = []  # Collect all junction table inserts

                        # Build a lookup dictionary of all star names to star objects for fast lookup
                        # This avoids N+1 queries - we do one query to get all stars, then use a dict
                        logger.debug("Building star name lookup dictionary...")
                        all_stars_list = session.execute(select(StarModel)).scalars().all()
                        star_name_to_star: dict[str, StarModel] = {}
                        for star in all_stars_list:
                            # Index by both name and common_name for fast lookup
                            if star.name:
                                star_name_to_star[star.name.lower()] = star
                            if star.common_name:
                                star_name_to_star[star.common_name.lower()] = star
                        logger.debug(f"Built lookup dictionary with {len(star_name_to_star)} entries")

                        # Decoration fields from JSON seed file (not position/geometry)
                        decoration_fields = {
                            "stars",
                            "description",
                            "season",
                            "cultural_info",
                            "guidepost_info",
                            "historical_notes",
                            "shape_description",
                            "wikipedia_url",
                            "alt_names",
                        }

                        for asterism_idx, asterism in enumerate(asterisms):
                            if self.isInterruptionRequested():
                                return

                            # Enrich asterism with decoration data from JSON seed file
                            if asterism.name in json_asterisms_map:
                                json_data = json_asterisms_map[asterism.name]
                                asterism_update_values: dict[str, Any] = {}
                                for field in decoration_fields:
                                    # Only update if field exists in JSON and model has this attribute
                                    if (
                                        field in json_data
                                        and json_data.get(field) is not None
                                        and hasattr(AsterismModel, field)
                                        and field in AsterismModel.__table__.columns
                                    ):
                                        current_value = getattr(asterism, field, None)
                                        # Update if field is empty or missing
                                        if current_value is None or current_value == "":
                                            asterism_update_values[field] = json_data[field]
                                if asterism_update_values:
                                    session.execute(
                                        update(AsterismModel)
                                        .where(AsterismModel.id == asterism.id)
                                        .values(**asterism_update_values)
                                    )
                                    # Refresh asterism object to get updated values
                                    session.refresh(asterism)

                            asterism_stars: list[str] = []
                            nearby_stars: list[StarModel] = []

                            # Use explicit star list from database (enriched from JSON seed file)
                            stars_field = asterism.stars
                            if stars_field:
                                # Parse comma-separated star names
                                star_names_from_db = [s.strip() for s in stars_field.split(",") if s.strip()]

                                # Look up stars using the pre-built dictionary (fast O(1) lookup)
                                for star_name in star_names_from_db:
                                    matched_star = star_name_to_star.get(star_name.lower())
                                    if matched_star:
                                        if matched_star not in nearby_stars:  # Avoid duplicates
                                            nearby_stars.append(matched_star)
                                        # Use common name if available, otherwise name
                                        display_name = (
                                            matched_star.common_name if matched_star.common_name else matched_star.name
                                        )
                                        if display_name and display_name not in asterism_stars:
                                            asterism_stars.append(display_name)
                                    else:
                                        logger.debug(
                                            f"Star '{star_name}' not found in database for asterism '{asterism.name}'"
                                        )

                            # Only use spatial query as fallback if NO explicit stars were found
                            # This should rarely happen if JSON file is properly populated
                            if not nearby_stars and asterism.geometry:
                                logger.warning(
                                    f"Asterism '{asterism.name}' has no explicit stars, falling back to slow spatial query"
                                )
                                # Find stars within asterism geometry using spatial query
                                # For asterisms, we use a buffer around the geometry since they're typically lines
                                # Use ST_Distance to find stars near the asterism pattern

                                for star in all_stars_list:
                                    # Convert RA from hours to degrees for spatial query
                                    ra_degrees = star.ra_hours * 15.0
                                    dec_degrees = star.dec_degrees

                                    # Create point geometry
                                    point_wkt = f"POINT({ra_degrees} {dec_degrees})"

                                    # Check distance to asterism geometry
                                    distance_stmt = select(
                                        functions.ST_Distance(
                                            functions.ST_GeomFromText(point_wkt, 0), AsterismModel.geometry
                                        )
                                    ).where(AsterismModel.id == asterism.id)

                                    result = session.execute(distance_stmt)
                                    distance_raw = result.scalar_one_or_none()
                                    distance: float | None = None
                                    if distance_raw is not None:
                                        try:
                                            distance = float(distance_raw)
                                        except (TypeError, ValueError):
                                            distance = None

                                    # Use 2 degrees tolerance for line-based asterisms
                                    if distance is not None and distance <= 2.0:
                                        nearby_stars.append(star)

                            # Track which stars belong to this asterism for junction table
                            for star in nearby_stars:
                                # Use common name if available, otherwise use name
                                star_name = star.common_name if star.common_name else star.name
                                if star_name and star_name not in asterism_stars:
                                    asterism_stars.append(star_name)

                                # Add to junction table if relationship doesn't already exist
                                if (star.id, asterism.id) not in existing_pairs:
                                    asterism_junction_inserts.append({"star_id": star.id, "asterism_id": asterism.id})

                            # Update asterism's stars field
                            if asterism_stars:
                                stars_str = ",".join(asterism_stars)
                                session.execute(
                                    update(AsterismModel).where(AsterismModel.id == asterism.id).values(stars=stars_str)
                                )

                                # Find brightest star
                                brightest = None
                                brightest_mag = float("inf")
                                for star in nearby_stars:
                                    if star.magnitude is not None and star.magnitude < brightest_mag:
                                        brightest_mag = star.magnitude
                                        brightest = star.common_name if star.common_name else star.name

                                if brightest:
                                    session.execute(
                                        update(AsterismModel)
                                        .where(AsterismModel.id == asterism.id)
                                        .values(brightest_star=brightest)
                                    )

                            # Emit progress for asterisms (33-66% of total)
                            if total_asterisms > 0:
                                progress_pct = 33 + int(((asterism_idx + 1) / total_asterisms) * 33)
                                self.progress_updated.emit(
                                    f"Mapping stars to asterisms... ({asterism_idx + 1}/{total_asterisms})",
                                    progress_pct,
                                    100,
                                )

                        # Batch insert into junction table
                        if asterism_junction_inserts:
                            total_updates = len(asterism_junction_inserts)
                            batch_size = 1000
                            num_batches = (total_updates + batch_size - 1) // batch_size

                            logger.debug(
                                f"Inserting {total_updates} star-asterism relationships into junction table in {num_batches} batches"
                            )

                            for batch_idx in range(num_batches):
                                if self.isInterruptionRequested():
                                    return

                                start_idx = batch_idx * batch_size
                                end_idx = min(start_idx + batch_size, total_updates)
                                batch = asterism_junction_inserts[start_idx:end_idx]

                                # Emit progress before batch insert
                                progress_range = asterism_end - asterism_start
                                progress_pct = asterism_start + int(
                                    ((asterism_idx + 1) / total_asterisms) * progress_range
                                )
                                self.progress_updated.emit(
                                    f"Inserting star-asterism relationships... batch {batch_idx + 1}/{num_batches} ({end_idx}/{total_updates})",
                                    progress_pct,
                                    100,
                                )

                                # Use executemany for efficient batch inserts into junction table
                                if len(batch) > 0:
                                    session.execute(sa.insert(star_asterism_table), batch)

                                # Commit this batch
                                session.commit()

                                # Emit progress after batch completes
                                self.progress_updated.emit(
                                    f"Inserted star-asterism relationships... ({end_idx}/{total_updates})",
                                    progress_pct,
                                    100,
                                )
                        else:
                            logger.debug("No star-asterism relationships to insert")
                            session.commit()
                        self.operation_complete.emit(
                            "stars_to_asterisms", True, f"Mapped stars to {len(asterisms)} asterisms"
                        )
                    except Exception as e:
                        session.rollback()
                        logger.error(f"Error mapping stars to asterisms: {e}", exc_info=True)
                        self.error_occurred.emit("stars_to_asterisms", str(e))
                        self.operation_complete.emit("stars_to_asterisms", False, str(e))

                # Operation 3: Find brightest stars in constellations
                if "constellations" in self.operations:
                    self.progress_updated.emit(
                        "Finding brightest stars in constellations...", brightest_const_start, 100
                    )
                    try:
                        # Get constellations (always reload to ensure we have fresh data)
                        constellations = (
                            session.execute(select(ConstellationModel).where(ConstellationModel.geometry.isnot(None)))
                            .scalars()
                            .all()
                        )
                        total_constellations = len(constellations)
                        for const_idx, constellation in enumerate(constellations):
                            if self.isInterruptionRequested():
                                return

                            # Only update if brightest_star_id is not already set
                            if not constellation.brightest_star_id:
                                # Find brightest star in this constellation using junction table
                                # Get stars in this constellation from junction table
                                stars_in_const_stmt = (
                                    select(StarModel)
                                    .join(
                                        star_constellation_table,
                                        StarModel.id == star_constellation_table.c.star_id,
                                    )
                                    .where(
                                        star_constellation_table.c.constellation_id == constellation.id,
                                        StarModel.magnitude.isnot(None),
                                    )
                                    .order_by(StarModel.magnitude.asc())
                                    .limit(1)
                                )
                                brightest_star = session.execute(stars_in_const_stmt).scalars().first()

                                if brightest_star is not None:
                                    # Set the foreign key to the star's ID
                                    session.execute(
                                        update(ConstellationModel)
                                        .where(ConstellationModel.id == constellation.id)
                                        .values(brightest_star_id=brightest_star.id)
                                    )
                                    logger.debug(
                                        f"Set brightest_star_id={brightest_star.id} for constellation '{constellation.name}'"
                                    )
                            else:
                                logger.debug(
                                    f"Constellation '{constellation.name}' already has brightest_star_id={constellation.brightest_star_id}"
                                )

                            # Emit progress for constellations
                            if total_constellations > 0:
                                progress_range = brightest_const_end - brightest_const_start
                                progress_pct = brightest_const_start + int(
                                    ((const_idx + 1) / total_constellations) * progress_range
                                )
                                self.progress_updated.emit(
                                    f"Finding brightest stars... ({const_idx + 1}/{total_constellations})",
                                    progress_pct,
                                    100,
                                )

                        session.commit()

                        # Emit final progress for this operation
                        self.progress_updated.emit(
                            f"Updated brightest stars for {len(constellations)} constellations",
                            brightest_const_end,
                            100,
                        )

                        self.operation_complete.emit(
                            "brightest_stars_constellations",
                            True,
                            f"Updated brightest stars for {len(constellations)} constellations",
                        )
                    except Exception as e:
                        session.rollback()
                        logger.error(f"Error finding brightest stars in constellations: {e}", exc_info=True)
                        self.error_occurred.emit("brightest_stars_constellations", str(e))
                        self.operation_complete.emit("brightest_stars_constellations", False, str(e))

                # Operation 4: Find brightest stars in asterisms
                if "asterisms" in self.operations:
                    self.progress_updated.emit("Finding brightest stars in asterisms...", brightest_asterism_start, 100)
                    try:
                        # Get all asterisms (already loaded earlier, but refresh to get updated data)
                        asterisms = session.execute(select(AsterismModel)).scalars().all()
                        total_asterisms = len(asterisms)

                        for asterism_idx, asterism in enumerate(asterisms):
                            if self.isInterruptionRequested():
                                return

                            # Only update if brightest_star is not already set (from JSON decoration)
                            if not asterism.brightest_star:
                                # Find brightest star in this asterism using junction table
                                stars_in_asterism_stmt = (
                                    select(StarModel)
                                    .join(
                                        star_asterism_table,
                                        StarModel.id == star_asterism_table.c.star_id,
                                    )
                                    .where(
                                        star_asterism_table.c.asterism_id == asterism.id,
                                        StarModel.magnitude.isnot(None),
                                    )
                                    .order_by(StarModel.magnitude.asc())
                                    .limit(1)
                                )
                                brightest_star = session.execute(stars_in_asterism_stmt).scalars().first()

                                if brightest_star is not None:
                                    star_name = (
                                        brightest_star.common_name
                                        if brightest_star.common_name
                                        else brightest_star.name
                                    )
                                    if star_name:
                                        session.execute(
                                            update(AsterismModel)
                                            .where(AsterismModel.id == asterism.id)
                                            .values(brightest_star=star_name)
                                        )
                            else:
                                logger.debug(
                                    f"Asterism '{asterism.name}' already has brightest_star={asterism.brightest_star}"
                                )

                            # Emit progress for asterisms
                            if total_asterisms > 0:
                                progress_range = brightest_asterism_end - brightest_asterism_start
                                progress_pct = brightest_asterism_start + int(
                                    ((asterism_idx + 1) / total_asterisms) * progress_range
                                )
                                self.progress_updated.emit(
                                    f"Finding brightest stars in asterisms... ({asterism_idx + 1}/{total_asterisms})",
                                    progress_pct,
                                    100,
                                )

                        session.commit()

                        # Emit final progress for this operation
                        self.progress_updated.emit(
                            f"Updated brightest stars for {len(asterisms)} asterisms", brightest_asterism_end, 100
                        )

                        self.operation_complete.emit(
                            "brightest_stars_asterisms",
                            True,
                            f"Updated brightest stars for {len(asterisms)} asterisms",
                        )
                    except Exception as e:
                        session.rollback()
                        logger.error(f"Error finding brightest stars in asterisms: {e}", exc_info=True)
                        self.error_occurred.emit("brightest_stars_asterisms", str(e))
                        self.operation_complete.emit("brightest_stars_asterisms", False, str(e))

                # Operation 5: Decorate stars with common names from star_name_mappings
                # This runs for both constellations and asterisms since it's a general star update
                if "constellations" in self.operations or "asterisms" in self.operations:
                    # Determine where to start based on what operations ran
                    star_names_start = 95 if len(self.operations) == 1 else 85  # Near the end for single operation
                    star_names_end = 100

                    self.progress_updated.emit("Updating star common names from mappings...", star_names_start, 100)
                    try:
                        # Load star name mappings from JSON seed file for decoration
                        # NOTE: Source of truth is stars.*.min.geojson files in ~/.cache/celestron-nexstar/celestial-data/
                        # The seed file is ONLY for decoration (common names, Bayer designations).
                        try:
                            from celestron_nexstar.api.database.database_seeder import load_seed_json

                            json_name_mappings_data = load_seed_json("star_name_mappings.json")
                            logger.debug(
                                f"Loaded {len(json_name_mappings_data)} star name mappings from JSON seed file"
                            )
                        except Exception as e:
                            logger.warning(f"Could not load star name mappings JSON seed file: {e}")
                            json_name_mappings_data = []

                        # Build a mapping of HR numbers to common names
                        hr_to_common_name: dict[int, str] = {}
                        for mapping in json_name_mappings_data:
                            hr_number = mapping.get("hr_number")
                            common_name = mapping.get("common_name")
                            if hr_number and common_name:
                                hr_to_common_name[hr_number] = common_name

                        # Update stars that have HR catalog numbers but no common_name
                        updated_count = 0
                        if hr_to_common_name:
                            stars_to_update = (
                                session.execute(
                                    select(StarModel).where(
                                        StarModel.catalog == "HR",
                                        StarModel.catalog_number.in_(hr_to_common_name.keys()),
                                        (StarModel.common_name.is_(None) | (StarModel.common_name == "")),
                                    )
                                )
                                .scalars()
                                .all()
                            )

                            for star in stars_to_update:
                                if star.catalog_number and star.catalog_number in hr_to_common_name:
                                    common_name = hr_to_common_name[star.catalog_number]
                                    session.execute(
                                        update(StarModel).where(StarModel.id == star.id).values(common_name=common_name)
                                    )
                                    updated_count += 1

                            if updated_count > 0:
                                session.commit()
                                logger.debug(f"Updated {updated_count} stars with common names from mappings")

                        self.progress_updated.emit("Star name mappings updated", star_names_end, 100)
                        self.operation_complete.emit(
                            "star_name_mappings",
                            True,
                            f"Updated {updated_count} stars with common names",
                        )
                    except Exception as e:
                        session.rollback()
                        logger.error(f"Error updating star name mappings: {e}", exc_info=True)
                        self.error_occurred.emit("star_name_mappings", str(e))
                        self.operation_complete.emit("star_name_mappings", False, str(e))

            self.progress_updated.emit("Sync complete", 100, 100)
        except Exception as e:
            logger.error(f"Error in sync operation: {e}", exc_info=True)
            self.error_occurred.emit("sync", str(e))
