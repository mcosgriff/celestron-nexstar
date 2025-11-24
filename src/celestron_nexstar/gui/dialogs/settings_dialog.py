"""
Dialog to display and manage application settings.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
        self._create_location_tab()
        self._create_optics_tab()
        self._create_time_tab()
        self._create_data_tab()

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data
        self._load_config_info()
        self._load_ephemeris_info()
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
        """Create the ephemeris tab."""
        ephemeris_text = QTextEdit()
        ephemeris_text.setReadOnly(True)
        ephemeris_text.setAcceptRichText(True)
        ephemeris_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        self.ephemeris_text = ephemeris_text
        self.tab_widget.addTab(ephemeris_text, "Ephemeris")

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
        """Load ephemeris file information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.ephemeris.ephemeris_manager import get_ephemeris_directory, get_installed_files

            eph_dir = get_ephemeris_directory()
            installed_files = get_installed_files()

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 10px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Ephemeris Files</span></p>"
            )

            html_content.append(
                f"<p style='color: {colors['text']}; margin-bottom: 10px;'><b>Ephemeris Directory:</b> <span style='color: {colors['text_dim']};'>{eph_dir}</span></p>"
            )

            if installed_files:
                html_content.append(
                    f"<p><span style='color: {colors['header']}; font-weight: bold; font-size: 12pt;'>Installed Files</span></p>"
                )
                html_content.append(
                    "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse;'>"
                )
                html_content.append(
                    f"<tr><td style='color: {colors['cyan']};'><b>File</b></td><td style='color: {colors['green']};'><b>Size</b></td></tr>"
                )
                for _file_key, file_info, file_path in sorted(installed_files, key=lambda x: x[0]):
                    size_mb = (
                        file_info.size_mb
                        if hasattr(file_info, "size_mb")
                        else (file_path.stat().st_size / 1024 / 1024 if file_path.exists() else 0)
                    )
                    html_content.append(
                        f"<tr><td style='color: {colors['text']};'>{file_info.filename}</td><td style='color: {colors['text']};'>{size_mb:.1f} MB</td></tr>"
                    )
                html_content.append("</table>")
            else:
                html_content.append(f"<p style='color: {colors['text_dim']};'>No ephemeris files installed.</p>")
                html_content.append(
                    f"<p style='color: {colors['text']};'>Use the CLI command <code>nexstar data ephemeris download</code> to install ephemeris files.</p>"
                )

            self.ephemeris_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading ephemeris info: {e}", exc_info=True)
            self.ephemeris_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load ephemeris information: {e}</span></p>"
            )

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
