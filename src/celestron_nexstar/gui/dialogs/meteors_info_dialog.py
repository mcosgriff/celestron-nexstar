"""
Dialog to display meteor shower predictions with tabs for best and next.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QProgressDialog,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


def _run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


class MeteorsInfoDialog(QDialog):
    """Dialog to display meteor shower predictions with tabs."""

    def __init__(self, parent: QWidget | None = None, progress: QProgressDialog | None = None) -> None:
        """Initialize the meteors info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Meteor Shower Predictions")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)  # Match ObjectInfoDialog width

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
        self._create_next_tab()
        self._create_best_tab()

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data upfront
        if progress:
            progress.setLabelText("Loading next meteor showers...")
            QApplication.processEvents()
        self._load_next_info()

        if progress:
            progress.setLabelText("Loading best viewing windows...")
            QApplication.processEvents()
        self._load_best_info()
        self._best_loaded = True

    def _create_next_tab(self) -> None:
        """Create the next meteor showers tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.next_text = QTextEdit()
        self.next_text.setReadOnly(True)
        self.next_text.setAcceptRichText(True)
        self.next_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.next_text)

        self.tab_widget.addTab(tab, "Next")

    def _create_best_tab(self) -> None:
        """Create the best viewing windows tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.best_text = QTextEdit()
        self.best_text.setReadOnly(True)
        self.best_text.setAcceptRichText(True)
        self.best_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.best_text)

        self.tab_widget.addTab(tab, "Best")

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change event."""
        # All data is now loaded upfront, so no action needed
        pass

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
            "bright_green": "#81c784" if is_dark else "#66bb6a",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _load_predictions_content(self, predictions: list[Any], location: Any, months: int, title: str) -> list[str]:
        """Generate HTML content for meteor shower predictions list."""
        colors = self._get_theme_colors()
        _lat, _lon = location.latitude, location.longitude
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        html_content = []
        html_content.append(
            f"<style>"
            f"h1 {{ color: {colors['header']}; font-size: 16pt; font-weight: bold; margin-top: 0; margin-bottom: 0.5em; }}"
            f"h2 {{ color: {colors['header']}; margin-top: 1.5em; margin-bottom: 0.5em; }}"
            f"p {{ margin-top: 0.5em; margin-bottom: 0.5em; }}"
            f"</style>"
        )

        # Header
        html_content.append(f"<h1>{title} for {location_name}</h1>")
        html_content.append(f"<p style='color: {colors['text_dim']};'>Searching next {months} months</p>")

        if not predictions:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No meteor showers found in the forecast period.</span></p>"
            )
            return html_content

        # Display predictions in a table
        html_content.append("<h2>Meteor Shower Predictions</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Date</th>"
            "<th style='padding: 8px; text-align: left;'>Shower</th>"
            "<th style='padding: 8px; text-align: right;'>ZHR</th>"
            "<th style='padding: 8px; text-align: right;'>Adjusted ZHR</th>"
            "<th style='padding: 8px; text-align: right;'>Moon</th>"
            "<th style='padding: 8px; text-align: left;'>Quality</th>"
            "</tr>"
        )

        for pred in predictions:
            # Format date
            date_obj = pred.date.replace(tzinfo=UTC) if pred.date.tzinfo is None else pred.date.astimezone(UTC)
            date_str = date_obj.strftime("%Y-%m-%d")

            # Format ZHR
            zhr_str = str(pred.zhr_peak)
            adj_zhr_str = f"{pred.zhr_adjusted:.0f}"

            # Format moon
            moon_str = f"{pred.moon_illumination:.0%}"

            # Format quality with color
            if pred.viewing_quality == "excellent":
                quality_color = colors["bright_green"]
                quality_style = f"color: {quality_color}; font-weight: bold;"
            elif pred.viewing_quality == "good":
                quality_color = colors["green"]
                quality_style = f"color: {quality_color};"
            elif pred.viewing_quality == "fair":
                quality_color = colors["yellow"]
                quality_style = f"color: {quality_color};"
            else:  # poor
                quality_color = colors["red"]
                quality_style = f"color: {quality_color};"

            quality_str = pred.viewing_quality.capitalize()

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{date_str}</td>"
                f"<td style='padding: 6px; color: {colors['text']};'>{pred.shower.name}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{zhr_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{adj_zhr_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{moon_str}</td>"
                f"<td style='padding: 6px; {quality_style}'>{quality_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Show details
        html_content.append("<h2>Prediction Details</h2>")

        for pred in predictions[:10]:  # Show first 10
            # Format date
            date_obj = pred.date.replace(tzinfo=UTC) if pred.date.tzinfo is None else pred.date.astimezone(UTC)
            date_display = date_obj.strftime("%B %d, %Y")

            html_content.append(f"<p><b style='color: {colors['header']};'>{pred.shower.name}</b> - {date_display}</p>")
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']}; margin-top: 0.5em; margin-bottom: 1em;'>"
                f"<li>Peak ZHR: {pred.zhr_peak} → Adjusted: {pred.zhr_adjusted:.0f} (moon impact)</li>"
                f"<li>Moon: {pred.moon_illumination:.0%} illuminated at {pred.moon_altitude:.0f}° altitude</li>"
                f"<li>Radiant: {pred.radiant_altitude:.0f}° altitude</li>"
            )

            # Format quality
            if pred.viewing_quality == "excellent":
                quality_color = colors["bright_green"]
            elif pred.viewing_quality == "good":
                quality_color = colors["green"]
            elif pred.viewing_quality == "fair":
                quality_color = colors["yellow"]
            else:
                quality_color = colors["red"]

            html_content.append(
                f"<li>Quality: <span style='color: {quality_color}; font-weight: bold;'>{pred.viewing_quality.capitalize()}</span> - {pred.notes}</li>"
            )
            html_content.append("</ul>")

        # Viewing tips
        html_content.append(
            "<h2>Viewing Tips</h2>"
            f"<ul style='margin-left: 20px; color: {colors['text']}; margin-top: 0.5em;'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>ZHR = Zenithal Hourly Rate (meteors per hour under ideal conditions)</li>"
            f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>Adjusted ZHR accounts for moonlight interference</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Best viewing: After midnight when radiant is highest</li>"
            f"<li style='margin-bottom: 5px;'>Don't stare at the radiant - meteors appear throughout the sky</li>"
            f"<li style='margin-bottom: 5px;'>Give your eyes 20+ minutes to adapt to darkness</li>"
            "</ul>"
            f"<p style='color: {colors['text_dim']}; margin-top: 1em;'>💡 Tip: Use 'nexstar meteors best' to find showers with minimal moonlight!</p>"
        )

        return html_content

    def _load_next_info(self) -> None:
        """Load next meteor showers information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.next_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            months = 12  # Default for next

            # get_enhanced_meteor_predictions is sync but uses asyncio.run() internally
            # We need to wrap it in a way that handles the async call properly
            from celestron_nexstar.api.astronomy.meteor_shower_predictions import (
                get_enhanced_meteor_predictions,
            )

            predictions = get_enhanced_meteor_predictions(location, months_ahead=months)

            html_content = self._load_predictions_content(predictions, location, months, "Meteor Shower Predictions")
            self.next_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading next meteors info: {e}", exc_info=True)
            self.next_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load meteor shower predictions: {e}</span></p>"
            )

    def _load_best_info(self) -> None:
        """Load best viewing windows information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.best_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            months = 12  # Default for best
            min_quality = "good"  # Default min quality

            # get_best_viewing_windows is sync but calls get_enhanced_meteor_predictions which uses asyncio.run()
            from celestron_nexstar.api.astronomy.meteor_shower_predictions import get_best_viewing_windows

            predictions = get_best_viewing_windows(location, months_ahead=months, min_quality=min_quality)

            html_content = self._load_predictions_content(
                predictions, location, months, "Best Meteor Shower Viewing Windows"
            )
            self.best_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading best meteors info: {e}", exc_info=True)
            self.best_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load best viewing windows: {e}</span></p>"
            )
