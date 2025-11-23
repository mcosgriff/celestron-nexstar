"""
Dialog to display planetary events information with tabs for conjunctions and oppositions.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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


class PlanetsInfoDialog(QDialog):
    """Dialog to display planetary events information with tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the planets info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Planetary Events")
        self.setMinimumWidth(750)
        self.setMinimumHeight(550)

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
        self._create_conjunctions_tab()
        self._create_oppositions_tab()

        # Connect tab change signal to load data when tab is selected
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load data for the first tab (conjunctions)
        self._load_conjunctions_info()

    def _create_conjunctions_tab(self) -> None:
        """Create the conjunctions tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.conjunctions_text = QTextEdit()
        self.conjunctions_text.setReadOnly(True)
        self.conjunctions_text.setAcceptRichText(True)
        self.conjunctions_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.conjunctions_text)

        self.tab_widget.addTab(tab, "Conjunctions")

    def _create_oppositions_tab(self) -> None:
        """Create the oppositions tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.oppositions_text = QTextEdit()
        self.oppositions_text.setReadOnly(True)
        self.oppositions_text.setAcceptRichText(True)
        self.oppositions_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.oppositions_text)

        self.tab_widget.addTab(tab, "Oppositions")

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event."""
        if index == 1 and not hasattr(self, "_oppositions_loaded"):
            # Load oppositions tab data when first accessed
            self._load_oppositions_info()
            self._oppositions_loaded = True

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
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _load_conjunctions_content(self, events: list[Any], location: Any, months: int) -> list[str]:
        """Generate HTML content for conjunctions list."""
        colors = self._get_theme_colors()
        lat, lon = location.latitude, location.longitude
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Planetary Conjunctions for {location_name}</span></p>"
        )
        html_content.append(f"<p style='color: {colors['text_dim']};'>Searching next {months} months</p>")
        html_content.append("<br>")

        if not events:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No conjunctions found in the forecast period.</span></p>"
            )
            return html_content

        # Display conjunctions in a table
        html_content.append("<h2>Upcoming Conjunctions</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Date</th>"
            "<th style='padding: 8px; text-align: left;'>Planets</th>"
            "<th style='padding: 8px; text-align: right;'>Separation</th>"
            "<th style='padding: 8px; text-align: center;'>Visible</th>"
            "<th style='padding: 8px; text-align: right;'>Altitude</th>"
            "</tr>"
        )

        for event in events[:20]:  # Show first 20
            # Format date
            date_obj = event.date.replace(tzinfo=UTC) if event.date.tzinfo is None else event.date.astimezone(UTC)
            self._format_local_time(event.date, lat, lon)
            date_only = date_obj.strftime("%Y-%m-%d %I:%M %p")

            # Format planets
            planet2_str = event.planet2.capitalize() if event.planet2 else "N/A"
            planets_str = f"{event.planet1.capitalize()} - {planet2_str}"

            # Format separation
            sep_str = f"{event.separation_degrees:.2f}°"

            # Format visibility
            if event.is_visible:
                visible_str = "✓ Yes"
                visible_color = colors["green"]
            else:
                visible_str = "✗ No"
                visible_color = colors["text_dim"]

            # Format altitude
            alt_str = f"{event.altitude_at_event:.0f}°"

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{date_only}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>{planets_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{sep_str}</td>"
                f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Show details for visible conjunctions
        visible_events = [e for e in events if e.is_visible]
        if visible_events:
            html_content.append("<br>")
            html_content.append("<h2>Visible Conjunctions Details</h2>")

            for event in visible_events[:5]:  # Show first 5
                # Format date
                date_obj = event.date.replace(tzinfo=UTC) if event.date.tzinfo is None else event.date.astimezone(UTC)
                date_display = date_obj.strftime("%B %d, %Y at %I:%M %p")

                planet2_str = event.planet2.capitalize() if event.planet2 else "N/A"

                html_content.append(
                    f"<p><b style='color: {colors['header']};'>{event.planet1.capitalize()} - {planet2_str}</b> - {date_display}</p>"
                )
                html_content.append(
                    f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                    f"<li>Separation: {event.separation_degrees:.2f}° at {event.altitude_at_event:.0f}° altitude</li>"
                    f"<li>{event.notes}</li>"
                    "</ul>"
                )
                html_content.append("<br>")

        # Viewing tips
        html_content.append("<br>")
        html_content.append("<h2>Viewing Tips</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='margin-bottom: 5px;'>Conjunctions are best viewed with binoculars or telescope</li>"
            f"<li style='margin-bottom: 5px;'>Look for planets appearing close together in the sky</li>"
            f"<li style='margin-bottom: 5px;'>Some conjunctions may be visible to the naked eye</li>"
            "</ul>"
        )
        html_content.append("<br>")
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Conjunctions are great photo opportunities!</p>"
        )

        return html_content

    def _load_oppositions_content(self, events: list[Any], location: Any, years: int) -> list[str]:
        """Generate HTML content for oppositions list."""
        colors = self._get_theme_colors()
        _lat, _lon = location.latitude, location.longitude
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Planetary Oppositions for {location_name}</span></p>"
        )
        html_content.append(f"<p style='color: {colors['text_dim']};'>Searching next {years} years</p>")
        html_content.append("<br>")

        if not events:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No oppositions found in the forecast period.</span></p>"
            )
            return html_content

        # Display oppositions in a table
        html_content.append("<h2>Upcoming Oppositions</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Date</th>"
            "<th style='padding: 8px; text-align: left;'>Planet</th>"
            "<th style='padding: 8px; text-align: right;'>Elongation</th>"
            "<th style='padding: 8px; text-align: center;'>Visible</th>"
            "<th style='padding: 8px; text-align: right;'>Altitude</th>"
            "</tr>"
        )

        for event in events:
            # Format date
            date_obj = event.date.replace(tzinfo=UTC) if event.date.tzinfo is None else event.date.astimezone(UTC)
            date_only = date_obj.strftime("%Y-%m-%d %I:%M %p")

            # Format planet
            planet_str = event.planet1.capitalize()

            # Format elongation (should be close to 180°)
            elong_str = f"{event.separation_degrees:.1f}°"

            # Format visibility
            if event.is_visible:
                visible_str = "✓ Yes"
                visible_color = colors["green"]
            else:
                visible_str = "✗ No"
                visible_color = colors["text_dim"]

            # Format altitude
            alt_str = f"{event.altitude_at_event:.0f}°"

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{date_only}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>{planet_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{elong_str}</td>"
                f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Show details
        html_content.append("<br>")
        html_content.append("<h2>Opposition Details</h2>")

        for event in events[:10]:  # Show first 10
            # Format date
            date_obj = event.date.replace(tzinfo=UTC) if event.date.tzinfo is None else event.date.astimezone(UTC)
            date_display = date_obj.strftime("%B %d, %Y at %I:%M %p")

            html_content.append(
                f"<p><b style='color: {colors['header']};'>{event.planet1.capitalize()}</b> - {date_display}</p>"
            )
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li>Elongation: {event.separation_degrees:.1f}° at {event.altitude_at_event:.0f}° altitude</li>"
                f"<li>{event.notes}</li>"
                "</ul>"
            )
            html_content.append("<br>")

        # Viewing tips
        html_content.append("<br>")
        html_content.append("<h2>Viewing Tips</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Opposition is the best time to observe outer planets</li>"
            f"<li style='margin-bottom: 5px;'>Planet is closest to Earth and brightest</li>"
            f"<li style='margin-bottom: 5px;'>Planet is visible all night (rises at sunset, sets at sunrise)</li>"
            f"<li style='margin-bottom: 5px;'>Best viewing with telescope for detail</li>"
            "</ul>"
        )
        html_content.append("<br>")
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Plan your observing sessions around oppositions!</p>"
        )

        return html_content

    def _load_conjunctions_info(self) -> None:
        """Load conjunctions information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.conjunctions_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            months = 12  # Default for conjunctions
            max_separation = 5.0  # Default max separation

            from celestron_nexstar.api.astronomy.planetary_events import get_planetary_conjunctions

            events = get_planetary_conjunctions(location, max_separation=max_separation, months_ahead=months)

            html_content = self._load_conjunctions_content(events, location, months)
            self.conjunctions_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading conjunctions info: {e}", exc_info=True)
            self.conjunctions_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load conjunctions information: {e}</span></p>"
            )

    def _load_oppositions_info(self) -> None:
        """Load oppositions information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.oppositions_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            years = 5  # Default for oppositions

            from celestron_nexstar.api.astronomy.planetary_events import get_planetary_oppositions

            events = get_planetary_oppositions(location, years_ahead=years)

            html_content = self._load_oppositions_content(events, location, years)
            self.oppositions_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading oppositions info: {e}", exc_info=True)
            self.oppositions_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load oppositions information: {e}</span></p>"
            )
