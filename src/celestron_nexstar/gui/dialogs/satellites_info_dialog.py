"""
Dialog to display satellite passes information with tabs for visual, bright, starlink, and stations.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections import defaultdict
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


class SatellitesInfoDialog(QDialog):
    """Dialog to display satellite passes information with tabs."""

    def __init__(self, parent: QWidget | None = None, progress: QProgressDialog | None = None) -> None:
        """Initialize the satellites info dialog."""
        super().__init__(parent)
        self.setWindowTitle("Satellite Passes")
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
        self._create_visual_tab()
        self._create_bright_tab()
        self._create_starlink_tab()
        self._create_stations_tab()

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all tab data upfront
        if progress:
            progress.setLabelText("Loading visual satellite passes...")
            QApplication.processEvents()
        self._load_visual_info()

        if progress:
            progress.setLabelText("Loading bright satellite passes...")
            QApplication.processEvents()
        self._load_bright_info()
        self._bright_loaded = True

        if progress:
            progress.setLabelText("Loading Starlink passes...")
            QApplication.processEvents()
        self._load_starlink_info()
        self._starlink_loaded = True

        if progress:
            progress.setLabelText("Loading space station passes...")
            QApplication.processEvents()
        self._load_stations_info()
        self._stations_loaded = True

    def _create_visual_tab(self) -> None:
        """Create the visual satellites tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.visual_text = QTextEdit()
        self.visual_text.setReadOnly(True)
        self.visual_text.setAcceptRichText(True)
        self.visual_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.visual_text)

        self.tab_widget.addTab(tab, "Visual")

    def _create_bright_tab(self) -> None:
        """Create the bright satellites tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.bright_text = QTextEdit()
        self.bright_text.setReadOnly(True)
        self.bright_text.setAcceptRichText(True)
        self.bright_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.bright_text)

        self.tab_widget.addTab(tab, "Bright")

    def _create_starlink_tab(self) -> None:
        """Create the Starlink satellites tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.starlink_text = QTextEdit()
        self.starlink_text.setReadOnly(True)
        self.starlink_text.setAcceptRichText(True)
        self.starlink_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.starlink_text)

        self.tab_widget.addTab(tab, "Starlink")

    def _create_stations_tab(self) -> None:
        """Create the stations tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.stations_text = QTextEdit()
        self.stations_text.setReadOnly(True)
        self.stations_text.setAcceptRichText(True)
        self.stations_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        layout.addWidget(self.stations_text)

        self.tab_widget.addTab(tab, "Stations")

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

    def _load_satellite_passes_content(
        self,
        passes: list[Any],
        location: Any,
        days: int,
        title: str,
    ) -> list[str]:
        """Generate HTML content for satellite passes list."""
        colors = self._get_theme_colors()
        _lat, _lon = location.latitude, location.longitude
        location_name = location.name or f"{location.latitude:.2f}°N, {location.longitude:.2f}°E"

        html_content = []
        html_content.append(
            f"<style>h2 {{ color: {colors['header']}; margin-top: 1em; margin-bottom: 0.5em; }}</style>"
        )

        # Header
        html_content.append(
            f"<p><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>{title} for {location_name}</span></p>"
        )
        html_content.append(f"<p style='color: {colors['text_dim']};'>Searching next {days} days</p>")

        if not passes:
            html_content.append(
                f"<p><span style='color: {colors['yellow']};'>No satellite passes found in the forecast period.</span></p>"
            )
            return html_content

        # Always group passes by satellite name
        passes_by_satellite: dict[str, list[Any]] = defaultdict(list)
        for pass_obj in passes:
            passes_by_satellite[pass_obj.name].append(pass_obj)

        sorted_satellites = sorted(passes_by_satellite.keys())

        for satellite_name in sorted_satellites:
            satellite_passes = passes_by_satellite[satellite_name]
            satellite_passes.sort(key=lambda p: p.rise_time)

            html_content.append(f"<h2>{satellite_name}</h2>")
            visible_count = sum(1 for p in satellite_passes if p.is_visible)
            html_content.append(
                f"<p style='color: {colors['text_dim']};'>{len(satellite_passes)} pass(es) found, {visible_count} visible</p>"
            )

            # Create table for this satellite
            html_content.append("<table style='border-collapse: collapse; width: 100%; border: 1px solid #444;'>")
            html_content.append(
                f"<tr style='background-color: {colors['header']}; color: white;'>"
                "<th style='padding: 8px; text-align: left;'>Date</th>"
                "<th style='padding: 8px; text-align: left;'>Rise</th>"
                "<th style='padding: 8px; text-align: left;'>Max</th>"
                "<th style='padding: 8px; text-align: left;'>Set</th>"
                "<th style='padding: 8px; text-align: right;'>Max Alt</th>"
                "<th style='padding: 8px; text-align: right;'>Mag</th>"
                "<th style='padding: 8px; text-align: right;'>Duration</th>"
                "<th style='padding: 8px; text-align: center;'>Visible</th>"
                "</tr>"
            )

            for pass_obj in satellite_passes:
                # Format dates and times
                rise_obj = (
                    pass_obj.rise_time.replace(tzinfo=UTC)
                    if pass_obj.rise_time.tzinfo is None
                    else pass_obj.rise_time.astimezone(UTC)
                )
                max_obj = (
                    pass_obj.max_time.replace(tzinfo=UTC)
                    if pass_obj.max_time.tzinfo is None
                    else pass_obj.max_time.astimezone(UTC)
                )
                set_obj = (
                    pass_obj.set_time.replace(tzinfo=UTC)
                    if pass_obj.set_time.tzinfo is None
                    else pass_obj.set_time.astimezone(UTC)
                )

                date_str = rise_obj.strftime("%Y-%m-%d")
                rise_time_only = rise_obj.strftime("%I:%M %p")
                max_time_only = max_obj.strftime("%I:%M %p")
                set_time_only = set_obj.strftime("%I:%M %p")

                # Format magnitude with color
                if pass_obj.magnitude < -1.0:
                    mag_color = colors["bright_green"]
                    mag_style = f"color: {mag_color}; font-weight: bold;"
                elif pass_obj.magnitude < 1.0:
                    mag_color = colors["green"]
                    mag_style = f"color: {mag_color};"
                elif pass_obj.magnitude < 3.0:
                    mag_color = colors["yellow"]
                    mag_style = f"color: {mag_color};"
                elif pass_obj.magnitude < 6.0:
                    mag_color = colors["text_dim"]
                    mag_style = f"color: {mag_color};"
                else:
                    mag_color = colors["red"]
                    mag_style = f"color: {mag_color};"

                # Format altitude
                alt_str = f"{pass_obj.max_altitude_deg:.0f}°"

                # Format duration
                duration_min = (pass_obj.set_time - pass_obj.rise_time).total_seconds() / 60.0
                duration_str = f"{duration_min:.0f}m"

                # Format visibility
                if pass_obj.is_visible:
                    visible_str = "Yes"
                    visible_color = colors["green"]
                else:
                    visible_str = "No"
                    visible_color = colors["text_dim"]

                html_content.append(
                    f"<tr style='border-bottom: 1px solid #444;'>"
                    f"<td style='padding: 6px; color: {colors['cyan']};'>{date_str}</td>"
                    f"<td style='padding: 6px; color: {colors['cyan']};'>{rise_time_only}</td>"
                    f"<td style='padding: 6px; color: {colors['cyan']};'>{max_time_only}</td>"
                    f"<td style='padding: 6px; color: {colors['cyan']};'>{set_time_only}</td>"
                    f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{alt_str}</td>"
                    f"<td style='padding: 6px; text-align: right; {mag_style}'>{pass_obj.magnitude:.2f}</td>"
                    f"<td style='padding: 6px; text-align: right; color: {colors['text']};'>{duration_str}</td>"
                    f"<td style='padding: 6px; text-align: center; color: {visible_color};'>{visible_str}</td>"
                    "</tr>"
                )

            html_content.append("</table>")

        # Summary
        total_satellites = len(sorted_satellites)
        visible_count = sum(1 for p in passes if p.is_visible)
        html_content.append(
            "<h2>Summary</h2>"
            f"<p style='color: {colors['text']};'>Total satellites: {total_satellites}</p>"
            f"<p style='color: {colors['text']};'>Total passes: {len(passes)} ({visible_count} visible)</p>"
        )

        # Viewing tips
        html_content.append(
            "<h2>Viewing Tips</h2>"
            f"<ul style='margin-left: 20px; color: {colors['text']};'>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Satellites are visible when sunlit</li>"
            f"<li style='color: {colors['yellow']}; margin-bottom: 5px;'>Look for steady moving 'stars' crossing the sky</li>"
            f"<li style='margin-bottom: 5px;'>Satellites move steadily (unlike aircraft which blink)</li>"
            f"<li style='color: {colors['green']}; margin-bottom: 5px;'>Best viewing when sky is dark and satellite is sunlit</li>"
            "</ul>"
        )

        return html_content

    def _load_visual_info(self) -> None:
        """Load visual satellites information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.visual_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            days = 7  # Default
            min_altitude = 10.0
            max_passes = 100

            async def _load_async_content() -> list[str]:
                from celestron_nexstar.api.events.satellite_flares import get_visual_passes

                passes = await get_visual_passes(
                    location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
                )

                # Filter to visible passes only
                visible_passes = [p for p in passes if p.is_visible]

                return self._load_satellite_passes_content(visible_passes, location, days, "Visual Satellite Passes")

            html_content = _run_async_safe(_load_async_content())
            self.visual_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading visual satellites info: {e}", exc_info=True)
            self.visual_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load visual satellites information: {e}</span></p>"
            )

    def _load_bright_info(self) -> None:
        """Load bright satellites information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.bright_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            days = 7  # Default
            min_magnitude = 3.0

            from celestron_nexstar.api.events.satellite_flares import get_bright_satellite_passes

            passes = get_bright_satellite_passes(location, days=days, min_magnitude=min_magnitude)

            html_content = self._load_satellite_passes_content(passes, location, days, "Bright Satellite Passes")
            self.bright_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading bright satellites info: {e}", exc_info=True)
            self.bright_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load bright satellites information: {e}</span></p>"
            )

    def _load_starlink_info(self) -> None:
        """Load Starlink satellites information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.starlink_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            days = 7  # Default
            min_altitude = 10.0
            max_passes = 50

            from celestron_nexstar.api.events.satellite_flares import get_starlink_passes

            passes = get_starlink_passes(
                location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
            )

            # Filter to visible passes only
            visible_passes = [p for p in passes if p.is_visible]

            html_content = self._load_satellite_passes_content(
                visible_passes, location, days, "Starlink Satellite Passes"
            )
            self.starlink_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading Starlink satellites info: {e}", exc_info=True)
            self.starlink_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load Starlink satellites information: {e}</span></p>"
            )

    def _load_stations_info(self) -> None:
        """Load stations information."""
        colors = self._get_theme_colors()

        try:
            from celestron_nexstar.api.location.observer import get_observer_location

            location = get_observer_location()
            if not location:
                self.stations_text.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> No observer location set. Use 'nexstar location set' to configure your location.</span></p>"
                )
                return

            days = 7  # Default
            min_altitude = 10.0
            max_passes = 50

            from celestron_nexstar.api.events.satellite_flares import get_stations_passes

            passes = get_stations_passes(
                location, days=days, min_altitude_deg=min_altitude, max_passes=max_passes, db_session=None
            )

            # Filter to visible passes only
            visible_passes = [p for p in passes if p.is_visible]

            html_content = self._load_satellite_passes_content(visible_passes, location, days, "Space Station Passes")
            self.stations_text.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading stations info: {e}", exc_info=True)
            self.stations_text.setHtml(
                f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load space station passes information: {e}</span></p>"
            )
