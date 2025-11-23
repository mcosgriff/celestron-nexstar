"""
Dialog to display comet visibility information.
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


class CometsInfoDialog(QDialog):
    """Dialog to display comet visibility information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the comets info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Comet Visibility")
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
        font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Store font family for later use
        self._font_family = font_family

        # Set initial stylesheet (will be updated with theme colors in _load_comets_info)
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

        # Load comets information
        self._load_comets_info()

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

    def _load_comets_info(self) -> None:
        """Load comet visibility information from the API and format it for display."""
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

            # Default parameters matching CLI
            months = 12
            max_magnitude = 8.0

            # Build HTML content
            html_content = []
            html_content.append(
                f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
            )

            # Header
            html_content.append(
                f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>Comet Visibility for {location_name}</span></p>"
            )
            html_content.append(f"<p style='color: {colors['text_dim']};'>Searching next {months} months</p>")
            html_content.append("<br>")

            # Load async content using safe async runner
            async def _load_async_content() -> list[str]:
                """Load all async content."""
                content_parts = []

                from celestron_nexstar.api.astronomy.comets import get_visible_comets
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as db_session:
                    comets = await get_visible_comets(
                        db_session, location, months_ahead=months, max_magnitude=max_magnitude
                    )

                if not comets:
                    content_parts.append(
                        f"<p><span style='color: {colors['yellow']};'>No bright comets found in the forecast period.</span></p>"
                    )
                    content_parts.append(
                        f"<p style='color: {colors['text_dim']};'>Comet visibility is highly variable. Check regularly for new discoveries.</p>"
                    )
                    return content_parts

                # Display comets in a table
                content_parts.append("<h2>Visible Comets</h2>")
                content_parts.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
                content_parts.append(
                    f"<tr style='background-color: {colors['header']}; color: white;'>"
                    "<th style='padding: 8px; text-align: left;'>Date</th>"
                    "<th style='padding: 8px; text-align: left;'>Comet</th>"
                    "<th style='padding: 8px; text-align: right;'>Magnitude</th>"
                    "<th style='padding: 8px; text-align: center;'>Visible</th>"
                    "<th style='padding: 8px; text-align: right;'>Altitude</th>"
                    "</tr>"
                )

                for vis in comets:
                    # Format date
                    self._format_local_time(vis.date, lat, lon)
                    # Also get just the date part
                    date_obj = vis.date.replace(tzinfo=UTC) if vis.date.tzinfo is None else vis.date.astimezone(UTC)
                    date_only = date_obj.strftime("%Y-%m-%d")

                    # Format comet name
                    comet_str = vis.comet.name

                    # Format magnitude with color
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

                    # Format visibility
                    if vis.is_visible:
                        visible_str = "✓ Yes"
                        visible_color = colors["green"]
                    else:
                        visible_str = "✗ No"
                        visible_color = colors["text_dim"]

                    # Format altitude
                    alt_str = f"{vis.altitude:.0f}°"

                    content_parts.append(
                        f"<tr style='border-bottom: 1px solid #444;'>"
                        f"<td style='padding: 6px; color: {colors['cyan']};'>{date_only}</td>"
                        f"<td style='padding: 6px; color: {colors['text']};'>{comet_str}</td>"
                        f"<td style='padding: 6px; text-align: right; {mag_style}'>{vis.magnitude:.2f}</td>"
                        f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                        f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt_str}</td>"
                        "</tr>"
                    )

                content_parts.append("</table>")

                # Show details
                content_parts.append("<br>")
                content_parts.append("<h2>Comet Details</h2>")

                for vis in comets[:10]:  # Show first 10
                    # Format dates
                    self._format_local_time(vis.date, lat, lon)
                    self._format_local_time(vis.comet.peak_date, lat, lon)

                    # Get date strings for display
                    date_obj = vis.date.replace(tzinfo=UTC) if vis.date.tzinfo is None else vis.date.astimezone(UTC)
                    date_display = date_obj.strftime("%B %d, %Y")

                    if vis.comet.peak_date.tzinfo is None:
                        peak_obj = vis.comet.peak_date.replace(tzinfo=UTC)
                    else:
                        peak_obj = vis.comet.peak_date.astimezone(UTC)
                    peak_display = peak_obj.strftime("%B %d, %Y")

                    content_parts.append(
                        f"<p><b style='color: {colors['header']};'>{vis.comet.name}</b> ({vis.comet.designation})</p>"
                    )
                    content_parts.append(
                        f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                        f"<li>Peak: {peak_display} at magnitude {vis.comet.peak_magnitude:.2f}</li>"
                        f"<li>{date_display}: Magnitude {vis.magnitude:.2f} at {vis.altitude:.0f}° altitude</li>"
                    )

                    if vis.comet.is_periodic and vis.comet.period_years:
                        content_parts.append(f"<li>Periodic: {vis.comet.period_years:.0f}-year orbit</li>")

                    content_parts.append(f"<li>{vis.comet.notes}</li>")
                    content_parts.append(f"<li>{vis.notes}</li>")
                    content_parts.append("</ul>")
                    content_parts.append("<br>")

                return content_parts

            # Run async content loading
            async_content = _run_async_safe(_load_async_content())
            html_content.extend(async_content)

            # Viewing tips
            html_content.append("<br>")
            html_content.append("<h2>Viewing Tips</h2>")
            html_content.append(
                f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Magnitude < 6.0: Potentially visible to naked eye under dark skies</li>"
                f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>Magnitude 6.0-8.0: Visible with binoculars</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Magnitude > 8.0: Requires telescope</li>"
                f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Comets are best viewed away from city lights</li>"
                f"<li style='color: {colors['text_dim']}; margin-bottom: 5px;'>Comet brightness can change unpredictably due to outbursts</li>"
                "</ul>"
            )
            html_content.append("<br>")
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>💡 Tip: Comet visibility is highly variable - check regularly for updates!</p>"
            )

            self.info_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading comets info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load comet visibility information: {e}</span></p>"
            )
