"""
Dialog to display space weather information.
"""

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class SpaceWeatherInfoDialog(QDialog):
    """Dialog to display space weather information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the space weather info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Space Weather Conditions")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(800, 700)  # Set reasonable default size

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        self._font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Set initial stylesheet (will be updated with theme colors in _load_space_weather_info)
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load space weather information
        self._load_space_weather_info()

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
            "header": "#00bcd4" if is_dark else "#00838f",  # Cyan
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "bright_red": "#ef5350" if is_dark else "#d32f2f",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_scale(self, scale: Any, colors: dict[str, str]) -> tuple[str, str]:
        """Format NOAA scale for display."""
        if scale is None:
            return colors["text_dim"], "-"

        level = scale.level
        scale_type = scale.scale_type
        display_name = scale.display_name
        scale_display = f"{scale_type}{level} ({display_name})"

        if level == 0:
            return colors["green"], scale_display
        elif level <= 2:
            return colors["yellow"], scale_display
        elif level <= 3:
            return colors["red"], scale_display
        else:
            return colors["bright_red"], scale_display

    def _format_value(self, value: float | None, unit: str = "", precision: int = 1) -> str:
        """Format a value with unit, or show dash if None."""
        if value is None:
            return "-"
        return f"{value:.{precision}f}{unit}"

    def _load_space_weather_info(self) -> None:
        """Load space weather information from the API and format it for display."""
        colors = self._get_theme_colors()

        # Update stylesheet with theme-aware colors
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
            h2 {{
                color: {colors["header"]};
                margin-top: 1em;
                margin-bottom: 0.5em;
            }}
        """
        )

        try:
            import asyncio

            from celestron_nexstar.api.events.space_weather import get_space_weather_conditions

            # Run async function - this is a sync entry point, so asyncio.run() is safe
            conditions = asyncio.run(get_space_weather_conditions())

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
            )

            # Header
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Space Weather Conditions</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Data from NOAA Space Weather Prediction Center</p>"
            )
            html_content.append("<br>")

            # NOAA Scales Table
            html_content.append("<h2>NOAA Space Weather Scales</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Scale</th>"
                "<th style='padding: 8px; text-align: center;'>Level</th>"
                "<th style='padding: 8px; text-align: left;'>Description</th>"
                "</tr>"
            )

            # R-Scale
            r_color, r_display = self._format_scale(conditions.r_scale, colors)
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>R-Scale (Radio Blackouts)</td>"
                f"<td style='padding: 6px; text-align: center; color: {r_color}; font-weight: bold;'>{r_display}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>Solar flare impacts on radio communications</td>"
                "</tr>"
            )

            # S-Scale
            s_color, s_display = self._format_scale(conditions.s_scale, colors)
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>S-Scale (Radiation Storms)</td>"
                f"<td style='padding: 6px; text-align: center; color: {s_color}; font-weight: bold;'>{s_display}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>Solar radiation storm impacts</td>"
                "</tr>"
            )

            # G-Scale
            g_color, g_display = self._format_scale(conditions.g_scale, colors)
            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>G-Scale (Geomagnetic)</td>"
                f"<td style='padding: 6px; text-align: center; color: {g_color}; font-weight: bold;'>{g_display}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>Geomagnetic storm impacts on power grids, aurora</td>"
                "</tr>"
            )

            html_content.append("</table>")
            html_content.append("<br>")

            # Geomagnetic Activity
            html_content.append("<h2>Geomagnetic Activity</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Parameter</th>"
                "<th style='padding: 8px; text-align: right;'>Value</th>"
                "</tr>"
            )

            # Kp Index with color coding
            kp_value = self._format_value(conditions.kp_index, "", 1)
            kp_color = colors["text"]
            if conditions.kp_index is not None:
                if conditions.kp_index >= 7:
                    kp_color = colors["red"]
                elif conditions.kp_index >= 5:
                    kp_color = colors["yellow"]
                else:
                    kp_color = colors["green"]

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Kp Index</td>"
                f"<td style='padding: 6px; text-align: right; color: {kp_color}; font-weight: bold;'>{kp_value}</td>"
                "</tr>"
            )

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Ap Index</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{self._format_value(conditions.ap_index, '', 0)}</td>"
                "</tr>"
            )

            html_content.append("</table>")
            html_content.append("<br>")

            # Solar Wind
            html_content.append("<h2>Solar Wind</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Parameter</th>"
                "<th style='padding: 8px; text-align: right;'>Value</th>"
                "</tr>"
            )

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Speed</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{self._format_value(conditions.solar_wind_speed, ' km/s', 0)}</td>"
                "</tr>"
            )

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Magnetic Field (Bt)</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{self._format_value(conditions.solar_wind_bt, ' nT', 1)}</td>"
                "</tr>"
            )

            # Bz Component with color coding
            bz_value = self._format_value(conditions.solar_wind_bz, " nT", 1)
            bz_color = colors["text"]
            bz_note = ""
            if conditions.solar_wind_bz is not None:
                if conditions.solar_wind_bz < -5:
                    bz_color = colors["green"]
                    bz_note = " (favorable for aurora)"
                elif conditions.solar_wind_bz < 0:
                    bz_color = colors["yellow"]
                else:
                    bz_color = colors["text"]

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Bz Component</td>"
                f"<td style='padding: 6px; text-align: right; color: {bz_color};'>{bz_value}{bz_note}</td>"
                "</tr>"
            )

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>Density</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{self._format_value(conditions.solar_wind_density, ' particles/cm³', 1)}</td>"
                "</tr>"
            )

            html_content.append("</table>")
            html_content.append("<br>")

            # Solar Activity
            html_content.append("<h2>Solar Activity</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Parameter</th>"
                "<th style='padding: 8px; text-align: right;'>Value</th>"
                "</tr>"
            )

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>10.7cm Radio Flux</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{self._format_value(conditions.radio_flux_107, ' sfu', 1)}</td>"
                "</tr>"
            )

            xray_display = self._format_value(conditions.xray_flux, " W/m²", 2)
            if conditions.xray_class:
                xray_display = f"{conditions.xray_class} ({xray_display})"

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>X-ray Flux</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{xray_display}</td>"
                "</tr>"
            )

            html_content.append("</table>")
            html_content.append("<br>")

            # Alerts
            if conditions.alerts:
                html_content.append("<h2>Space Weather Alerts</h2>")
                html_content.append(
                    f"<div style='border: 2px solid {colors['yellow']}; padding: 10px; background-color: rgba(255, 193, 7, 0.1);'>"
                )
                html_content.append(
                    f"<p style='color: {colors['yellow']}; font-weight: bold; margin-top: 0;'>Active Alerts:</p>"
                )
                for alert in conditions.alerts:
                    html_content.append(f"<p style='color: {colors['yellow']}; margin: 5px 0;'>⚠ {alert}</p>")
                html_content.append("</div>")
                html_content.append("<br>")

            # Information panel
            html_content.append("<h2>Information</h2>")
            html_content.append(
                f"<div style='border: 1px solid {colors['text_dim']}; padding: 10px; background-color: rgba(158, 158, 158, 0.1);'>"
            )
            html_content.append(
                f"<p style='color: {colors['text']}; font-weight: bold; margin-top: 0;'>About NOAA Scales:</p>"
            )
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li>R-Scale: Radio blackouts from solar flares (R1-R5)</li>"
                f"<li>S-Scale: Solar radiation storms (S1-S5)</li>"
                f"<li>G-Scale: Geomagnetic storms (G1-G5)</li>"
                "</ul>"
            )
            html_content.append(f"<p style='color: {colors['text']}; font-weight: bold;'>Aurora Visibility:</p>")
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li>G3+ storms often produce visible aurora at mid-latitudes</li>"
                f"<li>Negative Bz values enhance aurora activity</li>"
                f"<li>Use 'nexstar aurora tonight' for detailed aurora forecast</li>"
                "</ul>"
            )
            html_content.append("</div>")
            html_content.append("<br>")

            # Last updated
            if conditions.last_updated:
                last_updated_str = conditions.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")
                html_content.append(f"<p style='color: {colors['text_dim']};'>Last updated: {last_updated_str}</p>")

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading space weather info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load space weather information: {e}</span></p>"
            )
