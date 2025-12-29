"""
Dialog to display asteroid visibility information.
"""

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


class AsteroidsInfoDialog(QDialog):
    """Dialog to display asteroid visibility information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the asteroids info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Asteroid Visibility")
        self.setMinimumWidth(625)
        self.setMinimumHeight(500)
        self.resize(625, 700)

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)

        # Get monospace font from application property
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        # Use the loaded font directly without fallback to avoid Qt font lookup warnings
        font_family = f"'{monospace_font}'" if monospace_font else "'Courier New'"

        self._font_family = font_family

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

        # Flag to track if content has been loaded (lazy loading)
        self._content_loaded = False

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Override showEvent to lazy load content on first display."""
        super().showEvent(event)
        if not self._content_loaded:
            self._load_asteroids_info()
            self._content_loaded = True

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
            "header": "#ff9800" if is_dark else "#e65100",  # Orange for asteroids
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "bright_green": "#81c784" if is_dark else "#66bb6a",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "orange": "#ff9800" if is_dark else "#e65100",
            "purple": "#9c27b0" if is_dark else "#7b1fa2",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _explain_magnitude(self, magnitude: float) -> str:
        """Provide brief explanation of magnitude value."""
        if magnitude < 1:
            return "very bright"
        elif magnitude < 3:
            return "bright"
        elif magnitude < 5:
            return "visible to naked eye"
        elif magnitude < 6:
            return "visible under dark skies"
        elif magnitude < 8:
            return "binoculars needed"
        else:
            return "telescope required"

    def _load_asteroids_info(self) -> None:
        """Load asteroid visibility information from the API and format it for display."""
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
            from celestron_nexstar.api.astronomy.asteroids import get_visible_asteroids
            from celestron_nexstar.api.database.models import get_db_session
            from celestron_nexstar.api.location.observer import get_observer_location

            # Get location
            location = get_observer_location()
            if not location:
                self.info_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            lat, lon = location.latitude, location.longitude
            location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

            # Default parameters
            max_magnitude = 12.0
            min_altitude = -5.0

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
            )

            # Header
            now = datetime.now(UTC)
            local_time_str = self._format_local_time(now, lat, lon)
            html_content.append(
                f"<p style='margin-bottom: 5px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Asteroid Visibility for {location_name}</span></p>"
            )
            html_content.append(
                f"<p style='color: {colors['text_dim']}; margin-bottom: 10px;'>Current time: {local_time_str}</p>"
            )

            # Load content
            content_parts = []

            with get_db_session() as db_session:
                asteroids = get_visible_asteroids(
                    db_session, location, max_magnitude=max_magnitude, min_altitude=min_altitude
                )

            if not asteroids:
                content_parts.append(
                    f"<p><span style='color: {colors['yellow']};'>No bright asteroids found in current sky.</span></p>"
                )
                content_parts.append(
                    f"<p style='color: {colors['text_dim']};'>Try checking during nighttime or seed more asteroids.</p>"
                )
            else:
                # Display asteroids in a table
                content_parts.append("<h2>Visible Asteroids</h2>")
                content_parts.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
                content_parts.append(
                    f"<tr style='background-color: {colors['header']}; color: white;'>"
                    "<th style='padding: 8px; text-align: left;'>Asteroid</th>"
                    "<th style='padding: 8px; text-align: left;'>Type</th>"
                    "<th style='padding: 8px; text-align: right;'>Magnitude</th>"
                    "<th style='padding: 8px; text-align: center;'>Visible</th>"
                    "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                    "<th style='padding: 8px; text-align: right;'>Elongation</th>"
                    "</tr>"
                )

                for vis in asteroids[:30]:  # Top 30
                    # Format asteroid name
                    asteroid_name = vis.asteroid.name or vis.asteroid.designation
                    if len(asteroid_name) > 20:
                        asteroid_name = asteroid_name[:20] + "..."

                    # Format type with color
                    atype = vis.asteroid.asteroid_type
                    if atype == "neo":
                        type_str = "NEO"
                        type_color = colors["red"]
                        type_style = f"color: {type_color}; font-weight: bold;"
                    elif atype == "dwarf_planet":
                        type_str = "Dwarf Planet"
                        type_color = colors["purple"]
                        type_style = f"color: {type_color};"
                    elif atype == "trojan":
                        type_str = "Trojan"
                        type_color = colors["orange"]
                        type_style = f"color: {type_color};"
                    elif atype == "centaur":
                        type_str = "Centaur"
                        type_color = colors["cyan"]
                        type_style = f"color: {type_color};"
                    elif atype == "tno":
                        type_str = "TNO"
                        type_color = colors["cyan"]
                        type_style = f"color: {type_color};"
                    else:
                        type_str = "Main Belt"
                        type_color = colors["text"]
                        type_style = f"color: {type_color};"

                    # Format magnitude with color and explanation
                    if vis.magnitude < 3.0:
                        mag_color = colors["bright_green"]
                        mag_style = f"color: {mag_color}; font-weight: bold;"
                    elif vis.magnitude < 6.0:
                        mag_color = colors["green"]
                        mag_style = f"color: {mag_color};"
                    elif vis.magnitude < 8.0:
                        mag_color = colors["yellow"]
                        mag_style = f"color: {mag_color};"
                    else:
                        mag_color = colors["text_dim"]
                        mag_style = f"color: {mag_color};"
                    mag_explanation = f" <span style='color: {colors['text_dim']}; font-size: 0.85em;'>({self._explain_magnitude(vis.magnitude)})</span>"

                    # Format visibility
                    if vis.is_visible:
                        visible_str = "✓ Yes"
                        visible_color = colors["green"]
                    else:
                        visible_str = "✗ No"
                        visible_color = colors["text_dim"]

                    # Format altitude
                    alt_str = f"{vis.altitude:.0f}°"

                    # Format elongation
                    elong = vis.elongation_deg or 0
                    if elong > 150:
                        elong_str = f"{elong:.0f}°"
                        elong_color = colors["bright_green"]
                        elong_note = " <span style='color: {}; font-size: 0.85em;'>(opposition)</span>".format(
                            colors["text_dim"]
                        )
                    elif elong < 30:
                        elong_str = f"{elong:.0f}°"
                        elong_color = colors["red"]
                        elong_note = ""
                    else:
                        elong_str = f"{elong:.0f}°"
                        elong_color = colors["text"]
                        elong_note = ""

                    content_parts.append(
                        f"<tr style='border-bottom: 1px solid #444;'>"
                        f"<td style='padding: 6px; color: {colors['cyan']};'>{asteroid_name}</td>"
                        f"<td style='padding: 6px; {type_style}'>{type_str}</td>"
                        f"<td style='padding: 6px; text-align: right; {mag_style}'>{vis.magnitude:.2f}{mag_explanation}</td>"
                        f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                        f"<td style='padding: 6px; text-align: right; color: {colors['text']}; font-size: 0.9em;'>{alt_str}</td>"
                        f"<td style='padding: 6px; text-align: right; color: {elong_color}; font-size: 0.9em;'>{elong_str}{elong_note}</td>"
                        "</tr>"
                    )

                content_parts.append("</table>")

                # Add helpful tips
                content_parts.append(
                    f"<p style='margin-top: 15px; color: {colors['text_dim']}; font-size: 0.9em;'>"
                    f"💡 <b>Tips:</b> Altitude shows how high the asteroid is in the sky. "
                    f"Magnitude indicates brightness - lower numbers are brighter. "
                    f"Elongation shows angular distance from the Sun - asteroids near opposition (>150°) are brightest.</p>"
                )

                # Show details for top visible asteroids
                visible_above = [v for v in asteroids if v.is_visible][:10]
                if visible_above:
                    content_parts.append("<h2>Asteroid Details</h2>")

                    for vis in visible_above:
                        # Format type
                        atype_display = vis.asteroid.asteroid_type.replace("_", " ").title()

                        content_parts.append(
                            f"<p><b style='color: {colors['header']};'>{vis.asteroid.display_name}</b> ({vis.asteroid.designation})</p>"
                        )

                        mag_explanation = self._explain_magnitude(vis.magnitude)
                        alt_str = f"{vis.altitude:.0f}°"

                        content_parts.append(
                            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                            f"<li>Type: {atype_display}</li>"
                            f"<li>Magnitude: {vis.magnitude:.2f} ({mag_explanation})</li>"
                            f"<li>Altitude: {alt_str}, Azimuth: {vis.azimuth:.0f}°</li>"
                        )

                        # Show RA/Dec if available
                        if vis.ra_hours is not None and vis.dec_degrees is not None:
                            ra_h = int(vis.ra_hours)
                            ra_m = int((vis.ra_hours - ra_h) * 60)
                            dec_sign = "+" if vis.dec_degrees >= 0 else ""
                            content_parts.append(
                                f"<li>Position: RA {ra_h}h {ra_m}m, Dec {dec_sign}{vis.dec_degrees:.1f}°</li>"
                            )

                        # Show elongation
                        if vis.elongation_deg is not None:
                            elong_desc = " (near opposition - brightest)" if vis.elongation_deg > 150 else ""
                            content_parts.append(f"<li>Elongation from Sun: {vis.elongation_deg:.0f}°{elong_desc}</li>")

                        # Show distances
                        if vis.helio_distance_au is not None and vis.geo_distance_au is not None:
                            content_parts.append(
                                f"<li>Distance: {vis.helio_distance_au:.2f} AU from Sun, {vis.geo_distance_au:.2f} AU from Earth</li>"
                            )

                        # Show diameter if available
                        if vis.asteroid.diameter_km:
                            content_parts.append(f"<li>Diameter: {vis.asteroid.diameter_km:.1f} km</li>")

                        # Show notes if available
                        if vis.notes:
                            content_parts.append(f"<li>{vis.notes}</li>")

                        if vis.asteroid.notes:
                            content_parts.append(f"<li>{vis.asteroid.notes}</li>")

                        content_parts.append("</ul>")

            html_content.extend(content_parts)

            # Viewing tips
            html_content.append(
                "<h2>Viewing Tips</h2>"
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Magnitude < 6.0: Potentially visible to naked eye under dark skies (rare for asteroids)</li>"
                f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>Magnitude 6.0-8.0: Visible with binoculars</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Magnitude > 8.0: Requires telescope</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Asteroids near opposition (elongation >150°) are at their brightest</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Track asteroids over multiple nights to observe their motion against background stars</li>"
                "</ul>"
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Vesta is the only asteroid that can occasionally reach naked-eye visibility at opposition!</p>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading asteroids info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load asteroid visibility information: {e}</span></p>"
            )
