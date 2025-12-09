"""
Dialog to display and manage application settings.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
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
        self._font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Create tabs
        self._create_config_tab()
        self._create_ephemeris_tab()
        self._create_celestial_data_tab()
        self._create_custom_yaml_tab()
        self._create_wds_tab()
        self._create_light_pollution_tab()
        self._create_location_tab()
        self._create_optics_tab()
        self._create_time_tab()
        self._create_data_tab()

        # Track active download workers
        self._download_workers: dict[str, object] = {}

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data
        self._load_config_info()
        self._load_ephemeris_info()
        self._load_celestial_data_info()
        self._load_custom_yaml_info()
        self._load_wds_info()
        self._load_light_pollution_info()
        self._load_location_info()
        self._load_optics_info()
        self._load_time_info()
        self._load_data_info()

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
            "header": "#00bcd4" if is_dark else "#00838f",
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _create_config_tab(self) -> None:
        """Create the config tab."""
        config_text = QTextEdit()
        config_text.setReadOnly(True)
        config_text.setAcceptRichText(True)
        config_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.config_text = config_text
        self.tab_widget.addTab(config_text, "Config")

    def _create_ephemeris_tab(self) -> None:
        """Create the ephemeris tab with download functionality."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Ephemeris Files")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Table for ephemeris files
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["File", "Status", "Size", "Coverage", "Download", "Sync"])
        table.horizontalHeader().setStretchLastSection(False)
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
        self.tab_widget.addTab(location_text, "Location")

    def _create_optics_tab(self) -> None:
        """Create the optics tab."""
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
        self.tab_widget.addTab(optics_text, "Optics")

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
        header = QLabel("Celestial Data Sources")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)

        # Table for celestial data sources
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Source", "Description", "Status", "Size", "Download", "Import"])
        table.horizontalHeader().setStretchLastSection(False)
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
        table.horizontalHeader().setStretchLastSection(False)
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
        data_text = QTextEdit()
        data_text.setReadOnly(True)
        data_text.setAcceptRichText(True)
        data_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.data_text = data_text
        self.tab_widget.addTab(data_text, "Data")

    def _load_config_info(self) -> None:
        """Load general configuration information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.optics import get_current_configuration

            optical_config = get_current_configuration()
            observer_location = get_observer_location()

            # Get config file paths
            config_dir = Path.home() / ".config" / "celestron-nexstar"
            optical_config_path = config_dir / "optical_config.json"
            location_config_path = config_dir / "observer_location.json"

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Configuration</span></p>"
            )

            # Optical Configuration
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Optical Configuration</span></p>"
            )
            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Setting</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Telescope</td><td style='color: {colors['text']};'>{optical_config.telescope.display_name}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Aperture</td><td style='color: {colors['text']};'>{optical_config.telescope.aperture_mm:.0f}mm ({optical_config.telescope.aperture_inches:.1f}\")</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Focal Length</td><td style='color: {colors['text']};'>{optical_config.telescope.focal_length_mm:.0f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Focal Ratio</td><td style='color: {colors['text']};'>f/{optical_config.telescope.focal_ratio:.1f}</td></tr>"
            )
            eyepiece_name = optical_config.eyepiece.name or f"{optical_config.eyepiece.focal_length_mm:.0f}mm"
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Eyepiece</td><td style='color: {colors['text']};'>{eyepiece_name}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Eyepiece Focal Length</td><td style='color: {colors['text']};'>{optical_config.eyepiece.focal_length_mm:.0f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Apparent FOV</td><td style='color: {colors['text']};'>{optical_config.eyepiece.apparent_fov_deg:.0f}°</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Magnification</td><td style='color: {colors['text']};'>{optical_config.magnification:.0f}x</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Exit Pupil</td><td style='color: {colors['text']};'>{optical_config.exit_pupil_mm:.1f}mm</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>True FOV</td><td style='color: {colors['text']};'>{optical_config.true_fov_deg:.2f}° ({optical_config.true_fov_arcmin:.1f}')</td></tr>"
            )
            html_content.append("</table>")

            # Observer Location
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Observer Location</span></p>"
            )
            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Setting</b></td><td style='color: {colors['green']};'><b>Value</b></td></tr>"
            )
            if observer_location.name:
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Location Name</td><td style='color: {colors['text']};'>{observer_location.name}</td></tr>"
                )
            lat_dir = "N" if observer_location.latitude >= 0 else "S"
            lon_dir = "E" if observer_location.longitude >= 0 else "W"
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Latitude</td><td style='color: {colors['text']};'>{abs(observer_location.latitude):.4f}°{lat_dir}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Longitude</td><td style='color: {colors['text']};'>{abs(observer_location.longitude):.4f}°{lon_dir}</td></tr>"
            )
            if observer_location.elevation:
                html_content.append(
                    f"<tr><td style='color: {colors['text']};'>Elevation</td><td style='color: {colors['text']};'>{observer_location.elevation:.0f} m above sea level</td></tr>"
                )
            html_content.append("</table>")

            # Config File Paths
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Configuration Files</span></p>"
            )
            html_content.append("<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>")
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>File</b></td><td style='color: {colors['green']};'><b>Path</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Config Directory</td><td style='color: {colors['text_dim']};'>{config_dir}</td></tr>"
            )
            exists_marker = (
                f"<span style='color: {colors['green']};'>✓</span>"
                if optical_config_path.exists()
                else f"<span style='color: {colors['text_dim']};'>(not saved)</span>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Optical Config</td><td style='color: {colors['text_dim']};'>{optical_config_path} {exists_marker}</td></tr>"
            )
            exists_marker = (
                f"<span style='color: {colors['green']};'>✓</span>"
                if location_config_path.exists()
                else f"<span style='color: {colors['text_dim']};'>(not saved)</span>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Location Config</td><td style='color: {colors['text_dim']};'>{location_config_path} {exists_marker}</td></tr>"
            )
            html_content.append("</table>")

            self.config_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading config info: {e}", exc_info=True)
            self.config_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load configuration: {e}</span></p>"
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

                # Sync button (syncs metadata to database)
                sync_btn = QPushButton("Sync")
                sync_btn.setFixedWidth(80)
                sync_btn.setEnabled(installed)  # Only enable if file is downloaded
                sync_btn.setToolTip(
                    "Sync ephemeris file metadata from NAIF to the database. "
                    "This updates file information, coverage dates, and descriptions. "
                    "Only available after the file has been downloaded."
                )
                sync_btn.clicked.connect(lambda checked, key=file_key: self._on_sync_ephemeris_file(key))
                table.setCellWidget(row, 5, sync_btn)

            table.resizeColumnsToContents()

        except Exception as e:
            logger.error(f"Error loading ephemeris info: {e}", exc_info=True)

    def _load_celestial_data_info(self) -> None:
        """Load celestial data sources into table."""
        try:
            from celestron_nexstar.cli.data_import import DATA_SOURCES, get_cache_dir

            # Filter to only celestial data sources
            celestial_sources = {k: v for k, v in DATA_SOURCES.items() if k.startswith("celestial_")}

            table = self.celestial_data_table
            table.setRowCount(len(celestial_sources))

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

            cache_dir = get_cache_dir()

            for row, (source_id, source) in enumerate(sorted(celestial_sources.items())):
                # Source name (remove "Celestial Data - " prefix if present)
                display_name = source.name.replace("Celestial Data - ", "")
                table.setItem(row, 0, QTableWidgetItem(display_name))

                # Description
                desc = source.description[:60] + "..." if len(source.description) > 60 else source.description
                table.setItem(row, 1, QTableWidgetItem(desc))

                # Status
                filename = filename_map.get(source_id)
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

                # Size (estimated)
                size_text = f"~{source.objects_available:,} objects"
                table.setItem(row, 3, QTableWidgetItem(size_text))

                # Download button
                download_btn = QPushButton("Download")
                download_btn.setFixedWidth(100)
                if filename and cache_path.exists():
                    download_btn.setText("Re-download")
                download_btn.clicked.connect(lambda checked, sid=source_id: self._on_download_celestial_data(sid))
                table.setCellWidget(row, 4, download_btn)

                # Import button
                import_btn = QPushButton("Import")
                import_btn.setFixedWidth(80)
                import_btn.setEnabled(filename and cache_path.exists())
                import_btn.clicked.connect(lambda checked, sid=source_id: self._on_import_celestial_data(sid))
                table.setCellWidget(row, 5, import_btn)

            table.resizeColumnsToContents()

            # Clear status label
            self.celestial_data_status_label.clear()

        except Exception as e:
            logger.error(f"Error loading celestial data info: {e}", exc_info=True)
            self.celestial_data_status_label.setText(f"Error: {e}")

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
            from celestron_nexstar.cli.data_import import get_cache_dir

            cache_dir = get_cache_dir()
            wds_path = cache_dir / "wdsweb_summ2.txt"

            info_text = "<b>Washington Double Star Catalog (WDS)</b><br><br>"
            info_text += f"<b>Location:</b> {wds_path}<br><br>"

            if wds_path.exists():
                size_mb = wds_path.stat().st_size / (1024 * 1024)
                info_text += f"<span style='color: green;'>✓ Downloaded ({size_mb:.1f} MB)</span><br><br>"
                info_text += "The WDS catalog is ready to import into the database."
                # Enable import button
                self.wds_import_btn.setEnabled(True)
            else:
                info_text += "<span style='color: orange;'>Not downloaded</span><br><br>"
                info_text += "Click 'Download WDS Catalog' to download from US Naval Observatory."
                # Disable import button
                self.wds_import_btn.setEnabled(False)

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
                        # Count grid points for this region (we'll use a simple query)
                        # Note: The database doesn't store region names, so we'll check if data exists
                        result = session.scalar(select(func.count(LightPollutionGridModel.id)))
                        if result and result > 0:
                            # We have some data, but can't distinguish regions easily
                            # For now, just show if we have any data
                            region_counts[region] = result if region == "north_america" else 0
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
                f"<tr><td style='color: {colors['text']};'>Elevation</td><td style='color: {colors['text']};'>{location.elevation:.0f} m above sea level</td></tr>"
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
                f"<p style='color: {colors['text_dim']}; margin-top: 15px;'>To change location, use the CLI command: <code>nexstar location set</code></p>"
            )

            self.location_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading location info: {e}", exc_info=True)
            self.location_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load location information: {e}</span></p>"
            )

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

            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-top: 15px;'>To change optics configuration, use the CLI command: <code>nexstar optics config</code></p>"
            )

            self.optics_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading optics info: {e}", exc_info=True)
            self.optics_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load optics information: {e}</span></p>"
            )

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
            from pathlib import Path

            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory

            config_dir = Path.home() / ".config" / "celestron-nexstar"
            eph_dir = get_ephemeris_directory()

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Data Directories</span></p>"
            )

            html_content.append(
                "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 15px;'>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Directory</b></td><td style='color: {colors['green']};'><b>Path</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Configuration</td><td style='color: {colors['text_dim']};'>{config_dir}</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Ephemeris</td><td style='color: {colors['text_dim']};'>{eph_dir}</td></tr>"
            )
            html_content.append("</table>")

            # Check directory sizes
            config_size = (
                sum(f.stat().st_size for f in config_dir.rglob("*") if f.is_file()) if config_dir.exists() else 0
            )
            eph_size = sum(f.stat().st_size for f in eph_dir.rglob("*") if f.is_file()) if eph_dir.exists() else 0

            html_content.append(
                f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Directory Sizes</span></p>"
            )
            html_content.append("<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>")
            html_content.append(
                f"<tr><td style='color: {colors['cyan']};'><b>Directory</b></td><td style='color: {colors['green']};'><b>Size</b></td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Configuration</td><td style='color: {colors['text']};'>{config_size / 1024:.1f} KB</td></tr>"
            )
            html_content.append(
                f"<tr><td style='color: {colors['text']};'>Ephemeris</td><td style='color: {colors['text']};'>{eph_size / 1024 / 1024:.1f} MB</td></tr>"
            )
            html_content.append("</table>")

            self.data_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading data info: {e}", exc_info=True)
            self.data_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load data information: {e}</span></p>"
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

    def _on_import_celestial_data(self, source_id: str) -> None:
        """Handle celestial data import button click."""
        from celestron_nexstar.gui.workers.download_workers import ImportCelestialDataThread

        # Check if already importing
        worker_key = f"celestial_import_{source_id}"
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
        self.celestial_data_status_label.setText(f"Importing {source_name}...")

        # Create and start worker
        worker = ImportCelestialDataThread(source_id, mag_limit=15.0)

        def on_progress(status: str, current: int, total: int) -> None:
            self._on_celestial_import_progress(source_id, status, current, total)

        def on_status_message(message: str) -> None:
            self._on_celestial_import_status_message(message)

        def on_complete(worker_source_id: str, success: bool, message: str, imported: int, skipped: int) -> None:
            self._on_celestial_import_complete(worker_source_id, success, message, imported, skipped)
            self._download_workers.pop(worker_key, None)
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

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            # Check palette brightness
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _show_toast(self, message: str, duration_ms: int = 2000, preset: str | None = None) -> None:
        """Show a temporary toast notification using pyqt-toast-notification.

        Args:
            message: The message to display
            duration_ms: How long to show the toast (milliseconds)
            preset: Optional preset type ('success', 'error', 'warning', 'info').
                    If None, auto-detects from message content.
        """
        try:
            from pyqttoast import Toast, ToastPreset

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
                            from PySide6.QtWidgets import QApplication

                            # Ensure toast has valid geometry
                            toast.adjustSize()
                            toast_width = toast.width()

                            # Get primary screen geometry
                            app = QApplication.instance()
                            if app:
                                screen = app.primaryScreen()
                                if screen:
                                    screen_geometry = screen.availableGeometry()
                                    # Position at top right of screen
                                    x = screen_geometry.right() - toast_width - 20  # 20px from right edge
                                    y = screen_geometry.top() + 20  # 20px from top
                                else:
                                    # Fallback if no screen
                                    x = 800 - toast_width - 20
                                    y = 20
                            else:
                                # Fallback if no app
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

        # Show progress bar
        self.wds_progress.setVisible(True)
        self.wds_progress.setRange(0, 100)
        self.wds_progress.setValue(0)
        self.wds_download_btn.setEnabled(False)
        self.wds_status_label.setText("Downloading...")

        # Create and start worker
        worker = DownloadWDSCatalogThread(force=False)

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

        def on_complete(success: bool, message: str, points: int) -> None:
            self._on_light_pollution_import_complete(region, success, message, points)
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
