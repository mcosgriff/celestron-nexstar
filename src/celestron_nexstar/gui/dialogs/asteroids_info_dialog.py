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
        font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

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

        # Load asteroid information
        self._load_asteroids_info()

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
            "bg": "#1e1e1e" if is_dark else "#ffffff",
            "table_header_bg": "#2d2d2d" if is_dark else "#f5f5f5",
            "table_row_bg": "#252525" if is_dark else "#ffffff",
            "table_row_alt_bg": "#2a2a2a" if is_dark else "#fafafa",
            "border": "#444444" if is_dark else "#e0e0e0",
        }

    def _load_asteroids_info(self) -> None:
        """Load and display asteroid visibility information."""
        try:
            from celestron_nexstar.api.astronomy.asteroids import get_visible_asteroids
            from celestron_nexstar.api.database.models import get_db_session
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

            with get_db_session() as db_session:
                visible = get_visible_asteroids(db_session, location, max_magnitude=12.0, min_altitude=-5.0)

            colors = self._get_theme_colors()
            now = datetime.now(UTC)

            # Build HTML content
            html = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: {self._font_family};
                        color: {colors["text"]};
                        margin: 8px;
                    }}
                    h2 {{
                        color: {colors["header"]};
                        margin-bottom: 5px;
                    }}
                    h3 {{
                        color: {colors["cyan"]};
                        margin-top: 15px;
                        margin-bottom: 5px;
                    }}
                    .dim {{
                        color: {colors["text_dim"]};
                    }}
                    .green {{
                        color: {colors["green"]};
                    }}
                    .yellow {{
                        color: {colors["yellow"]};
                    }}
                    .orange {{
                        color: {colors["orange"]};
                    }}
                    .red {{
                        color: {colors["red"]};
                    }}
                    table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin-top: 10px;
                    }}
                    th {{
                        background-color: {colors["table_header_bg"]};
                        padding: 6px 8px;
                        text-align: left;
                        border-bottom: 1px solid {colors["border"]};
                    }}
                    td {{
                        padding: 4px 8px;
                        border-bottom: 1px solid {colors["border"]};
                    }}
                    tr:nth-child(even) {{
                        background-color: {colors["table_row_alt_bg"]};
                    }}
                    .type-neo {{
                        color: {colors["red"]};
                        font-weight: bold;
                    }}
                    .type-dwarf {{
                        color: {colors["purple"]};
                    }}
                    .type-trojan {{
                        color: {colors["orange"]};
                    }}
                    .type-centaur {{
                        color: {colors["cyan"]};
                    }}
                </style>
            </head>
            <body>
                <h2>☄ Asteroid Visibility</h2>
                <p class="dim">{location_name} • {now.strftime("%Y-%m-%d %H:%M UTC")}</p>
            """

            if not visible:
                html += """
                <p class="yellow">No bright asteroids currently visible.</p>
                <p class="dim">Try checking during nighttime or seed more asteroids.</p>
                """
            else:
                # Summary
                above_horizon = [v for v in visible if v.altitude > 0]
                bright = [v for v in visible if v.magnitude < 8]
                html += f"""
                <p><span class="green">{len(above_horizon)}</span> asteroids above horizon,
                   <span class="green">{len(bright)}</span> brighter than mag 8</p>
                """

                # Table
                html += """
                <table>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Mag</th>
                        <th>Alt</th>
                        <th>Elong</th>
                        <th>Status</th>
                    </tr>
                """

                for vis in visible[:30]:  # Top 30
                    name = vis.asteroid.name or vis.asteroid.designation
                    if len(name) > 15:
                        name = name[:15] + "..."

                    # Type styling
                    atype = vis.asteroid.asteroid_type
                    if atype == "neo":
                        type_html = '<span class="type-neo">NEO</span>'
                    elif atype == "dwarf_planet":
                        type_html = '<span class="type-dwarf">Dwarf</span>'
                    elif atype == "trojan":
                        type_html = '<span class="type-trojan">Trojan</span>'
                    elif atype == "centaur":
                        type_html = '<span class="type-centaur">Centaur</span>'
                    elif atype == "tno":
                        type_html = '<span class="type-centaur">TNO</span>'
                    else:
                        type_html = "Belt"

                    # Magnitude styling
                    if vis.magnitude < 6:
                        mag_html = f'<span class="green">{vis.magnitude:.1f}</span>'
                    elif vis.magnitude < 9:
                        mag_html = f'<span class="yellow">{vis.magnitude:.1f}</span>'
                    else:
                        mag_html = f'<span class="dim">{vis.magnitude:.1f}</span>'

                    # Altitude
                    alt_html = f"{vis.altitude:.0f}°"
                    if vis.altitude < 0:
                        alt_html = f'<span class="dim">{vis.altitude:.0f}°</span>'

                    # Elongation
                    elong = vis.elongation_deg or 0
                    if elong > 150:
                        elong_html = f'<span class="green">{elong:.0f}°</span>'
                    elif elong < 30:
                        elong_html = f'<span class="red">{elong:.0f}°</span>'
                    else:
                        elong_html = f"{elong:.0f}°"

                    # Status
                    if vis.is_visible and elong > 150:
                        status = '<span class="green">★ Opposition</span>'
                    elif vis.is_visible:
                        status = '<span class="green">✓ Visible</span>'
                    else:
                        status = '<span class="dim">Below horizon</span>'

                    html += f"""
                    <tr>
                        <td>{name}</td>
                        <td>{type_html}</td>
                        <td>{mag_html}</td>
                        <td>{alt_html}</td>
                        <td>{elong_html}</td>
                        <td>{status}</td>
                    </tr>
                    """

                html += "</table>"

                # Details for top 5 visible
                visible_above = [v for v in visible if v.is_visible][:5]
                if visible_above:
                    html += "<h3>Top Visible Asteroids</h3>"

                    for vis in visible_above:
                        html += f"""
                        <p>
                            <b>{vis.asteroid.display_name}</b><br/>
                            Type: {vis.asteroid.asteroid_type.replace("_", " ").title()}<br/>
                        """

                        if vis.ra_hours is not None and vis.dec_degrees is not None:
                            ra_h = int(vis.ra_hours)
                            ra_m = int((vis.ra_hours - ra_h) * 60)
                            dec_sign = "+" if vis.dec_degrees >= 0 else ""
                            html += f"Position: RA {ra_h}h {ra_m}m, Dec {dec_sign}{vis.dec_degrees:.1f}°<br/>"

                        html += f"""
                            Altitude: {vis.altitude:.1f}° &nbsp; Azimuth: {vis.azimuth:.1f}°<br/>
                            Magnitude: {vis.magnitude:.2f} &nbsp; Elongation: {vis.elongation_deg:.0f}°<br/>
                        """

                        if vis.helio_distance_au and vis.geo_distance_au:
                            html += f"Distance: {vis.helio_distance_au:.2f} AU from Sun, {vis.geo_distance_au:.2f} AU from Earth<br/>"

                        if vis.asteroid.diameter_km:
                            html += f"Diameter: {vis.asteroid.diameter_km:.1f} km<br/>"

                        if vis.notes:
                            html += f'<span class="dim">{vis.notes}</span><br/>'

                        if vis.asteroid.notes:
                            html += f'<span class="dim">{vis.asteroid.notes}</span><br/>'

                        html += "</p>"

            # Tips
            html += """
                <h3>Viewing Tips</h3>
                <ul>
                    <li class="green">Elongation >150° = near opposition (brightest)</li>
                    <li class="yellow">Magnitude <8 = visible in binoculars</li>
                    <li class="dim">Track asteroids over multiple nights to observe motion</li>
                    <li class="dim">Vesta can reach naked-eye visibility at opposition</li>
                </ul>
            </body>
            </html>
            """

            self.info_text.setHtml(html)

        except Exception as e:
            logger.error(f"Failed to load asteroid visibility: {e}", exc_info=True)
            self.info_text.setPlainText(f"Error: Failed to load asteroid visibility information: {e}")
