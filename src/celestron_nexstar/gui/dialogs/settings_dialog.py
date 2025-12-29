"""
Dialog to display and manage application settings.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.database.database_seeder import seed_asteroids
from celestron_nexstar.gui.utils.table_utils import autosize_table_columns


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Dialog to display and manage application settings with tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the settings dialog."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.resize(900, 700)

        # Create layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        self._font_family = f"'{monospace_font}'" if monospace_font else "'Courier New'"

        # Create tabs
        self._create_config_tab()
        self._create_ephemeris_tab()
        self._create_celestial_data_tab()
        self._create_seed_data_tab()
        self._create_solar_system_tab()
        self._create_custom_yaml_tab()
        self._create_wds_tab()
        self._create_light_pollution_tab()
        self._create_location_tab()
        self._create_optics_tab()
        self._create_time_tab()
        self._create_data_tab()
        self._create_database_tab()

        # Track active download workers
        self._download_workers: dict[str, object] = {}

        # Track import all progress
        self._import_all_queue: list[str] = []
        self._import_all_in_progress = False
        self._import_all_total = 0
        self._import_all_completed = 0

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data
        self._load_config_info()
        self._load_ephemeris_info()
        self._load_celestial_data_info()
        self._load_seed_data_info()
        self._load_solar_system_info()
        self._load_custom_yaml_info()
        self._load_wds_info()
        self._load_light_pollution_info()
        self._load_location_info()
        self._load_optics_info()
        self._load_time_info()
        self._load_data_info()
        self._load_database_info()

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-aware colors."""
        is_dark = self._is_dark_theme()
        return {
            "text": "#ffffff" if is_dark else "#000000",
            "text_dim": "#9e9e9e" if is_dark else "#666666",
            "header": "#ff9800" if is_dark else "#e65100",  # Orange
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _create_config_tab(self) -> None:
        """Create the config tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("User Config")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        info = QLabel("Settings here are written to disk and take effect after restarting the app.")
        info.setWordWrap(True)
        self.user_config_info_label = info
        layout.addWidget(info)

        form = QFormLayout()

        use_memory = QCheckBox("Use in-memory database (faster reads, uses more RAM)")
        self.user_config_use_memory_db = use_memory
        form.addRow("Database:", use_memory)

        # Protocol log location
        protocol_log_combo = QComboBox()
        protocol_log_combo.addItem("Main Window Only", "main")
        protocol_log_combo.addItem("Telescope Window Only", "telescope")
        protocol_log_combo.addItem("Both Windows", "both")
        protocol_log_combo.setToolTip("Choose where to display telescope protocol commands/responses")
        self.user_config_protocol_log_location = protocol_log_combo
        form.addRow("Protocol Log:", protocol_log_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_user_config)
        self.user_config_save_btn = save_btn
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status = QLabel()
        status.setWordWrap(True)
        self.user_config_status_label = status
        layout.addWidget(status)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Config")

    def _create_solar_system_tab(self) -> None:
        """Create Solar System tab for MPC/Horizons data management."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("Solar System Data (MPC / Horizons)")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(header)

        desc = QLabel(
            "Manage offline comet/asteroid elements (MPC), optional Horizons/SPK caches, and eclipse seeds "
            "for accurate offline visibility when traveling without internet."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Source", "Description", "Count", "Actions"])
        autosize_table_columns(table, stretch_last=True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.solar_system_table = table
        layout.addWidget(table)

        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 0)
        self.solar_system_progress = progress
        layout.addWidget(progress)

        status = QLabel()
        status.setWordWrap(True)
        self.solar_system_status = status
        layout.addWidget(status)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Solar System Data")

    def _create_ephemeris_tab(self) -> None:
        """Create the ephemeris tab with download functionality."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Ephemeris Files")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Quick download sets
        sets_row = QHBoxLayout()
        sets_row.addWidget(QLabel("Download set:"))
        set_buttons = [
            ("Basic", "minimal"),
            ("Recommended", "recommended"),
            ("Standard", "standard"),
            ("Complete", "complete"),
            ("Full", "full"),
        ]
        for label, set_name in set_buttons:
            btn = QPushButton(label)
            btn.setToolTip(f"Download ephemeris set: {set_name}")
            btn.clicked.connect(lambda checked, s=set_name: self._on_download_ephemeris_set(s))
            sets_row.addWidget(btn)
        sets_row.addStretch()
        layout.addLayout(sets_row)

        # Sync metadata (all files)
        sync_row = QHBoxLayout()
        sync_all_btn = QPushButton("Sync Metadata")
        sync_all_btn.setToolTip("Refresh ephemeris file metadata from NAIF for all files")
        sync_all_btn.clicked.connect(self._on_sync_ephemeris_all)
        sync_row.addWidget(sync_all_btn)
        sync_row.addStretch()
        layout.addLayout(sync_row)

        # Table for ephemeris files
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["File", "Status", "Size", "Coverage", "Download"])
        autosize_table_columns(table, stretch_last=False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ephemeris_table = table
        layout.addWidget(table)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.ephemeris_progress = progress
        layout.addWidget(progress)

        # Status label
        status_label = QLabel()
        status_label.setVisible(False)
        status_label.setWordWrap(True)
        self.ephemeris_status_label = status_label
        layout.addWidget(status_label)

        self.tab_widget.addTab(widget, "Ephemeris")

    def _create_location_tab(self) -> None:
        """Create the location tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        location_text = QTextEdit()
        location_text.setReadOnly(True)
        location_text.setAcceptRichText(True)
        location_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.location_text = location_text
        layout.addWidget(location_text, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        set_btn = QPushButton("Set Location…")
        set_btn.setToolTip("Set observer location used for calculations")
        set_btn.clicked.connect(self._on_set_location)
        self.location_set_btn = set_btn
        button_row.addWidget(set_btn)
        layout.addLayout(button_row)

        self.tab_widget.addTab(widget, "Location")

    def _create_optics_tab(self) -> None:
        """Create the optics tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        optics_text = QTextEdit()
        optics_text.setReadOnly(True)
        optics_text.setAcceptRichText(True)
        optics_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.optics_text = optics_text
        layout.addWidget(optics_text, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        edit_btn = QPushButton("Edit Optics…")
        edit_btn.setToolTip("Change the active telescope model and eyepiece")
        edit_btn.clicked.connect(self._on_edit_optics)
        self.optics_edit_btn = edit_btn
        button_row.addWidget(edit_btn)
        layout.addLayout(button_row)

        self.tab_widget.addTab(widget, "Optics")

    def _create_time_tab(self) -> None:
        """Create the time tab."""
        time_text = QTextEdit()
        time_text.setReadOnly(True)
        time_text.setAcceptRichText(True)
        time_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.time_text = time_text
        self.tab_widget.addTab(time_text, "Time")

    def _create_celestial_data_tab(self) -> None:
        """Create the celestial data tab with download functionality."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Celestial Data Sources")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Button toolbar
        toolbar_layout = QHBoxLayout()

        # Import All button
        import_all_btn = QPushButton("Import All Data")
        import_all_btn.setToolTip(
            "Import all celestial data in the correct order:\n"
            "1. Constellations\n"
            "2. Asterisms\n"
            "3. DSOs\n"
            "4. Local Group\n"
            "5. Stars\n"
            "6. Messier Objects"
        )
        import_all_btn.clicked.connect(self._on_import_all_celestial_data)
        self.import_all_celestial_btn = import_all_btn
        toolbar_layout.addWidget(import_all_btn)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # Table for celestial data sources
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Source", "Description", "Status", "Size", "Download", "Import", "Delete"])
        autosize_table_columns(table, stretch_last=False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.celestial_data_table = table
        layout.addWidget(table)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.celestial_data_progress = progress
        layout.addWidget(progress)

        # Status label
        status_label = QLabel()
        status_label.setWordWrap(True)
        self.celestial_data_status_label = status_label
        layout.addWidget(status_label)

        self.tab_widget.addTab(widget, "Celestial Data")

    def _create_seed_data_tab(self) -> None:
        """Create the seed data tab with re-import functionality."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Seed Data")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Table for seed data sources
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Source", "Description", "Count", "Re-import", "All"])
        autosize_table_columns(table, stretch_last=False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.seed_data_table = table
        layout.addWidget(table)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.seed_data_progress = progress
        layout.addWidget(progress)

        # Status label
        status_label = QLabel()
        status_label.setWordWrap(True)
        self.seed_data_status_label = status_label
        layout.addWidget(status_label)

        self.tab_widget.addTab(widget, "Seed Data")

    def _create_custom_yaml_tab(self) -> None:
        """Create the custom YAML tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Custom YAML Catalog")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Info label
        info_label = QLabel()
        info_label.setWordWrap(True)
        self.custom_yaml_info = info_label
        layout.addWidget(info_label)

        # Import button
        import_btn = QPushButton("Import Custom YAML")
        import_btn.clicked.connect(self._on_import_custom_yaml)
        self.custom_yaml_import_btn = import_btn
        layout.addWidget(import_btn)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        self.custom_yaml_progress = progress
        layout.addWidget(progress)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Custom YAML")

    def _create_wds_tab(self) -> None:
        """Create the WDS catalog tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Washington Double Star Catalog (WDS)")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Info label
        info_label = QLabel()
        info_label.setWordWrap(True)
        self.wds_info = info_label
        layout.addWidget(info_label)

        # Button layout
        button_layout = QHBoxLayout()

        # Download button
        download_btn = QPushButton("Download WDS Catalog")
        download_btn.clicked.connect(self._on_download_wds)
        self.wds_download_btn = download_btn
        button_layout.addWidget(download_btn)

        # Import button
        import_btn = QPushButton("Import WDS Catalog")
        import_btn.clicked.connect(self._on_import_wds)
        import_btn.setEnabled(False)  # Disabled until file is downloaded
        self.wds_import_btn = import_btn
        button_layout.addWidget(import_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.wds_progress = progress
        layout.addWidget(progress)

        # Status label
        status_label = QLabel()
        status_label.setWordWrap(True)
        self.wds_status_label = status_label
        layout.addWidget(status_label)

        layout.addStretch()
        self.tab_widget.addTab(widget, "WDS")

    def _create_light_pollution_tab(self) -> None:
        """Create the light pollution tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Light Pollution Data")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Table for regions
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Region", "Status", "Grid Points", "Download", "Import"])
        autosize_table_columns(table, stretch_last=False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.light_pollution_table = table
        layout.addWidget(table)

        # Progress bar
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setRange(0, 100)
        self.light_pollution_progress = progress
        layout.addWidget(progress)

        # Status label
        status_label = QLabel()
        status_label.setWordWrap(True)
        self.light_pollution_status_label = status_label
        layout.addWidget(status_label)

        self.tab_widget.addTab(widget, "Light Pollution")

    def _create_data_tab(self) -> None:
        """Create the data tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header_row = QHBoxLayout()
        header = QLabel("Data Usage")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 6px;")
        header_row.addWidget(header)
        header_row.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Re-scan data directories and file sizes")
        refresh_btn.clicked.connect(self._load_data_info)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        summary = QLabel()
        summary.setWordWrap(True)
        self.data_summary_label = summary
        layout.addWidget(summary)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Type", "Name", "Size", "Modified", "Path"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        self.data_table = table
        layout.addWidget(table, 1)

        self.tab_widget.addTab(widget, "Data")

    def _create_database_tab(self) -> None:
        """Create the database tab for migrations and stats."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel("Database")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        info = QLabel(
            "Manage the local database: create it if missing, apply Alembic migrations, and view basic statistics."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.database_status_label = QLabel()
        self.database_status_label.setWordWrap(True)
        layout.addWidget(self.database_status_label)

        self.database_migration_label = QLabel()
        self.database_migration_label.setWordWrap(True)
        layout.addWidget(self.database_migration_label)

        self.database_stats_label = QLabel()
        self.database_stats_label.setWordWrap(True)
        layout.addWidget(self.database_stats_label)

        btn_row = QHBoxLayout()
        create_btn = QPushButton("Create DB + Apply Migrations")
        create_btn.clicked.connect(self._on_database_create_and_migrate)
        btn_row.addWidget(create_btn)

        migrate_btn = QPushButton("Apply Migrations")
        migrate_btn.clicked.connect(self._on_database_apply_migrations)
        btn_row.addWidget(migrate_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_database_info)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        log_label = QLabel("Migration Output")
        layout.addWidget(log_label)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMinimumHeight(120)
        self.database_log = log
        layout.addWidget(log)

        self.tab_widget.addTab(widget, "Database")

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Format bytes as a human readable string."""
        try:
            size = float(max(0, int(num_bytes)))
        except Exception:
            return "—"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024.0 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _load_database_info(self) -> None:
        """Load database status, migrations, and stats."""
        try:
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory
            from sqlalchemy import create_engine

            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.statistics import get_light_pollution_stats, get_tle_stats

            db = get_database()
            db_path = db.db_path
            exists = db_path.exists()
            size_str = f"{db_path.stat().st_size / 1024 / 1024:.2f} MB" if exists else "n/a"
            status_lines = [
                f"<b>Path:</b> {db_path}",
                f"<b>Exists:</b> {'Yes' if exists else 'No'}",
                f"<b>Size:</b> {size_str}",
            ]

            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

            current_rev = None
            heads: tuple[str, ...] | None = None
            pending: list[Any] | None = None

            engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
            try:
                with engine.connect() as conn:
                    context = MigrationContext.configure(conn)
                    current_rev = context.get_current_revision()
                script = ScriptDirectory.from_config(alembic_cfg)
                heads_tuple = tuple(script.get_heads())
                heads = heads_tuple
                pending = list(script.iterate_revisions(heads_tuple, current_rev)) if heads_tuple else []  # type: ignore[arg-type]
            finally:
                engine.dispose()

            pending_list = [getattr(rev, "revision", "") for rev in pending] if pending else []
            migration_text = (
                f"<b>Current revision:</b> {current_rev or 'None'}<br>"
                f"<b>Head(s):</b> {', '.join(heads) if heads else 'None'}<br>"
                f"<b>Pending:</b> {', '.join(pending_list) if pending_list else 'None'}"
            )

            # Stats
            lp_stats = get_light_pollution_stats()
            tle_stats = get_tle_stats()
            stats_parts = []
            stats_parts.append(
                f"<b>Light pollution:</b> "
                f"{'table missing' if not lp_stats.table_exists else f'{lp_stats.total_count or 0:,} rows'}"
            )
            if lp_stats.table_exists and lp_stats.total_count:
                regions_str = ", ".join(f"{r[0]} ({r[1]:,})" for r in (lp_stats.region_counts or [])) or "none"
                stats_parts.append(f"Regions: {regions_str}")
            stats_parts.append(
                f"<b>TLE:</b> "
                f"{'table missing' if not tle_stats.table_exists else f'{tle_stats.total_count or 0:,} rows'}"
            )
            stats_text = "<br>".join(stats_parts)

            self.database_status_label.setText("<br>".join(status_lines))
            self.database_migration_label.setText(migration_text)
            self.database_stats_label.setText(stats_text)
        except Exception as e:
            logger.error(f"Error loading database info: {e}", exc_info=True)
            self.database_status_label.setText(f"Error loading database info: {e}")

    def _on_database_create_and_migrate(self) -> None:
        """Create DB if needed and apply migrations."""
        self._run_database_action(create_if_missing=True)

    def _on_database_apply_migrations(self) -> None:
        """Apply migrations to existing DB."""
        self._run_database_action(create_if_missing=False)

    def _run_database_action(self, create_if_missing: bool) -> None:
        """Run migrations (and optionally create DB) with UI updates."""
        try:
            msg, applied = self._apply_migrations(create_if_missing=create_if_missing)
            applied_str = ", ".join(applied) if applied else "None"
            self.database_log.setPlainText(msg)
            self._show_toast(
                f"Database updated. Applied migrations: {applied_str}",
                duration_ms=4000,
                preset="success",
            )
        except Exception as e:
            logger.error(f"Database action failed: {e}", exc_info=True)
            self.database_log.setPlainText(str(e))
            self._show_toast(f"Database action failed: {e}", duration_ms=4000, preset="error")
        finally:
            self._load_database_info()

    def _apply_migrations(self, create_if_missing: bool) -> tuple[str, list[str]]:
        """Apply Alembic migrations, returning log text and applied revisions."""
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text

        from alembic import command  # type: ignore[attr-defined]
        from celestron_nexstar.api.database.database import get_database

        db = get_database()
        db_path = db.db_path
        if create_if_missing and not db_path.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

        current_rev = None
        pending_revs: list[str] = []

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        script = ScriptDirectory.from_config(alembic_cfg)
        heads = script.get_heads()
        if heads:
            pending = list(script.iterate_revisions(heads, current_rev))
            pending_revs = [rev.revision for rev in pending]

        log_lines = [
            f"DB Path: {db_path}",
            f"Current revision: {current_rev or 'None'}",
            f"Target head(s): {', '.join(heads) if heads else 'None'}",
            f"Pending: {', '.join(pending_revs) if pending_revs else 'None'}",
            "Applying migrations...",
        ]

        try:
            try:
                command.upgrade(alembic_cfg, "heads")
            except Exception as e:
                error_str = str(e)
                if hasattr(e, "__cause__") and e.__cause__:
                    error_str += f" {e.__cause__}"
                if hasattr(e, "orig") and getattr(e, "orig", None):
                    error_str += f" {e.orig}"
                error_msg = error_str.lower()
                if "objects_fts" in error_msg and ("trigger" in error_msg or "no such table" in error_msg):
                    log_lines.append("Encountered FTS trigger issue; dropping triggers and retrying.")
                    with engine.connect() as conn:
                        conn.execute(text("DROP TRIGGER IF EXISTS objects_ai"))
                        conn.execute(text("DROP TRIGGER IF EXISTS objects_ad"))
                        conn.execute(text("DROP TRIGGER IF EXISTS objects_au"))
                        conn.commit()
                    command.upgrade(alembic_cfg, "heads")
                else:
                    raise
        finally:
            engine.dispose()

        # Determine new revision after upgrade
        engine2 = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        new_rev = None
        with engine2.connect() as conn:
            context = MigrationContext.configure(conn)
            new_rev = context.get_current_revision()
        engine2.dispose()

        log_lines.append(f"Completed. Current revision: {new_rev or 'None'}")
        return "\n".join(log_lines), pending_revs

    def _load_config_info(self) -> None:
        """Load user-config values into the Config tab."""
        colors = self._get_theme_colors()
        try:
            import os

            from celestron_nexstar.api.config.user_config import get_user_config_path, load_user_config

            cfg = load_user_config()
            self.user_config_use_memory_db.setChecked(cfg.use_memory_db)

            # Set protocol log location
            combo = self.user_config_protocol_log_location
            for i in range(combo.count()):
                if combo.itemData(i) == cfg.protocol_log_location:
                    combo.setCurrentIndex(i)
                    break

            # Communicate effective value (env var overrides)
            env_val = os.getenv("CELESTRON_USE_MEMORY_DB")
            if env_val is not None:
                effective = env_val.lower() in ("true", "1", "yes")
                self.user_config_status_label.setText(
                    f"<span style='color: {colors['yellow']};'>Note:</span> "
                    f"`CELESTRON_USE_MEMORY_DB` is set and overrides this setting. "
                    f"Effective in-memory DB: <b>{'ON' if effective else 'OFF'}</b>"
                )
            else:
                self.user_config_status_label.setText(
                    f"Config file: <span style='color: {colors['text_dim']};'>{get_user_config_path()}</span>"
                )

        except Exception as e:
            logger.error(f"Error loading config info: {e}", exc_info=True)
            self.user_config_status_label.setText(
                f"<span style='color: {colors['error']};'><b>Error:</b> Failed to load configuration: {e}</span>"
            )

    def _on_save_user_config(self) -> None:
        """Save user-config values to disk."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.config.user_config import UserConfig, get_user_config_path, save_user_config

            protocol_log_location = self.user_config_protocol_log_location.currentData()
            cfg = UserConfig(
                use_memory_db=bool(self.user_config_use_memory_db.isChecked()),
                protocol_log_location=protocol_log_location,
            )
            save_user_config(cfg)
            self.user_config_status_label.setText(
                f"<span style='color: {colors['green']};'>✓ Saved</span> "
                f"to <span style='color: {colors['text_dim']};'>{get_user_config_path()}</span>. "
                "Restart the app for changes to take effect."
            )
        except Exception as e:
            logger.error(f"Error saving user config: {e}", exc_info=True)
            self.user_config_status_label.setText(
                f"<span style='color: {colors['error']};'><b>Error:</b> Failed to save configuration: {e}</span>"
            )

    def _load_ephemeris_info(self) -> None:
        """Load ephemeris file information into table."""
        try:
            from celestron_nexstar.api.ephemeris.ephemeris_manager import (
                EPHEMERIS_FILES,
                get_file_size,
                is_file_installed,
            )

            table = self.ephemeris_table
            table.setRowCount(len(EPHEMERIS_FILES))

            for row, (file_key, file_info) in enumerate(sorted(EPHEMERIS_FILES.items())):
                # File name
                table.setItem(row, 0, QTableWidgetItem(file_info.display_name))

                # Status
                installed = is_file_installed(file_key)
                status_text = "✓ Downloaded" if installed else "Not downloaded"
                status_item = QTableWidgetItem(status_text)
                if installed:
                    status_item.setForeground(Qt.GlobalColor.green)
                table.setItem(row, 1, status_item)

                # Size
                if installed:
                    size = get_file_size(file_key)
                    size_mb = size / (1024 * 1024) if size else 0
                    size_text = f"{size_mb:.1f} MB"
                else:
                    size_text = f"{file_info.size_mb:.0f} MB (est.)"
                table.setItem(row, 2, QTableWidgetItem(size_text))

                # Coverage
                coverage_text = f"{file_info.coverage_start}-{file_info.coverage_end}"
                table.setItem(row, 3, QTableWidgetItem(coverage_text))

                # Download button
                download_btn = QPushButton("Download" if not installed else "Re-download")
                download_btn.setFixedWidth(100)
                download_btn.setToolTip(
                    "Download this ephemeris file from NAIF. Re-download will replace the existing file if it exists."
                )
                download_btn.clicked.connect(lambda checked, key=file_key: self._on_download_ephemeris_file(key))
                table.setCellWidget(row, 4, download_btn)

            table.resizeColumnsToContents()

        except Exception as e:
            logger.error(f"Error loading ephemeris info: {e}", exc_info=True)

    def _load_celestial_data_info(self) -> None:
        """Load celestial data sources into table with enforced import order."""
        try:
            import json

            from sqlalchemy import select

            from celestron_nexstar.api.database.models import AsterismModel, ConstellationModel, get_db_session
            from celestron_nexstar.cli.data_import import DATA_SOURCES, get_cache_dir

            # Filter to only celestial data sources
            celestial_sources = {k: v for k, v in DATA_SOURCES.items() if k.startswith("celestial_")}

            cache_dir = get_cache_dir()

            # Some sources (Messier / Local Group) can overlap with other catalogs, and the DB schema
            # enforces unique names per table. To keep the UI accurate, we compute an "imported count"
            # for these sources based on whether objects from the source file exist in the DB.
            messier_names: set[str] = set()
            local_group_names: set[str] = set()

            messier_path = cache_dir / "messier.min.geojson"
            if messier_path.exists():
                try:
                    data = json.loads(messier_path.read_text(encoding="utf-8"))
                    for feat in data.get("features", []):
                        if not isinstance(feat, dict):
                            continue
                        props = feat.get("properties", {})
                        if not isinstance(props, dict):
                            continue
                        name = (
                            props.get("name")
                            or props.get("n")
                            or props.get("Name")
                            or props.get("id")
                            or props.get("designation")
                        )
                        if isinstance(name, str) and name.strip():
                            messier_names.add(name.strip())
                except Exception:
                    messier_names = set()

            local_group_path = cache_dir / "lg.min.geojson"
            if local_group_path.exists():
                try:
                    data = json.loads(local_group_path.read_text(encoding="utf-8"))
                    for feat in data.get("features", []):
                        if not isinstance(feat, dict):
                            continue
                        props = feat.get("properties", {})
                        if not isinstance(props, dict):
                            continue
                        name = (
                            props.get("name")
                            or props.get("n")
                            or props.get("Name")
                            or props.get("id")
                            or props.get("designation")
                        )
                        if isinstance(name, str) and name.strip():
                            local_group_names.add(name.strip())
                except Exception:
                    local_group_names = set()

            # Check if constellations and asterisms are imported
            constellations_imported = False
            asterisms_imported = False
            try:
                with get_db_session() as session:
                    const_count = session.scalar(select(ConstellationModel.id).limit(1))
                    constellations_imported = const_count is not None
                    asterism_count = session.scalar(select(AsterismModel.id).limit(1))
                    asterisms_imported = asterism_count is not None
            except Exception:
                pass  # Tables might not exist yet

            # Helper function to check if data is imported for a source
            def get_imported_count(source_id: str) -> int:
                """Return how many records are currently imported for a source."""
                try:
                    with get_db_session() as session:
                        from sqlalchemy import func

                        from celestron_nexstar.api.database.models import (
                            ClusterModel,
                            GalaxyModel,
                            NebulaModel,
                            StarModel,
                        )

                        if source_id == "celestial_constellations":
                            count = session.scalar(select(func.count(ConstellationModel.id)))
                            return int(count or 0)
                        elif source_id == "celestial_asterisms":
                            count = session.scalar(select(func.count(AsterismModel.id)))
                            return int(count or 0)
                        elif source_id.startswith("celestial_stars"):
                            count = session.scalar(
                                select(func.count(StarModel.id)).where(StarModel.catalog == "celestial_stars")
                            )
                            return int(count or 0)
                        elif source_id.startswith("celestial_dsos"):
                            # Check galaxies, nebulae, and clusters
                            galaxy_count = session.scalar(
                                select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "celestial_dsos")
                            )
                            nebula_count = session.scalar(
                                select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "celestial_dsos")
                            )
                            cluster_count = session.scalar(
                                select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "celestial_dsos")
                            )
                            return int((galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0))
                        elif source_id == "celestial_messier":
                            # Prefer name-membership counting so the UI reflects objects that already exist
                            # from other imports (e.g. celestial_dsos) even if they can't be duplicated.
                            if messier_names:
                                galaxy_count = session.scalar(
                                    select(func.count(GalaxyModel.id)).where(GalaxyModel.name.in_(messier_names))
                                )
                                nebula_count = session.scalar(
                                    select(func.count(NebulaModel.id)).where(NebulaModel.name.in_(messier_names))
                                )
                                cluster_count = session.scalar(
                                    select(func.count(ClusterModel.id)).where(ClusterModel.name.in_(messier_names))
                                )
                                # Include StarModel too (handles any legacy/mis-imported rows)
                                star_count = session.scalar(
                                    select(func.count(StarModel.id)).where(StarModel.name.in_(messier_names))
                                )
                                return int(
                                    (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                                )

                            # Fallback: count rows explicitly tagged as messier (or any legacy mis-imports)
                            galaxy_count = session.scalar(
                                select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "messier")
                            )
                            nebula_count = session.scalar(
                                select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "messier")
                            )
                            cluster_count = session.scalar(
                                select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "messier")
                            )
                            star_count = session.scalar(
                                select(func.count(StarModel.id)).where(StarModel.catalog == "messier")
                            )
                            return int(
                                (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                            )
                        elif source_id == "celestial_local_group":
                            if local_group_names:
                                galaxy_count = session.scalar(
                                    select(func.count(GalaxyModel.id)).where(GalaxyModel.name.in_(local_group_names))
                                )
                                nebula_count = session.scalar(
                                    select(func.count(NebulaModel.id)).where(NebulaModel.name.in_(local_group_names))
                                )
                                cluster_count = session.scalar(
                                    select(func.count(ClusterModel.id)).where(ClusterModel.name.in_(local_group_names))
                                )
                                star_count = session.scalar(
                                    select(func.count(StarModel.id)).where(StarModel.name.in_(local_group_names))
                                )
                                return int(
                                    (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                                )

                            galaxy_count = session.scalar(
                                select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "local_group")
                            )
                            cluster_count = session.scalar(
                                select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "local_group")
                            )
                            star_count = session.scalar(
                                select(func.count(StarModel.id)).where(StarModel.catalog == "local_group")
                            )
                            nebula_count = session.scalar(
                                select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "local_group")
                            )
                            return int(
                                (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                            )
                except Exception:
                    return 0
                return 0

            def check_data_imported(source_id: str) -> bool:
                """Check if data for a source has been imported."""
                return get_imported_count(source_id) > 0

            table = self.celestial_data_table
            table.setRowCount(len(celestial_sources))

            filename_map = {
                "celestial_stars_14": "stars.14.min.geojson",
                "celestial_dsos_20": "dsos.20.min.geojson",
                "celestial_messier": "messier.min.geojson",
                "celestial_asterisms": "asterisms.min.geojson",
                "celestial_constellations": "constellations.min.geojson",
                "celestial_local_group": "lg.min.geojson",
            }

            # Define import order: constellations first, then asterisms, then the rest

            # Sort sources: constellations first, asterisms second, then alphabetically
            def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
                source_id, _ = item
                if source_id == "celestial_constellations":
                    return (0, source_id)
                elif source_id == "celestial_asterisms":
                    return (1, source_id)
                else:
                    return (2, source_id)

            sorted_sources = sorted(celestial_sources.items(), key=sort_key)

            for row, (source_id, source) in enumerate(sorted_sources):
                # Source name (remove "Celestial Data - " prefix if present)
                display_name = source.name.replace("Celestial Data - ", "")
                table.setItem(row, 0, QTableWidgetItem(display_name))

                # Description
                desc = source.description[:60] + "..." if len(source.description) > 60 else source.description
                table.setItem(row, 1, QTableWidgetItem(desc))

                # Status
                filename = filename_map.get(source_id)
                cache_path: Path | None = None
                if filename:
                    cache_path = cache_dir / filename
                    if cache_path.exists():
                        size_mb = cache_path.stat().st_size / (1024 * 1024)
                        status_text = f"✓ Downloaded ({size_mb:.1f} MB)"
                        status_item = QTableWidgetItem(status_text)
                        status_item.setForeground(Qt.GlobalColor.green)
                    else:
                        status_text = "Not downloaded"
                        status_item = QTableWidgetItem(status_text)
                else:
                    status_text = "N/A"
                    status_item = QTableWidgetItem(status_text)
                table.setItem(row, 2, status_item)

                # Size: show actual imported count if available, otherwise estimate
                imported_count = get_imported_count(source_id)
                size_text = (
                    f"{imported_count:,} imported" if imported_count > 0 else f"~{source.objects_available:,} objects"
                )
                table.setItem(row, 3, QTableWidgetItem(size_text))

                # Download button
                download_btn = QPushButton("Download")
                download_btn.setFixedWidth(100)
                if filename and cache_path and cache_path.exists():
                    download_btn.setText("Re-download")
                download_btn.clicked.connect(lambda checked, sid=source_id: self._on_download_celestial_data(sid))
                table.setCellWidget(row, 4, download_btn)

                # Import button - enforce import order
                import_btn = QPushButton("Import")
                import_btn.setFixedWidth(80)

                # Determine whether this source already has imported DB data (used for Import/Re-import label)
                data_imported = check_data_imported(source_id)
                if data_imported:
                    import_btn.setText("Re-import")
                    import_btn.setToolTip("Re-import will truncate existing data and import again")

                # Enable import button based on:
                # 1. File must be downloaded
                # 2. Import order dependencies must be met
                file_downloaded = bool(filename and cache_path and cache_path.exists())
                can_import = file_downloaded
                tooltip_parts = []

                # First check: file must be downloaded
                if not file_downloaded:
                    can_import = False
                    tooltip_parts.append("File must be downloaded first")
                else:
                    # Constellations can always be imported (no dependencies)
                    if source_id == "celestial_constellations":
                        pass  # No dependencies
                    # Asterisms require constellations to be imported first
                    elif source_id == "celestial_asterisms":
                        if not constellations_imported:
                            can_import = False
                            tooltip_parts.append("Constellations must be imported first")
                    # All other sources require both constellations and asterisms
                    else:
                        if not constellations_imported or not asterisms_imported:
                            can_import = False
                            missing = []
                            if not constellations_imported:
                                missing.append("constellations")
                            if not asterisms_imported:
                                missing.append("asterisms")
                            tooltip_parts.append(f"Must import {' and '.join(missing)} first")

                # Set tooltip if there are any requirements
                if tooltip_parts:
                    import_btn.setToolTip("; ".join(tooltip_parts))
                else:
                    # Keep the existing tooltip (e.g. Re-import message) if one was set above
                    if not import_btn.toolTip():
                        import_btn.setToolTip("")

                import_btn.setEnabled(can_import)
                import_btn.clicked.connect(lambda checked, sid=source_id: self._on_import_celestial_data(sid))
                table.setCellWidget(row, 5, import_btn)

                # Delete button - only enabled if data is imported
                delete_btn = QPushButton("Delete")
                delete_btn.setFixedWidth(80)
                delete_btn.setEnabled(data_imported)
                if not data_imported:
                    delete_btn.setToolTip("No data imported")
                else:
                    delete_btn.setToolTip("Delete imported data and downloaded file")
                delete_btn.clicked.connect(lambda checked, sid=source_id: self._on_delete_celestial_data(sid))
                table.setCellWidget(row, 6, delete_btn)

            table.resizeColumnsToContents()

            # Clear status label
            self.celestial_data_status_label.clear()

        except Exception as e:
            logger.error(f"Error loading celestial data info: {e}", exc_info=True)
            self.celestial_data_status_label.setText(f"Error: {e}")

    def _load_seed_data_info(self) -> None:
        """Load seed data sources into table."""
        try:
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import (
                BortleCharacteristicsModel,
                CometModel,
                ConstellationModel,
                DarkSkySiteModel,
                EclipseModel,
                MeteorShowerModel,
                MoonModel,
                PlanetModel,
                SpaceEventModel,
                StarNameMappingModel,
                VariableStarModel,
                get_db_session,
            )

            # Define seed data sources
            seed_sources = [
                {
                    "id": "star_name_mappings",
                    "name": "Star Name Mappings",
                    "description": "Common names and Bayer designations for stars",
                },
                {
                    "id": "meteor_showers",
                    "name": "Meteor Showers",
                    "description": "Annual meteor shower calendar with peak dates and activity periods",
                },
                {
                    "id": "constellations",
                    "name": "Constellations",
                    "description": "Constellation reference data (names, abbreviations, mythology)",
                },
                {
                    "id": "planets",
                    "name": "Planets",
                    "description": "Planetary reference data (core solar system bodies)",
                },
                {
                    "id": "moons",
                    "name": "Moons",
                    "description": "Major planetary moons (ephemeris-linked)",
                },
                {
                    "id": "bortle_characteristics",
                    "name": "Bortle Characteristics",
                    "description": "Reference characteristics for Bortle classes 1-9",
                },
                {
                    "id": "dark_sky_sites",
                    "name": "Dark Sky Sites",
                    "description": "International Dark Sky Association certified viewing sites",
                },
                {
                    "id": "space_events",
                    "name": "Space Events",
                    "description": "Calendar of astronomical events (eclipses, meteor showers, etc.)",
                },
                {
                    "id": "variable_stars",
                    "name": "Variable Stars",
                    "description": "Reference set of notable variable stars",
                },
                {
                    "id": "comets",
                    "name": "Comets",
                    "description": "Reference set of bright/cometary objects",
                },
                {
                    "id": "eclipses",
                    "name": "Eclipses",
                    "description": "Reference solar/lunar eclipses",
                },
                {
                    "id": "asteroids",
                    "name": "Asteroids",
                    "description": "Notable asteroids with orbital elements",
                },
            ]

            def get_seed_count(seed_id: str) -> int:
                """Return how many records are currently in the database for a seed type."""
                try:
                    with get_db_session() as session:
                        if seed_id == "star_name_mappings":
                            count = session.scalar(select(func.count(StarNameMappingModel.hr_number)))
                            return int(count or 0)
                        elif seed_id == "meteor_showers":
                            count = session.scalar(select(func.count(MeteorShowerModel.id)))
                            return int(count or 0)
                        elif seed_id == "constellations":
                            count = session.scalar(select(func.count(ConstellationModel.id)))
                            return int(count or 0)
                        elif seed_id == "planets":
                            count = session.scalar(select(func.count(PlanetModel.id)))
                            return int(count or 0)
                        elif seed_id == "moons":
                            count = session.scalar(select(func.count(MoonModel.id)))
                            return int(count or 0)
                        elif seed_id == "dark_sky_sites":
                            count = session.scalar(select(func.count(DarkSkySiteModel.id)))
                            return int(count or 0)
                        elif seed_id == "space_events":
                            count = session.scalar(select(func.count(SpaceEventModel.id)))
                            return int(count or 0)
                        elif seed_id == "bortle_characteristics":
                            count = session.scalar(select(func.count(BortleCharacteristicsModel.bortle_class)))
                            return int(count or 0)
                        elif seed_id == "variable_stars":
                            count = session.scalar(select(func.count(VariableStarModel.id)))
                            return int(count or 0)
                        elif seed_id == "comets":
                            count = session.scalar(select(func.count(CometModel.id)))
                            return int(count or 0)
                        elif seed_id == "eclipses":
                            count = session.scalar(select(func.count(EclipseModel.id)))
                            return int(count or 0)
                        elif seed_id == "asteroids":
                            from celestron_nexstar.api.database.models import AsteroidModel

                            count = session.scalar(select(func.count(AsteroidModel.id)))
                            return int(count or 0)
                except Exception:
                    return 0
                return 0

            table = self.seed_data_table
            table.setRowCount(len(seed_sources))

            for row, source in enumerate(seed_sources):
                # Source name
                table.setItem(row, 0, QTableWidgetItem(source["name"]))

                # Description
                table.setItem(row, 1, QTableWidgetItem(source["description"]))

                # Count
                count = get_seed_count(source["id"])
                count_text = str(count) if count > 0 else "0"
                count_item = QTableWidgetItem(count_text)
                table.setItem(row, 2, count_item)

                # Import / Re-import button based on whether data exists
                has_data = count > 0
                button_label = "Re-import" if has_data else "Import"
                button_tooltip = (
                    "Clear existing data and re-import from seed files" if has_data else "Import from seed files"
                )
                reimport_btn = QPushButton(button_label)
                reimport_btn.setFixedWidth(100)
                reimport_btn.setToolTip(button_tooltip)
                reimport_btn.clicked.connect(lambda checked, sid=source["id"]: self._on_reimport_seed_data(sid))
                table.setCellWidget(row, 3, reimport_btn)

                # Disabled placeholder for per-row "All" to keep column alignment (global button below)
                placeholder_btn = QPushButton("-")
                placeholder_btn.setEnabled(False)
                placeholder_btn.setFixedWidth(80)
                table.setCellWidget(row, 4, placeholder_btn)

            table.resizeColumnsToContents()

            # Clear status label
            self.seed_data_status_label.clear()

        except Exception as e:
            logger.error(f"Error loading seed data info: {e}", exc_info=True)
            self.seed_data_status_label.setText(f"Error: {e}")

    def _load_solar_system_info(self) -> None:
        """Load solar system data (MPC/Horizons/Eclipses) into table."""
        try:
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.database_seeder import get_seed_data_path
            from celestron_nexstar.api.database.models import CometModel, EclipseModel, get_db_session

            with get_db_session() as session:
                comet_count = int(session.scalar(select(func.count(CometModel.id))) or 0)
                eclipse_count = int(session.scalar(select(func.count(EclipseModel.id))) or 0)
                # Count SPK files
                from celestron_nexstar.api.database.models import CometSPKModel

                int(session.scalar(select(func.count(CometSPKModel.id))) or 0)

            seed_dir = get_seed_data_path()
            comet_seed_exists = (seed_dir / "comets.json").exists()

            sources = [
                {
                    "id": "mpc_comets",
                    "name": "MPC Comets",
                    "description": "Comet orbital elements + photometric params (MPC Soft00Cmt)",
                    "count": comet_count,
                    "seed_exists": comet_seed_exists,
                },
                # NOTE: SPK downloads removed - JPL Horizons does not provide downloadable SPK files
                # for comets or asteroids through their API. Use orbital elements instead.
                # {
                #     "id": "horizons_spk",
                #     "name": "Horizons SPK",
                #     "description": "High-accuracy SPK kernels for comets from JPL Horizons",
                #     "count": spk_count,
                #     "seed_exists": spk_count > 0,
                # },
                {
                    "id": "eclipses",
                    "name": "Eclipses Seed",
                    "description": "Seed eclipses with contact times/path (offline visibility)",
                    "count": eclipse_count,
                    "seed_exists": True,
                },
            ]

            table = self.solar_system_table
            table.setRowCount(len(sources))

            for row, source in enumerate(sources):
                table.setItem(row, 0, QTableWidgetItem(source["name"]))
                table.setItem(row, 1, QTableWidgetItem(source["description"]))
                table.setItem(row, 2, QTableWidgetItem(f"{source['count']:,}"))

                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(0, 0, 0, 0)

                if source["id"] == "mpc_comets":
                    download_btn = QPushButton("Download")
                    download_btn.clicked.connect(self._on_download_mpc_comets)
                    self.solar_mpc_download_btn = download_btn
                    action_layout.addWidget(download_btn)

                    import_btn = QPushButton("Re-import" if source["count"] > 0 else "Import")
                    import_btn.clicked.connect(self._on_import_mpc_comets)
                    import_btn.setEnabled(source["seed_exists"])
                    if not source["seed_exists"]:
                        import_btn.setToolTip("Download MPC comets first to enable import")
                    self.solar_mpc_import_btn = import_btn
                    action_layout.addWidget(import_btn)

                elif source["id"] == "horizons_spk":
                    manage_btn = QPushButton("Manage SPKs...")
                    manage_btn.clicked.connect(self._on_manage_spks)
                    manage_btn.setToolTip("Download and manage SPK files for comets")
                    self.solar_spk_manage_btn = manage_btn
                    action_layout.addWidget(manage_btn)

                elif source["id"] == "eclipses":
                    import_btn = QPushButton("Re-import" if source["count"] > 0 else "Import")
                    import_btn.clicked.connect(self._on_import_eclipses_solar)
                    self.solar_eclipses_import_btn = import_btn
                    action_layout.addWidget(import_btn)

                action_layout.addStretch()
                table.setCellWidget(row, 3, action_widget)

            table.resizeColumnsToContents()
            self.solar_system_status.clear()
        except Exception as e:
            logger.error(f"Error loading solar system info: {e}", exc_info=True)
            self.solar_system_status.setText(f"Error: {e}")

    def _load_custom_yaml_info(self) -> None:
        """Load custom YAML catalog information."""
        try:
            module_path = Path(__file__).parent.parent.parent.parent / "cli" / "data"
            yaml_path = module_path / "catalogs.yaml"

            info_text = "<b>Custom YAML Catalog</b><br><br>"
            info_text += f"<b>Location:</b> {yaml_path}<br><br>"

            if yaml_path.exists():
                size = yaml_path.stat().st_size
                info_text += f"<span style='color: green;'>✓ File exists ({size:,} bytes)</span><br><br>"
                info_text += "Click 'Import Custom YAML' to import objects into the database."
                # Enable import button
                self.custom_yaml_import_btn.setEnabled(True)
            else:
                info_text += "<span style='color: red;'>✗ File not found</span><br><br>"
                info_text += f"Create a catalogs.yaml file at:<br>{yaml_path}"
                # Disable import button
                self.custom_yaml_import_btn.setEnabled(False)

            self.custom_yaml_info.setText(info_text)

        except Exception as e:
            logger.error(f"Error loading custom YAML info: {e}", exc_info=True)
            self.custom_yaml_info.setText(f"<b>Error:</b> {e}")

    def _load_wds_info(self) -> None:
        """Load WDS catalog information."""
        try:
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.models import DoubleStarModel, get_db_session
            from celestron_nexstar.cli.data_import import get_cache_dir

            cache_dir = get_cache_dir()
            wds_path = cache_dir / "wdsweb_summ2.txt"

            # Count imported WDS rows (DB)
            imported_count = 0
            try:
                with get_db_session() as session:
                    imported_count = int(
                        session.scalar(select(func.count(DoubleStarModel.id)).where(DoubleStarModel.catalog == "wds"))
                        or 0
                    )
            except Exception:
                imported_count = 0

            info_text = "<b>Washington Double Star Catalog (WDS)</b><br><br>"
            info_text += f"<b>Location:</b> {wds_path}<br><br>"

            if wds_path.exists():
                size_mb = wds_path.stat().st_size / (1024 * 1024)
                info_text += f"<span style='color: green;'>✓ Downloaded ({size_mb:.1f} MB)</span><br><br>"
                if imported_count > 0:
                    info_text += f"<b>Imported:</b> {imported_count:,} rows<br><br>"
                info_text += "The WDS catalog is ready to import into the database."
                # Enable import button
                self.wds_import_btn.setEnabled(True)
                self.wds_download_btn.setText("Re-download WDS Catalog")
                self.wds_import_btn.setText("Re-import WDS Catalog" if imported_count > 0 else "Import WDS Catalog")
            else:
                info_text += "<span style='color: orange;'>Not downloaded</span><br><br>"
                info_text += "Click 'Download WDS Catalog' to download from US Naval Observatory."
                # Disable import button
                self.wds_import_btn.setEnabled(False)
                self.wds_download_btn.setText("Download WDS Catalog")
                self.wds_import_btn.setText("Import WDS Catalog")

            self.wds_info.setText(info_text)
            self.wds_status_label.clear()

        except Exception as e:
            logger.error(f"Error loading WDS info: {e}", exc_info=True)
            self.wds_info.setText(f"<b>Error:</b> {e}")

    def _load_light_pollution_info(self) -> None:
        """Load light pollution regions into table."""
        try:
            from sqlalchemy import func, select

            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.database.light_pollution_db import WORLD_ATLAS_URLS
            from celestron_nexstar.api.database.models import LightPollutionGridModel, get_db_session

            table = self.light_pollution_table
            regions = list(WORLD_ATLAS_URLS.keys())
            table.setRowCount(len(regions))

            # Get counts from database
            get_database()
            region_counts: dict[str, int] = {}

            try:
                with get_db_session() as session:
                    for region in regions:
                        # Count grid points for this specific region
                        result = session.scalar(
                            select(func.count(LightPollutionGridModel.id)).where(
                                LightPollutionGridModel.region == region
                            )
                        )
                        region_counts[region] = int(result or 0)
            except Exception:
                pass  # Table might not exist yet

            # Check for downloaded PNG files
            from pathlib import Path

            cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"
            png_files = {region: (cache_dir / f"{region}2024.png").exists() for region in regions}

            for row, region in enumerate(sorted(regions)):
                # Region name
                region_display = region.replace("_", " ").title()
                table.setItem(row, 0, QTableWidgetItem(region_display))

                # Status - check both PNG file and database
                count = region_counts.get(region, 0)
                png_exists = png_files.get(region, False)

                if count > 0:
                    status_text = "✓ Imported"
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(Qt.GlobalColor.green)
                elif png_exists:
                    status_text = "Downloaded (not imported)"
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(Qt.GlobalColor.yellow)
                else:
                    status_text = "Not downloaded"
                    status_item = QTableWidgetItem(status_text)
                table.setItem(row, 1, status_item)

                # Grid points
                points_text = f"{count:,}" if count > 0 else "-"
                table.setItem(row, 2, QTableWidgetItem(points_text))

                # Download button
                download_btn = QPushButton("Download")
                download_btn.setFixedWidth(100)
                if png_exists:
                    download_btn.setText("Re-download")
                download_btn.clicked.connect(lambda checked, r=region: self._on_download_light_pollution(r))
                table.setCellWidget(row, 3, download_btn)

                # Import button
                import_btn = QPushButton("Import")
                import_btn.setFixedWidth(80)
                if count > 0:
                    import_btn.setText("Re-import")
                import_btn.setEnabled(png_exists)  # Only enable if PNG is downloaded
                import_btn.clicked.connect(lambda checked, r=region: self._on_import_light_pollution(r))
                table.setCellWidget(row, 4, import_btn)

            table.resizeColumnsToContents()
            self.light_pollution_status_label.clear()

        except Exception as e:
            logger.error(f"Error loading light pollution info: {e}", exc_info=True)

    def _load_location_info(self) -> None:
        """Load location configuration information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.location.observer import get_config_path, get_observer_location

            location = get_observer_location()
            config_path = get_config_path()

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Observer Location</span></p>"
            )

            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Setting</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            if location.name:
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Location Name</td><td style='color: {colors['text']};'>{location.name}</td></tr>"
                )
            lat_dir = "N" if location.latitude >= 0 else "S"
            lon_dir = "E" if location.longitude >= 0 else "W"
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Latitude</td><td style='color: {colors['text']};'>{abs(location.latitude):.4f}°{lat_dir}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Longitude</td><td style='color: {colors['text']};'>{abs(location.longitude):.4f}°{lon_dir}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Elevation</td><td style='color: {colors['text']};'>{location.elevation:.0f} ft above sea level</td></tr>"
            )
            html_content.append("</table>")

            html_content.append(
                f"<p style='color: {colors['text']};'><b>Config File:</b> <span style='color: {colors['text_dim']};'>{config_path}</span></p>"
            )
            exists_marker = (
                f"<span style='color: {colors['green']};'>✓ Exists</span>"
                if config_path.exists()
                else f"<span style='color: {colors['text_dim']};'>(not saved)</span>"
            )
            html_content.append(f"<p style='color: {colors['text']};'>{exists_marker}</p>")
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-top: 15px;'>Tip: You can also set it via CLI: nexstar location set.</p>"
            )

            self.location_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading location info: {e}", exc_info=True)
            self.location_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load location information: {e}</span></p>"
            )

    def _on_set_location(self) -> None:
        """Open modal dialog to set observer location."""
        try:
            from celestron_nexstar.gui.dialogs.location_config_dialog import LocationConfigDialog

            dlg = LocationConfigDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._load_location_info()
        except Exception as e:
            logger.error("Error opening location configuration dialog", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to open location configuration dialog:\n{e!s}")

    def _load_optics_info(self) -> None:
        """Load optics configuration information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.observation.optics import get_current_configuration

            config = get_current_configuration()

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Optical Configuration</span></p>"
            )

            # Telescope
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Telescope</span></p>"
            )
            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Parameter</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Model</td><td style='color: {colors['text']};'>{config.telescope.display_name}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Aperture</td><td style='color: {colors['text']};'>{config.telescope.aperture_mm:.0f}mm ({config.telescope.aperture_inches:.1f}\")</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Focal Length</td><td style='color: {colors['text']};'>{config.telescope.focal_length_mm:.0f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Focal Ratio</td><td style='color: {colors['text']};'>f/{config.telescope.focal_ratio:.1f}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Effective Aperture</td><td style='color: {colors['text']};'>{config.telescope.effective_aperture_mm:.1f}mm (with obstruction)</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Light Gathering</td><td style='color: {colors['text']};'>{config.telescope.light_gathering_power:.0f}x naked eye</td></tr>"
            )
            html_content.append("</table>")

            # Eyepiece
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Eyepiece</span></p>"
            )
            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Parameter</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            eyepiece_name = config.eyepiece.name or f"{config.eyepiece.focal_length_mm:.0f}mm"
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Name</td><td style='color: {colors['text']};'>{eyepiece_name}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Focal Length</td><td style='color: {colors['text']};'>{config.eyepiece.focal_length_mm:.0f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Apparent FOV</td><td style='color: {colors['text']};'>{config.eyepiece.apparent_fov_deg:.0f}°</td></tr>"
            )
            html_content.append("</table>")

            # Performance
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Performance</span></p>"
            )
            html_content.append("<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>")
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Parameter</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Magnification</td><td style='color: {colors['text']};'>{config.magnification:.0f}x</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Exit Pupil</td><td style='color: {colors['text']};'>{config.exit_pupil_mm:.1f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>True FOV</td><td style='color: {colors['text']};'>{config.true_fov_deg:.2f}° ({config.true_fov_arcmin:.1f}')</td></tr>"
            )
            html_content.append("</table>")

            self.optics_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading optics info: {e}", exc_info=True)
            self.optics_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load optics information: {e}</span></p>"
            )

    def _on_edit_optics(self) -> None:
        """Open modal dialog to change telescope and eyepiece configuration."""
        try:
            from celestron_nexstar.gui.dialogs.optics_config_dialog import OpticsConfigDialog

            dlg = OpticsConfigDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._load_optics_info()
        except Exception as e:
            logger.error("Error opening optics configuration dialog", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to open optics configuration dialog:\n{e!s}")

    def _load_time_info(self) -> None:
        """Load time configuration information."""
        colors = self._get_theme_colors()
        try:
            from datetime import UTC, datetime

            from celestron_nexstar.api.core.utils import get_local_timezone
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            local_tz = get_local_timezone(location.latitude, location.longitude)
            now_utc = datetime.now(UTC)
            now_local = now_utc.astimezone(local_tz) if local_tz else now_utc

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Time Settings</span></p>"
            )

            html_content.append("<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>")
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Setting</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Current UTC Time</td><td style='color: {colors['text']};'>{now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC</td></tr>"
            )
            if local_tz:
                tz_name = str(local_tz) if hasattr(local_tz, "__str__") else local_tz.tzname(now_local) or "Unknown"
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Local Timezone</td><td style='color: {colors['text']};'>{tz_name}</td></tr>"
                )
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Current Local Time</td><td style='color: {colors['text']};'>{now_local.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>"
                )
            else:
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Local Timezone</td><td style='color: {colors['text_dim']};'>Could not determine</td></tr>"
                )
            html_content.append("</table>")

            self.time_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading time info: {e}", exc_info=True)
            self.time_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load time information: {e}</span></p>"
            )

    def _load_data_info(self) -> None:
        """Load data directory and file information."""
        colors = self._get_theme_colors()
        try:
            from datetime import datetime
            from pathlib import Path

            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            # Directories we own/use
            config_dir = Path.home() / ".config" / "celestron-nexstar"
            eph_dir = get_ephemeris_directory()
            # Celestial data download cache
            try:
                from celestron_nexstar.cli.data_import import get_cache_dir

                celestial_cache_dir = get_cache_dir()
            except Exception:
                celestial_cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "celestial-data"

            light_pollution_cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "light-pollution"

            # Database file (SQLite)
            db_path = config_dir / "catalogs.db"

            def _safe_list_files(base: Path) -> list[Path]:
                if not base.exists():
                    return []
                try:
                    return [p for p in base.rglob("*") if p.is_file()]
                except Exception:
                    return []

            def _dir_total_bytes(files: list[Path]) -> int:
                total = 0
                for p in files:
                    try:
                        total += int(p.stat().st_size)
                    except Exception:
                        continue
                return total

            def _mtime_str(p: Path) -> str:
                try:
                    ts = p.stat().st_mtime
                    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    return "—"

            # Collect files
            config_files = _safe_list_files(config_dir)
            eph_files = _safe_list_files(eph_dir)
            celestial_cache_files = _safe_list_files(celestial_cache_dir)
            light_pollution_cache_files = _safe_list_files(light_pollution_cache_dir)

            # Build rows: (type, name, size_bytes, mtime, path)
            rows: list[tuple[str, str, int, str, str]] = []

            # Database row first (even though it also lives in config dir)
            if db_path.exists():
                try:
                    size = int(db_path.stat().st_size)
                except Exception:
                    size = 0
                rows.append(("Database", db_path.name, size, _mtime_str(db_path), str(db_path)))
            else:
                rows.append(("Database", db_path.name, 0, "—", f"{db_path} (missing)"))

            # Individual files
            def _add_files(file_type: str, files: list[Path]) -> None:
                for p in files:
                    # Avoid duplicating the DB row (still keep it in config totals)
                    if p == db_path:
                        continue
                    try:
                        sz = int(p.stat().st_size)
                    except Exception:
                        sz = 0
                    rows.append((file_type, p.name, sz, _mtime_str(p), str(p)))

            _add_files("Config", config_files)
            _add_files("Ephemeris", eph_files)
            _add_files("Cache (Celestial)", celestial_cache_files)
            _add_files("Cache (Light Pollution)", light_pollution_cache_files)

            # Sort by size descending for easier “what's using space” scanning
            rows.sort(key=lambda r: r[2], reverse=True)

            # Cap rows to keep UI responsive if a directory is unexpectedly huge
            max_rows = 500
            truncated = False
            if len(rows) > max_rows:
                rows = rows[:max_rows]
                truncated = True

            # Populate table
            table: QTableWidget = self.data_table
            table.setRowCount(len(rows))
            for i, (typ, name, size_b, mtime, path_str) in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(typ))
                table.setItem(i, 1, QTableWidgetItem(name))
                table.setItem(i, 2, QTableWidgetItem(self._format_bytes(size_b)))
                table.setItem(i, 3, QTableWidgetItem(mtime))
                table.setItem(i, 4, QTableWidgetItem(path_str))

            autosize_table_columns(table, stretch_last=True)

            # Summary totals
            totals = {
                "Config": _dir_total_bytes(config_files),
                "Ephemeris": _dir_total_bytes(eph_files),
                "Cache (Celestial)": _dir_total_bytes(celestial_cache_files),
                "Cache (Light Pollution)": _dir_total_bytes(light_pollution_cache_files),
            }
            overall = sum(totals.values())
            summary_lines = [
                f"<b>Database:</b> <span style='color:{colors['text_dim']};'>{db_path}</span>",
                f"<b>Config dir:</b> <span style='color:{colors['text_dim']};'>{config_dir}</span> "
                f"(<b>{self._format_bytes(totals['Config'])}</b>)",
                f"<b>Ephemeris dir:</b> <span style='color:{colors['text_dim']};'>{eph_dir}</span> "
                f"(<b>{self._format_bytes(totals['Ephemeris'])}</b>)",
                f"<b>Celestial cache:</b> <span style='color:{colors['text_dim']};'>{celestial_cache_dir}</span> "
                f"(<b>{self._format_bytes(totals['Cache (Celestial)'])}</b>)",
                f"<b>Light pollution cache:</b> <span style='color:{colors['text_dim']};'>{light_pollution_cache_dir}</span> "
                f"(<b>{self._format_bytes(totals['Cache (Light Pollution)'])}</b>)",
                f"<b>Total (dirs):</b> {self._format_bytes(overall)}",
            ]
            if truncated:
                summary_lines.append(
                    f"<span style='color:{colors['yellow']};'>Showing first {max_rows} files (sorted by size).</span>"
                )
            self.data_summary_label.setText("<br/>".join(summary_lines))

        except Exception as e:
            logger.error(f"Error loading data info: {e}", exc_info=True)
            if hasattr(self, "data_summary_label"):
                self.data_summary_label.setText(
                    f"<span style='color: {colors['error']};'><b>Error:</b> Failed to load data information: {e}</span>"
                )

    def _on_download_ephemeris_file(self, file_key: str) -> None:
        """Handle ephemeris file download button click."""
        from celestron_nexstar.gui.workers.download_workers import DownloadEphemerisFileThread

        # Check if already downloading
        worker_key = f"ephemeris_{file_key}"
        if worker_key in self._download_workers:
            return

        # Create and start worker
        worker = DownloadEphemerisFileThread(file_key, force=False)
        worker.progress_updated.connect(
            lambda status, current, total, key=file_key: self._on_ephemeris_progress(key, status, current, total)
        )
        worker.download_complete.connect(
            lambda key, success, message: self._on_ephemeris_complete(key, success, message)
        )
        worker.error_occurred.connect(lambda key, error: self._on_ephemeris_error(key, error))
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_download_ephemeris_set(self, set_name: str) -> None:
        """Download an ephemeris set (e.g., recommended, standard, full)."""
        from celestron_nexstar.gui.workers.download_workers import DownloadEphemerisSetThread

        worker_key = f"ephemeris_set_{set_name}"
        if worker_key in self._download_workers:
            return

        worker = DownloadEphemerisSetThread(set_name=set_name, force=False)

        worker.progress_updated.connect(
            lambda status, current, total, s=set_name: self._on_ephemeris_set_progress(s, status, current, total)
        )
        worker.download_complete.connect(
            lambda key, success, message: self._on_ephemeris_set_complete(key, success, message)
        )
        worker.error_occurred.connect(lambda key, error: self._on_ephemeris_set_error(key, error))
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_ephemeris_progress(self, file_key: str, status: str, current: int, total: int) -> None:
        """Handle ephemeris download progress update."""
        # Update progress bar and status label
        if total > 0:
            percentage = int((current / total) * 100) if total > 0 else 0
            self.ephemeris_progress.setValue(percentage)
            self.ephemeris_progress.setVisible(True)
        else:
            self.ephemeris_progress.setValue(0)
            self.ephemeris_progress.setVisible(True)

        if status:
            self.ephemeris_status_label.setText(status)
            self.ephemeris_status_label.setVisible(True)

    def _on_ephemeris_complete(self, file_key: str, success: bool, message: str) -> None:
        """Handle ephemeris download completion."""
        # Hide progress bar and status label
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)

        if success:
            logger.info(f"Ephemeris download complete: {message}")
            # Reload ephemeris info to update table
            self._load_ephemeris_info()
            self._show_toast(f"Ephemeris downloaded: {message}", duration_ms=3000, preset="success")
        else:
            logger.error(f"Ephemeris download failed: {message}")
            self._show_toast(f"Ephemeris download failed: {message}", duration_ms=4000, preset="error")

    def _on_ephemeris_error(self, file_key: str, error: str) -> None:
        """Handle ephemeris download error."""
        # Hide progress bar and status label
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)

        logger.error(f"Ephemeris download error for {file_key}: {error}")
        self._show_toast(f"Ephemeris download error: {error}", duration_ms=4000, preset="error")

    def _on_ephemeris_set_progress(self, set_name: str, status: str, current: int, total: int) -> None:
        """Handle ephemeris set download progress update."""
        if total > 0:
            percentage = int((current / total) * 100) if total > 0 else 0
            self.ephemeris_progress.setValue(percentage)
            self.ephemeris_progress.setVisible(True)
        else:
            self.ephemeris_progress.setValue(0)
            self.ephemeris_progress.setVisible(True)

        if status:
            self.ephemeris_status_label.setText(status)
            self.ephemeris_status_label.setVisible(True)

    def _on_ephemeris_set_complete(self, set_name: str, success: bool, message: str) -> None:
        """Handle ephemeris set download completion."""
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)

        if success:
            logger.info(f"Ephemeris set download complete: {message}")
            self._load_ephemeris_info()
            self._show_toast(f"Ephemeris set downloaded: {message}", duration_ms=3000, preset="success")
        else:
            logger.error(f"Ephemeris set download failed: {message}")
            self._show_toast(f"Ephemeris set download failed: {message}", duration_ms=4000, preset="error")

    def _on_ephemeris_set_error(self, set_name: str, error: str) -> None:
        """Handle ephemeris set download error."""
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)
        logger.error(f"Ephemeris set download error for {set_name}: {error}")
        self._show_toast(f"Ephemeris set download error: {error}", duration_ms=4000, preset="error")

    def _on_sync_ephemeris_file(self, file_key: str) -> None:
        """Handle ephemeris file sync button click."""
        # Sync ephemeris metadata to database
        from celestron_nexstar.gui.workers.download_workers import SyncEphemerisThread

        # Check if already syncing
        worker_key = f"ephemeris_sync_{file_key}"
        if worker_key in self._download_workers:
            return

        # Create and start worker
        worker = SyncEphemerisThread(force=False)
        worker.progress_updated.connect(
            lambda status, current, total: self._on_ephemeris_sync_progress(file_key, status, current, total)
        )
        worker.sync_complete.connect(
            lambda success, message: self._on_ephemeris_sync_complete(file_key, success, message)
        )
        worker.error_occurred.connect(lambda error: self._on_ephemeris_sync_error(file_key, error))
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_sync_ephemeris_all(self) -> None:
        """Sync ephemeris metadata for all files."""
        from celestron_nexstar.gui.workers.download_workers import SyncEphemerisThread

        worker_key = "ephemeris_sync_all"
        if worker_key in self._download_workers:
            return

        worker = SyncEphemerisThread(force=False)
        worker.progress_updated.connect(
            lambda status, current, total: self._on_ephemeris_sync_progress("all", status, current, total)
        )
        worker.sync_complete.connect(lambda success, message: self._on_ephemeris_sync_complete("all", success, message))
        worker.error_occurred.connect(lambda error: self._on_ephemeris_sync_error("all", error))
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_ephemeris_sync_progress(self, file_key: str, status: str, current: int, total: int) -> None:
        """Handle ephemeris sync progress update."""
        # Update progress bar and status label
        if total > 0:
            percentage = int((current / total) * 100) if total > 0 else 0
            self.ephemeris_progress.setValue(percentage)
            self.ephemeris_progress.setVisible(True)
        else:
            self.ephemeris_progress.setValue(0)
            self.ephemeris_progress.setVisible(True)

        if status:
            self.ephemeris_status_label.setText(status)
            self.ephemeris_status_label.setVisible(True)

    def _on_ephemeris_sync_complete(self, file_key: str, success: bool, message: str) -> None:
        """Handle ephemeris sync completion."""
        # Hide progress bar and status label
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)

        if success:
            logger.info(f"Ephemeris sync complete: {message}")
            # Reload ephemeris info to update table
            self._load_ephemeris_info()
            self._show_toast(f"Ephemeris synced: {message}", duration_ms=3000, preset="success")
        else:
            logger.error(f"Ephemeris sync failed: {message}")
            self._show_toast(f"Ephemeris sync failed: {message}", duration_ms=4000, preset="error")

    def _on_ephemeris_sync_error(self, file_key: str, error: str) -> None:
        """Handle ephemeris sync error."""
        # Hide progress bar and status label
        self.ephemeris_progress.setVisible(False)
        self.ephemeris_status_label.setVisible(False)

        logger.error(f"Ephemeris sync error for {file_key}: {error}")
        self._show_toast(f"Ephemeris sync error: {error}", duration_ms=4000, preset="error")

    def _on_download_celestial_data(self, source_id: str) -> None:
        """Handle celestial data download button click."""
        from celestron_nexstar.gui.workers.download_workers import DownloadCelestialDataThread

        # Check if already downloading
        worker_key = f"celestial_download_{source_id}"
        if worker_key in self._download_workers:
            return

        # Get source name for display (remove "Celestial Data - " prefix if present)
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id

        # Show progress bar
        self.celestial_data_progress.setVisible(True)
        self.celestial_data_progress.setRange(0, 100)
        self.celestial_data_progress.setValue(0)
        self.celestial_data_status_label.setText(f"Downloading {source_name}...")

        # Create and start worker
        worker = DownloadCelestialDataThread(source_id, force=False)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_celestial_download_progress(source_id, status, current, total)

        def on_complete(success: bool, message: str) -> None:
            self._on_celestial_download_complete(source_id, success, message)
            self._download_workers.pop(worker_key, None)
            self.celestial_data_progress.setVisible(False)

        def on_error(error: str) -> None:
            self._on_celestial_download_error(source_id, error)

        worker.progress_updated.connect(on_progress)
        worker.download_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_celestial_download_progress(self, source_id: str, status: str, current: int, total: int) -> None:
        """Handle celestial data download progress update."""
        if total > 0:
            self.celestial_data_progress.setRange(0, total)
            self.celestial_data_progress.setValue(current)
            self.celestial_data_status_label.setText(f"{status} ({current}/{total})")
        else:
            self.celestial_data_status_label.setText(status)

    def _on_celestial_download_complete(self, source_id: str, success: bool, message: str) -> None:
        """Handle celestial data download completion."""
        if success:
            self.celestial_data_status_label.setText(f"✓ {message}")
            logger.info(f"Celestial data download complete: {message}")
            # Reload celestial data info to update table (this will enable import buttons)
            self._load_celestial_data_info()
            # Get source name for toast
            from celestron_nexstar.cli.data_import import DATA_SOURCES

            source = DATA_SOURCES.get(source_id)
            source_name = source.name.replace("Celestial Data - ", "") if source else source_id
            self._show_toast(f"{source_name} downloaded successfully", duration_ms=3000)
        else:
            self.celestial_data_status_label.setText(f"✗ Download failed: {message}")
            logger.error(f"Celestial data download failed: {message}")
            from celestron_nexstar.cli.data_import import DATA_SOURCES

            source = DATA_SOURCES.get(source_id)
            source_name = source.name.replace("Celestial Data - ", "") if source else source_id
            self._show_toast(f"{source_name} download failed: {message}", duration_ms=4000)

    def _on_celestial_download_error(self, source_id: str, error: str) -> None:
        """Handle celestial data download error."""
        self.celestial_data_status_label.setText(f"✗ Error: {error}")
        logger.error(f"Celestial data download error for {source_id}: {error}")
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id
        self._show_toast(f"{source_name} download error: {error}", duration_ms=4000)

    def _truncate_celestial_data(self, source_id: str) -> int:
        """
        Truncate (delete) existing data for a celestial data source from the database.

        Args:
            source_id: The source ID to truncate

        Returns:
            Number of records deleted
        """
        try:
            import json

            from sqlalchemy import delete, func, select

            from celestron_nexstar.api.database.models import (
                AsterismModel,
                ClusterModel,
                ConstellationModel,
                GalaxyModel,
                NebulaModel,
                StarModel,
                get_db_session,
            )
            from celestron_nexstar.cli.data_import import get_cache_dir

            deleted_count = 0
            cache_dir = get_cache_dir()

            def _load_source_names(filename: str) -> set[str]:
                """Load object names from a cached GeoJSON FeatureCollection."""
                path = cache_dir / filename
                if not path.exists():
                    return set()
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    names: set[str] = set()
                    for feat in data.get("features", []):
                        if not isinstance(feat, dict):
                            continue
                        props = feat.get("properties", {})
                        if not isinstance(props, dict):
                            continue
                        name = (
                            props.get("name")
                            or props.get("n")
                            or props.get("Name")
                            or props.get("id")
                            or props.get("designation")
                        )
                        if isinstance(name, str) and name.strip():
                            names.add(name.strip())
                    return names
                except Exception:
                    return set()

            with get_db_session() as session:
                if source_id == "celestial_constellations":
                    # Delete all constellations (CASCADE will handle related foreign keys)
                    count = session.scalar(select(func.count(ConstellationModel.id)))
                    session.execute(delete(ConstellationModel))
                    deleted_count = count or 0

                elif source_id == "celestial_asterisms":
                    # Delete all asterisms (CASCADE will handle related foreign keys)
                    count = session.scalar(select(func.count(AsterismModel.id)))
                    session.execute(delete(AsterismModel))
                    deleted_count = count or 0

                elif source_id.startswith("celestial_stars"):
                    # Delete stars with celestial_stars catalog
                    count = session.scalar(
                        select(func.count(StarModel.id)).where(StarModel.catalog == "celestial_stars")
                    )
                    session.execute(delete(StarModel).where(StarModel.catalog == "celestial_stars"))
                    deleted_count = count or 0

                elif source_id.startswith("celestial_dsos"):
                    # Delete DSOs from galaxies, nebulae, and clusters
                    galaxy_count = session.scalar(
                        select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "celestial_dsos")
                    )
                    nebula_count = session.scalar(
                        select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "celestial_dsos")
                    )
                    cluster_count = session.scalar(
                        select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "celestial_dsos")
                    )
                    session.execute(delete(GalaxyModel).where(GalaxyModel.catalog == "celestial_dsos"))
                    session.execute(delete(NebulaModel).where(NebulaModel.catalog == "celestial_dsos"))
                    session.execute(delete(ClusterModel).where(ClusterModel.catalog == "celestial_dsos"))
                    deleted_count = (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0)

                elif source_id == "celestial_messier":
                    # Clean import: delete matching objects across all relevant tables.
                    messier_names = _load_source_names("messier.min.geojson")
                    if messier_names:
                        galaxy_count = session.scalar(
                            select(func.count(GalaxyModel.id)).where(GalaxyModel.name.in_(messier_names))
                        )
                        nebula_count = session.scalar(
                            select(func.count(NebulaModel.id)).where(NebulaModel.name.in_(messier_names))
                        )
                        cluster_count = session.scalar(
                            select(func.count(ClusterModel.id)).where(ClusterModel.name.in_(messier_names))
                        )
                        star_count = session.scalar(
                            select(func.count(StarModel.id)).where(StarModel.name.in_(messier_names))
                        )
                        session.execute(delete(GalaxyModel).where(GalaxyModel.name.in_(messier_names)))
                        session.execute(delete(NebulaModel).where(NebulaModel.name.in_(messier_names)))
                        session.execute(delete(ClusterModel).where(ClusterModel.name.in_(messier_names)))
                        session.execute(delete(StarModel).where(StarModel.name.in_(messier_names)))
                        deleted_count = (
                            (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                        )
                    else:
                        # Fallback: delete any explicitly tagged rows
                        galaxy_count = session.scalar(
                            select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "messier")
                        )
                        nebula_count = session.scalar(
                            select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "messier")
                        )
                        cluster_count = session.scalar(
                            select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "messier")
                        )
                        star_count = session.scalar(
                            select(func.count(StarModel.id)).where(StarModel.catalog == "messier")
                        )
                        session.execute(delete(GalaxyModel).where(GalaxyModel.catalog == "messier"))
                        session.execute(delete(NebulaModel).where(NebulaModel.catalog == "messier"))
                        session.execute(delete(ClusterModel).where(ClusterModel.catalog == "messier"))
                        session.execute(delete(StarModel).where(StarModel.catalog == "messier"))
                        deleted_count = (
                            (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                        )

                elif source_id == "celestial_local_group":
                    # Clean import: delete matching objects across all relevant tables.
                    lg_names = _load_source_names("lg.min.geojson")
                    if lg_names:
                        galaxy_count = session.scalar(
                            select(func.count(GalaxyModel.id)).where(GalaxyModel.name.in_(lg_names))
                        )
                        nebula_count = session.scalar(
                            select(func.count(NebulaModel.id)).where(NebulaModel.name.in_(lg_names))
                        )
                        cluster_count = session.scalar(
                            select(func.count(ClusterModel.id)).where(ClusterModel.name.in_(lg_names))
                        )
                        star_count = session.scalar(
                            select(func.count(StarModel.id)).where(StarModel.name.in_(lg_names))
                        )
                        session.execute(delete(GalaxyModel).where(GalaxyModel.name.in_(lg_names)))
                        session.execute(delete(NebulaModel).where(NebulaModel.name.in_(lg_names)))
                        session.execute(delete(ClusterModel).where(ClusterModel.name.in_(lg_names)))
                        session.execute(delete(StarModel).where(StarModel.name.in_(lg_names)))
                        deleted_count = (
                            (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                        )
                    else:
                        galaxy_count = session.scalar(
                            select(func.count(GalaxyModel.id)).where(GalaxyModel.catalog == "local_group")
                        )
                        nebula_count = session.scalar(
                            select(func.count(NebulaModel.id)).where(NebulaModel.catalog == "local_group")
                        )
                        cluster_count = session.scalar(
                            select(func.count(ClusterModel.id)).where(ClusterModel.catalog == "local_group")
                        )
                        star_count = session.scalar(
                            select(func.count(StarModel.id)).where(StarModel.catalog == "local_group")
                        )
                        session.execute(delete(GalaxyModel).where(GalaxyModel.catalog == "local_group"))
                        session.execute(delete(NebulaModel).where(NebulaModel.catalog == "local_group"))
                        session.execute(delete(ClusterModel).where(ClusterModel.catalog == "local_group"))
                        session.execute(delete(StarModel).where(StarModel.catalog == "local_group"))
                        deleted_count = (
                            (galaxy_count or 0) + (nebula_count or 0) + (cluster_count or 0) + (star_count or 0)
                        )

                session.commit()

            return deleted_count

        except Exception as e:
            logger.error(f"Error truncating celestial data for {source_id}: {e}", exc_info=True)
            raise

    def _on_import_all_celestial_data(self) -> None:
        """Import all celestial data sources in the correct order."""
        # Define import order (dependencies first)
        self._import_all_queue = [
            "celestial_constellations",
            "celestial_asterisms",
            "celestial_dsos_20",
            "celestial_local_group",
            "celestial_stars_14",
            "celestial_messier",
        ]
        self._import_all_in_progress = True
        self._import_all_total = len(self._import_all_queue)
        self._import_all_completed = 0

        # Disable the import all button during the process
        if hasattr(self, "import_all_celestial_btn"):
            self.import_all_celestial_btn.setEnabled(False)

        # Start the first import
        self._import_next_celestial_source()

    def _import_next_celestial_source(self) -> None:
        """Import the next source in the import all queue."""
        if not self._import_all_queue:
            # All imports complete
            self._import_all_in_progress = False
            self._import_all_completed = 0
            if hasattr(self, "import_all_celestial_btn"):
                self.import_all_celestial_btn.setEnabled(True)
            self.celestial_data_progress.setVisible(False)
            self.celestial_data_status_label.setText("✓ All celestial data imported successfully")
            self._show_toast(
                f"Successfully imported all {self._import_all_total} celestial data sources",
                duration_ms=4000,
                preset="success",
            )
            # Reload the table to update all counts
            self._load_celestial_data_info()
            return

        # Get next source
        source_id = self._import_all_queue.pop(0)
        self._import_all_completed += 1

        # Update status to show progress
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id
        self.celestial_data_status_label.setText(
            f"Importing {self._import_all_completed}/{self._import_all_total}: {source_name}..."
        )

        # Start import with custom completion handler
        self._start_celestial_import_with_callback(source_id, self._on_import_all_source_complete)

    def _on_import_all_source_complete(
        self, source_id: str, success: bool, message: str, imported: int, skipped: int
    ) -> None:
        """Handle completion of a single source during import all."""
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id

        if success:
            logger.info(f"Import all: {source_name} complete - {imported:,} imported, {skipped:,} skipped")
            # Continue to next source
            self._import_next_celestial_source()
        else:
            # Import failed - stop the sequence
            self._import_all_queue.clear()
            self._import_all_in_progress = False
            self._import_all_completed = 0
            if hasattr(self, "import_all_celestial_btn"):
                self.import_all_celestial_btn.setEnabled(True)
            self.celestial_data_progress.setVisible(False)
            self.celestial_data_status_label.setText(f"✗ Import failed at {source_name}: {message}")
            self._show_toast(
                f"Import all stopped: {source_name} failed - {message}",
                duration_ms=5000,
                preset="error",
            )
            logger.error(f"Import all stopped at {source_name}: {message}")

    def _start_celestial_import_with_callback(
        self, source_id: str, completion_callback: Callable | None = None
    ) -> None:
        """Start a celestial data import with an optional custom completion callback."""
        from celestron_nexstar.gui.workers.download_workers import ImportCelestialDataThread

        # Check if already importing
        worker_key = f"celestial_import_{source_id}"
        if worker_key in self._download_workers:
            return

        # Get source name for display
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id

        # Truncate existing data before importing (clean import)
        try:
            if not self._import_all_in_progress:
                # Only show truncate message if not in import all mode
                self.celestial_data_status_label.setText(f"Truncating existing {source_name} data...")
            deleted_count = self._truncate_celestial_data(source_id)
            if deleted_count > 0:
                logger.info(f"Truncated {deleted_count:,} existing records for {source_name}")
        except Exception as e:
            logger.error(f"Error truncating data for {source_id}: {e}", exc_info=True)
            self._show_toast(
                f"Error truncating existing data: {e}",
                duration_ms=4000,
                preset="error",
            )
            return

        # Show progress bar
        self.celestial_data_progress.setVisible(True)
        self.celestial_data_progress.setRange(0, 100)
        self.celestial_data_progress.setValue(0)

        # Create and start worker
        worker = ImportCelestialDataThread(source_id, mag_limit=15.0)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_celestial_import_progress(source_id, status, current, total)

        def on_status_message(message: str) -> None:
            self._on_celestial_import_status_message(message)

        def on_complete(worker_source_id: str, success: bool, message: str, imported: int, skipped: int) -> None:
            # Call custom callback if provided, otherwise use default handler
            if completion_callback:
                completion_callback(worker_source_id, success, message, imported, skipped)
            else:
                self._on_celestial_import_complete(worker_source_id, success, message, imported, skipped)
            self._download_workers.pop(worker_key, None)
            if not self._import_all_in_progress:
                # Only hide progress if not in import all mode (import all manages progress bar)
                self.celestial_data_progress.setVisible(False)

        def on_error(worker_source_id: str, error: str) -> None:
            self._on_celestial_import_error(worker_source_id, error)

        worker.progress_updated.connect(on_progress)
        worker.status_message.connect(on_status_message)
        worker.import_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_import_celestial_data(self, source_id: str) -> None:
        """Handle celestial data import button click."""
        # Use the helper method with default completion handler
        self._start_celestial_import_with_callback(source_id, completion_callback=None)

    def _on_delete_celestial_data(self, source_id: str) -> None:
        """Handle celestial data delete button click."""
        from PySide6.QtWidgets import QMessageBox

        from celestron_nexstar.cli.data_import import DATA_SOURCES, get_cache_dir

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete all imported data for {source_name}?\n\n"
            "This will:\n"
            "- Delete all imported data from the database (with CASCADE)\n"
            "- Delete the downloaded GeoJSON file\n"
            "- Disable the import button",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Use the truncate helper to delete data
            deleted_count = self._truncate_celestial_data(source_id)

            # Delete the GeoJSON file
            filename_map = {
                "celestial_stars_14": "stars.14.min.geojson",
                "celestial_dsos_20": "dsos.20.min.geojson",
                "celestial_messier": "messier.min.geojson",
                "celestial_asterisms": "asterisms.min.geojson",
                "celestial_constellations": "constellations.min.geojson",
                "celestial_local_group": "lg.min.geojson",
            }

            cache_dir = get_cache_dir()
            filename = filename_map.get(source_id)
            if filename:
                cache_path = cache_dir / filename
                if cache_path.exists():
                    cache_path.unlink()

            # Reload the table to update UI
            self._load_celestial_data_info()

            # Show success message
            self._show_toast(
                f"Deleted {deleted_count:,} objects from {source_name}",
                duration_ms=3000,
                preset="success",
            )
            logger.info(f"Deleted {deleted_count:,} objects from {source_name}")

        except Exception as e:
            logger.error(f"Error deleting celestial data for {source_id}: {e}", exc_info=True)
            self._show_toast(
                f"Error deleting {source_name}: {e}",
                duration_ms=4000,
                preset="error",
            )

    def _on_reimport_seed_data(self, seed_id: str) -> None:
        """Handle seed data re-import button click."""
        from celestron_nexstar.api.database.database_seeder import (
            seed_bortle_characteristics,
            seed_comets,
            seed_constellations,
            seed_dark_sky_sites,
            seed_eclipses,
            seed_meteor_showers,
            seed_moons,
            seed_planets,
            seed_space_events,
            seed_star_name_mappings,
            seed_variable_stars,
        )
        from celestron_nexstar.api.database.models import get_db_session

        # Map seed IDs to functions and display names
        seed_map = {
            "star_name_mappings": (seed_star_name_mappings, "Star Name Mappings"),
            "meteor_showers": (seed_meteor_showers, "Meteor Showers"),
            "constellations": (seed_constellations, "Constellations"),
            "planets": (seed_planets, "Planets"),
            "moons": (seed_moons, "Moons"),
            "dark_sky_sites": (seed_dark_sky_sites, "Dark Sky Sites"),
            "space_events": (seed_space_events, "Space Events"),
            "bortle_characteristics": (seed_bortle_characteristics, "Bortle Characteristics"),
            "variable_stars": (seed_variable_stars, "Variable Stars"),
            "comets": (seed_comets, "Comets"),
            "eclipses": (seed_eclipses, "Eclipses"),
            "asteroids": (seed_asteroids, "Asteroids"),
        }

        if seed_id not in seed_map:
            logger.error(f"Unknown seed ID: {seed_id}")
            self._show_toast(f"Unknown seed data type: {seed_id}", duration_ms=3000, preset="error")
            return

        seed_func, display_name = seed_map[seed_id]

        # Show progress
        self.seed_data_progress.setVisible(True)
        self.seed_data_progress.setRange(0, 0)  # Indeterminate
        self.seed_data_status_label.setText(f"Re-importing {display_name}...")

        try:
            with get_db_session() as session:
                # Re-import with force=True to clear existing data
                added = seed_func(session, force=True)
                session.commit()

            # Reload the table to update counts
            self._load_seed_data_info()

            # Show success message
            self._show_toast(
                f"Re-imported {display_name}: {added:,} records",
                duration_ms=3000,
                preset="success",
            )
            logger.info(f"Re-imported {display_name}: {added:,} records")

        except Exception as e:
            logger.error(f"Error re-importing {display_name}: {e}", exc_info=True)
            self._show_toast(
                f"Error re-importing {display_name}: {e}",
                duration_ms=4000,
                preset="error",
            )
        finally:
            self.seed_data_progress.setVisible(False)
            self.seed_data_status_label.clear()

    def _on_reimport_all_seed_data(self) -> None:
        """Re-import all seed datasets in sequence."""
        seed_ids = [
            "star_name_mappings",
            "meteor_showers",
            "constellations",
            "planets",
            "moons",
            "dark_sky_sites",
            "space_events",
            "bortle_characteristics",
            "variable_stars",
        ]

        self.seed_data_progress.setVisible(True)
        self.seed_data_progress.setRange(0, 0)  # Indeterminate
        self.seed_data_status_label.setText("Re-importing all seed data...")

        try:
            for sid in seed_ids:
                self._on_reimport_seed_data(sid)
            self._show_toast("All seed data re-imported.", duration_ms=4000, preset="success")
        except Exception as e:
            logger.error(f"Error importing all seed data: {e}", exc_info=True)
            self._show_toast(f"Error importing all seed data: {e}", duration_ms=4000, preset="error")
        finally:
            self.seed_data_progress.setVisible(False)
            self.seed_data_status_label.clear()

    def _on_download_mpc_comets(self) -> None:
        """Handle MPC comet download."""
        from celestron_nexstar.gui.workers.download_workers import DownloadMPCCometsThread

        worker_key = "mpc_comets_download"
        if worker_key in self._download_workers:
            return

        self.solar_system_progress.setVisible(True)
        self.solar_system_progress.setRange(0, 0)
        self.solar_system_status.setText("Fetching MPC comet elements...")

        worker = DownloadMPCCometsThread()

        def on_progress(status: str, current: int, total: int) -> None:
            self.solar_system_status.setText(status)
            if total > 0:
                self.solar_system_progress.setRange(0, total)
                self.solar_system_progress.setValue(current)

        def on_complete(success: bool, message: str) -> None:
            self._download_workers.pop(worker_key, None)
            self.solar_system_progress.setVisible(False)
            if success:
                self.solar_system_status.setText(f"✓ {message}")
                self._show_toast(message, preset="success", duration_ms=3000)
                self._load_solar_system_info()
            else:
                self.solar_system_status.setText(f"✗ {message}")
                self._show_toast(message, preset="error", duration_ms=4000)

        def on_error(error: str) -> None:
            self._download_workers.pop(worker_key, None)
            self.solar_system_progress.setVisible(False)
            self.solar_system_status.setText(f"✗ {error}")
            self._show_toast(f"Download error: {error}", preset="error", duration_ms=4000)

        worker.progress_updated.connect(on_progress)
        worker.download_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_import_mpc_comets(self) -> None:
        """Import MPC comet seed data into DB."""
        from celestron_nexstar.api.database.database_seeder import seed_comets
        from celestron_nexstar.api.database.models import get_db_session

        self.solar_system_progress.setVisible(True)
        self.solar_system_progress.setRange(0, 0)
        self.solar_system_status.setText("Importing MPC comets...")

        try:
            with get_db_session() as session:
                added = seed_comets(session, force=True)
                session.commit()
            self._load_solar_system_info()
            self._show_toast(f"Imported {added} MPC comets", preset="success", duration_ms=3000)
            self.solar_system_status.setText(f"✓ Imported {added} comets")
        except Exception as e:
            logger.error(f"Error importing MPC comets: {e}", exc_info=True)
            self._show_toast(f"Error importing MPC comets: {e}", preset="error", duration_ms=4000)
            self.solar_system_status.setText(f"✗ Error importing: {e}")
        finally:
            self.solar_system_progress.setVisible(False)

    def _on_import_eclipses_solar(self) -> None:
        """Import eclipses seed data from Solar System tab."""
        from celestron_nexstar.api.database.database_seeder import seed_eclipses
        from celestron_nexstar.api.database.models import get_db_session

        self.solar_system_progress.setVisible(True)
        self.solar_system_progress.setRange(0, 0)
        self.solar_system_status.setText("Importing eclipses...")

        try:
            with get_db_session() as session:
                added = seed_eclipses(session, force=True)
                session.commit()
            self._load_solar_system_info()
            self._show_toast(f"Imported {added} eclipses", preset="success", duration_ms=3000)
            self.solar_system_status.setText(f"✓ Imported {added} eclipses")
        except Exception as e:
            logger.error(f"Error importing eclipses: {e}", exc_info=True)
            self._show_toast(f"Error importing eclipses: {e}", preset="error", duration_ms=4000)
            self.solar_system_status.setText(f"✗ Error importing: {e}")
        finally:
            self.solar_system_progress.setVisible(False)

    def _on_manage_spks(self) -> None:
        """Open the SPK management dialog."""
        from celestron_nexstar.gui.dialogs.spk_manager_dialog import SPKManagerDialog

        dialog = SPKManagerDialog(self)
        dialog.exec()
        # Refresh solar system info after dialog closes
        self._load_solar_system_info()

    def _on_celestial_import_progress(self, source_id: str, status: str, current: int, total: int) -> None:
        """Handle celestial data import progress update."""
        if total > 0:
            self.celestial_data_progress.setRange(0, total)
            self.celestial_data_progress.setValue(current)
            self.celestial_data_status_label.setText(f"{status} ({current}%)")
        else:
            self.celestial_data_status_label.setText(status)

    def _on_celestial_import_status_message(self, message: str) -> None:
        """Handle celestial data import status message (show toast notification)."""
        self._show_toast(message, duration_ms=3000)

    def _show_toast(self, message: str, duration_ms: int = 2000, preset: str | None = None) -> None:
        """Show a temporary toast notification using pyqt-toast-notification.

        Args:
            message: The message to display
            duration_ms: How long to show the toast (milliseconds)
            preset: Optional preset type ('success', 'error', 'warning', 'info').
                    If None, auto-detects from message content.
        """
        try:
            from pyqttoast import Toast, ToastPreset  # type: ignore[import-untyped]

            # Auto-detect preset from message if not provided
            if preset is None:
                message_lower = message.lower()
                if "failed" in message_lower or "error" in message_lower:
                    preset = "error"
                elif (
                    "complete" in message_lower
                    or "success" in message_lower
                    or "downloaded" in message_lower
                    or "imported" in message_lower
                ):
                    preset = "success"
                elif "warning" in message_lower:
                    preset = "warning"
                else:
                    preset = "info"

            # Detect dark mode
            is_dark = self._is_dark_theme()

            # Ensure dialog is shown and has valid geometry before creating toast
            if not self.isVisible():
                self.show()
            # Ensure dialog has valid size
            if self.width() < 100 or self.height() < 100:
                self.resize(900, 700)

            # Use QTimer to delay toast creation to ensure dialog is fully laid out
            import logging

            from PySide6.QtCore import QTimer

            def create_toast() -> None:
                # Double-check geometry is valid
                if self.width() < 100 or self.height() < 100:
                    return

                # Suppress Qt warnings about window positioning
                # The warning is harmless - Qt will use the primary screen
                qt_logger = logging.getLogger("qt.qpa.window")
                original_level = qt_logger.level
                qt_logger.setLevel(logging.ERROR)

                try:
                    # Use the settings dialog itself as parent (it's a modal dialog)
                    toast = Toast(self)
                    toast.setDuration(duration_ms)
                    toast.setText(message)

                    # Apply preset based on type, with theme-aware dark variants
                    # Note: ToastPreset may not have all presets, so we handle them carefully
                    preset_map = {
                        "success": ToastPreset.SUCCESS_DARK if is_dark else ToastPreset.SUCCESS,
                        "error": ToastPreset.ERROR_DARK if is_dark else ToastPreset.ERROR,
                        "warning": ToastPreset.WARNING_DARK if is_dark else ToastPreset.WARNING,
                        "info": ToastPreset.INFORMATION_DARK if is_dark else ToastPreset.INFORMATION,
                    }

                    # Try to apply the preset, with fallback if dark variant doesn't exist
                    if preset in preset_map:
                        try:
                            toast.applyPreset(preset_map[preset])
                        except (AttributeError, TypeError):
                            # Fallback to light variant if dark variant doesn't exist
                            fallback_map = {
                                "success": ToastPreset.SUCCESS,
                                "error": ToastPreset.ERROR,
                                "warning": ToastPreset.WARNING,
                            }
                            if preset in fallback_map:
                                toast.applyPreset(fallback_map[preset])
                            else:
                                toast.applyPreset(ToastPreset.SUCCESS)
                    else:
                        # For unknown presets, use SUCCESS as default
                        toast.applyPreset(ToastPreset.SUCCESS_DARK if is_dark else ToastPreset.SUCCESS)

                    # Don't try to set position via library API - it seems to cause issues
                    # We'll position it manually after it's shown

                    # Show toast first
                    toast.show()

                    # Position toast manually after it's shown at top right of screen
                    def position_toast() -> None:
                        if toast.isVisible():
                            from PySide6.QtGui import QGuiApplication

                            # Ensure toast has valid geometry
                            toast.adjustSize()
                            toast_width = toast.width()

                            # Get primary screen geometry
                            screen = QGuiApplication.primaryScreen()
                            if screen:
                                screen_geometry = screen.availableGeometry()
                                # Position at top right of screen
                                x = screen_geometry.right() - toast_width - 20  # 20px from right edge
                                y = screen_geometry.top() + 20  # 20px from top
                            else:
                                # Fallback if no screen
                                x = 800 - toast_width - 20
                                y = 20

                            # Ensure coordinates are valid (non-negative)
                            x = max(0, x)
                            y = max(0, y)

                            # Move toast to calculated position (global screen coordinates)
                            # Since we're using global coordinates, we need to make the toast a window
                            toast.setWindowFlags(toast.windowFlags() | 0x00000080)  # Qt::Window (top-level window)
                            toast.move(x, y)

                    # Position after a short delay to ensure toast is fully laid out
                    QTimer.singleShot(50, position_toast)

                finally:
                    # Restore original logging level
                    qt_logger.setLevel(original_level)

            # Delay toast creation slightly to ensure dialog geometry is established
            QTimer.singleShot(100, create_toast)
        except ImportError:
            # Fallback to simple QLabel if library not available
            from PySide6.QtCore import QTimer
            from PySide6.QtGui import QGuiApplication, QPalette
            from PySide6.QtWidgets import QLabel

            # Truncate long messages to prevent toast from being too wide
            max_length = 80
            display_message = message
            if len(message) > max_length:
                display_message = message[: max_length - 3] + "..."

            # Detect theme for toast styling
            is_dark = False
            app = QGuiApplication.instance()
            if app and isinstance(app, QGuiApplication):
                palette = app.palette()
                window_color = palette.color(QPalette.ColorRole.Window)
                brightness = window_color.lightness()
                is_dark = brightness < 128

            # Create a label for the toast
            toast = QLabel(display_message, self)
            # Theme-aware toast styling
            bg_color = "rgba(0, 0, 0, 200)" if not is_dark else "rgba(255, 255, 255, 200)"
            text_color = "white" if not is_dark else "black"
            toast.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {bg_color};
                    color: {text_color};
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 12px;
                }}
            """
            )
            toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toast.adjustSize()

            # Ensure dialog is visible and has valid geometry
            if not self.isVisible():
                self.show()
            if self.width() < 100 or self.height() < 100:
                self.resize(900, 700)

            # Position toast in the center of the dialog
            # Ensure coordinates are within valid screen bounds
            dialog_width = max(self.width(), 100)
            dialog_height = max(self.height(), 100)
            toast_width = toast.width()
            toast_height = toast.height()

            x = max(0, (dialog_width - toast_width) // 2)
            y = max(0, dialog_height // 3)

            # Ensure toast doesn't go outside dialog bounds
            x = min(x, dialog_width - toast_width - 10)
            y = min(y, dialog_height - toast_height - 10)

            toast.move(x, y)
            toast.raise_()
            toast.show()

            # Hide toast after duration
            QTimer.singleShot(duration_ms, toast.deleteLater)

    def _on_celestial_import_complete(
        self, source_id: str, success: bool, message: str, imported: int, skipped: int
    ) -> None:
        """Handle celestial data import completion."""
        if success:
            self.celestial_data_status_label.setText(f"✓ {message}")
            logger.info(f"Celestial data import complete: {message}")
            # Reload celestial data info to update table
            self._load_celestial_data_info()
            # Toast is already shown via status_message signal, but show completion toast too
            from celestron_nexstar.cli.data_import import DATA_SOURCES

            source = DATA_SOURCES.get(source_id)
            source_name = source.name.replace("Celestial Data - ", "") if source else source_id
            # Ensure imported and skipped are integers (safety check)
            imported_int = int(imported) if isinstance(imported, (int, float)) else 0
            skipped_int = int(skipped) if isinstance(skipped, (int, float)) else 0
            self._show_toast(
                f"{source_name} import complete: {imported_int:,} imported, {skipped_int:,} skipped", duration_ms=3000
            )
        else:
            self.celestial_data_status_label.setText(f"✗ Import failed: {message}")
            logger.error(f"Celestial data import failed: {message}")
            from celestron_nexstar.cli.data_import import DATA_SOURCES

            source = DATA_SOURCES.get(source_id)
            source_name = source.name.replace("Celestial Data - ", "") if source else source_id
            self._show_toast(f"{source_name} import failed: {message}", duration_ms=4000)

    def _on_celestial_import_error(self, source_id: str, error: str) -> None:
        """Handle celestial data import error."""
        self.celestial_data_status_label.setText(f"✗ Error: {error}")
        logger.error(f"Celestial data import error for {source_id}: {error}")
        from celestron_nexstar.cli.data_import import DATA_SOURCES

        source = DATA_SOURCES.get(source_id)
        source_name = source.name.replace("Celestial Data - ", "") if source else source_id
        self._show_toast(f"{source_name} import error: {error}", duration_ms=4000)

    def _on_download_wds(self) -> None:
        """Handle WDS catalog download button click."""
        from celestron_nexstar.gui.workers.download_workers import DownloadWDSCatalogThread

        # Check if already downloading
        worker_key = "wds_download"
        if worker_key in self._download_workers:
            return

        # Determine whether this is a re-download
        try:
            from celestron_nexstar.cli.data_import import get_cache_dir

            wds_exists = (get_cache_dir() / "wdsweb_summ2.txt").exists()
        except Exception:
            wds_exists = False

        # Show progress bar
        self.wds_progress.setVisible(True)
        self.wds_progress.setRange(0, 100)
        self.wds_progress.setValue(0)
        self.wds_download_btn.setEnabled(False)
        self.wds_status_label.setText("Downloading...")

        # Create and start worker
        worker = DownloadWDSCatalogThread(force=wds_exists)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_wds_download_progress(status, current, total)

        def on_complete(success: bool, message: str) -> None:
            self._on_wds_download_complete(success, message)
            self._download_workers.pop(worker_key, None)
            self.wds_progress.setVisible(False)
            self.wds_download_btn.setEnabled(True)

        def on_error(error: str) -> None:
            self._on_wds_download_error(error)

        worker.progress_updated.connect(on_progress)
        worker.download_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_wds_download_progress(self, status: str, current: int, total: int) -> None:
        """Handle WDS download progress update."""
        if total > 0:
            self.wds_progress.setRange(0, total)
            self.wds_progress.setValue(current)
            self.wds_status_label.setText(f"{status} ({current}/{total})")
        else:
            self.wds_status_label.setText(status)

    def _on_wds_download_complete(self, success: bool, message: str) -> None:
        """Handle WDS download completion."""
        if success:
            self.wds_status_label.setText(f"✓ {message}")
            # Reload WDS info to enable import button
            self._load_wds_info()
            self._show_toast("WDS catalog downloaded successfully", duration_ms=3000)
        else:
            self.wds_status_label.setText(f"✗ Download failed: {message}")
            self._show_toast(f"WDS catalog download failed: {message}", duration_ms=4000)

    def _on_wds_download_error(self, error: str) -> None:
        """Handle WDS download error."""
        self.wds_status_label.setText(f"✗ Error: {error}")
        self._show_toast(f"WDS download error: {error}", duration_ms=4000)

    def _on_import_wds(self) -> None:
        """Handle WDS catalog import button click."""
        from celestron_nexstar.gui.workers.download_workers import ImportWDSCatalogThread

        # Check if already importing
        worker_key = "wds_import"
        if worker_key in self._download_workers:
            return

        # Truncate existing WDS rows for clean import
        try:
            from sqlalchemy import delete

            from celestron_nexstar.api.database.models import DoubleStarModel, get_db_session

            self.wds_status_label.setText("Truncating existing WDS data...")
            with get_db_session() as session:
                session.execute(delete(DoubleStarModel).where(DoubleStarModel.catalog == "wds"))
                session.commit()
        except Exception as e:
            logger.error(f"Error truncating WDS data: {e}", exc_info=True)
            self.wds_status_label.setText(f"✗ Error truncating WDS data: {e}")
            self._show_toast(f"WDS truncate failed: {e}", duration_ms=4000)
            return

        # Show progress bar
        self.wds_progress.setVisible(True)
        self.wds_progress.setRange(0, 100)
        self.wds_progress.setValue(0)
        self.wds_import_btn.setEnabled(False)
        self.wds_status_label.setText("Importing...")

        # Create and start worker
        worker = ImportWDSCatalogThread(mag_limit=15.0)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_wds_import_progress(status, current, total)

        def on_status_message(message: str) -> None:
            self._on_wds_import_status_message(message)

        def on_complete(success: bool, message: str, imported: int, skipped: int) -> None:
            self._on_wds_import_complete(success, message, imported, skipped)
            self._download_workers.pop(worker_key, None)
            self.wds_progress.setVisible(False)
            self.wds_import_btn.setEnabled(True)
            self._load_wds_info()

        def on_error(error: str) -> None:
            self._on_wds_import_error(error)

        worker.progress_updated.connect(on_progress)
        worker.status_message.connect(on_status_message)
        worker.import_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_wds_import_progress(self, status: str, current: int, total: int) -> None:
        """Handle WDS import progress update."""
        if total > 0:
            self.wds_progress.setRange(0, total)
            self.wds_progress.setValue(current)
            self.wds_status_label.setText(f"{status} ({current}%)")
        else:
            self.wds_status_label.setText(status)

    def _on_wds_import_status_message(self, message: str) -> None:
        """Handle WDS import status message (show toast notification)."""
        self._show_toast(message, duration_ms=3000)

    def _on_wds_import_complete(self, success: bool, message: str, imported: int, skipped: int) -> None:
        """Handle WDS import completion."""
        if success:
            self.wds_status_label.setText(f"✓ {message}")
            # Toast is already shown via status_message signal, but show completion toast too
            self._show_toast(
                f"WDS import complete: {int(imported):,} imported, {int(skipped):,} skipped", duration_ms=3000
            )
        else:
            self.wds_status_label.setText(f"✗ Import failed: {message}")
            self._show_toast(f"WDS import failed: {message}", duration_ms=4000)

    def _on_wds_import_error(self, error: str) -> None:
        """Handle WDS import error."""
        self.wds_status_label.setText(f"✗ Error: {error}")
        self._show_toast(f"WDS import error: {error}", duration_ms=4000)

    def _on_download_light_pollution(self, region: str) -> None:
        """Handle light pollution download button click."""
        from celestron_nexstar.gui.workers.download_workers import DownloadLightPollutionThread

        # Check if already downloading
        worker_key = f"light_pollution_download_{region}"
        if worker_key in self._download_workers:
            return

        # Show progress bar
        self.light_pollution_progress.setVisible(True)
        self.light_pollution_progress.setRange(0, 100)
        self.light_pollution_progress.setValue(0)
        self.light_pollution_status_label.setText(f"Downloading {region}...")

        # Create and start worker
        worker = DownloadLightPollutionThread(region, force=False)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_light_pollution_download_progress(region, status, current, total)

        def on_complete(success: bool, message: str) -> None:
            self._on_light_pollution_download_complete(region, success, message)
            self._download_workers.pop(worker_key, None)
            self.light_pollution_progress.setVisible(False)

        def on_error(error: str) -> None:
            self._on_light_pollution_download_error(region, error)

        worker.progress_updated.connect(on_progress)
        worker.download_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_light_pollution_download_progress(self, region: str, status: str, current: int, total: int) -> None:
        """Handle light pollution download progress update."""
        if total > 0:
            self.light_pollution_progress.setRange(0, total)
            self.light_pollution_progress.setValue(current)
            self.light_pollution_status_label.setText(f"{status} ({current}/{total})")
        else:
            self.light_pollution_status_label.setText(status)

    def _on_light_pollution_download_complete(self, region: str, success: bool, message: str) -> None:
        """Handle light pollution download completion."""
        if success:
            self.light_pollution_status_label.setText(f"✓ {message}")
            logger.info(f"Light pollution download complete: {message}")
            # Reload light pollution info to update table (enable import button)
            self._load_light_pollution_info()
            self._show_toast(f"Light pollution data ({region}) downloaded successfully", duration_ms=3000)
        else:
            self.light_pollution_status_label.setText(f"✗ Download failed: {message}")
            logger.error(f"Light pollution download failed: {message}")
            self._show_toast(f"Light pollution download failed ({region}): {message}", duration_ms=4000)

    def _on_light_pollution_download_error(self, region: str, error: str) -> None:
        """Handle light pollution download error."""
        self.light_pollution_status_label.setText(f"✗ Error: {error}")
        logger.error(f"Light pollution download error for {region}: {error}")
        self._show_toast(f"Light pollution download error ({region}): {error}", duration_ms=4000)

    def _on_import_light_pollution(self, region: str) -> None:
        """Handle light pollution import button click."""
        from celestron_nexstar.gui.workers.download_workers import ImportLightPollutionThread

        # Check if already importing
        worker_key = f"light_pollution_import_{region}"
        if worker_key in self._download_workers:
            return

        # Show progress bar
        self.light_pollution_progress.setVisible(True)
        self.light_pollution_progress.setRange(0, 100)
        self.light_pollution_progress.setValue(0)
        self.light_pollution_status_label.setText(f"Importing {region}...")

        # Create and start worker
        worker = ImportLightPollutionThread(region, grid_resolution=0.1)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_light_pollution_import_progress(region, status, current, total)

        def on_complete(sig_region: str, success: bool, message: str, points: int) -> None:
            # Signal emits (region, success, message, points); prefer emitted region
            self._on_light_pollution_import_complete(sig_region, success, message, points)
            self._download_workers.pop(worker_key, None)
            self.light_pollution_progress.setVisible(False)

        def on_error(error: str) -> None:
            self._on_light_pollution_import_error(region, error)

        worker.progress_updated.connect(on_progress)
        worker.import_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_light_pollution_import_progress(self, region: str, status: str, current: int, total: int) -> None:
        """Handle light pollution import progress update."""
        if total > 0:
            self.light_pollution_progress.setRange(0, total)
            self.light_pollution_progress.setValue(current)
            self.light_pollution_status_label.setText(f"{status} ({current}%)")
        else:
            self.light_pollution_status_label.setText(status)

    def _on_light_pollution_import_complete(self, region: str, success: bool, message: str, points: int) -> None:
        """Handle light pollution import completion."""
        if success:
            self.light_pollution_status_label.setText(f"✓ {message}")
            logger.info(f"Light pollution import complete: {message}")
            # Reload light pollution info to update table
            self._load_light_pollution_info()
            self._show_toast(
                f"Light pollution ({region}) import complete: {int(points):,} points imported", duration_ms=3000
            )
        else:
            self.light_pollution_status_label.setText(f"✗ Import failed: {message}")
            logger.error(f"Light pollution import failed: {message}")
            self._show_toast(f"Light pollution import failed ({region}): {message}", duration_ms=4000)

    def _on_light_pollution_import_error(self, region: str, error: str) -> None:
        """Handle light pollution import error."""
        self.light_pollution_status_label.setText(f"✗ Error: {error}")
        logger.error(f"Light pollution import error for {region}: {error}")
        self._show_toast(f"Light pollution import error ({region}): {error}", duration_ms=4000)

    def _on_import_custom_yaml(self) -> None:
        """Handle custom YAML import button click."""
        from celestron_nexstar.gui.workers.download_workers import ImportCustomYAMLThread

        # Check if already importing
        worker_key = "custom_yaml_import"
        if worker_key in self._download_workers:
            return

        # Show progress bar
        self.custom_yaml_progress.setVisible(True)
        self.custom_yaml_progress.setRange(0, 100)
        self.custom_yaml_progress.setValue(0)
        self.custom_yaml_import_btn.setEnabled(False)

        # Create and start worker
        worker = ImportCustomYAMLThread(mag_limit=99.0)

        def on_progress(status: str, current: int, total: int) -> None:
            if total > 0:
                self.custom_yaml_progress.setRange(0, total)
                self.custom_yaml_progress.setValue(current)

        def on_complete(success: bool, message: str, imported: int, skipped: int) -> None:
            self._on_custom_yaml_import_complete(success, message, imported, skipped)
            self._download_workers.pop(worker_key, None)
            self.custom_yaml_progress.setVisible(False)
            self.custom_yaml_import_btn.setEnabled(True)

        def on_error(error: str) -> None:
            self._on_custom_yaml_import_error(error)

        worker.progress_updated.connect(on_progress)
        worker.import_complete.connect(on_complete)
        worker.error_occurred.connect(on_error)
        worker.finished.connect(lambda: self._download_workers.pop(worker_key, None))

        self._download_workers[worker_key] = worker
        worker.start()

    def _on_custom_yaml_import_complete(self, success: bool, message: str, imported: int, skipped: int) -> None:
        """Handle custom YAML import completion."""
        from PySide6.QtWidgets import QMessageBox

        if success:
            QMessageBox.information(self, "Import Complete", f"Successfully imported custom YAML catalog!\n\n{message}")
            self._show_toast(
                f"Custom YAML import complete: {int(imported):,} imported, {int(skipped):,} skipped", duration_ms=3000
            )
        else:
            QMessageBox.warning(self, "Import Failed", f"Failed to import custom YAML catalog:\n\n{message}")
            self._show_toast(f"Custom YAML import failed: {message}", duration_ms=4000)

    def _on_custom_yaml_import_error(self, error: str) -> None:
        """Handle custom YAML import error."""
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self, "Import Error", f"Error importing custom YAML catalog:\n\n{error}")
