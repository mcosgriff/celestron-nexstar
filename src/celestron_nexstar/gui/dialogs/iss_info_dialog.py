"""
Dialog to display International Space Station (ISS) pass predictions.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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


class ISSInfoDialog(QDialog):
    """Dialog to display ISS pass predictions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the ISS info dialog."""
        super().__init__(parent)
        self.setWindowTitle("ISS Visible Passes")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)  # Match ObjectInfoDialog width

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
        font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Store font family for later use
        self._font_family = font_family

        # Set initial stylesheet (will be updated with theme colors in _load_iss_info)
        self.info_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {font_family};
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

        # Load ISS information
        self._load_iss_info()

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
            "header": "#00bcd4" if is_dark else "#00838f",  # Cyan for ISS
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _load_iss_info(self) -> None:
        """Load ISS pass information from the API and format it for display."""
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
            from celestron_nexstar.api.events.iss_tracking import ISSPass, get_iss_passes_cached
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.telescope.compass import azimuth_to_compass_8point

            # Get location
            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            # Default parameters matching CLI
            days = 7
            min_altitude = 10.0
            now = datetime.now(UTC)

            # Get ISS passes (async call)
            async def _get_passes() -> list[ISSPass]:
                return await get_iss_passes_cached(
                    location.latitude,
                    location.longitude,
                    start_time=now,
                    days=days,
                    min_altitude_deg=min_altitude,
                    db_session=None,
                )

            iss_passes = asyncio.run(_get_passes())

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>"
                f"h1 {{ color: {colors['header']}; font-size: 16pt; font-weight: bold; margin-top: 0; margin-bottom: 0.5em; }}"
                f"h2 {{ color: {colors['header']}; margin-top: 1.5em; margin-bottom: 0.5em; }}"
                f"p {{ margin-top: 0.5em; margin-bottom: 0.5em; }}"
                f"</style>"
            )

            location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"
            html_content.append(f"<h1>ISS Visible Passes for {location_name}</h1>")
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>Searching next {days} days (minimum altitude: {min_altitude:.0f}°)</p>"
            )

            if not iss_passes:
                html_content.append(
                    f"<p><span style='color: {colors['yellow']};'>No visible ISS passes found in the forecast period.</span></p>"
                )
                self.info_text.setHtml("\n".join(html_content))
                return

            # Filter to visible passes only
            visible_passes = [p for p in iss_passes if p.is_visible]

            if not visible_passes:
                html_content.append(
                    f"<p><span style='color: {colors['yellow']};'>No visible ISS passes (all passes are in Earth's shadow).</span></p>"
                )
                self.info_text.setHtml("\n".join(html_content))
                return

            # Display passes in a table
            html_content.append("<h2>Upcoming Passes</h2>")
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Date</th>"
                "<th style='padding: 8px; text-align: left;'>Rise Time</th>"
                "<th style='padding: 8px; text-align: right;'>Max Alt</th>"
                "<th style='padding: 8px; text-align: left;'>Path</th>"
                "<th style='padding: 8px; text-align: right;'>Duration</th>"
                "<th style='padding: 8px; text-align: left;'>Quality</th>"
                "</tr>"
            )

            for iss_pass in visible_passes[:20]:  # Show first 20
                rise_time_str = self._format_local_time(iss_pass.rise_time, location.latitude, location.longitude)
                date_str = iss_pass.rise_time.strftime("%a %b %d")

                # Format path
                path_str = (
                    f"{azimuth_to_compass_8point(iss_pass.rise_azimuth_deg)} → "
                    f"{azimuth_to_compass_8point(iss_pass.max_azimuth_deg)} ({iss_pass.max_altitude_deg:.0f}°) → "
                    f"{azimuth_to_compass_8point(iss_pass.set_azimuth_deg)}"
                )

                duration_min = iss_pass.duration_seconds // 60
                duration_str = f"{duration_min}m {iss_pass.duration_seconds % 60}s"

                quality = iss_pass.quality_rating
                # Color code quality
                if quality == "Excellent" or quality == "Very Good":
                    quality_color = colors["green"]
                elif quality == "Good":
                    quality_color = colors["cyan"]
                elif quality == "Fair":
                    quality_color = colors["yellow"]
                else:
                    quality_color = colors["text_dim"]

                html_content.append(
                    f"<tr style='border-bottom: 1px solid #444;'>"
                    f"<td style='padding: 6px; color: {colors['cyan']};'>{date_str}</td>"
                    f"<td style='padding: 6px; color: {colors['green']};'>{rise_time_str}</td>"
                    f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{iss_pass.max_altitude_deg:.0f}°</td>"
                    f"<td style='padding: 6px; color: {colors['text_dim']};'>{path_str}</td>"
                    f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{duration_str}</td>"
                    f"<td style='padding: 6px; color: {quality_color};'>{quality}</td>"
                    "</tr>"
                )

            html_content.append("</table>")

            # Show details for excellent passes
            excellent_passes = [p for p in visible_passes if p.max_altitude_deg >= 50]
            if excellent_passes:
                html_content.append("<h2>Excellent Passes (≥50° altitude)</h2>")
                for iss_pass in excellent_passes[:5]:  # Show first 5
                    rise_time_str = self._format_local_time(iss_pass.rise_time, location.latitude, location.longitude)
                    max_time_str = self._format_local_time(iss_pass.max_time, location.latitude, location.longitude)
                    set_time_str = self._format_local_time(iss_pass.set_time, location.latitude, location.longitude)

                    date_str = iss_pass.rise_time.strftime("%B %d, %Y")
                    duration_min = iss_pass.duration_seconds // 60
                    quality = iss_pass.quality_rating

                    html_content.append(f"<p><b style='color: {colors['header']};'>{date_str}</b></p>")
                    html_content.append(
                        f"<ul style='margin-left: 20px; color: {colors['text']}; margin-top: 0.5em; margin-bottom: 1em;'>"
                        f"<li>Rise: {rise_time_str} from {azimuth_to_compass_8point(iss_pass.rise_azimuth_deg)}</li>"
                        f"<li>Max: {max_time_str} at {iss_pass.max_altitude_deg:.0f}° ({azimuth_to_compass_8point(iss_pass.max_azimuth_deg)})</li>"
                        f"<li>Set: {set_time_str} to {azimuth_to_compass_8point(iss_pass.set_azimuth_deg)}</li>"
                        f"<li>Duration: {duration_min}m {iss_pass.duration_seconds % 60}s | Quality: <span style='color: {colors['green']};'>{quality}</span></li>"
                        "</ul>"
                    )

            # Viewing tips
            html_content.append("<h2>Viewing Tips</h2>")
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']}; margin-top: 0.5em;'>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>ISS is visible to naked eye - no equipment needed!</li>"
                f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>Look for a bright, steady-moving 'star' crossing the sky</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>ISS moves faster than aircraft and doesn't blink</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Best viewing when sky is dark and ISS is sunlit</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Use binoculars for enhanced viewing of solar panels</li>"
                "</ul>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-top: 1em;'>💡 Tip: ISS is the third brightest object in the sky (after Sun and Moon)!</p>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading ISS info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load ISS pass information: {e}</span></p>"
            )
