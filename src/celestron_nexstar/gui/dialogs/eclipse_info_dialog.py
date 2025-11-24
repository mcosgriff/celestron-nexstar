"""
Dialog to display eclipse information with tabs for lunar, next, and solar.
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


class EclipseInfoDialog(QDialog):
    """Dialog to display eclipse information with tabs."""

    def __init__(self, parent: QWidget | None = None, progress: QProgressDialog | None = None) -> None:
        """Initialize the eclipse info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Eclipse Predictions")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.resize(900, 700)  # Set reasonable default size

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
        self._create_lunar_tab()
        self._create_next_tab()
        self._create_solar_tab()

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data upfront
        if progress:
            progress.setLabelText("Loading lunar eclipses...")
            QApplication.processEvents()
        self._load_lunar_info()

        if progress:
            progress.setLabelText("Loading next eclipses...")
            QApplication.processEvents()
        self._load_next_info()
        self._next_loaded = True

        if progress:
            progress.setLabelText("Loading solar eclipses...")
            QApplication.processEvents()
        self._load_solar_info()
        self._solar_loaded = True

    def _create_lunar_tab(self) -> None:
        """Create the lunar eclipse tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.lunar_text = QTextEdit()
        self.lunar_text.setReadOnly(True)
        self.lunar_text.setAcceptRichText(True)
        self.lunar_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.lunar_text)

        self.tab_widget.addTab(tab, "Lunar")

    def _create_next_tab(self) -> None:
        """Create the next eclipse tab."""
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

    def _create_solar_tab(self) -> None:
        """Create the solar eclipse tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.solar_text = QTextEdit()
        self.solar_text.setReadOnly(True)
        self.solar_text.setAcceptRichText(True)
        self.solar_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.solar_text)

        self.tab_widget.addTab(tab, "Solar")

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
            "bright_red": "#ef5350" if is_dark else "#d32f2f",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _format_local_time(self, dt: datetime, lat: float, lon: float) -> str:
        """Format datetime in local timezone."""
        from celestron_nexstar.api.core.utils import format_local_time

        return format_local_time(dt, lat, lon)

    def _format_eclipse_type(self, eclipse_type: str, colors: dict[str, str]) -> tuple[str, str]:
        """Format eclipse type with color."""
        type_colors = {
            "lunar_total": (colors["bright_green"], "Total Lunar"),
            "lunar_partial": (colors["green"], "Partial Lunar"),
            "lunar_penumbral": (colors["text_dim"], "Penumbral Lunar"),
            "solar_total": (colors["bright_red"], "Total Solar"),
            "solar_partial": (colors["yellow"], "Partial Solar"),
            "solar_annular": (colors["yellow"], "Annular Solar"),
        }
        color, label = type_colors.get(eclipse_type, (colors["text"], eclipse_type))
        return color, label

    def _load_eclipse_content(self, eclipses: list[Any], location: Any, years: int, title: str) -> list[str]:
        """Generate HTML content for eclipse list."""
        colors = self._get_theme_colors()
        lat, lon = location.latitude, location.longitude
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        # Header
        html_content.append(
            f"<p style='margin-bottom: 5px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>{title} for {location_name}</span></p>"
        )
        html_content.append(
            f"<p style='color: {colors['text_dim']}; margin-bottom: 10px;'>Searching next {years} years</p>"
        )

        if not eclipses:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No eclipses found in the forecast period.</span></p>"
            )
            return html_content

        # Display eclipses in a table
        html_content.append("<h2>Upcoming Eclipses</h2>")
        html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
        html_content.append(
            f"<tr style='background-color: {colors['header']}; color: white;'>"
            "<th style='padding: 8px; text-align: left;'>Date</th>"
            "<th style='padding: 8px; text-align: left;'>Type</th>"
            "<th style='padding: 8px; text-align: left;'>Maximum Time</th>"
            "<th style='padding: 8px; text-align: center;'>Visible</th>"
            "<th style='padding: 8px; text-align: right;'>Altitude</th>"
            "<th style='padding: 8px; text-align: right;'>Magnitude</th>"
            "</tr>"
        )

        for eclipse in eclipses:
            # Format date
            date_obj = eclipse.date.replace(tzinfo=UTC) if eclipse.date.tzinfo is None else eclipse.date.astimezone(UTC)
            date_only = date_obj.strftime("%Y-%m-%d")

            # Format maximum time
            max_obj = (
                eclipse.maximum_time.replace(tzinfo=UTC)
                if eclipse.maximum_time.tzinfo is None
                else eclipse.maximum_time.astimezone(UTC)
            )
            self._format_local_time(eclipse.maximum_time, lat, lon)
            max_time_only = max_obj.strftime("%I:%M %p")

            # Format type
            type_color, type_label = self._format_eclipse_type(eclipse.eclipse_type, colors)

            # Format visibility
            if eclipse.is_visible:
                visible_str = "✓ Yes"
                visible_color = colors["green"]
            else:
                visible_str = "✗ No"
                visible_color = colors["text_dim"]

            # Format altitude
            alt_str = f"{eclipse.altitude_at_maximum:.0f}°"

            # Format magnitude
            mag_str = f"{eclipse.magnitude:.2f}"

            html_content.append(
                f"<tr style='border-bottom: 1px solid #444;'>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{date_only}</td>"
                f"<td style='padding: 6px; color: {type_color}; font-weight: bold;'>{type_label}</td>"
                f"<td style='padding: 6px; color: {colors['cyan']};'>{max_time_only}</td>"
                f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt_str}</td>"
                f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{mag_str}</td>"
                "</tr>"
            )

        html_content.append("</table>")

        # Show details for visible eclipses
        visible_eclipses = [e for e in eclipses if e.is_visible]
        if visible_eclipses:
            html_content.append("<br>")
            html_content.append("<h2>Visible Eclipses Details</h2>")

            for eclipse in visible_eclipses[:5]:  # Show first 5
                # Format dates
                date_obj = (
                    eclipse.date.replace(tzinfo=UTC) if eclipse.date.tzinfo is None else eclipse.date.astimezone(UTC)
                )
                date_display = date_obj.strftime("%B %d, %Y")

                max_obj = (
                    eclipse.maximum_time.replace(tzinfo=UTC)
                    if eclipse.maximum_time.tzinfo is None
                    else eclipse.maximum_time.astimezone(UTC)
                )
                max_display = max_obj.strftime("%I:%M %p")

                type_color, type_label = self._format_eclipse_type(eclipse.eclipse_type, colors)

                html_content.append(f"<p><b style='color: {type_color};'>{type_label}</b> - {date_display}</p>")
                html_content.append(
                    f"<ul style='margin-left: 20px; color: {colors['text']};'>"
                    f"<li>Maximum: {max_display} at {eclipse.altitude_at_maximum:.0f}° altitude</li>"
                )

                if eclipse.visibility_start and eclipse.visibility_end:
                    start_obj = (
                        eclipse.visibility_start.replace(tzinfo=UTC)
                        if eclipse.visibility_start.tzinfo is None
                        else eclipse.visibility_start.astimezone(UTC)
                    )
                    end_obj = (
                        eclipse.visibility_end.replace(tzinfo=UTC)
                        if eclipse.visibility_end.tzinfo is None
                        else eclipse.visibility_end.astimezone(UTC)
                    )
                    start_str = start_obj.strftime("%I:%M %p")
                    end_str = end_obj.strftime("%I:%M %p")
                    html_content.append(
                        f"<li>Duration: {start_str} to {end_str} ({eclipse.duration_minutes:.0f} minutes)</li>"
                    )

                html_content.append(f"<li>{eclipse.notes}</li>")
                html_content.append("</ul>")
                html_content.append("<br>")

        # Viewing tips
        html_content.append("<br>")
        html_content.append("<h2>Viewing Tips</h2>")
        html_content.append(
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Lunar eclipses are safe to view with naked eye or binoculars</li>"
            f"<li style='color: {colors['red']}; margin-bottom: 5px;'>⚠ Solar eclipses require special eye protection - NEVER look directly at the sun</li>"
            f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>For solar eclipses, use ISO 12312-2 certified eclipse glasses</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Check weather forecast for cloud cover during eclipse times</li>"
            "</ul>"
        )
        html_content.append("<br>")
        html_content.append(
            f"<p style='color: {colors['text_dim']};'>💡 Tip: Eclipses are rare events - plan ahead for the best viewing experience!</p>"
        )

        return html_content

    def _load_lunar_info(self) -> None:
        """Load lunar eclipse information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.lunar_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            years = 5  # Default for lunar

            async def _load_async_content() -> list[str]:
                from celestron_nexstar.api.astronomy.eclipses import get_next_lunar_eclipse
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as db_session:
                    eclipses = await get_next_lunar_eclipse(db_session, location, years_ahead=years)

                return self._load_eclipse_content(eclipses, location, years, "Upcoming Lunar Eclipses")

            html_content = _run_async_safe(_load_async_content())
            self.lunar_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading lunar eclipse info: {e}", exc_info=True)
            self.lunar_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load lunar eclipse information: {e}</span></p>"
            )

    def _load_next_info(self) -> None:
        """Load next eclipse information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.next_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            years = 5  # Default for next

            async def _load_async_content() -> list[str]:
                from celestron_nexstar.api.astronomy.eclipses import get_upcoming_eclipses
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as db_session:
                    eclipses = await get_upcoming_eclipses(db_session, location, years_ahead=years, eclipse_type=None)

                return self._load_eclipse_content(eclipses, location, years, "Upcoming Eclipses")

            html_content = _run_async_safe(_load_async_content())
            self.next_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading next eclipse info: {e}", exc_info=True)
            self.next_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load eclipse information: {e}</span></p>"
            )

    def _load_solar_info(self) -> None:
        """Load solar eclipse information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.solar_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            years = 10  # Default for solar

            async def _load_async_content() -> list[str]:
                from celestron_nexstar.api.astronomy.eclipses import get_next_solar_eclipse
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as db_session:
                    eclipses = await get_next_solar_eclipse(db_session, location, years_ahead=years)

                return self._load_eclipse_content(eclipses, location, years, "Upcoming Solar Eclipses")

            html_content = _run_async_safe(_load_async_content())
            self.solar_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading solar eclipse info: {e}", exc_info=True)
            self.solar_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load solar eclipse information: {e}</span></p>"
            )
